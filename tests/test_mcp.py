"""Tests for the MCP guardrail surface.

The guardrail's whole value is that it reports *why* a test failed and refuses
to answer when it cannot know. So the cases below check the two refusals as
carefully as the successful mapping: a tool that quietly guesses is worse than
one that declines, because the caller cannot tell a guess from a measurement.

No Docker. The sandbox and the image check are the only I/O boundaries, and both
are injected, so everything here exercises the real verifier against real pytest
output shapes.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from ratchat.mcp.guardrail import (
    MCP_TEST_PREFIX,
    prepare_repo,
    verify_reproduction,
)
from ratchat.sandbox.run import RunResult

REPORT = "len() on a Float raises TypeError: object of type 'Float' has no len()"


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.email=t@t.t", "-c", "user.name=t",
         *args],
        check=True, capture_output=True,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A real git repository, because RepoView reads it with `git ls-tree`."""
    root = tmp_path / "tomlkit"
    (root / "tests").mkdir(parents=True)
    (root / "tomlkit").mkdir()
    (root / "tomlkit" / "items.py").write_text("def f():\n    return 1\n")
    (root / "tests" / "test_items.py").write_text("def test_f():\n    assert True\n")
    git(root, "init", "-q")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "init")
    # A real clone has an origin. The image build needs the GitHub slug, because
    # the Dockerfile clones the repository rather than copying the working tree.
    git(root, "remote", "add", "origin", "https://github.com/sdispater/tomlkit.git")
    return root


@pytest.fixture
def local_only_repo(tmp_path: Path) -> Path:
    """A repository with no GitHub origin, which cannot be imaged today."""
    root = tmp_path / "private"
    (root / "tests").mkdir(parents=True)
    (root / "tests" / "test_a.py").write_text("def test_a():\n    assert True\n")
    git(root, "init", "-q")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "init")
    return root


def run_result(outcome: str, exc: str | None, output: str) -> RunResult:
    return RunResult(outcome, 1, exc, 0.1, output)


def reproducing_output(test_rel_path: str) -> str:
    return (
        f"{test_rel_path}:8: in test_len_of_float\n"
        "    len(doc['x'])\n"
        "tomlkit/items.py:44: in __len__\n"
        "    return len(self._value)\n"
        "E   TypeError: object of type 'Float' has no len()\n"
        f"FAILED {test_rel_path}::test_len_of_float - TypeError: object of type\n"
    )


def reproducing_runner(test_rel_path: str):
    def runner(repo_name, sha, rel_path, source, timeout_s):
        return run_result("failed", "TypeError", reproducing_output(rel_path))

    return runner


def exploding_runner(*args, **kwargs):
    raise AssertionError("the sandbox must not run when the repo is unprepared")


# --- refusals ---------------------------------------------------------------


def test_unprepared_repo_refuses_instead_of_running(repo: Path):
    response = verify_reproduction(
        repo_path=str(repo),
        bug_report=REPORT,
        test_source="def test_x():\n    assert False\n",
        runner=exploding_runner,
        has_image=lambda name: False,
    )

    assert response["error"] == "repo not prepared"
    assert response["fix"] == "call prepare_repo first"
    assert response["repo_name"] == "tomlkit"
    assert "verdict" not in response


def test_existing_test_path_refuses_rather_than_overwriting(repo: Path):
    response = verify_reproduction(
        repo_path=str(repo),
        bug_report=REPORT,
        test_source="def test_x():\n    assert False\n",
        test_rel_path="tests/test_items.py",
        runner=exploding_runner,
        has_image=lambda name: True,
    )

    assert response["error"] == "test path already exists"
    assert response["path"] == "tests/test_items.py"
    assert "verdict" not in response


# --- the successful mapping -------------------------------------------------


def test_reproduction_reports_the_verdict_and_what_it_means(repo: Path):
    rel = "tests/test_ratchat_probe.py"
    response = verify_reproduction(
        repo_path=str(repo),
        bug_report=REPORT,
        test_source="def test_len_of_float():\n    len(doc['x'])\n",
        test_rel_path=rel,
        runner=reproducing_runner(rel),
        has_image=lambda name: True,
    )

    assert response["reproduces"] is True
    assert response["verdict"] == "reproduced_exception"
    assert "project's own code raised the error" in response["verdict_meaning"]
    assert response["exception_type"] == "TypeError"
    assert any("tomlkit/items.py" in f for f in response["source_frames"])
    assert response["outcome"] == "failed"


