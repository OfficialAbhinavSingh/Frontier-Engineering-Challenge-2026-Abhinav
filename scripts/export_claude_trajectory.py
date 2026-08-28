"""Export the Claude Code session that built this project, redacted.

Repro-Bot's own agents write their trajectories as they run. This script covers
the other agent involved: the coding agent that wrote the project itself.

A raw Claude Code session log is not safe to publish. It contains the operator's
private memory index, unrelated projects, absolute home paths and whatever
happened to be in the environment. So this exporter is deny-by-default: it keeps
the user's instructions, the assistant's reasoning and the tool calls and results,
and drops everything injected by the harness. Paths are rewritten to be relative
and anything shaped like a credential is replaced.

Read the output before publishing it. That is the point of the `--preview` flag.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

SESSIONS_DIR = Path.home() / ".claude" / "projects"

# Extra terms to scrub, one per line, read from outside the repository.
# The operator's other project names must not be hardcoded here: writing them
# into this file would put them in the published repository, which is the thing
# the redaction exists to prevent.
DEFAULT_REDACT_FILE = Path.home() / ".config" / "reprobot" / "redact.txt"

# Harness-injected content. None of it is part of the trajectory and some of it
# is private, so it is removed rather than summarised.
DROP_BLOCKS = [
    re.compile(r"<system-reminder>.*?</system-reminder>", re.S),
    re.compile(r"<command-name>.*?</local-command-stdout>", re.S),
    re.compile(r"# Memory Index.*?(?=\n#|\Z)", re.S),
    re.compile(r"<EXTREMELY_IMPORTANT>.*?</EXTREMELY_IMPORTANT>", re.S),
]

REDACTIONS = [
    (re.compile(r"sk-or-v1-[A-Za-z0-9_\-]+"), "sk-or-v1-<redacted>"),
    (re.compile(r"sk-ant-[A-Za-z0-9_\-]+"), "sk-ant-<redacted>"),
    (re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"), "gh<redacted>"),
    (re.compile(r"Bearer\s+[A-Za-z0-9._\-]{20,}"), "Bearer <redacted>"),
    (re.compile(r"/home/[^/\s\"']+"), "~"),
]


EXTRA_TERMS: list[re.Pattern] = []


def load_extra_terms(path: Path) -> None:
    """Load operator-supplied terms to scrub.

    A session transcript picks up more than credentials. Commands run during the
    session can quote unrelated project names -- a scan for leaked terms
    necessarily contains the terms it scans for -- and those should not travel
    into a published submission either.
    """
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        term = line.strip()
        if term and not term.startswith("#"):
            EXTRA_TERMS.append(re.compile(re.escape(term), re.I))


def clean(text: str) -> str:
    for pattern in DROP_BLOCKS:
        text = pattern.sub("", text)
    for pattern, replacement in REDACTIONS:
        text = pattern.sub(replacement, text)
    for pattern in EXTRA_TERMS:
        text = pattern.sub("<redacted>", text)
    return text.strip()


def content_to_text(content) -> tuple[str, list[dict]]:
    """Split a message into prose and structured tool events."""
    if isinstance(content, str):
        return clean(content), []
    prose, events = [], []
    for block in content or []:
        if not isinstance(block, dict):
            continue
        kind = block.get("type")
        if kind == "text":
            prose.append(block.get("text", ""))
        elif kind == "thinking":
            prose.append("_(thinking)_ " + block.get("thinking", ""))
        elif kind == "tool_use":
            events.append({
                "type": "tool_use",
                "name": block.get("name"),
                "input": block.get("input", {}),
            })
        elif kind == "tool_result":
            result = block.get("content")
            if isinstance(result, list):
                result = "\n".join(
                    b.get("text", "") for b in result if isinstance(b, dict)
                )
            events.append({
                "type": "tool_result",
                "is_error": block.get("is_error", False),
                "content": result,
            })
    return clean("\n\n".join(prose)), events


def load_session(path: Path, keep_marker: str | None) -> list[dict]:
    turns = []
    for raw in path.read_text(errors="replace").splitlines():
        if not raw.strip():
            continue
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError:
            continue
        message = entry.get("message")
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        if role not in ("user", "assistant"):
            continue
        prose, events = content_to_text(message.get("content"))
        if not prose and not events:
            continue
        turns.append({"role": role, "text": prose, "events": events,
                      "ts": entry.get("timestamp")})

    if keep_marker:
        blob = json.dumps(turns)
        if keep_marker not in blob:
            return []
    return turns


def render(turns: list[dict], max_chars: int) -> str:
    def clip(text: str) -> str:
        text = text if isinstance(text, str) else json.dumps(text, indent=2)
        text = clean(text)
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + f"\n… [{len(text) - max_chars} more chars]"

    out = [
        "# Coding-agent trajectory — building Repro-Bot\n",
        "The agent that wrote this project was Claude Code. This is its session, "
        "with harness-injected context and anything credential-shaped removed, and "
        "home paths rewritten. Tool calls and their results are kept in order so "
        "the feedback that shaped each next step is visible.\n",
    ]
    step = 0
    for turn in turns:
        if turn["role"] == "user" and turn["text"]:
            out.append(f"\n---\n\n## Operator\n\n{clip(turn['text'])}\n")
        elif turn["role"] == "assistant":
            if turn["text"]:
                out.append(f"\n### Agent\n\n{clip(turn['text'])}\n")
            for event in turn["events"]:
                step += 1
                if event["type"] == "tool_use":
                    out.append(f"\n**Tool call {step} — `{event['name']}`**\n")
                    out.append("````json\n" + clip(event["input"]) + "\n````\n")
                else:
                    flag = " (error)" if event.get("is_error") else ""
                    out.append(f"\n**Tool result {step}{flag}**\n")
                    out.append("````\n" + clip(event.get("content") or "") + "\n````\n")
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", help="path to a .jsonl session log")
    ap.add_argument("--session-id", help="session id to look up under ~/.claude/projects")
    ap.add_argument("--keep-marker", default="repro-bot",
                    help="only export sessions mentioning this string")
    ap.add_argument("--out", default="agent-trajectories/claude-code-build.md")
    ap.add_argument("--max-chars", type=int, default=2000)
    ap.add_argument("--preview", action="store_true",
                    help="print a summary instead of writing the file")
    ap.add_argument("--redact-file", default=str(DEFAULT_REDACT_FILE),
                    help="newline-separated extra terms to scrub; kept outside the repo")
    args = ap.parse_args()

    load_extra_terms(Path(args.redact_file))

    if args.session:
        paths = [Path(args.session)]
    elif args.session_id:
        paths = list(SESSIONS_DIR.rglob(f"{args.session_id}.jsonl"))
    else:
        paths = sorted(SESSIONS_DIR.rglob("*.jsonl"),
                       key=lambda p: p.stat().st_mtime, reverse=True)[:1]
    if not paths:
        raise SystemExit("no session log found")

    turns = load_session(paths[0], args.keep_marker)
    if not turns:
        raise SystemExit(
            f"{paths[0].name} does not mention {args.keep_marker!r}; refusing to export "
            "a session that is probably about something else"
        )

    text = render(turns, args.max_chars)
    if args.preview:
        print(f"source: {paths[0]}")
        print(f"turns: {len(turns)}  rendered: {len(text)} chars")
        print(text[:3000])
        return

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    print(f"wrote {out} ({len(text)} chars from {len(turns)} turns)")


if __name__ == "__main__":
    main()
