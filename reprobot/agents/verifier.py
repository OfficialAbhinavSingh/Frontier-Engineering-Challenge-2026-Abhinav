"""Typed verification of a candidate reproduction.

The central claim of this project is that "the test failed" is not evidence that
the bug was reproduced. A test can fail because the agent called a function that
does not exist, mistyped an argument, or asserted something unrelated. All of
those look identical to a boolean check, and all of them would be scored as
progress by a naive repair loop -- which then spends its remaining budget
polishing a test that was never measuring the bug.

So the verifier does not return pass or fail. It reads the pytest traceback and
decides *where* the failure happened, which is the part that carries meaning:

  reproduced_exception  the code under test raised; frames enter project source
  reproduced_assertion  an assertion about a value failed inside the test itself
  shallow_fail          it blew up in the test body without ever reaching the
                        project's code -- almost always a misused API
  broken_test           import, syntax or fixture problem; the test never ran
  no_fail               the test passed, so it does not reproduce anything
  timeout               it hung

Each verdict routes to a different repair instruction, because "you called an
API that does not exist" and "your test passed" require opposite corrections.
The verifier never sees the fix commit; it only ever runs at the buggy one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from reprobot.sandbox.run import RunResult

# "tomlkit/items.py:44: in __len__" -- a frame line in pytest's short traceback.
FRAME = re.compile(r"^(?P<path>[^\s:]+\.py):(?P<line>\d+): in (?P<func>\S+)", re.M)

VERDICTS = (
    "reproduced_exception",
    "reproduced_assertion",
    "shallow_fail",
    "broken_test",
    "no_fail",
    "timeout",
)

REPRODUCING = {"reproduced_exception", "reproduced_assertion"}


@dataclass
class Verdict:
    verdict: str
    exception_type: str | None
    source_frames: list[str]
    test_frames: list[str]
    reason: str
    run: RunResult

    @property
    def reproduces(self) -> bool:
        return self.verdict in REPRODUCING

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "exception_type": self.exception_type,
            "source_frames": self.source_frames[:8],
            "test_frames": self.test_frames[:8],
            "reason": self.reason,
        }


def _split_frames(output: str, test_rel_path: str) -> tuple[list[str], list[str]]:
    source_frames, test_frames = [], []
    test_name = test_rel_path.split("/")[-1]
    for match in FRAME.finditer(output):
        path = match.group("path")
        frame = f"{path}:{match.group('line')} in {match.group('func')}"
        if path.endswith(test_name) or "/site-packages/" in path or path.startswith("/usr/"):
            test_frames.append(frame)
        else:
            source_frames.append(frame)
    return source_frames, test_frames


def verify(run: RunResult, test_rel_path: str) -> Verdict:
    output = run.stdout_tail
    source_frames, test_frames = _split_frames(output, test_rel_path)
    exc = run.exception_type

    if run.outcome == "timeout":
        return Verdict("timeout", exc, source_frames, test_frames,
                       "the test did not finish inside the time limit", run)

    if run.outcome == "passed":
        return Verdict("no_fail", None, source_frames, test_frames,
                       "the test passed at the buggy commit, so it does not "
                       "demonstrate the reported behaviour", run)

    if run.outcome in ("collection_error", "infra_error", "no_tests"):
        return Verdict("broken_test", exc, source_frames, test_frames,
                       "the test could not be collected or ran into an "
                       "import, syntax or fixture problem before exercising "
                       "the reported behaviour", run)

    # From here the test ran and failed. The question is where.
    if exc in (None, "AssertionError", "Failed"):
        return Verdict(
            "reproduced_assertion", exc, source_frames, test_frames,
            "an assertion about the observed value failed, which is what a "
            "wrong-output bug looks like", run,
        )

    if source_frames:
        return Verdict(
            "reproduced_exception", exc, source_frames, test_frames,
            f"{exc} was raised from inside the project's own code "
            f"({source_frames[0]})", run,
        )

    return Verdict(
        "shallow_fail", exc, source_frames, test_frames,
        f"{exc} was raised in the test body without any frame entering the "
        "project's code, so the test is most likely misusing the API rather "
        "than exercising the bug", run,
    )


REPAIR_INSTRUCTIONS = {
    "broken_test": (
        "Your test could not run at all. Fix the import, syntax or fixture problem "
        "first. Check the real module layout and the real fixture names before "
        "rewriting: read the file you are importing from, do not guess its "
        "contents. Keep the test's intent unchanged."
    ),
    "shallow_fail": (
        "Your test failed, but the traceback never entered the project's own code, "
        "which means you are almost certainly calling the API incorrectly rather "
        "than triggering the bug. Read the function you are calling and check its "
        "real signature and return type, then rewrite the test so the failure comes "
        "from the project's behaviour and not from your call."
    ),
    "no_fail": (
        "Your test passed, so it does not reproduce anything. The bug is present at "
        "this commit, so your test is not exercising the reported path. Re-read the "
        "report for the exact input and the exact condition, and make the assertion "
        "check the specific behaviour the reporter says is wrong. Do not weaken the "
        "test to force a failure -- it must pass once the bug is fixed."
    ),
    "timeout": (
        "Your test did not finish. Remove any loop, network access or large input, "
        "and reproduce the bug with the smallest possible case."
    ),
}


def repair_instruction(verdict: Verdict) -> str:
    return REPAIR_INSTRUCTIONS.get(
        verdict.verdict,
        "Improve the test so that it fails because of the reported bug.",
    )


# --- The experiment that was removed -------------------------------------

LLM_VERIFIER_SYSTEM = """You are checking whether a generated test actually
reproduces a reported bug.

