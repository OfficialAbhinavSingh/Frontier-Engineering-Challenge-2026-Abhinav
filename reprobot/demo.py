"""One case, start to finish, narrated.

This is the view a maintainer would actually have: a bug report goes in, the
pipeline works through it out loud, and a reviewable test comes out with the
evidence attached. It is also the run recorded in the solution video.
"""

from __future__ import annotations

import argparse
import json
import textwrap
from pathlib import Path

from reprobot.agents.memory import RepoMemory
from reprobot.artifact import Proposal, render_report, write_proposal
from reprobot.agents.solver import SolverConfig, solve
from reprobot.eval.run import DEFAULT_MODEL, score_case
from reprobot.llm.client import LLMClient
from reprobot.repo import RepoView
from reprobot.trace import Trace

RULE = "─" * 78

# Mirrors variant s5 in reprobot/eval/run.py -- the shipped system.
#
# Not s6. Signature grounding scored higher overall but lost on the held-out
# subset (4.3/13 against s5's 4.7/13), which is the signature of a rule fitted to
# the case that motivated it. The switch stays available in SolverConfig.
FINAL_CONFIG = SolverConfig(
    use_map=True,
    use_examples=True,
    use_typed_repair=True,
    use_memory=True,
    use_minimal_claim=True,
)


def header(title: str) -> None:
    print(f"\n{RULE}\n {title}\n{RULE}")


def wrap(text: str, width: int = 76, indent: str = "  ") -> str:
    out = []
    for para in (text or "").strip().splitlines():
        out.extend(textwrap.wrap(para, width=width, initial_indent=indent,
                                 subsequent_indent=indent) or [indent])
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default="data/cases/validated.json")
    ap.add_argument("--case-id", help="default: the first case in the eval split")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--repos-dir", default="data/repos")
    ap.add_argument("--approve", action="store_true",
                    help="write the proposed test to disk after review")
    ap.add_argument("--out-dir", default="proposals")
    args = ap.parse_args()

    cases = json.loads(Path(args.cases).read_text())
    if args.case_id:
        case = next((c for c in cases if c["case_id"] == args.case_id), None)
        if case is None:
            raise SystemExit(f"no such case: {args.case_id}")
    else:
        from reprobot.eval.run import split_cases
        _, evaluation = split_cases(cases)
        case = sorted(evaluation, key=lambda c: (c["repo_name"], c["case_id"]))[0]

    header(f"THE BUG REPORT — {case['repo']} issue #{case['issue_number']}")
    print(f"  {case['issue_title']}\n")
    body = case["issue_body"]
    print(wrap(body if len(body) < 1200 else body[:1200] + " …"))
    print(f"\n  Repository is checked out at {case['parent_sha'][:12]}, "
          f"where this bug is still present.")
    print("  The agent is never shown the fix.")

    view = RepoView(Path(args.repos_dir) / case["repo_name"], case["parent_sha"])
    trace = Trace("traces", "demo", case["case_id"])
    client = LLMClient(model=args.model)
    memory = RepoMemory(Path("data/memory/demo"), case["repo_name"], enabled=True)

    header("REPRO-BOT RUNNING")
    print("  cartographer → locator → author → sandbox → verifier → repair\n")
    # The narrated run uses the final configuration, not the library default,
    # so what a reader sees here is the system the results describe.
    result = solve(case, view, client, trace, memory, FINAL_CONFIG)

    for attempt in result["attempts"]:
        print(f"  round {attempt['round']}: {attempt['verdict']}"
              f"  ({attempt['exception_type'] or 'no exception'})")
        print(wrap(attempt["reason"], indent="      "))

    header("PROPOSED TEST")
    print(f"  would be added as {result['test_rel_path']} (new file, nothing else touched)\n")
    print(textwrap.indent(result["test_source"].strip(), "  "))

    header("GROUND TRUTH — Fail-to-Pass check")
    print("  This is the only step that looks at the real fix commit.\n")
    scored = score_case(case, result["test_rel_path"], result["test_source"])
    print(f"  at parent {case['parent_sha'][:12]}: "
          f"{(scored['parent'] or {}).get('outcome')}")
    print(f"  at fix    {case['fix_sha'][:12]}: "
          f"{(scored['fix'] or {}).get('outcome')}")
    print(f"\n  Fail-to-Pass: {'YES' if scored['f2p'] else 'NO'}  ({scored['reason']})")

    usage = result["usage"]
    print(f"\n  {usage['calls']} model calls, "
          f"{usage['prompt_tokens'] + usage['completion_tokens']} tokens, "
          f"${usage['cost_usd']:.4f}")
    print(f"  trajectory: {trace.path}")

    proposal = Proposal(
        case=case,
        test_rel_path=result["test_rel_path"],
        test_source=result["test_source"],
        attempts=result["attempts"],
        verdict=result.get("self_verdict"),
        located=result.get("located", {}),
        usage=result["usage"],
        trace_path=trace.path,
    )

    header("HUMAN CHECKPOINT")
    if args.approve:
        target = write_proposal(proposal, args.out_dir)
        print(f"  Approved. Reviewable bundle written to {target}/\n")
        for item in sorted(target.iterdir()):
            print(f"    {item.name}")
        print("\n  Apply it with:")
        print(f"    git apply {target}/add-test.patch")
    else:
        print("  Not approved, so nothing was written. Repro-Bot never commits.")
        print("  Re-run with --approve to emit the reviewable bundle:")
        print("    the test, a git-applyable patch, the verifier's evidence,")
        print("    the attempts that were rejected, and what is still unverified.\n")
        preview = render_report(proposal).splitlines()
        print("  --- report preview ---")
        for line in preview[:16]:
            print(f"  {line}")
        print(f"  … [{len(preview) - 16} more lines]")


if __name__ == "__main__":
    main()
