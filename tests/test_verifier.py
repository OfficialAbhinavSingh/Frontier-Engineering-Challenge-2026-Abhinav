"""Tests for the typed verdicts.

The whole result rests on this classification being right, so the cases below are
real pytest output shapes rather than invented strings. If `shallow_fail` and
`reproduced_exception` ever collapse into each other, the repair loop starts
giving the opposite advice and the numbers stop meaning anything.
"""

from __future__ import annotations

from ratchat.agents.verifier import repair_instruction, verify
from ratchat.sandbox.run import RunResult, classify

TEST_PATH = "tests/test_reprobot_case.py"


def result(outcome: str, exc: str | None, output: str) -> RunResult:
    return RunResult(outcome, 1, exc, 0.1, output)


def test_exception_from_project_code_is_a_reproduction():
    output = (
        "tests/test_reprobot_case.py:8: in test_len_of_float\n"
        "    len(doc['x'])\n"
        "tomlkit/items.py:44: in __len__\n"
        "    return len(self._value)\n"
        "E   TypeError: object of type 'Float' has no len()\n"
        "FAILED tests/test_reprobot_case.py::test_len_of_float - TypeError: object of type\n"
    )
    verdict = verify(result("failed", "TypeError", output), TEST_PATH)
    assert verdict.verdict == "reproduced_exception"
    assert verdict.reproduces
    assert any("tomlkit/items.py" in frame for frame in verdict.source_frames)


def test_same_exception_raised_only_in_the_test_body_is_shallow():
    """The distinction the project is built on.

    Identical exit code, identical exception type, identical 'the test failed'.
    The only difference is that no frame ever entered the project's code, which
    means the test misused the API instead of exercising the bug.
    """
    output = (
        "tests/test_reprobot_case.py:6: in test_len_of_float\n"
        "    doc.parse_value('x', mode='strict')\n"
        "E   TypeError: parse_value() got an unexpected keyword argument 'mode'\n"
        "FAILED tests/test_reprobot_case.py::test_len_of_float - TypeError: parse_value()\n"
    )
    verdict = verify(result("failed", "TypeError", output), TEST_PATH)
    assert verdict.verdict == "shallow_fail"
    assert not verdict.reproduces
    assert verdict.source_frames == []


def test_assertion_failure_is_a_reproduction_even_with_no_source_frames():
    """A wrong-output bug reproduces as an assertion inside the test itself.

    Requiring a project frame would reject exactly the class of bug that does not
    raise, which is most of them.
    """
    output = (
        "tests/test_reprobot_case.py:9: in test_roundtrip\n"
        "    assert dumps(doc) == expected\n"
        "E   AssertionError: assert 'a = 1\\n\\n' == 'a = 1\\n'\n"
        "FAILED tests/test_reprobot_case.py::test_roundtrip - AssertionError\n"
    )
    verdict = verify(result("failed", "AssertionError", output), TEST_PATH)
    assert verdict.verdict == "reproduced_assertion"
    assert verdict.reproduces


def test_passing_test_reproduces_nothing():
    verdict = verify(RunResult("passed", 0, None, 0.1, "1 passed"), TEST_PATH)
    assert verdict.verdict == "no_fail"
    assert not verdict.reproduces


def test_import_error_is_a_broken_test_not_a_failure():
    verdict = verify(result("infra_error", "ModuleNotFoundError", "E   ModuleNotFoundError: no module named 'tomlkit.parsr'"), TEST_PATH)
    assert verdict.verdict == "broken_test"
    assert not verdict.reproduces


def test_site_packages_frames_do_not_count_as_project_code():
    output = (
        "tests/test_reprobot_case.py:5: in test_x\n"
        "    click.echo(1)\n"
        "/usr/local/lib/python3.12/site-packages/_pytest/python.py:12: in call\n"
        "    raise TypeError()\n"
        "E   TypeError: boom\n"
    )
    verdict = verify(result("failed", "TypeError", output), TEST_PATH)
    assert verdict.verdict == "shallow_fail"


def test_each_non_reproducing_verdict_has_its_own_repair_instruction():
    """The repair advice must differ, or the typed verdict buys nothing."""
    instructions = {}
    for outcome, exc, output in [
        ("passed", None, "1 passed"),
        ("failed", "TypeError", "tests/test_reprobot_case.py:1: in t\nE   TypeError: x\n"),
        ("infra_error", "ImportError", "E   ImportError: x"),
        ("timeout", None, ""),
    ]:
        verdict = verify(result(outcome, exc, output), TEST_PATH)
        instructions[verdict.verdict] = repair_instruction(verdict)
    assert len(set(instructions.values())) == len(instructions)


