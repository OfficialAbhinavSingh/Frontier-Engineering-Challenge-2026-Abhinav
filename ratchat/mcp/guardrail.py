"""The guardrail, with no protocol and no model in it.

This module is the whole decision. `server.py` only carries it over MCP, so
everything here is importable and testable without the `mcp` extra installed
and without a Docker daemon -- which is why the two I/O boundaries, the sandbox
run and the image check, are injected rather than reached for directly.

What the guardrail does *not* do is score Fail-to-Pass. F2P needs the fix commit
to check the "passes afterwards" half, and in real use there is no fix commit --
that is the point of the tool. So every successful response carries
`not_established`, which says in words what the run did not show.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

from ratchat.agents.common import default_test_dir
from ratchat.agents.verifier import (
    failure_is_named_in_report,
    overspecification,
    ungrounded_literals,
    verify,
)
from ratchat.artifact import VERDICT_MEANING
from ratchat.repo import RepoView
from ratchat.sandbox.run import (
    RunResult,
    build_image,
    image_exists,
    image_name,
    pin_sha_for,
    run_test,
)

# Not `LEGACY_TEST_PREFIX`. That constant is frozen at the project's former name
# because it is quoted into 1425 recorded prompts and the model cache is
# content-addressed on the prompt text, so reusing or renaming it would invalidate
# the committed cache the $0 replay depends on. The MCP surface writes no cache,
# so it gets its own name and leaves that one alone.
MCP_TEST_PREFIX = "test_ratchat_"

# Stated on every successful response. The first entry is the one that matters:
# it is the most common way a generated reproduction is wrong, and nothing in a
# black-box run can rule it out.
NOT_ESTABLISHED = (
    (
        "That the asserted value is the value a fix will produce. Confirming "
        "that needs an oracle this tool does not have."
    ),
    (
        "That the test will pass once the bug is fixed. Only a run at the fix "
        "commit shows that, and there is no fix commit yet."
    ),
    (
        "That the test is the only one that should be added, or that it covers "
        "every case the report describes."
    ),
)


def _repo_name(repo_path: str) -> str:
    return Path(repo_path).name


def test_path_for_report(view: RepoView, bug_report: str) -> str:
    """A new path under the project's own test directory.

    The slug is a hash of the report rather than sanitised report text: it is
    stable across retries for one report, and arbitrary prose cannot turn it
    into an invalid module name.
    """
    slug = hashlib.sha256(bug_report.encode("utf-8")).hexdigest()[:12]
    return f"{default_test_dir(view)}/{MCP_TEST_PREFIX}{slug}.py"


# `build_image` tags the image after the slug's name, not the directory's, since
# the Dockerfile clones https://github.com/<slug>.git rather than copying the
# working tree. Keying the lookup off the directory name would therefore check
# for one image while building another the moment a clone is renamed, so the
# slug's name wins wherever both are available.
GITHUB_REMOTE = re.compile(
    r"github\.com[:/](?P<owner>[^/]+)/(?P<name>[^/]+?)(?:\.git)?/?$"
)


def github_slug(repo_path: str) -> str | None:
    """`owner/name` from the clone's origin, or None when there is not one."""
    proc = subprocess.run(
        ["git", "-C", str(repo_path), "remote", "get-url", "origin"],
        capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        return None
    match = GITHUB_REMOTE.search(proc.stdout.strip())
    return f"{match['owner']}/{match['name']}" if match else None


def _image_key(repo_path: str) -> str:
    slug = github_slug(repo_path)
    return slug.split("/")[1] if slug else _repo_name(repo_path)


def _is_git_repo(repo_path: str) -> bool:
    """Whether git will answer questions about this path.

    Checked before anything reads a commit, because `pin_sha_for` runs git with
    check=True: without this, a wrong path leaves the protocol layer reporting
    an opaque "Error executing tool" instead of the one fact the caller needs.
    """
    proc = subprocess.run(
        ["git", "-C", str(repo_path), "rev-parse", "--git-dir"],
        capture_output=True, text=True, check=False,
    )
    return proc.returncode == 0


def _not_a_repo(repo_path: str) -> dict:
    return {
        "error": "not a git repository",
        "path": str(repo_path),
        "fix": "pass the path to a local clone of the project",
    }


def _pin_sha(repo_path: str) -> str:
    path = Path(repo_path)
    return pin_sha_for(path.parent, path.name)


def prepare_repo(
    repo_path: str,
    force: bool = False,
    *,
    has_image: Callable[[str], bool] | None = None,
    builder: Callable[..., None] | None = None,
) -> dict:
    """Build the repository's sandbox image, or report that it is already there."""
    has_image = has_image or image_exists
    builder = builder or build_image

    if not _is_git_repo(repo_path):
        return _not_a_repo(repo_path)

    image_key = _image_key(repo_path)

    if has_image(image_key) and not force:
        return {
            "repo_name": image_key,
            "image": image_name(image_key),
            "pin_sha": _pin_sha(repo_path),
            "built": False,
            "duration_s": 0.0,
        }

    slug = github_slug(repo_path)
    if slug is None:
        return {
            "error": "no GitHub origin",
            "fix": (
                "the sandbox image is built by cloning the repository, so it "
                "needs an origin remote on github.com; add one, or build the "
                "image yourself and tag it "
                f"{image_name(image_key)}"
            ),
            "repo_name": image_key,
        }

    pin_sha = _pin_sha(repo_path)
    started = time.time()
    builder(slug, pin_sha)
    return {
        "repo_name": image_key,
        "image": image_name(image_key),
        "pin_sha": pin_sha,
        "built": True,
        "duration_s": round(time.time() - started, 2),
    }


def verify_reproduction(
    repo_path: str,
    bug_report: str,
    test_source: str,
    test_rel_path: str | None = None,
    timeout_s: int = 180,
    *,
    runner: Callable[..., RunResult] | None = None,
    has_image: Callable[[str], bool] | None = None,
) -> dict:
    """Run one candidate test at the repository's HEAD and report why it failed."""
    runner = runner or run_test
    has_image = has_image or image_exists

    # Before the image gate: a bad path is more useful to report than the
    # preparation state of an image keyed off its directory name.
    if not _is_git_repo(repo_path):
        return _not_a_repo(repo_path)

    # The same key `prepare_repo` built under, so the image checked for is the
    # image that exists.
    repo_name = _image_key(repo_path)

    # Checked before the run, so an unprepared call is cheap and says so rather
    # than half-working.
    if not has_image(repo_name):
        return {
            "error": "repo not prepared",
            "fix": "call prepare_repo first",
            "repo_name": repo_name,
        }

    # The same pin the image was built at. `pin_sha_for` is deliberately the one
    # definition of that: when two callers computed it separately the images
    # differed silently.
    sha = _pin_sha(repo_path)
    view = RepoView(Path(repo_path), sha)

    rel_path = test_rel_path or test_path_for_report(view, bug_report)

    # The patch must only ever add a file. Refusing beats auto-suffixing: writing
    # a path the caller did not ask for makes the returned verdict describe a
    # file they do not know exists.
    if (Path(repo_path) / rel_path).exists():
        return {
            "error": "test path already exists",
            "path": rel_path,
            "fix": "pass a test_rel_path that does not exist in the repository",
        }

    run = runner(repo_name, sha, rel_path, test_source, timeout_s)
    verdict = verify(run, rel_path, bug_report)

    return {
        "reproduces": verdict.reproduces,
        "verdict": verdict.verdict,
        "verdict_meaning": VERDICT_MEANING.get(verdict.verdict, ""),
        "exception_type": verdict.exception_type,
        "source_frames": verdict.source_frames[:8],
        "test_frames": verdict.test_frames[:8],
        "reason": verdict.reason,
        "reported_symbol_matched": failure_is_named_in_report(
            run.stdout_tail, bug_report
        ),
        "overspecified": overspecification(test_source, bug_report),
        "ungrounded_literals": ungrounded_literals(test_source, bug_report),
        "test_rel_path": rel_path,
        "outcome": run.outcome,
        "exit_code": run.exit_code,
        "duration_s": run.duration_s,
        "not_established": list(NOT_ESTABLISHED),
    }
