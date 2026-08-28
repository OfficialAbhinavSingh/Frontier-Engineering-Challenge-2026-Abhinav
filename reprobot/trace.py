"""Trajectory recording.

Trajectories are a graded deliverable, so they are produced by the system rather
than reconstructed afterwards. Every agent prompt, model reply, tool invocation,
tool response and verdict is appended as it happens, in order, to one JSONL file
per case. Nothing is summarised at write time -- a trace is meant to let a reader
reconstruct exactly why the agent did what it did next.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any


class Trace:
    """Append-only event log for a single case run."""

    def __init__(self, root: Path | str, variant: str, case_id: str) -> None:
        self.dir = Path(root) / variant
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / f"{case_id}.jsonl"
        # A fresh run replaces the previous trace for that case so the file always
        # describes one coherent execution rather than several interleaved ones.
        self.path.write_text("")
        self.run_id = uuid.uuid4().hex[:12]
        self.variant = variant
        self.case_id = case_id
        self.seq = 0
        self.started = time.time()

    def event(self, kind: str, **fields: Any) -> None:
        self.seq += 1
        record = {
            "seq": self.seq,
            "t": round(time.time() - self.started, 3),
            "run_id": self.run_id,
            "variant": self.variant,
            "case_id": self.case_id,
            "kind": kind,
            **fields,
        }
        with self.path.open("a") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    # Convenience wrappers, so call sites read like the story they tell.

    def agent_start(self, agent: str, system: str, user: str) -> None:
        self.event("agent_prompt", agent=agent, system=system, user=user)

    def llm_reply(self, agent: str, text: str, usage: dict, from_cache: bool) -> None:
        self.event("llm_response", agent=agent, text=text, usage=usage,
                   from_cache=from_cache)

    def tool_call(self, tool: str, args: dict) -> None:
        self.event("tool_call", tool=tool, args=args)

    def tool_result(self, tool: str, result: Any, truncated: bool = False) -> None:
        self.event("tool_result", tool=tool, result=result, truncated=truncated)

    def verdict(self, round_no: int, outcome: str, detail: dict) -> None:
        self.event("verdict", round=round_no, outcome=outcome, detail=detail)

    def checkpoint(self, name: str, detail: dict) -> None:
        """A point where a human would approve or intervene."""
        self.event("human_checkpoint", name=name, detail=detail)

    def finish(self, result: dict) -> None:
        self.event("run_end", result=result,
                   wall_clock_s=round(time.time() - self.started, 2))


def render_markdown(jsonl_path: Path | str, max_chars: int = 1600) -> str:
    """Turn a trace into something a judge can read straight through."""
    path = Path(jsonl_path)
    lines: list[str] = [f"# Trajectory — `{path.stem}`\n"]

    def clip(text: str) -> str:
        text = text if isinstance(text, str) else json.dumps(text, indent=2)
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + f"\n… [{len(text) - max_chars} more chars]"

    for raw in path.read_text().splitlines():
        if not raw.strip():
            continue
        ev = json.loads(raw)
        kind, t = ev["kind"], ev["t"]
        if kind == "agent_prompt":
            lines.append(f"\n## [{t}s] agent `{ev['agent']}` — instructions\n")
            lines.append("**System**\n\n````\n" + clip(ev["system"]) + "\n````\n")
            lines.append("**User**\n\n````\n" + clip(ev["user"]) + "\n````")
        elif kind == "llm_response":
            src = "cache replay" if ev.get("from_cache") else "live"
            lines.append(f"\n### [{t}s] model reply to `{ev['agent']}` ({src})\n")
            lines.append("````\n" + clip(ev["text"]) + "\n````")
        elif kind == "tool_call":
            lines.append(f"\n### [{t}s] tool call `{ev['tool']}`\n")
            lines.append("````json\n" + clip(ev["args"]) + "\n````")
        elif kind == "tool_result":
            lines.append(f"\n### [{t}s] tool result `{ev['tool']}`\n")
            lines.append("````\n" + clip(ev["result"]) + "\n````")
        elif kind == "verdict":
            lines.append(
                f"\n### [{t}s] verifier verdict — round {ev['round']}: "
                f"**{ev['outcome']}**\n"
            )
            lines.append("````json\n" + clip(ev["detail"]) + "\n````")
        elif kind == "human_checkpoint":
            lines.append(f"\n### [{t}s] human checkpoint — `{ev['name']}`\n")
            lines.append("````json\n" + clip(ev["detail"]) + "\n````")
        elif kind == "run_end":
            lines.append(f"\n## [{t}s] run finished ({ev['wall_clock_s']}s)\n")
            lines.append("````json\n" + clip(ev["result"]) + "\n````")
    return "\n".join(lines) + "\n"


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="Render a JSONL trace as markdown.")
    ap.add_argument("jsonl")
    ap.add_argument("--out")
    args = ap.parse_args()
    md = render_markdown(args.jsonl)
    if args.out:
        Path(args.out).write_text(md)
        print(f"wrote {args.out}")
    else:
        print(md)


if __name__ == "__main__":
    main()
