"""Measure how exactly the committed cache reproduces the reported numbers.

The replay claim is only worth making if it is checked, so this checks it rather
than asserting it. For each variant it re-runs the evaluation offline against the
committed cache and compares, case by case, against the result file in `results/`.

A case can diverge for one reason: a prompt in the replay is not byte-identical to
the prompt that was recorded, so its cache key is different and the lookup misses.
That happens where a prompt quotes pytest output, because pytest prints its own
runtime. See REPRODUCTION.md for why that is documented rather than fixed.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path


def replay(variant: str, split: str, model: str, workdir: Path) -> dict:
    tag = "fidelity"
    cmd = [
        sys.executable, "-m", "ratchat.eval.run",
        "--variant", variant, "--split", split, "--model", model,
        "--out-dir", str(workdir), "--traces-dir", str(workdir / "traces"),
        "--memory-dir", str(workdir / "memory"), "--tag", tag,
    ]
    env = {**dict(__import__("os").environ), "RATCHAT_OFFLINE": "1"}
    subprocess.run(cmd, check=True, env=env,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return json.loads((workdir / f"{split}_{variant}{tag}.json").read_text())


def compare(recorded: dict, replayed: dict) -> dict:
    by_id = {r["case_id"]: r for r in replayed["results"]}
    identical, diverged, misses = [], [], []
    for rec in recorded["results"]:
        rep = by_id.get(rec["case_id"])
        if rep is None:
            diverged.append(rec["case_id"])
            continue
        if (rep.get("error") or "").startswith("OfflineCacheMiss"):
            misses.append(rec["case_id"])
        elif rec["test_source"] == rep["test_source"] and rec["f2p"] == rep["f2p"]:
            identical.append(rec["case_id"])
        else:
            diverged.append(rec["case_id"])
    return {
        "n": len(recorded["results"]),
        "identical": identical,
        "cache_miss": misses,
        "diverged": diverged,
        "f2p_recorded": recorded["f2p_solved"],
        "f2p_replayed": replayed["f2p_solved"],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", action="append", required=True)
    ap.add_argument("--split", default="eval")
    ap.add_argument("--model", default="google/gemini-2.5-flash")
    ap.add_argument("--results-dir", default="results")
    ap.add_argument("--out", help="write a markdown table here")
    args = ap.parse_args()

    rows = ["| Variant | Cases reproduced byte-identically | Fail-to-Pass recorded | replayed |",
            "| --- | ---: | ---: | ---: |"]
    detail = []
    with tempfile.TemporaryDirectory() as tmp:
        for variant in args.variant:
            recorded_path = Path(args.results_dir) / f"{args.split}_{variant}.json"
            if not recorded_path.exists():
                print(f"skip {variant}: no {recorded_path}")
                continue
            recorded = json.loads(recorded_path.read_text())
            print(f"replaying {variant} ...", flush=True)
            rep = replay(variant, args.split, args.model, Path(tmp))
            c = compare(recorded, rep)
            rows.append(
                f"| `{variant}` | {len(c['identical'])}/{c['n']} | "
                f"{c['f2p_recorded']} | {c['f2p_replayed']} |"
            )
            if c["cache_miss"]:
                detail.append(f"- `{variant}` cache miss: {', '.join(c['cache_miss'])}")
            if c["diverged"]:
                detail.append(f"- `{variant}` diverged: {', '.join(c['diverged'])}")
            print(rows[-1], flush=True)

    text = "\n".join(rows) + ("\n\n" + "\n".join(detail) if detail else "") + "\n"
    if args.out:
        Path(args.out).write_text(text)
        print(f"wrote {args.out}")
    else:
        print("\n" + text)


if __name__ == "__main__":
    main()
