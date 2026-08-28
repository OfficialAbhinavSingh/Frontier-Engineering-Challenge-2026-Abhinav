"""Tests for the parts of the pipeline that decide what counts as evidence.

Two things here would quietly corrupt every downstream number if they broke: a
case whose issue body contains the fix, and a dev/eval split that moves between
runs.
"""

from __future__ import annotations

from reprobot.agents.common import extract_code, parse_json_object
from reprobot.dataset.mine import body_is_usable, is_python_source, is_test_file
from reprobot.dataset.validate import added_test_names
from reprobot.eval.run import split_cases


def test_issue_bodies_containing_a_patch_are_rejected():
    """A report that quotes the diff hands the agent the answer."""
    leaking = "It crashes.\n\n```diff\n--- a/x.py\n+++ b/x.py\n-  return 1\n+  return 2\n```\n" + "x" * 100
    ok, why = body_is_usable(leaking)
    assert not ok
    assert why.startswith("leaks_fix")


def test_short_and_empty_bodies_are_rejected():
    assert body_is_usable("")[0] is False
    assert body_is_usable("broken")[1] == "too_short"
    assert body_is_usable("x" * 9000)[1] == "too_long"


def test_a_normal_report_is_accepted():
    body = (
        "When I call len() on a Float item parsed from a document, it raises "
        "TypeError instead of returning the length of its string form. This used "
        "to work in the previous release and it breaks my serialiser."
    )
    assert body_is_usable(body) == (True, "ok")


def test_test_and_source_paths_are_told_apart():
    assert is_test_file("tests/test_items.py")
    assert is_test_file("jsonschema/tests/test_validators.py")
    assert is_test_file("src/foo_test.py")
    assert not is_test_file("tomlkit/items.py")

    assert is_python_source("tomlkit/items.py", "tomlkit")
    assert not is_python_source("tests/test_items.py", "tomlkit")
    assert not is_python_source("setup.py", "tomlkit")
    assert not is_python_source("README.md", "tomlkit")


def test_gold_tests_are_found_when_a_commit_adds_a_new_test():
    patch = "@@ -1,3 +1,8 @@\n+def test_float_len():\n+    assert True\n"
    assert added_test_names(patch) == ["test_float_len"]


def test_gold_tests_are_found_when_a_commit_extends_an_existing_one():
    """Table-driven suites edit a test instead of adding one.

    Only looking for added definitions silently biased the dataset towards
    projects that write tests one way.
    """
    patch = (
        "@@ -120,6 +120,7 @@ def test_starrocks_table_function(self):\n"
        "         self.validate_identity(\"SELECT 1\")\n"
        "+        self.validate_identity(\"SELECT TABLE(x)\")\n"
    )
    assert added_test_names(patch) == ["test_starrocks_table_function"]


def test_a_new_definition_wins_over_the_enclosing_one():
    patch = (
        "@@ -10,3 +10,7 @@ def test_existing(self):\n"
        "+def test_added():\n"
        "+    assert True\n"
    )
    assert added_test_names(patch) == ["test_added"]


def make_case(repo: str, n: int) -> dict:
    return {"case_id": f"{repo}__{n}", "repo_name": repo, "repo": f"o/{repo}"}


def test_the_split_is_stratified_and_stable():
    cases = [make_case("tomlkit", n) for n in (562, 543, 542, 439)] + \
            [make_case("click", n) for n in (2263, 2644, 2703)]
    dev_a, eval_a = split_cases(cases)
    dev_b, eval_b = split_cases(list(reversed(cases)))

    # Input order must not change the split, or two runs are not comparable.
    assert {c["case_id"] for c in dev_a} == {c["case_id"] for c in dev_b}
    assert {c["case_id"] for c in eval_a} == {c["case_id"] for c in eval_b}

    # Every repository is represented on both sides.
    assert {c["repo_name"] for c in dev_a} == {"tomlkit", "click"}
    assert {c["repo_name"] for c in eval_a} == {"tomlkit", "click"}

    # And no case is in both.
    assert not ({c["case_id"] for c in dev_a} & {c["case_id"] for c in eval_a})


def test_code_is_extracted_from_a_reply_that_also_contains_prose():
    reply = (
        "Here is a short snippet:\n```python\nx = 1\n```\n"
        "and here is the actual file:\n"
        "```python\nimport pytest\n\n\ndef test_thing():\n    assert False\n```\n"
        "Hope that helps."
    )
    code = extract_code(reply)
    assert code.startswith("import pytest")
    assert "Hope that helps" not in code


def test_json_is_recovered_from_a_reply_wrapped_in_prose():
    assert parse_json_object('Sure!\n```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_object('{"a": [1, 2]}') == {"a": [1, 2]}
    assert parse_json_object("no json here") is None