def test_a_test_that_never_reaches_project_code_does_not_reproduce(repo: Path):
    """The distinction the project rests on, surfaced through the tool.

    Same exit code, same exception type, same "it failed". The tool must not
    report this as a reproduction, or the guardrail waves through exactly the
    mistake it exists to catch.
    """
    rel = "tests/test_ratchat_probe.py"
    shallow = (
        f"{rel}:6: in test_len_of_float\n"
        "    doc.parse_value('x', mode='strict')\n"
        "E   TypeError: parse_value() got an unexpected keyword argument 'mode'\n"
        f"FAILED {rel}::test_len_of_float - TypeError: parse_value()\n"
    )

    response = verify_reproduction(
        repo_path=str(repo),
        bug_report=REPORT,
        test_source="def test_len_of_float():\n    doc.parse_value('x', mode='strict')\n",
        test_rel_path=rel,
        runner=lambda *a, **k: run_result("failed", "TypeError", shallow),
        has_image=lambda name: True,
    )

    assert response["reproduces"] is False
    assert response["verdict"] == "shallow_fail"
    assert response["source_frames"] == []


def test_every_success_names_what_it_did_not_establish(repo: Path):
    rel = "tests/test_ratchat_probe.py"
    response = verify_reproduction(
        repo_path=str(repo),
        bug_report=REPORT,
        test_source="def test_len_of_float():\n    len(doc['x'])\n",
        test_rel_path=rel,
        runner=reproducing_runner(rel),
        has_image=lambda name: True,
    )

    assert response["not_established"]
    assert any("fix will produce" in item for item in response["not_established"])


def test_asserted_values_absent_from_the_report_are_flagged(repo: Path):
    """A test can fail for the right reason and still assert an invented value."""
    rel = "tests/test_ratchat_probe.py"
    source = (
        "def test_len_of_float():\n"
        "    assert render(doc) == 'a completely invented expected string'\n"
    )
    response = verify_reproduction(
        repo_path=str(repo),
        bug_report=REPORT,
        test_source=source,
        test_rel_path=rel,
        runner=reproducing_runner(rel),
        has_image=lambda name: True,
    )

    assert "a completely invented expected string" in response["ungrounded_literals"]


# --- generated test path ----------------------------------------------------


def test_generated_path_uses_the_mcp_prefix_not_the_frozen_legacy_one(repo: Path):
    captured = {}

    def runner(repo_name, sha, rel_path, source, timeout_s):
        captured["rel_path"] = rel_path
        return run_result("failed", "TypeError", reproducing_output(rel_path))

    verify_reproduction(
        repo_path=str(repo),
        bug_report=REPORT,
        test_source="def test_x():\n    assert False\n",
        runner=runner,
        has_image=lambda name: True,
    )

    rel_path = captured["rel_path"]
    assert Path(rel_path).name.startswith(MCP_TEST_PREFIX)
    assert "test_reprobot_" not in rel_path
    assert rel_path.startswith("tests/")
    assert not (repo / rel_path).exists()


def test_generated_path_is_stable_for_one_report_and_differs_across_reports(
    repo: Path,
):
    """A hash of the report, so a retry lands on the same path and two reports
    do not collide."""
    seen = []

    def runner(repo_name, sha, rel_path, source, timeout_s):
        seen.append(rel_path)
        return run_result("failed", "TypeError", reproducing_output(rel_path))

    common = {
        "repo_path": str(repo),
        "test_source": "def test_x():\n    assert False\n",
        "runner": runner,
        "has_image": lambda name: True,
    }
    verify_reproduction(bug_report=REPORT, **common)
    verify_reproduction(bug_report=REPORT, **common)
    verify_reproduction(bug_report="an entirely different bug report", **common)

    assert seen[0] == seen[1]
    assert seen[2] != seen[0]


# --- prepare_repo -----------------------------------------------------------


