"""MCP wiring, and nothing else.

Every decision lives in `guardrail.py`. This file exists only to carry it over
the protocol, so that the guardrail stays importable and testable with neither
the MCP SDK nor a Docker daemon present.
"""

from __future__ import annotations

from ratchat.mcp import missing_sdk_message

try:
    from mcp.server.mcpserver import MCPServer
except ModuleNotFoundError as exc:  # pragma: no cover - needs the SDK absent
    # Distinguish "no SDK" from "wrong SDK": both raise ModuleNotFoundError here,
    # and only one of them is fixed by installing the extra.
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as _version

    try:
        _installed: str | None = _version("mcp")
    except PackageNotFoundError:
        _installed = None
    raise ImportError(missing_sdk_message(_installed)) from exc

from ratchat.mcp.guardrail import prepare_repo as _prepare_repo
from ratchat.mcp.guardrail import verify_reproduction as _verify_reproduction

server = MCPServer(name="ratchat")


@server.tool()
def prepare_repo(repo_path: str, force: bool = False) -> dict:
    """Build the sandbox image a repository needs before any test can be run.

    Slow the first time for a repository -- it clones and installs the project
    inside a pinned image -- and instant afterwards. Call it once per
    repository, then call verify_reproduction as often as you like.

    Args:
        repo_path: Path to a local clone. Needs an origin remote on github.com,
            because the image is built by cloning rather than by copying the
            working tree.
        force: Rebuild even when the image already exists.
    """
    return _prepare_repo(repo_path, force=force)


@server.tool()
def verify_reproduction(
    repo_path: str,
    bug_report: str,
    test_source: str,
    test_rel_path: str | None = None,
    timeout_s: int = 180,
) -> dict:
    """Prove whether a test reproduces a reported bug, and say why it failed.

    Runs one candidate test at the repository's pinned commit, in a container
    with no network, and reports the reason for the failure rather than only the
    fact of it. Use it before claiming a bug is fixed: a test that fails without
    ever entering the project's own code demonstrates nothing, and this is what
    tells the two apart.

    Calls no model and reads no API key, so the same inputs give the same answer.

    It does not establish that the test will pass once the bug is fixed -- that
    needs a fix commit, which does not exist yet. Every successful response says
    so in `not_established`; read it before reporting the result to anyone.

    Args:
        repo_path: Path to a local clone already passed to prepare_repo.
        bug_report: The report, in the reporter's own words. Used to judge
            whether the failure is the reported one and whether the test asserts
            values the report never mentions, so paraphrasing it weakens both.
        test_source: The complete test file to run.
        test_rel_path: Where to place it, relative to the repository root.
            Defaults to a new path under the project's own test directory. Must
            not already exist.
        timeout_s: Seconds before the run is abandoned.
    """
    return _verify_reproduction(
        repo_path,
        bug_report,
        test_source,
        test_rel_path=test_rel_path,
        timeout_s=timeout_s,
    )


def main() -> None:
    server.run()


if __name__ == "__main__":
    main()
