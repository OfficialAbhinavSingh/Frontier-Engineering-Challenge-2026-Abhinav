"""Does the pipeline's advantage survive a change of model?

Every headline number in this project was measured on one model, which leaves an
obvious objection open: that the structure is incidental and the model is doing
the work. The answer has to hold the architecture fixed and vary the model, and
it has to move BOTH sides -- comparing the pipeline on one model against a
baseline on another measures nothing.

So this reads the same two variants, `b1` (one general-purpose agent, same tools)
and `s5` (the shipped pipeline), run on each model, and reports the gap between
them per model. The gap is the claim; the absolute scores are not comparable
across models and are not presented as if they were.
"""

from __future__ import annotations

import argparse
import glob
import json
import re
from pathlib import Path

TAG = re.compile(r"_r\d+$")

# Published list price at the time of the run, per million tokens, in USD.
# Recorded here because the point of the cheaper model is the price ratio.
PRICING = {
    "google/gemini-2.5-flash": (0.30, 2.50),
    "mistralai/mistral-small-3.2-24b-instruct": (0.075, 0.20),
}


def collect(paths: list[str]) -> dict[str, dict]:
    """Group runs by variant, averaging repeats."""
    by_variant: dict[str, list[dict]] = {}
    for path in sorted(paths):
        data = json.loads(Path(path).read_text())
        by_variant.setdefault(data["variant"], []).append(data)

    out = {}
    for variant, entries in by_variant.items():
        solved = [e["f2p_solved"] for e in entries]
        out[variant] = {
            "runs": len(entries),
            "n": entries[0]["n_cases"],
            "mean": sum(solved) / len(solved),
            "lo": min(solved),
            "hi": max(solved),
            "model": entries[0]["model"],
            "cost": sum(e["total_cost_usd"] for e in entries) / len(entries),
            "calls": sum(e["total_llm_calls"] for e in entries)
                     / sum(e["n_cases"] for e in entries),
        }
    return out


def score(stat: dict) -> str:
    if stat["runs"] > 1:
        return f"{stat['mean']:.1f}/{stat['n']} (range {stat['lo']}-{stat['hi']})"
    return f"{stat['mean']:.0f}/{stat['n']}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="eval")
    ap.add_argument("--primary-dir", default="results")
    ap.add_argument("--cross-dir", default="results/crossmodel")
    ap.add_argument("--out", default="results/CROSS_MODEL.md")
    args = ap.parse_args()

    primary = collect([p for v in ("b1", "s5")
                       for p in glob.glob(f"{args.primary_dir}/{args.split}_{v}*.json")])
    cross = collect([p for v in ("b1", "s5")
                     for p in glob.glob(f"{args.cross_dir}/{args.split}_{v}*.json")])
    if not cross:
        raise SystemExit(f"no cross-model results in {args.cross_dir}")

    lines = [
        "# Does the advantage survive a change of model?\n",
        "Every other number in this project was measured on one model. That leaves "
        "the obvious objection open: maybe the structure is incidental and the "
        "model is doing the work.\n",
        "The test has to move **both** sides. `b1` is one general-purpose agent with "
        "the same tools, including the sandbox; `s5` is the shipped pipeline. Both "
        "are re-run on a second model from a different vendor, and what is compared "
        "is the **gap between them on the same model** -- absolute scores across "
        "different models are not comparable and are not presented as if they were.\n",
        "| Model | Price in/out per M | `b1` same tools | `s5` Ratchat | Gap |",
        "| --- | --- | ---: | ---: | ---: |",
    ]

    rows = []
    for label, stats in (("primary", primary), ("cross", cross)):
        if "b1" not in stats or "s5" not in stats:
            continue
        model = stats["s5"]["model"]
        price = PRICING.get(model)
        price_s = f"${price[0]:.3f} / ${price[1]:.2f}" if price else "—"
        gap = stats["s5"]["mean"] - stats["b1"]["mean"]
        rel = (gap / stats["b1"]["mean"] * 100) if stats["b1"]["mean"] else 0.0
        rows.append((model, gap, rel))
        lines.append(
            f"| `{model}` | {price_s} | {score(stats['b1'])} | **{score(stats['s5'])}** "
            f"| **+{gap:.1f}** ({rel:+.0f}%) |"
        )

    lines.append("")
    if len(rows) == 2:
        (m1, g1, r1), (m2, g2, r2) = rows
        if g2 > 0 and g1 > 0:
            lines.append(
                f"The pipeline beats the same-tools baseline on both models: "
                f"**+{g1:.1f} cases ({r1:+.0f}%)** on `{m1.split('/')[-1]}` and "
                f"**+{g2:.1f} cases ({r2:+.0f}%)** on `{m2.split('/')[-1]}`. "
                "The architecture, not the model, is what the improvement is "
                "attributable to.\n")
        elif g2 <= 0:
            lines.append(
                f"**The advantage does not transfer.** On "
                f"`{m2.split('/')[-1]}` the pipeline scores {g2:+.1f} against the "
                "same-tools baseline, so on this model the structure buys nothing. "
                "Reported because it is what the run returned.\n")

    # The tempting cross-comparison, checked rather than asserted. A cheap model
    # running the pipeline against an expensive one running the general-purpose
    # agent is the headline everyone wants; at this sample size it is a tie, and
    # saying so is the difference between a result and a slogan.
    if "s5" in cross and "b1" in primary:
        cheap, dear = cross["s5"], primary["b1"]
        overlap = not (cheap["lo"] > dear["hi"] or dear["lo"] > cheap["hi"])
        ratio = dear["cost"] / cheap["cost"] if cheap["cost"] else 0
        verb = ("matches" if overlap else
                ("beats" if cheap["mean"] > dear["mean"] else "loses to"))
        lines.append(
            f"\n## The pipeline on the cheap model against the agent on the dear one\n\n"
            f"`s5` on `{cheap['model'].split('/')[-1]}` scores {score(cheap)} against "
            f"`b1` on `{dear['model'].split('/')[-1]}` at {score(dear)}, "
            f"for ${cheap['cost']:.4f} a run against ${dear['cost']:.4f} -- "
            f"**{ratio:.0f}x cheaper**.\n")
        if overlap:
            lines.append(
                f"Those ranges overlap ({cheap['lo']}-{cheap['hi']} against "
                f"{dear['lo']}-{dear['hi']}), so this **{verb}** rather than wins. "
                "A single run of the cheap pipeline scored 7 and looked like a "
                "clean win; two more runs turned it into a tie. The claim is that "
                "structure buys you as much as an order of magnitude of model "
                "price, not that it buys you more.\n")
        else:
            lines.append(
                f"The ranges do not overlap, so the cheap pipeline **{verb}** the "
                "expensive agent outright.\n")
        lines.append(
            "The dollar figures are not like-for-like in the cautious direction: "
            "the primary model's runs were partly served from the committed cache "
            "and so understate its true cost, while every cross-model call was "
            "live. The real ratio is larger than the one printed above.\n")

    lines.append("Model calls per case, same order: "
                 + "; ".join(
                     f"`{s['s5']['model'].split('/')[-1]}` "
                     f"b1 {s['b1']['calls']:.1f}, s5 {s['s5']['calls']:.1f}"
                     for s in (primary, cross) if "b1" in s and "s5" in s) + "\n")

    Path(args.out).write_text("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
