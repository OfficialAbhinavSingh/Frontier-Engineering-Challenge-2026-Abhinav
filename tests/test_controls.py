"""The controls are only worth publishing if their expected values are enforced.

These tests read the committed control results and assert the two floors scored
exactly zero and the ceiling scored everything. A control that quietly drifts is
worse than no control at all: it still appears in the report as evidence.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ratchat.eval.controls import SABOTAGE_SOURCE, VACUOUS_SOURCE, produce_control
from ratchat.eval.run import CONTROL_EXPECTATION, CONTROLS, VARIANTS

RESULTS = Path("results")


def _load(split: str, variant: str) -> dict:
    path = RESULTS / f"{split}_{variant}.json"
    if not path.exists():
        pytest.skip(f"{path} not generated yet")
    return json.loads(path.read_text())


@pytest.mark.parametrize("split", ["eval", "dev"])
@pytest.mark.parametrize("variant", sorted(CONTROLS))
def test_controls_score_what_they_must(split: str, variant: str) -> None:
    data = _load(split, variant)
    n, solved = data["n_cases"], data["f2p_solved"]
    required = n if CONTROL_EXPECTATION[variant] == "all" else 0
    assert solved == required, (
        f"{split}/{variant} scored {solved}/{n}, must be {required}/{n}"
    )


@pytest.mark.parametrize("split", ["eval", "dev"])
def test_the_two_floors_fail_for_different_reasons(split: str) -> None:
    """Each floor must break a different half of the Fail-to-Pass conjunction.

    If both failed the same way, only one condition would be under test and the
    other would be unmeasured.
    """
    sabotage = _load(split, "c_sabotage")
    vacuous = _load(split, "c_vacuous")

    assert all(r["score_reason"].startswith("did_not_pass_at_fix")
               for r in sabotage["results"])
    assert all(r["score_reason"].startswith("did_not_fail_at_parent")
               for r in vacuous["results"])


def test_controls_call_no_model() -> None:
    """A control that spent money would not be reproducible for free."""
    for split in ("eval", "dev"):
        for variant in sorted(CONTROLS):
            data = _load(split, variant)
            assert data["total_llm_calls"] == 0
            assert data["total_cost_usd"] == 0.0


def test_control_sources_are_what_they_claim(tmp_path: Path) -> None:
    case = {"repo_name": "click", "fix_sha": "HEAD",
            "validation": {"gold_test_path": "x.py", "gold_test_names": ["test_a"]}}

    sabotage = produce_control("c_sabotage", case, tmp_path)
    assert sabotage["test_source"] == SABOTAGE_SOURCE
    assert "assert False" in sabotage["test_source"]
    assert sabotage.get("extra_pytest_args", ()) == ()

    vacuous = produce_control("c_vacuous", case, tmp_path)
    assert vacuous["test_source"] == VACUOUS_SOURCE
    assert "assert True" in vacuous["test_source"]

    # Gold is selected down to the tests the fix commit added, so the score
    # reflects the reproduction rather than the health of the whole file.
    gold = produce_control("c_gold", case, tmp_path)
    assert gold["extra_pytest_args"] == ("-k", "'test_a'")


def test_controls_are_excluded_from_the_comparison() -> None:
    """Controls must never appear as a row in the improvement table."""
    from ratchat.eval.report import ORDER

    assert CONTROLS == {"c_gold", "c_sabotage", "c_vacuous"}
    for variant in CONTROLS:
        assert VARIANTS[variant]["kind"] == "control"
        assert ORDER[variant] > max(ORDER[v] for v in VARIANTS if v not in CONTROLS)
