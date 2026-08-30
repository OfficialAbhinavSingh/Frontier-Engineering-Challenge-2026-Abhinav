"""Ratchat: the full solution.

The pipeline is deliberately narrow at each step, because the failure this
project is built around -- a test that fails for the wrong reason -- is caused by
an agent guessing while it still has room to guess.

  cartographer (no model)  rank modules and tests against the report, and read
                           the project's real fixtures and import idiom
  locator      (model)     commit to a target module and a sibling test file,
                           with evidence, before any code is written
  author       (model)     write the test with the located source and two real
                           tests from this project in front of it
  verifier     (no model)  run it at the buggy commit and classify *where* it
                           failed, never whether it "worked"
  repair       (model)     re-author under an instruction chosen by that verdict

Every configuration switch here exists so a claim in the changelog can be
measured rather than asserted: each stage can be turned off and the same
evaluation re-run.

The verifier only ever runs at the parent commit. Nothing in this module can
read the fix, which is what keeps the Fail-to-Pass number meaningful.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ratchat.agents.cartographer import build_map, focused_excerpt, sample_tests
from ratchat.agents.common import (
    Budget,
    default_test_dir,
    extract_code,
    issue_block,
    parse_json_object,
    run_candidate,
    test_path_for,
)
from ratchat.agents.memory import RepoMemory
from ratchat.agents.verifier import (
    Verdict,
    overspecification,
    repair_instruction,
    verify,
    verify_with_model,
)
from ratchat.llm.client import LLMClient
from ratchat.repo import RepoView
from ratchat.trace import Trace

LOCATOR_SYSTEM = """You are triaging a bug report in a Python repository.

Decide two things before anyone writes code:
  1. which source file most likely contains the reported behaviour
  2. which existing test file a regression test for it belongs in

Base both on the evidence you are given. Do not guess at files that are not listed.

Reply with one JSON object and nothing else:
{"source_files": ["path/a.py"], "test_file": "tests/test_x.py", "why": "one sentence"}
List at most two source files, most likely first."""

AUTHOR_SYSTEM = """You write regression tests for a Python project.

You are given a bug report and the current, still-buggy source. Write a pytest
test file that fails right now *because of that bug*, and that will pass once the
bug is fixed.

Rules that decide whether your test is any good:
- Trigger the behaviour the reporter describes. Not a similar one.
- Assert the correct expected value -- what the code *should* produce. Never
  assert the buggy value, and never write an unconditional failure.
- Use the project's real API. Match the imports, helpers and fixtures shown in
  the example tests; do not invent names.
- Keep it minimal and self-contained. No network, no sleeps, no large inputs.

Reply with one Python code block containing the complete file, and nothing else."""

# The minimal-claim rules, added after measuring why generated tests failed at the
# fix commit. They did not miss the bug -- they caught it and a great deal else.
MINIMAL_CLAIM_RULES = """
Assert as little as possible:
- Write ONE assertion. If you genuinely need two, you probably need one.
- Assert only what the reporter actually claims. Never assert exact help text,
  error wording, formatting or whitespace unless the report quotes it verbatim.
- If the report says something raises, assert that it stops raising. Do not also
  assert what it returns.
- Do not assert a round-trip or a pretty-printed form unless the report shows
  that exact output.

