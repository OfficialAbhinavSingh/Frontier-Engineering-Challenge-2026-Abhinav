"""Tests for the typed verdicts.

The whole result rests on this classification being right, so the cases below are
real pytest output shapes rather than invented strings. If `shallow_fail` and
`reproduced_exception` ever collapse into each other, the repair loop starts
giving the opposite advice and the numbers stop meaning anything.
"""

from __future__ import annotations

from reprobot.agents.verifier import repair_instruction, verify
from reprobot.sandbox.run import RunResult, classify

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