You are given the bug report, the test, and the pytest output from running it
against the code that still contains the bug.

Answer one question: did this test fail *because of the reported bug*?

Reply with one JSON object and nothing else:
{"reproduced": true or false, "why": "one sentence"}"""


def verify_with_model(run: RunResult, test_rel_path: str, issue_text: str,
                      test_source: str, client, trace=None) -> Verdict:
    """Ask a model whether the bug was reproduced, instead of reading the traceback.

    This is the obvious way to build the verifier and it is the version that was
    tried and dropped. It is kept in the tree because the changelog claims it lost,
    and a reader should be able to re-run it rather than take that on trust.

    Structurally it cannot do better than the deterministic check on the one
    distinction that matters: whether a frame entered the project's own code is a
    fact in the traceback, and asking a model to infer it introduces an opinion
    where a fact was already available.
    """
    from reprobot.agents.common import parse_json_object

    if run.outcome == "passed":
        return verify(run, test_rel_path)
    if run.outcome == "timeout":
        return verify(run, test_rel_path)

    user = (
        f"--- bug report ---\n{issue_text}\n\n"
        f"--- the test ---\n{test_source}\n\n"
        f"--- pytest output at the buggy commit ---\n{run.stdout_tail[-2500:]}"
    )
    if trace is not None:
        trace.agent_start("llm_verifier", LLM_VERIFIER_SYSTEM, user)
    reply = client.chat(
        [{"role": "system", "content": LLM_VERIFIER_SYSTEM},
         {"role": "user", "content": user}],
        max_tokens=300,
    )
    if trace is not None:
        trace.llm_reply("llm_verifier", reply.text, reply.usage.to_dict(),
                        reply.from_cache)

    parsed = parse_json_object(reply.text) or {}
    reproduced = bool(parsed.get("reproduced"))
    why = str(parsed.get("why", ""))[:300]
    source_frames, test_frames = _split_frames(run.stdout_tail, test_rel_path)

    return Verdict(
        "reproduced_assertion" if reproduced else "no_fail",
        run.exception_type, source_frames, test_frames,
        f"model verdict: {why}", run,
    )
