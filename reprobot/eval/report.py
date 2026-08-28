"""Turn result files into the tables the report is built from.

Three things are reported beyond the headline rate, because without them the
headline is not interpretable.

**Range across repetitions.** Fourteen cases means one case is seven percentage
points. A single run is one sample, and a variant has been observed moving by a
full case from a harness change alone, so every repeated variant is reported as
a mean with the range it actually spanned.

**Cost.** An improvement that costs three times as much is a trade, not a win.

**The self-verification gap.** How often the agent believed it had reproduced the
bug when the Fail-to-Pass check disagreed. That is the distance between "my test
failed" and "my test reproduces the bug", and it is the number this project
exists to shrink.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ORDER = {"b0": 0, "b1": 1, "s1": 2, "s2": 3, "s3": 4, "s4": 5, "s5": 6,
         "s6": 7, "x1": 8}

TAG = re.compile(r"_r\d+$")

# Anything a reader must be told rather than left to infer from a table.
FOOTNOTES = {
    "s6": "Post-hoc. The blind spot this fixes was found on the evaluation "
          "split, so this row is not a clean held-out result and is reported "
          "separately from the pre-registered comparison.",
    "x1": "Removed. Kept switchable so the claim can be re-run.",
}


def load(results_dir: Path, split: str) -> dict[str, list[dict]]:
    """Group result files by variant, collecting repeated runs together."""
    runs: dict[str, list[dict]] = defaultdict(list)
    for path in sorted(results_dir.glob(f"{split}_*.json")):
        data = json.loads(path.read_text())
        base = TAG.sub("", data["variant"])
        runs[base].append(data)
    return dict(sorted(runs.items(), key=lambda kv: ORDER.get(kv[0], 99)))


def _stats(entries: list[dict]) -> dict:
    solved = [e["f2p_solved"] for e in entries]
    n = entries[0]["n_cases"]
    costs = [e["total_cost_usd"] for e in entries]
    rounds = [r.get("rounds", 1) for e in entries for r in e["results"]]
    calls = sum(e["total_llm_calls"] for e in entries)
    cached = sum(e["cached_llm_calls"] for e in entries)
    cases = sum(e["n_cases"] for e in entries)
    return {
        "runs": len(entries),
        "n": n,
        "mean": sum(solved) / len(solved),
        "lo": min(solved),
        "hi": max(solved),
        "rate": (sum(solved) / len(solved)) / n if n else 0.0,
        "cost": sum(costs) / len(costs),
        "mean_rounds": sum(rounds) / len(rounds) if rounds else 0,
        "calls_per_case": calls / cases if cases else 0,
        "cached_share": cached / calls if calls else 0,
        "desc": entries[0]["description"],
    }


def headline_table(runs: dict[str, list[dict]]) -> str:
    rows = [
        "| Variant | What it is | Runs | Fail-to-Pass | Rate | Model calls/case | Cost/run |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for variant, entries in runs.items():
        s = _stats(entries)
        if s["runs"] > 1:
            score = f"{s['mean']:.1f}/{s['n']} (range {s['lo']}-{s['hi']})"
        else:
            score = f"{s['mean']:.0f}/{s['n']}"
        mark = " +" if variant in FOOTNOTES else ""
        rows.append(
            f"| `{variant}`{mark} | {s['desc']} | {s['runs']} | {score} | "
            f"{s['rate']:.0%} | {s['calls_per_case']:.1f} | ${s['cost']:.4f} |"
        )
    notes = [f"\n**+ `{v}`** — {FOOTNOTES[v]}" for v in runs if v in FOOTNOTES]
    return "\n".join(rows) + "\n" + "\n".join(notes)


def per_case_matrix(runs: dict[str, list[dict]]) -> str:
    """First run of each variant, so the columns are directly comparable."""
    firsts = {v: entries[0] for v, entries in runs.items()}
    case_ids = sorted({r["case_id"] for e in firsts.values() for r in e["results"]})
    header = "| Case | " + " | ".join(f"`{v}`" for v in firsts) + " |"
    sep = "| --- | " + " | ".join("---" for _ in firsts) + " |"
    rows = [header, sep]
    for case_id in case_ids:
        cells = []
        for entry in firsts.values():
            hit = next((r for r in entry["results"] if r["case_id"] == case_id), None)
            cells.append("—" if hit is None else ("**pass**" if hit["f2p"] else "·"))
        rows.append(f"| `{case_id}` | " + " | ".join(cells) + " |")
    return "\n".join(rows)


def failure_breakdown(entries: list[dict]) -> str:
    reasons: Counter = Counter()
    for entry in entries:
        for r in entry["results"]:
            reasons["solved" if r["f2p"] else r["score_reason"].split(":")[0]] += 1
    total = sum(reasons.values())
    lines = ["| Outcome | Cases | Share |", "| --- | ---: | ---: |"]
    for reason, count in reasons.most_common():
        lines.append(f"| `{reason}` | {count} | {count / total:.0%} |")
    return "\n".join(lines)


def self_verification_gap(runs: dict[str, list[dict]]) -> str:
    rows = [
        "| Variant | Claimed reproduced | Actually Fail-to-Pass | False-confidence rate |",
        "| --- | ---: | ---: | ---: |",
    ]
    any_row = False
    for variant, entries in runs.items():
        claimed = [r for e in entries for r in e["results"] if r.get("self_reproduces")]
        if not claimed:
            continue
        correct = sum(1 for r in claimed if r["f2p"])
        rows.append(
            f"| `{variant}` | {len(claimed)} | {correct} | "
            f"{1 - correct / len(claimed):.0%} |"
        )
        any_row = True
    return "\n".join(rows) if any_row else "_No variant reported a self-verdict._"


def verdict_distribution(entries: list[dict]) -> str:
    verdicts: Counter = Counter()
    for entry in entries:
        for r in entry["results"]:
            for attempt in r.get("attempts") or []:
                verdicts[attempt["verdict"]] += 1
    if not verdicts:
        return "_No verdicts recorded._"
    total = sum(verdicts.values())
    lines = ["| Verdict at the buggy commit | Attempts | Share |",
             "| --- | ---: | ---: |"]
    for verdict, count in verdicts.most_common():
        lines.append(f"| `{verdict}` | {count} | {count / total:.0%} |")
    return "\n".join(lines)


def build(results_dir: Path, split: str) -> str:
    runs = load(results_dir, split)
    if not runs:
        return f"No results found in {results_dir} for split '{split}'."

    first = next(iter(runs.values()))[0]
    final = runs.get("s6") or runs.get("s5") or list(runs.values())[-1]

    return "\n".join([
        f"# Results — `{split}` split\n",
        f"Model: `{first['model']}`. Cases: {first['n_cases']}. "
        "Primary metric: Fail-to-Pass, measured in a sandbox against the real fix "
        "commit, with no model involved in scoring.\n",
        "## Headline comparison\n",
        headline_table(runs),
        "\nModel calls per case is the honest efficiency measure here. The dollar "
        "column is deflated for any variant whose prompts were already in the "
        "committed cache from an earlier run, so it understates what a cold run "
        "costs; the call count is not affected by caching.\n",
        "\n## Per-case outcomes\n",
        "First run of each variant.\n",
        per_case_matrix(runs),
        "\n## What the verifier saw\n",
        "Every attempt the final system made, classified at the buggy commit "
        "with no access to the fix.\n",
        verdict_distribution(final),
        "\n## Where the final system still fails\n",
        failure_breakdown(final),
        "\n## Self-verification gap\n",
        "The agent decides for itself whether it reproduced the bug. This is how "
        "often that judgement was wrong.\n",
        self_verification_gap(runs),
        "",
    ])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results-dir", default="results")
    ap.add_argument("--split", default="eval")
    ap.add_argument("--out")
    args = ap.parse_args()
    text = build(Path(args.results_dir), args.split)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text)
        print(f"wrote {args.out}")
    else:
        print(text)


if __name__ == "__main__":
    main()
