"""Run a candidate test inside a pinned, offline Docker container.

Two properties matter more than anything else here.

First, isolation: the container gets no network, so a test cannot reach out and
cannot silently install something that makes a later run irreproducible.

Second, typed outcomes. Every other part of this project is built on the claim
that "the test failed" is not a useful signal -- what matters is *why* it failed.
So this module never returns a boolean. It returns a classified outcome plus the
exception type, which is what the repair loop actually reasons over.
"""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

IMAGE_PREFIX = "reprobot-env"

# Printed inside the container once checkout and injection have both succeeded.
CHECKOUT_OK = "__REPROBOT_SANDBOX_READY__"
DEFAULT_TIMEOUT = 180

# pytest's documented exit codes.
EXIT_OK = 0
EXIT_TESTS_FAILED = 1
EXIT_INTERRUPTED = 2
EXIT_INTERNAL = 3
EXIT_USAGE = 4
EXIT_NO_TESTS = 5

# Last line of a pytest traceback, e.g. "E   TypeError: bad operand".
EXC_LINE = re.compile(r"^E\s+([A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception|Warning)):", re.M)
# Short-test-summary line, e.g. "FAILED tests/x.py::test_y - KeyError: 'a'".
SUMMARY_EXC = re.compile(r"^(?:FAILED|ERROR)\s+\S+\s+-\s+([A-Za-z_][A-Za-z0-9_.]*):", re.M)

# Failures that mean the test never really ran, as opposed to the code being wrong.
INFRA_EXCEPTIONS = {
    "ImportError",
    "ModuleNotFoundError",
    "SyntaxError",
    "IndentationError",
    "NameError",
    "AttributeError",
    "FixtureLookupError",
    "UsageError",
    "CollectError",
}


@dataclass
class RunResult:
    """Outcome of running one test file at one commit."""

    outcome: str  # passed | failed | collection_error | no_tests | timeout | infra_error
    exit_code: int
    exception_type: str | None
    duration_s: float
    stdout_tail: str

    @property
    def is_real_failure(self) -> bool:
        """True when the test ran and failed on the code under test."""
        return self.outcome == "failed"

    def to_dict(self) -> dict:
        return asdict(self)


def _force_remove(container: str) -> None:
    subprocess.run(["docker", "rm", "-f", container],
                   capture_output=True, check=False)


def image_name(repo_name: str) -> str:
    return f"{IMAGE_PREFIX}:{repo_name}"


