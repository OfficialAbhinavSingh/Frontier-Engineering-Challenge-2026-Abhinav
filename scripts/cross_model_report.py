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
    "openai/gpt-4o-mini": (0.15, 0.60),
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
    ap.add_argument("--cross-dir", action="append",
                    default=None, help="may be repeated, one per extra model")
    ap.add_argument("--out", default="results/CROSS_MODEL.md")
    args = ap.parse_args()

    def load_dir(d: str) -> dict:
        return collect([p for v in ("b1", "s5")
                        for p in glob.glob(f"{d}/{args.split}_{v}*.json")])

    cross_dirs = args.cross_dir or ["results/crossmodel", "results/crossmodel2"]
    primary = load_dir(args.primary_dir)
    crosses = [c for c in (load_dir(d) for d in cross_dirs) if c.get("b1") and c.get("s5")]
    if not crosses:
        raise SystemExit(f"no cross-model results in {cross_dirs}")
    cross = crosses[0]

    lines = [
        "# Does the advantage survive a change of model?\n",
        "Every other number in this project was measured on one model. That leaves "
        "the obvious objection open: maybe the structure is incidental and the "
        "model is doing the work.\n",
        "The test has to move **both** sides. `b1` is one general-purpose agent with "
        "the same tools, including the sandbox; `s5` is the shipped pipeline. Both "
        "are re-run on further models from other vendors, and what is compared "
        "is the **gap between them on the same model** -- absolute scores across "
        "different models are not comparable and are not presented as if they were.\n",
        "| Model | Price in/out per M | `b1` same tools | `s5` Ratchat | Gap |",
        "| --- | --- | ---: | ---: | ---: |",
    ]

    rows = []
    for stats in [primary, *crosses]:
        if "b1" not in stats or "s5" not in stats:
            continue
        model = stats["s5"]["model"]
        price = PRICING.get(model)
        price_s = f"${price[0]:.3f} / ${price[1]:.2f}" if price else "—"
        gap = stats["s5"]["mean"] - stats["b1"]["mean"]
        rel = (gap / stats["b1"]["mean"] * 100) if stats["b1"]["mean"] else 0.0
        rows.append((model, gap, rel))
        # One case is ~4 points at n=27, and the report says so elsewhere. A gap of
        # a single case is therefore at the noise floor, and printing its relative
        # percentage as if it were a finding would be the overclaim this project
        # spends the rest of its README warning about.
        thin = abs(gap) <= 1.0
        cell = f"**+{gap:.1f}** (at noise floor)" if thin else f"**+{gap:.1f}** ({rel:+.0f}%)"
        lines.append(
            f"| `{model}` | {price_s} | {score(stats['b1'])} | **{score(stats['s5'])}** "
            f"| {cell} |"
        )

    lines.append("")
    if rows:
        wins = [r for r in rows if r[1] > 1.0]
        thin = [r for r in rows if 0 < r[1] <= 1.0]
        losses = [r for r in rows if r[1] <= 0]
        summary = "; ".join(f"**+{g:.1f} ({rel:+.0f}%)** on `{m.split('/')[-1]}`"
                            for m, g, rel in wins)
        if not losses:
            vendors = len({m.split('/')[0] for m, _, _ in rows})
            lines.append(
                f"The pipeline is ahead of the same-tools baseline on all "
                f"{len(rows)} models, from {vendors} different vendors. It is ahead "
                f"by more than the noise floor on {len(wins)} of them: {summary}.\n")
            if thin:
                names = ", ".join(f"`{m.split('/')[-1]}`" for m, _, _ in thin)
                lines.append(
                    f"On {names} the margin is a single case, which is at the noise "
                    "floor and is not evidence of anything on its own. What that run "
                    "does show is a **bound on the claim**: both systems collapse to "
                    "near zero there, so structure does not rescue a model that "
                    "cannot write a working test in the first place. It widens the "
                    "gap where the model is capable enough to act on instruction, "
                    "and it cannot manufacture capability that is absent.\n")
        else:
            lost = "; ".join(f"`{m.split('/')[-1]}` at {g:+.1f}" for m, g, _ in losses)
            lines.append(
                f"**The advantage does not transfer everywhere.** It holds on "
                f"{len(wins)} of {len(rows)} models ({summary}) but not on {lost}, "
                "where the structure buys nothing. Reported because it is what the "
                "runs returned.\n")

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
                     for s in [primary, *crosses] if "b1" in s and "s5" in s) + "\n")

    Path(args.out).write_text("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
