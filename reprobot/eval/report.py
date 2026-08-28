"""Turn result files into the tables the report is built from.

Two numbers matter beyond the headline rate.

The first is cost: an improvement that triples spend is a trade, not a win, so
every variant is reported with what it cost to run.

The second is the self-verification error rate -- how often the agent believed it
had reproduced the bug when the Fail-to-Pass check disagreed. That is the gap
between "my test failed" and "my test reproduces the bug", and it is the number
this project exists to shrink.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def load(results_dir: Path, split: str) -> list[dict]:
    out = []
    for path in sorted(results_dir.glob(f"{split}_*.json")):
        out.append(json.loads(path.read_text()))
    # Report in pipeline order rather than alphabetically.
    order = {"b0": 0, "b1": 1, "s1": 2, "s2": 3, "s3": 4, "s4": 5}
    return sorted(out, key=lambda s: order.get(s["variant"], 99))


def headline_table(summaries: list[dict]) -> str:
    rows = [
        "| Variant | What it is | F2P solved | F2P rate | Cost (USD) | Mean rounds | Mean wall clock |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for s in summaries:
        mean_rounds = (
            sum(r.get("rounds", 1) for r in s["results"]) / len(s["results"])
            if s["results"] else 0
        )
        rows.append(
            f"| `{s['variant']}` | {s['description']} | "
            f"{s['f2p_solved']}/{s['n_cases']} | {s['f2p_rate']:.0%} | "
            f"${s['total_cost_usd']:.4f} | {mean_rounds:.1f} | "
            f"{s['mean_wall_clock_s']:.0f}s |"
        )
    return "\n".join(rows)


def per_case_matrix(summaries: list[dict]) -> str:
    case_ids = sorted({r["case_id"] for s in summaries for r in s["results"]})
    header = "| Case | " + " | ".join(f"`{s['variant']}`" for s in summaries) + " |"
    sep = "| --- | " + " | ".join("---" for _ in summaries) + " |"
    rows = [header, sep]
    for case_id in case_ids:
        cells = []
        for s in summaries:
            hit = next((r for r in s["results"] if r["case_id"] == case_id), None)
            cells.append("—" if hit is None else ("**pass**" if hit["f2p"] else "fail"))
        rows.append(f"| `{case_id}` | " + " | ".join(cells) + " |")
    return "\n".join(rows)


def failure_breakdown(summary: dict) -> str:
    reasons = Counter(
        r["score_reason"].split(":")[0] if not r["f2p"] else "solved"
        for r in summary["results"]
    )
    lines = [f"| Outcome | Cases |", "| --- | ---: |"]
    for reason, count in reasons.most_common():
        lines.append(f"| `{reason}` | {count} |")
    return "\n".join(lines)


def self_verification_gap(summaries: list[dict]) -> str:
    """How often the agent's own verdict disagreed with the ground truth."""
    rows = [
        "| Variant | Claimed reproduced | Of those, actually F2P | False-confidence rate |",
        "| --- | ---: | ---: | ---: |",
    ]
    for s in summaries:
        claimed = [r for r in s["results"] if r.get("self_reproduces")]
        if not claimed:
            continue
        correct = sum(1 for r in claimed if r["f2p"])
        rate = 1 - (correct / len(claimed))
        rows.append(
            f"| `{s['variant']}` | {len(claimed)} | {correct} | {rate:.0%} |"
        )
    return "\n".join(rows) if len(rows) > 2 else "_No variant reported a self-verdict._"


def build(results_dir: Path, split: str) -> str:
    summaries = load(results_dir, split)
    if not summaries:
        return f"No results found in {results_dir} for split '{split}'."

    parts = [
        f"# Results — `{split}` split\n",
        f"Model: `{summaries[0]['model']}`. "
        f"Cases: {summaries[0]['n_cases']}. "
        "Primary metric: Fail-to-Pass, measured in a sandbox against the real fix "
        "commit, with no model involved in scoring.\n",
        "## Headline comparison\n",
        headline_table(summaries),
        "\n## Per-case outcomes\n",
        per_case_matrix(summaries),
        "\n## Where the final system still fails\n",
        failure_breakdown(summaries[-1]),
        "\n## Self-verification gap\n",
        "The agent decides for itself whether it reproduced the bug. This is how "
        "often that judgement was wrong.\n",
        self_verification_gap(summaries),
    ]
    return "\n".join(parts) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results-dir", default="results")
    ap.add_argument("--split", default="eval")
    ap.add_argument("--out")
    args = ap.parse_args()
    text = build(Path(args.results_dir), args.split)
    if args.out:
        Path(args.out).write_text(text)
        print(f"wrote {args.out}")
    else:
        print(text)


if __name__ == "__main__":
    main()