def image_exists(repo_name: str) -> bool:
    proc = subprocess.run(
        ["docker", "image", "inspect", image_name(repo_name)],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode == 0


def build_image(repo: str, pin_sha: str, dockerfile: str = "envs/Dockerfile.repo",
                quiet: bool = False) -> None:
    """Build the per-repo environment image.

    The image is built once per repository at a pinned SHA. Individual cases only
    move the working tree within that image, so no case can change the installed
    dependency set out from under another one.
    """
    repo_name = repo.split("/")[1]
    cmd = [
        "docker", "build",
        "-f", dockerfile,
        "-t", image_name(repo_name),
        "--build-arg", f"REPO_URL=https://github.com/{repo}.git",
        "--build-arg", f"REPO_NAME={repo_name}",
        "--build-arg", f"PIN_SHA={pin_sha}",
        ".",
    ]
    if quiet:
        cmd.insert(2, "-q")
    subprocess.run(cmd, check=True)


def classify(exit_code: int, output: str, timed_out: bool) -> tuple[str, str | None]:
    """Map a pytest run onto a typed outcome and the exception that caused it."""
    if timed_out:
        return "timeout", None

    exc = None
    m = SUMMARY_EXC.search(output) or EXC_LINE.search(output)
    if m:
        exc = m.group(1).split(".")[-1]

    if exit_code == EXIT_OK:
        return "passed", None
    if exit_code == EXIT_NO_TESTS:
        return "no_tests", exc
    if exit_code in (EXIT_INTERRUPTED, EXIT_INTERNAL, EXIT_USAGE):
        return "collection_error", exc
    if exit_code == EXIT_TESTS_FAILED:
        # A test can be collected and still fail for a reason that has nothing to
        # do with the bug -- calling an API that does not exist, for instance.
        # That is an infrastructure failure wearing a test failure's exit code.
        if exc in INFRA_EXCEPTIONS:
            return "infra_error", exc
        return "failed", exc
    return "collection_error", exc


def run_test(
    repo_name: str,
    sha: str,
    test_rel_path: str,
    test_source: str,
    timeout_s: int = DEFAULT_TIMEOUT,
    extra_pytest_args: tuple[str, ...] = (),
) -> RunResult:
    """Check out `sha`, inject `test_source` at `test_rel_path`, run pytest on it."""
    started = time.time()
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as fh:
        fh.write(test_source)
        host_path = fh.name
    Path(host_path).chmod(0o644)

    # The test is mounted outside the working tree and copied in only after the
    # checkout. Mounting it directly over a tracked path makes git treat it as a
    # local modification and abort the checkout, which silently invalidates the
    # run -- a bug that costs you correct-looking results for the wrong commit.
    inject_path = "/tmp/reprobot_inject.py"
    quoted_rel = shlex.quote(test_rel_path)
    inner = (
        f"git checkout -q {shlex.quote(sha)} && "
        f"mkdir -p \"$(dirname {quoted_rel})\" && "
        f"cp {inject_path} {quoted_rel} && "
        f"echo {CHECKOUT_OK} && "
        f"python -m pytest {quoted_rel} "
        f"-q --no-header -p no:cacheprovider --tb=short "
        f"{' '.join(extra_pytest_args)}"
    )
    # Named, so a run that outlives its client can still be cleaned up. Killing
    # the docker CLI does not stop the container it started, and an orphan keeps
    # burning CPU and distorting every timing measured after it.
    container = f"reprobot-{uuid.uuid4().hex[:12]}"
    cmd = [
        "docker", "run", "--rm",
        "--name", container,
        "--network", "none",
        "--memory", "2g",
        "--cpus", "2",
        "-v", f"{host_path}:{inject_path}:ro",
        "-w", "/work/repo",
        image_name(repo_name),
        "bash", "-lc", inner,
    ]

    timed_out = False
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout_s + 30, check=False,
            # A generated test that reads stdin would otherwise block until the
            # timeout instead of failing immediately.
            stdin=subprocess.DEVNULL,
        )
        output = proc.stdout + proc.stderr
        exit_code = proc.returncode
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        output = (exc.stdout or b"").decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        exit_code = -1
        _force_remove(container)
    finally:
        Path(host_path).unlink(missing_ok=True)

    # If the checkout or injection failed, pytest never ran. Without this guard a
    # failed checkout exits 1 and masquerades as a legitimate test failure.
    if not timed_out and CHECKOUT_OK not in output:
        return RunResult(
            outcome="infra_error",
            exit_code=exit_code,
            exception_type="SandboxSetupFailed",
            duration_s=round(time.time() - started, 2),
            stdout_tail=output[-4000:],
        )

    outcome, exception_type = classify(exit_code, output, timed_out)
    return RunResult(
        outcome=outcome,
        exit_code=exit_code,
        exception_type=exception_type,
        duration_s=round(time.time() - started, 2),
        stdout_tail=output[-4000:],
    )


def run_suite(repo_name: str, sha: str, timeout_s: int = 900) -> RunResult:
    """Run the repository's own test suite -- used for the P2P regression check."""
    started = time.time()
    inner = (
        f"git checkout -q {shlex.quote(sha)} && "
        "python -m pytest -q --no-header -p no:cacheprovider --tb=no"
    )
    container = f"reprobot-suite-{uuid.uuid4().hex[:12]}"
    cmd = [
        "docker", "run", "--rm", "--name", container, "--network", "none",
        "--memory", "2g", "--cpus", "2",
        "-w", "/work/repo",
        image_name(repo_name),
        "bash", "-lc", inner,
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout_s, check=False,
            stdin=subprocess.DEVNULL,
        )
        output = proc.stdout + proc.stderr
        outcome, exc = classify(proc.returncode, output, False)
        code = proc.returncode
    except subprocess.TimeoutExpired:
        _force_remove(container)
        output, outcome, exc, code = "", "timeout", None, -1
    return RunResult(outcome, code, exc, round(time.time() - started, 2), output[-4000:])


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Build a repo image or smoke-test a run.")
    ap.add_argument("--build", metavar="OWNER/NAME")
    ap.add_argument("--pin", help="SHA to pin the image at")
    args = ap.parse_args()

    if args.build:
        build_image(args.build, args.pin)
        print(json.dumps({"image": image_name(args.build.split("/")[1]), "pin": args.pin}))
