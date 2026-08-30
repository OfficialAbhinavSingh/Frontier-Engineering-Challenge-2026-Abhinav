"""Assemble the agent-trajectories deliverable.

Every run already writes a JSONL trajectory as it happens, so nothing here
reconstructs anything. This picks a representative set, renders them as readable
markdown, and writes an index that says why each one was chosen.

The selection is deliberate rather than a dump. A reader learns more from one
run that failed verification and repaired itself than from twenty that succeeded
on the first attempt.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Run as a script from anywhere in the project without an install step.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ratchat.trace import render_markdown  # noqa: E402

INDEX_HEADER = """# Agent trajectories

Two kinds of agent were used, and both are represented here.

**Ratchat's own agents** — the locator, the author, the memory writer, and the
model-judged verifier in the removed experiment. Each run writes its trajectory
as it happens, in order, to `traces/<variant>/<case>.jsonl`: every prompt, every
model reply, every tool call and its response, every verdict, and the human
checkpoint at the end. The files below are those logs rendered as markdown.

**Claude Code (Claude Opus 5)** — the coding agent that built the project. Its
session is in [`claude-code-build.md`](claude-code-build.md), exported with
harness-injected context removed, credential-shaped strings redacted and home
paths rewritten.

Every trajectory here is complete from the agent's instructions through to the
scored result. Nothing is summarised or reordered.

## What to read, and why

"""


def summarise(path: Path) -> dict:
    """Pull the shape of a run out of its trace."""
    info = {"verdicts": [], "tools": 0, "llm_calls": 0, "f2p": None,
            "case": path.stem, "checkpoint": False}
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = event.get("kind")
        if kind == "verdict":
            info["verdicts"].append(event["outcome"])
        elif kind == "tool_call":
            info["tools"] += 1
        elif kind == "llm_response":
            info["llm_calls"] += 1
        elif kind == "human_checkpoint":
            info["checkpoint"] = True
        elif kind == "scored":
            info["f2p"] = event.get("f2p")
        elif kind == "run_end":
            result = event.get("result") or {}
            if info["f2p"] is None:
                info["f2p"] = result.get("f2p")
    return info


def pick(traces_dir: Path, variant: str, want: int) -> list[tuple[Path, str]]:
    """Choose runs that show something, not just runs that worked."""
    candidates = sorted(traces_dir.glob(f"{variant}/*.jsonl"))
    scored = [(p, summarise(p)) for p in candidates]

    chosen: list[tuple[Path, str]] = []
    used: set[Path] = set()

    def take(pred, why: str) -> None:
        for path, info in scored:
            if len(chosen) >= want or path in used:
                continue
            if pred(info):
                chosen.append((path, why))
                used.add(path)
                return

    take(lambda i: i["f2p"] and len(i["verdicts"]) > 1,
         "solved, but only after verification rejected the first attempt and the "
         "typed repair instruction sent it back")
    take(lambda i: "overspecified" in i["verdicts"],
         "the over-specification check firing: the test failed, but on claims the "
         "report never made")
    take(lambda i: i["f2p"] is False,
         "a genuine failure, kept because the failure modes are the point")
    take(lambda i: i["f2p"] is True,
         "a clean first-attempt reproduction")
    for path, _ in scored:
        if len(chosen) >= want:
            break
        if path not in used:
            chosen.append((path, "additional run"))
            used.add(path)
    return chosen


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--traces-dir", default="traces")
    ap.add_argument("--out-dir", default="agent-trajectories")
    ap.add_argument("--variant", action="append",
                    default=None, help="defaults to s5, x1 and b1")
    ap.add_argument("--per-variant", type=int, default=3)
    args = ap.parse_args()

    variants = args.variant or ["s5", "x1", "b1"]
    traces_dir = Path(args.traces_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    labels = {
        "s5": "Ratchat, the final system",
        "x1": "the removed experiment — verification by model instead of traceback (it outscores the shipped system; removed for cost and determinism)",
        "b1": "the fair baseline — one general-purpose agent with the same tools",
        "s4": "Ratchat before minimal-claim authoring",
        "demo": "the narrated single-case run",
    }

    lines = [INDEX_HEADER]
    written = 0
    for variant in variants:
        picks = pick(traces_dir, variant, args.per_variant)
        if not picks:
            continue
        lines.append(f"### `{variant}` — {labels.get(variant, variant)}\n")
        for path, why in picks:
            info = summarise(path)
            rel = f"{variant}/{path.stem}.md"
            target = out_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(render_markdown(path))
            written += 1
            verdicts = " → ".join(info["verdicts"]) or "no verdict recorded"
            outcome = {True: "Fail-to-Pass", False: "did not reach Fail-to-Pass",
                       None: "not scored"}[info["f2p"]]
            lines.append(
                f"- [`{path.stem}`]({rel}) — {why}.  \n"
                f"  {info['llm_calls']} model calls, {info['tools']} tool calls, "
                f"verdicts: {verdicts}. Result: {outcome}."
            )
        lines.append("")

    (out_dir / "README.md").write_text("\n".join(lines) + "\n")
    print(f"wrote {written} trajectories and an index to {out_dir}")


if __name__ == "__main__":
    main()