def test_classify_treats_a_failed_checkout_shaped_exit_as_collection_error():
    """pytest's own exit codes, not guesses about them."""
    assert classify(5, "no tests ran", False)[0] == "no_tests"
    assert classify(2, "!!! Interrupted: 1 error during collection !!!", False)[0] == "collection_error"
    assert classify(0, "3 passed", False)[0] == "passed"
    assert classify(-1, "", True)[0] == "timeout"


def test_a_missing_signature_the_report_names_is_a_reproduction():
    """Some bugs *are* a missing parameter.

    When the fix adds one, the correct reproduction calls it and gets a
    TypeError at the call site, with no frame entering project code. By frames
    alone that is indistinguishable from the agent inventing an API, and
    rejecting it costs a case that was already solved.
    """
    output = (
        "tests/test_reprobot_case.py:39: in test_runner\n"
        "    runner = CliRunner(catch_exceptions=True)\n"
        "E   TypeError: CliRunner.__init__() got an unexpected keyword argument "
        "'catch_exceptions'\n"
    )
    issue = "CliRunner should accept catch_exceptions so it can be set on the runner."
    verdict = verify(result("failed", "TypeError", output), TEST_PATH, issue)
    assert verdict.verdict == "reproduced_signature"
    assert verdict.reproduces


def test_an_invented_parameter_is_still_a_shallow_failure():
    """The same shape, but the report never mentions it."""
    output = (
        "tests/test_reprobot_case.py:6: in test_x\n"
        "    doc.parse_value('x', mode='strict')\n"
        "E   TypeError: parse_value() got an unexpected keyword argument 'mode'\n"
    )
    issue = "Whitespace in dotted keys is not preserved when re-serialising."
    verdict = verify(result("failed", "TypeError", output), TEST_PATH, issue)
    assert verdict.verdict == "shallow_fail"
    assert not verdict.reproduces


def test_signature_grounding_is_off_unless_the_report_is_supplied():
    output = (
        "tests/test_reprobot_case.py:6: in test_x\n"
        "    CliRunner(catch_exceptions=True)\n"
        "E   TypeError: CliRunner.__init__() got an unexpected keyword argument "
        "'catch_exceptions'\n"
    )
    assert verify(result("failed", "TypeError", output), TEST_PATH).verdict == "shallow_fail"


def test_the_proposed_patch_adds_one_file_and_touches_nothing_else():
    """The patch is the part a maintainer applies, so its shape is load-bearing.

    Add-only is what makes the proposal safe to review at a glance: no existing
    test or source file can be modified by it.
    """
    from ratchat.artifact import build_patch

    source = "import pytest\n\n\ndef test_thing():\n    assert 1 == 2\n"
    patch = build_patch("tests/test_reprobot_case.py", source)

    assert patch.startswith("diff --git a/tests/test_reprobot_case.py")
    assert "new file mode 100644" in patch
    assert "--- /dev/null" in patch
    # Every content line is an addition; nothing is removed anywhere.
    body = patch.split("@@")[-1]
    assert all(line.startswith("+") for line in body.splitlines() if line.strip())
    assert "\n-" not in body
    assert f"+1,{len(source.splitlines())} @@" in patch


def test_a_report_states_what_it_has_not_established():
    """A proposal that hides its own limit is worse than useless to a reviewer."""
    from ratchat.artifact import Proposal, render_report

    case = {
        "case_id": "demo__1", "repo": "o/demo", "repo_name": "demo",
        "issue_number": 1, "issue_title": "it breaks", "parent_sha": "a" * 40,
    }
    report = render_report(Proposal(
        case=case, test_rel_path="tests/test_x.py",
        test_source="def test_x():\n    assert False\n",
        attempts=[{"round": 1, "verdict": "reproduced_assertion",
                   "exception_type": "AssertionError", "reason": "r", "output": "o"}],
        verdict="reproduced_assertion", located={}, usage={"calls": 2, "cost_usd": 0.001},
    ))
    assert "Not established" in report
    assert "oracle" in report.lower() or "intended behaviour" in report.lower()
    assert "Reviewer's checklist" in report
