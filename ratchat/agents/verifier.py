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

from ratchat.sandbox.run import RunResult

# "tomlkit/items.py:44: in __len__" -- a frame line in pytest's short traceback.
FRAME = re.compile(r"^(?P<path>[^\s:]+\.py):(?P<line>\d+): in (?P<func>\S+)", re.M)

# Kept equal to `artifact.VERDICT_MEANING` by a test, because this is that same
# fact written a second time and it had already drifted from it: `verify` emits
# `reproduced_signature` and the solver emits `overspecified`, and neither was
# listed here. Nothing read this tuple, so nothing caught it.
VERDICTS = (
    "reproduced_exception",
    "reproduced_assertion",
    "reproduced_signature",
    "overspecified",
    "shallow_fail",
    "broken_test",
    "no_fail",
    "timeout",
)

REPRODUCING = {"reproduced_exception", "reproduced_assertion", "reproduced_signature"}

# The message of the exception that ended the run, e.g.
# "CliRunner.__init__() got an unexpected keyword argument 'catch_exceptions'".
EXC_MESSAGE = re.compile(
    r"^E\s+[A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception):\s*(.+)$", re.M
)
QUOTED_IDENT = re.compile(r"['\"`]([A-Za-z_][A-Za-z0-9_]{2,})['\"`]")
BARE_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")

# Words that appear in almost every interpreter message and identify nothing.
MESSAGE_NOISE = {
    "got", "unexpected", "keyword", "argument", "arguments", "object", "type",
    "has", "attribute", "module", "name", "not", "defined", "required",
    "positional", "missing", "takes", "were", "given", "callable", "instance",
    "supported", "operand", "str", "int", "list", "dict", "none", "nonetype",
}


def _message_identifiers(output: str) -> list[str]:
    """Identifiers named by the exception message, most specific first."""
    matches = EXC_MESSAGE.findall(output or "")
    if not matches:
        return []
    message = matches[-1]
    quoted = QUOTED_IDENT.findall(message)
    if quoted:
        return quoted
    return [w for w in BARE_IDENT.findall(message) if w.lower() not in MESSAGE_NOISE]


def failure_is_named_in_report(output: str, issue_text: str) -> str | None:
    """Return the identifier that ties this failure to the report, if any.

    Some bugs *are* a missing or wrong signature. When the fix adds a parameter,
    the correct reproduction calls it and gets a TypeError at the call site, with
    no frame ever entering project code -- which is indistinguishable, by frames
    alone, from the agent inventing an API.

    The report separates them. If the thing the interpreter complained about is
    what the reporter asked for, the test is demonstrating the bug.
    """
    if not issue_text:
        return None
    haystack = re.sub(r"\s+", " ", issue_text).lower()
    for ident in _message_identifiers(output):
        if ident.lower() in haystack:
            return ident
    return None


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


def verify(run: RunResult, test_rel_path: str,
           issue_text: str = "") -> Verdict:
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

    named = failure_is_named_in_report(output, issue_text)
    if named:
        return Verdict(
            "reproduced_signature", exc, source_frames, test_frames,
            f"{exc} names {named!r}, which the report itself asks about, so the "
            "missing or wrong signature is the reported bug rather than a "
            "misused API", run,
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
    from ratchat.agents.common import parse_json_object

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


# --- Over-specification -----------------------------------------------------
#
# Measured on the development split: every case self-verified as reproduced on
# the first attempt, and half of them still failed the Fail-to-Pass check. The
# reason was not that they missed the bug. They caught the bug *and* a pile of
# incidental detail -- invented help text, exact whitespace, a round-trip
# equality the report never mentions -- so they failed at the fix commit too.
#
# That is detectable without ever seeing the fix. A test whose assertions rest
# on strings the reporter never wrote is asserting the agent's imagination, and
# a test with a dozen assertions is no longer a reproduction of one bug.

MAX_REASONABLE_ASSERTIONS = 3
MIN_INTERESTING_LITERAL = 12
ASSERTION_HELPERS = ("validate_", "assert_", "check_")


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


def assertion_profile(test_source: str) -> tuple[int, list[str]]:
    """Count assertions and collect the string literals they depend on."""
    import ast

    try:
        tree = ast.parse(test_source)
    except SyntaxError:
        return 0, []

    count = 0
    literals: list[str] = []

    def collect(node) -> None:
        for sub in ast.walk(node):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                literals.append(sub.value)

    for node in ast.walk(tree):
        if isinstance(node, ast.Assert):
            count += 1
            # Only the condition constrains behaviour. The message after the
            # comma is documentation, and counting it would flag every
            # well-written test that explains itself.
            collect(node.test)
        elif isinstance(node, ast.Call):
            # Projects with table-driven suites assert through helpers rather
            # than the assert statement, so those count too.
            name = ""
            if isinstance(node.func, ast.Attribute):
                name = node.func.attr
            elif isinstance(node.func, ast.Name):
                name = node.func.id
            if name.startswith(ASSERTION_HELPERS):
                count += 1
                collect(node)
    return count, literals


def ungrounded_literals(test_source: str, issue_text: str) -> list[str]:
    """Asserted strings of real length that the reporter never wrote."""
    _, literals = assertion_profile(test_source)
    haystack = _normalise(issue_text)
    out = []
    for literal in literals:
        norm = _normalise(literal)
        if len(norm) < MIN_INTERESTING_LITERAL:
            continue
        if norm in haystack:
            continue
        if norm in out:
            continue
        out.append(norm)
    return out


def overspecification(test_source: str, issue_text: str) -> dict | None:
    """Evidence that a test claims more than the report supports, or None."""
    count, _ = assertion_profile(test_source)
    ungrounded = ungrounded_literals(test_source, issue_text)
    too_many = count > MAX_REASONABLE_ASSERTIONS
    invented = len(ungrounded) >= 2
    if not (too_many or invented):
        return None
    return {
        "assertions": count,
        "ungrounded_literals": ungrounded[:5],
        "too_many": too_many,
        "invented": invented,
    }


REPAIR_INSTRUCTIONS["overspecified"] = (
    "Your test does fail, but it asserts more than the report actually claims, so "
    "it will keep failing even after the bug is fixed. Cut it down to the single "
    "smallest assertion that demonstrates the reported symptom. Do not assert exact "
    "wording, help text, formatting or whitespace unless the report quotes that text "
    "verbatim. If the report says something raises, assert that it no longer raises; "
    "if it says a value is wrong, assert only that one value."
)