A test that checks the one reported symptom passes once the bug is fixed. A test
that also checks five details you invented keeps failing forever, and is worth
nothing to the maintainer."""


@dataclass
class SolverConfig:
    """Switches that let each changelog claim be measured instead of asserted."""

    use_map: bool = True
    use_examples: bool = True
    use_typed_repair: bool = True
    use_memory: bool = True
    # The removed experiment: judge the run with a model instead of reading the
    # traceback. Kept switchable so the claim that it lost stays checkable.
    use_llm_verdict: bool = False
    # Authored under the minimal-claim rules, and over-specified tests are sent
    # back for repair instead of being accepted as reproductions.
    use_minimal_claim: bool = False
    # Treat a signature error the report itself names as a reproduction rather
    # than as a misused API.
    use_signature_grounding: bool = False
    max_rounds: int = 3
    budget: Budget = field(default_factory=Budget)


def _locate(case: dict, view: RepoView, client: LLMClient, trace: Trace,
            repo_map, cfg: SolverConfig) -> dict:
    if cfg.use_map:
        evidence = repo_map.brief()
    else:
        # Without the map the locator sees what a general-purpose agent sees:
        # a flat listing, with no signal about relevance or test conventions.
        files = view.list_files()
        evidence = "Files in the repository:\n" + "\n".join(
            f"  {p}" for p in files[:250]
        )

    user = f"{issue_block(case)}\n\n{evidence}"
    trace.agent_start("locator", LOCATOR_SYSTEM, user)
    reply = client.chat(
        [{"role": "system", "content": LOCATOR_SYSTEM},
         {"role": "user", "content": user}],
        max_tokens=600,
    )
    trace.llm_reply("locator", reply.text, reply.usage.to_dict(), reply.from_cache)

    parsed = parse_json_object(reply.text) or {}
    source_files = [p for p in (parsed.get("source_files") or [])
                    if isinstance(p, str) and view.file_exists(p)][:2]
    test_file = parsed.get("test_file")
    if not isinstance(test_file, str) or not view.file_exists(test_file):
        test_file = None

    # The locator can name a file that does not exist. Falling back to the map's
    # top-ranked candidate keeps the pipeline moving on evidence rather than on
    # a hallucinated path.
    if not source_files and repo_map.ranked_modules:
        source_files = [repo_map.ranked_modules[0][0]]
    if not test_file and repo_map.ranked_test_files:
        test_file = repo_map.ranked_test_files[0][0]

    located = {"source_files": source_files, "test_file": test_file,
               "why": parsed.get("why", "")}
    trace.event("located", **located)
    return located


def _author_prompt(case: dict, view: RepoView, located: dict, repo_map,
                   memory: RepoMemory, cfg: SolverConfig, test_rel_path: str,
                   feedback: str | None, previous: str | None) -> str:
    parts = [issue_block(case)]

    for path in located["source_files"]:
        excerpt = focused_excerpt(view, path, case["issue_title"] + "\n" + case["issue_body"])
        parts.append(f"--- current source of {path} (the bug is still present here) ---\n{excerpt}")

    if cfg.use_examples and located.get("test_file"):
        examples = sample_tests(view, located["test_file"], count=2)
        if examples:
            joined = "\n\n".join(examples)
            parts.append(
                f"--- two real tests from {located['test_file']}, "
                f"showing this project's conventions ---\n{joined}"
            )

    if cfg.use_map:
        fixtures = ", ".join(repo_map.fixtures[:20]) or "none"
        idiom = "\n".join(repo_map.import_idiom[:6])
        parts.append(f"--- fixtures available ---\n{fixtures}")
        parts.append(f"--- how this project's tests import it ---\n{idiom}")

    if cfg.use_memory:
        notes = memory.brief()
        if notes:
            parts.append(f"--- {notes}")

    parts.append(f"Your file will be saved as {test_rel_path}.")

    if feedback and previous:
        parts.append(
            f"--- your previous attempt ---\n```python\n{previous}```\n\n"
            f"--- what happened when it ran ---\n{feedback}"
        )
    return "\n\n".join(parts)


def solve(case: dict, view: RepoView, client: LLMClient, trace: Trace,
          memory: RepoMemory, cfg: SolverConfig | None = None) -> dict:
    cfg = cfg or SolverConfig()
    test_dir = default_test_dir(view)
    test_rel_path = test_path_for(view, case["case_id"])
    issue_text = case["issue_title"] + "\n" + case["issue_body"]

    repo_map = build_map(view, issue_text, test_dir)
    trace.event(
        "repo_map",
        top_modules=[p for p, _ in repo_map.ranked_modules[:5]],
        top_tests=[p for p, _ in repo_map.ranked_test_files[:5]],
        fixtures=repo_map.fixtures[:15],
    )

    located = _locate(case, view, client, trace, repo_map, cfg)

    attempts: list[dict] = []
    feedback: str | None = None
    previous: str | None = None
    final_source = ""
    final_verdict = None

    for round_no in range(1, cfg.max_rounds + 1):
        user = _author_prompt(case, view, located, repo_map, memory, cfg,
                              test_rel_path, feedback, previous)
        system = AUTHOR_SYSTEM + (MINIMAL_CLAIM_RULES if cfg.use_minimal_claim else "")
        trace.agent_start(f"author.round{round_no}", system, user)
        reply = client.chat(
            [{"role": "system", "content": system},
             {"role": "user", "content": user}],
        )
        trace.llm_reply(f"author.round{round_no}", reply.text,
                        reply.usage.to_dict(), reply.from_cache)

        source = extract_code(reply.text)
        final_source = source

        trace.tool_call("run_test", {"round": round_no, "path": test_rel_path})
        run = run_candidate(case["repo_name"], case["parent_sha"], test_rel_path, source)
        trace.tool_result("run_test", {
            "outcome": run.outcome,
            "exception_type": run.exception_type,
            "duration_s": run.duration_s,
            "pytest_output": run.stdout_tail[-2000:],
        })

        if cfg.use_llm_verdict:
            verdict = verify_with_model(
                run, test_rel_path, issue_text, source, client, trace
            )
        else:
            verdict = verify(
                run, test_rel_path,
                issue_text if cfg.use_signature_grounding else "",
            )

        # A reproduction that asserts things the report never claimed will fail
        # at the fix commit as well, which scores zero. That is visible here,
        # without looking at the fix.
        if cfg.use_minimal_claim and verdict.reproduces:
            evidence = overspecification(source, issue_text)
            if evidence:
                verdict = Verdict(
                    "overspecified", verdict.exception_type,
                    verdict.source_frames, verdict.test_frames,
                    f"the test failed, but it makes {evidence['assertions']} "
                    f"assertions and {len(evidence['ungrounded_literals'])} of them "
                    f"rest on text the report never contains, so it will keep "
                    f"failing after the bug is fixed",
                    verdict.run,
                )
                trace.event("overspecification", **evidence)

        final_verdict = verdict
        trace.verdict(round_no, verdict.verdict, verdict.to_dict())

        attempts.append({
            "round": round_no,
            "verdict": verdict.verdict,
            "exception_type": verdict.exception_type,
            "reason": verdict.reason,
            "output": run.stdout_tail[-1200:],
            "source": source,
        })

        if verdict.reproduces:
            break

        if cfg.use_typed_repair:
            instruction = repair_instruction(verdict)
        else:
            # The ablation: the agent is told only that it did not work, which is
            # the signal a boolean check can provide.
            instruction = ("Your test did not reproduce the bug. Try again.")
        feedback = (
            f"Verdict: {verdict.verdict}\n"
            f"Why: {verdict.reason}\n"
            f"pytest output:\n{run.stdout_tail[-1500:]}\n\n"
            f"{instruction}"
        )
        previous = source

    lessons = memory.distill(client, case["case_id"], case["issue_title"], attempts)
    if lessons:
        trace.event("memory_write", repo=case["repo_name"], lessons=lessons)

    # Nothing is written to a repository here. The proposal is handed to a human,
    # who decides whether it becomes a commit.
    trace.checkpoint("approval_required", {
        "test_rel_path": test_rel_path,
        "verdict": final_verdict.verdict if final_verdict else None,
        "rounds_used": len(attempts),
    })

    return {
        "test_source": final_source,
        "test_rel_path": test_rel_path,
        "located": located,
        "attempts": [
            {k: v for k, v in a.items() if k != "source"} for a in attempts
        ],
        "rounds": len(attempts),
        "self_verdict": final_verdict.verdict if final_verdict else None,
        "self_reproduces": bool(final_verdict and final_verdict.reproduces),
        "lessons_learned": lessons,
        "usage": client.total.to_dict(),
        "approved": False,
    }
