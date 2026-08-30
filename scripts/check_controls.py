"""Run the metric's controls and fail loudly if any of them is not what it must be.

This is the check worth running on a machine that is not the author's, because
it needs no API key, no model and no committed cache -- only Docker and the
repository. It answers the one question a reader cannot take on trust: does
Fail-to-Pass actually reject a test that reproduces nothing?

    c_gold       the maintainer's own regression test    must score every case
    c_sabotage   a test that always fails                must score zero
    c_vacuous    a test that always passes               must score zero

CI runs this restricted to a single repository so it builds one sandbox image
instead of six. The controls are per-case facts, so a subset is a real check of
the same property -- just a cheaper one.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ratchat.agents.common import Budget  # noqa: E402
from ratchat.eval.run import (  # noqa: E402
    CONTROL_EXPECTATION,
    CONTROLS,
    run_variant,
    split_cases,
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default="data/cases/validated.json")
    ap.add_argument("--split", choices=["dev", "eval", "all"], default="eval")
    ap.add_argument("--only-repo", action="append", default=[])
    ap.add_argument("--repos-dir", default="data/repos")
    ap.add_argument("--timeout", type=int, default=300)
    args = ap.parse_args()

    all_cases = json.loads(Path(args.cases).read_text())
    dev, evaluation = split_cases(all_cases)
    chosen = {"dev": dev, "eval": evaluation, "all": all_cases}[args.split]
    if args.only_repo:
        chosen = [c for c in chosen if c["repo_name"] in set(args.only_repo)]
    if not chosen:
        print(f"no cases for split={args.split} repos={args.only_repo}")
        return 1

    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        scratch = Path(tmp)
        for variant in sorted(CONTROLS):
            summary = run_variant(
                variant, chosen, Path(args.repos_dir), model="none",
                traces_root=scratch / "traces", memory_root=scratch / "memory",
                cache_dir=scratch / "cache", budget=Budget(),
                timeout_s=args.timeout,
            )
            n, solved = summary["n_cases"], summary["f2p_solved"]
            required = n if CONTROL_EXPECTATION[variant] == "all" else 0
            ok = solved == required
            print(f"{'PASS' if ok else 'FAIL'}  {variant:<12} "
                  f"scored {solved}/{n}, required {required}/{n}")
            if not ok:
                failures.append(f"{variant}: scored {solved}/{n}, required {required}/{n}")

            # A control that called a model would not be free to re-run, and the
            # claim that it needs no API key would be false.
            if summary["total_llm_calls"]:
                failures.append(f"{variant}: made {summary['total_llm_calls']} model calls")

    if failures:
        print("\nCONTROLS FAILED — the metric does not do what the report claims:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"\nAll controls behaved as required on {len(chosen)} cases.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