def test_prepare_builds_the_image_when_there_is_none(repo: Path):
    built = []

    response = prepare_repo(
        repo_path=str(repo),
        has_image=lambda name: False,
        builder=lambda repo_arg, pin_sha: built.append((repo_arg, pin_sha)),
    )

    assert response["built"] is True
    assert response["repo_name"] == "tomlkit"
    assert response["image"] == "ratchat-env:tomlkit"
    assert len(response["pin_sha"]) == 40
    assert len(built) == 1
    # Built at the same pin the guardrail will later run at, not a fresh HEAD read.
    assert built[0][1] == response["pin_sha"]


def test_prepare_is_idempotent_and_does_not_rebuild(repo: Path):
    def exploding_builder(*args, **kwargs):
        raise AssertionError("must not rebuild an image that already exists")

    response = prepare_repo(
        repo_path=str(repo),
        has_image=lambda name: True,
        builder=exploding_builder,
    )

    assert response["built"] is False
    assert response["image"] == "ratchat-env:tomlkit"


def test_prepare_rebuilds_when_forced(repo: Path):
    built = []

    response = prepare_repo(
        repo_path=str(repo),
        force=True,
        has_image=lambda name: True,
        builder=lambda repo_arg, pin_sha: built.append(repo_arg),
    )

    assert response["built"] is True
    assert len(built) == 1


def test_prepare_passes_the_github_slug_from_origin_to_the_builder(repo: Path):
    built = []

    prepare_repo(
        repo_path=str(repo),
        has_image=lambda name: False,
        builder=lambda repo_arg, pin_sha: built.append(repo_arg),
    )

    # Not the local directory name: the Dockerfile clones
    # https://github.com/<slug>.git, so the slug must be owner/name.
    assert built == ["sdispater/tomlkit"]


def test_prepare_refuses_a_repo_with_no_github_origin(local_only_repo: Path):
    def exploding_builder(*args, **kwargs):
        raise AssertionError("must not attempt a build without a resolvable slug")

    response = prepare_repo(
        repo_path=str(local_only_repo),
        has_image=lambda name: False,
        builder=exploding_builder,
    )

    assert response["error"] == "no GitHub origin"
    assert "built" not in response


# --- the protocol layer -----------------------------------------------------


def test_importing_the_server_without_the_extra_says_how_to_install_it():
    """The guardrail must stay usable without the MCP SDK, and the server must
    fail with an instruction rather than a bare ModuleNotFoundError."""
    pytest.importorskip  # noqa: B018 - documents intent; the check below is real
    try:
        import mcp  # noqa: F401
    except ModuleNotFoundError:
        pass
    else:
        pytest.skip("mcp is installed, so the guard cannot be observed here")

    with pytest.raises(ImportError, match=r"ratchat\[mcp\]"):
        import ratchat.mcp.server  # noqa: F401


def test_absent_and_incompatible_sdk_are_diagnosed_differently():
    """A wrong version is not a missing install.

    Reporting "not installed" for an SDK that is installed sends the reader to
    fix the one thing that is already true -- the same failure mode the
    guardrail exists to catch, in the tool's own plumbing.
    """
    from ratchat.mcp import missing_sdk_message

    absent = missing_sdk_message(installed_version=None)
    assert "ratchat[mcp]" in absent

    incompatible = missing_sdk_message(installed_version="1.9.0")
    assert "1.9.0" in incompatible
    assert "mcp>=2" in incompatible
    # Installing the extra cannot fix a version that is already installed.
    assert "pip install 'ratchat[mcp]'" not in incompatible


def test_a_path_that_is_not_a_git_repository_is_reported_not_raised(tmp_path: Path):
    """Found by calling the tool for real, not by reading the code.

    `pin_sha_for` runs git with check=True, so a bad path raised
    CalledProcessError out through the protocol layer as an opaque
    "Error executing tool". It surfaces as a stated error instead. Reachable in
    practice because the image lookup is keyed on the directory name, so a
    stale image for some other clone of the same name passes the first gate.
    """
    response = verify_reproduction(
        repo_path=str(tmp_path / "not-a-repo"),
        bug_report="len() on a Float raises TypeError",
        test_source="def test_x():\n    assert False\n",
        runner=exploding_runner,
        has_image=lambda name: True,
    )

    assert response["error"] == "not a git repository"
    assert str(tmp_path / "not-a-repo") in response["path"]
    assert "verdict" not in response
