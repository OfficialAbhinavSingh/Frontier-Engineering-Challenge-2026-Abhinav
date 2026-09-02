"""The MCP surface.

Nothing here imports the MCP SDK, so `ratchat.mcp.guardrail` stays importable
with no extra installed and no Docker daemon running. Only `server.py` needs the
SDK, and it fails with an instruction rather than a traceback.
"""

from __future__ import annotations


def missing_sdk_message(installed_version: str | None) -> str:
    """What to tell someone whose MCP SDK cannot provide the server class.

    Two different problems, deliberately two different messages. Saying "not
    installed" about an SDK that is installed points the reader at the one thing
    already true and hides the real cause -- a diagnosis that reads plausibly
    and is wrong, which is the failure this project exists to catch.
    """
    if installed_version is None:
        return (
            "The Ratchat MCP server needs the optional MCP SDK, which is not "
            "installed. Install it with:\n"
            "    pip install 'ratchat[mcp]'\n"
            "The rest of Ratchat, including the offline replay, needs no "
            "dependencies and is unaffected."
        )
    return (
        f"The Ratchat MCP server needs mcp>=2, but mcp {installed_version} is "
        "installed and does not provide MCPServer (it was named FastMCP before "
        "2.0). Upgrade it with:\n"
        "    pip install --upgrade 'mcp>=2'"
    )
