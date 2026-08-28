"""Run a variant over the case set and score it.

Scoring is the one place in this project that is allowed to look at the fix
commit. Everything upstream -- the agents, the tools, the verifier -- sees only
the parent commit, where the bug is still present. Keeping that boundary in a
single module is what makes the headline number trustworthy.

Fail-to-Pass is deliberately strict and needs no judgement:

    the generated test must FAIL at the parent commit  (it demonstrates the bug)
    and PASS at the fix commit                         (the fix resolves it)

A test that always fails is caught by the second condition. A test that never
fails is caught by the first. There is nothing to grade and nothing to argue
with.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from collections import defaultdict
from pathlib import Path

from reprobot.agents.baselines import run_b0, run_b1
from reprobot.agents.common import Budget
from reprobot.agents.memory import RepoMemory
from reprobot.agents.solver import SolverConfig, solve
from reprobot.agents.verifier import verify
from reprobot.llm.client import LLMClient
from reprobot.repo import RepoView
from reprobot.sandbox.run import run_test
from reprobot.trace import Trace

DEFAULT_MODEL = "google/gemini-2.5-flash"

# Each variant is one row of the improvement changelog. They differ only in the
# switches below, so any difference in the score is attributable to that switch.
VARIANTS: dict[str, dict] = {
    "b0": {"kind": "baseline", "desc": "one prompt, no tools, no execution"},
    "b1": {"kind": "baseline", "desc": "one general-purpose agent with tools and a test runner"},
    "s1": {
        "kind": "solver",
        "desc": "structured pipeline with sandbox verification and a repair loop",
        "cfg": dict(use_map=False, use_examples=False, use_typed_repair=False, use_memory=False),
    },
    "s2": {
        "kind": "solver",
        "desc": "adds the deterministic repo map and in-repo example tests",
        "cfg": dict(use_map=True, use_examples=True, use_typed_repair=False, use_memory=False),
    },
    "s3": {
        "kind": "solver",
        "desc": "adds failure-class-specific repair instructions",
        "cfg": dict(use_map=True, use_examples=True, use_typed_repair=True, use_memory=False),
    },
    "s4": {
        "kind": "solver",
        "desc": "adds cross-case repository memory (full Repro-Bot)",
        "cfg": dict(use_map=True, use_examples=True, use_typed_repair=True, use_memory=True),
    },
    "s5": {
        "kind": "solver",
        "desc": "adds minimal-claim authoring and over-specification repair (full Repro-Bot)",
        "cfg": dict(use_map=True, use_examples=True, use_typed_repair=True,
                    use_memory=True, use_minimal_claim=True),
    },
    # Ran, measured, removed. Same pipeline as s5 with the deterministic verifier
    # swapped for a model asked "did this reproduce the bug?".
    "x1": {
        "kind": "solver",
        "desc": "REMOVED: model-judged verification instead of traceback analysis",
        "cfg": dict(use_map=True, use_examples=True, use_typed_repair=True,
                    use_memory=True, use_minimal_claim=True, use_llm_verdict=True),
    },
}


def split_cases(cases: list[dict], dev_fraction: float = 0.25) -> tuple[list, list]:
    """Stratified dev/eval split, fixed before any result was seen.

    Within each repository, cases are sorted by id and the first few become the
    development set. The split is a pure function of the case ids, so it cannot
    drift as results come in, and it is reproducible by anyone with the dataset.
    """
    by_repo: dict[str, list[dict]] = defaultdict(list)
    for case in cases:
        by_repo[case["repo_name"]].append(case)

    dev, evaluation = [], []
    for repo in sorted(by_repo):
        ordered = sorted(by_repo[repo], key=lambda c: c["case_id"])
        n_dev = max(1, math.ceil(len(ordered) * dev_fraction)) if len(ordered) > 2 else 1
        dev.extend(ordered[:n_dev])
        evaluation.extend(ordered[n_dev:])
    return dev, evaluation


def score_case(case: dict, test_rel_path: str, test_source: str,
               timeout_s: int = 300) -> dict:
    """The Fail-to-Pass check. The only code permitted to touch the fix commit."""
    if not test_source.strip():
        return {"f2p": False, "reason": "empty_test", "parent": None, "fix": None}

    at_parent = run_test(case["repo_name"], case["parent_sha"], test_rel_path,
                         test_source, timeout_s=timeout_s)
    verdict = verify(at_parent, test_rel_path)

    if at_parent.outcome != "failed":
        return {
            "f2p": False,
            "reason": f"did_not_fail_at_parent:{at_parent.outcome}",
            "verdict": verdict.verdict,
            "parent": at_parent.to_dict(),
            "fix": None,
        }

    at_fix = run_test(case["repo_name"], case["fix_sha"], test_rel_path,
                      test_source, timeout_s=timeout_s)
    passed = at_fix.outcome == "passed"
    return {
        "f2p": passed,
        "reason": "ok" if passed else f"did_not_pass_at_fix:{at_fix.outcome}",
        "verdict": verdict.verdict,
        "parent": at_parent.to_dict(),
        "fix": at_fix.to_dict(),
    }


def run_variant(variant: str, cases: list[dict], repos_dir: Path, model: str,
                traces_root: Path, memory_root: Path, cache_dir: Path,
                budget: Budget, timeout_s: int, temperature: float = 0.0,
                tag: str = "") -> dict:
    spec = VARIANTS[variant]
    results = []
    started = time.time()

    # Memory is reset per run so two runs of the same variant are comparable.
    memories: dict[str, RepoMemory] = {}
    for repo_name in {c["repo_name"] for c in cases}:
        mem = RepoMemory(memory_root / variant, repo_name,
                         enabled=spec.get("cfg", {}).get("use_memory", False))
        mem.reset()
        memories[repo_name] = mem

    # Fixed order, so memory accumulates identically on every run.
    for case in sorted(cases, key=lambda c: (c["repo_name"], c["case_id"])):
        case_started = time.time()
        view = RepoView(repos_dir / case["repo_name"], case["parent_sha"])
        trace = Trace(traces_root, variant + tag, case["case_id"])
        client = LLMClient(model=model, cache_dir=cache_dir,
                           temperature=temperature)

        trace.event("case_start", repo=case["repo"], issue=case["issue_number"],
                    parent_sha=case["parent_sha"], variant=variant,
                    variant_desc=spec["desc"], model=model)

        try:
            if variant == "b0":
                produced = run_b0(case, view, client, trace)
            elif variant == "b1":
                produced = run_b1(case, view, client, trace, budget)
            else:
                cfg = SolverConfig(budget=budget, **spec["cfg"])
                produced = solve(case, view, client, trace,
                                 memories[case["repo_name"]], cfg)
            error = None
        except Exception as exc:  # a variant crash is a result, not a stop
            produced = {"test_source": "", "test_rel_path": "", "usage": client.total.to_dict()}
            error = f"{type(exc).__name__}: {exc}"
            trace.event("variant_error", error=error)

        scored = score_case(case, produced.get("test_rel_path") or "tests/test_reprobot.py",
                            produced.get("test_source", ""), timeout_s)
        trace.event("scored", **{k: v for k, v in scored.items()
                                 if k in ("f2p", "reason", "verdict")})

        record = {
            "case_id": case["case_id"],
            "repo": case["repo"],
            "variant": variant,
            "f2p": scored["f2p"],
            "score_reason": scored["reason"],
            "verdict_at_parent": scored.get("verdict"),
            "self_reproduces": produced.get("self_reproduces"),
            "rounds": produced.get("rounds", 1),
            "usage": produced.get("usage", {}),
            "wall_clock_s": round(time.time() - case_started, 1),
            "error": error,
            "test_source": produced.get("test_source", ""),
            "test_rel_path": produced.get("test_rel_path", ""),
            "attempts": produced.get("attempts", []),
        }
        trace.finish({k: v for k, v in record.items() if k != "test_source"})
        results.append(record)

        mark = "PASS" if scored["f2p"] else "fail"
        print(f"  [{variant}] {case['case_id']:<22} {mark:<5} "
              f"{scored['reason']:<34} {record['wall_clock_s']}s")

    solved = sum(1 for r in results if r["f2p"])
    summary = {
        "variant": variant,
        "tag": tag,
        "temperature": temperature,
        "description": spec["desc"],
        "model": model,
        "n_cases": len(results),
        "f2p_solved": solved,
        "f2p_rate": round(solved / len(results), 4) if results else 0.0,
        "total_cost_usd": round(sum(r["usage"].get("cost_usd", 0.0) for r in results), 4),
        "total_llm_calls": sum(r["usage"].get("calls", 0) for r in results),
        "cached_llm_calls": sum(r["usage"].get("cached_calls", 0) for r in results),
        "mean_wall_clock_s": round(
            sum(r["wall_clock_s"] for r in results) / len(results), 1) if results else 0,
        "wall_clock_total_s": round(time.time() - started, 1),
        "results": results,
    }
    return summary


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", action="append", required=True,
                    choices=sorted(VARIANTS), help="may be repeated")
    ap.add_argument("--cases", default="data/cases/validated.json")
    ap.add_argument("--split", choices=["dev", "eval", "all"], default="eval")
    ap.add_argument("--repos-dir", default="data/repos")
    ap.add_argument("--out-dir", default="results")
    ap.add_argument("--traces-dir", default="traces")
    ap.add_argument("--memory-dir", default="data/memory")
    ap.add_argument("--cache-dir", default="data/cache/llm")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--max-steps", type=int, default=12)
    ap.add_argument("--max-test-runs", type=int, default=6)
    ap.add_argument("--limit", type=int, default=0, help="run only the first N cases")
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--tag", default="",
                    help="suffix for result files and traces, used for repeat runs")
    args = ap.parse_args()

    all_cases = json.loads(Path(args.cases).read_text())
    dev, evaluation = split_cases(all_cases)
    chosen = {"dev": dev, "eval": evaluation, "all": all_cases}[args.split]
    if args.limit:
        chosen = sorted(chosen, key=lambda c: (c["repo_name"], c["case_id"]))[:args.limit]

    budget = Budget(max_steps=args.max_steps, max_test_runs=args.max_test_runs)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"model={args.model} split={args.split} cases={len(chosen)}")
    for variant in args.variant:
        print(f"\n=== {variant}: {VARIANTS[variant]['desc']} ===")
        summary = run_variant(
            variant, chosen, Path(args.repos_dir), args.model,
            Path(args.traces_dir), Path(args.memory_dir), Path(args.cache_dir),
            budget, args.timeout, args.temperature, args.tag,
        )
        path = out_dir / f"{args.split}_{variant}{args.tag}.json"
        path.write_text(json.dumps(summary, indent=2))
        print(f"  -> {summary['f2p_solved']}/{summary['n_cases']} "
              f"({summary['f2p_rate']:.0%})  ${summary['total_cost_usd']}  -> {path}")


if __name__ == "__main__":
    main()
