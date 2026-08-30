"""Controls that bound the metric from both sides, with no model involved.

A score is only worth reading if you know what it does on inputs whose correct
answer is already known. These three variants supply that. None of them calls a
model, so they cost nothing and return the same thing on every machine.

    c_gold       the maintainer's own regression test    -> the ceiling
    c_sabotage   a test that always fails                -> must score zero
    c_vacuous    a test that always passes               -> must score zero

The two floors matter because Fail-to-Pass is a conjunction, and each control
removes one half of it. `c_sabotage` satisfies "fails at the parent" and nothing
else; `c_vacuous` satisfies "passes at the fix" and nothing else. If either
scored above zero the metric would be reporting agreement with one condition as
if it were evidence, and every number in the report would be inflated.

`c_gold` is the other end. The dataset admits a case only after the maintainer's
test is replayed at both commits, but that check runs in `dataset.validate`,
which is a different code path from the scorer used for the headline. Running
gold back through `eval.run.score_case` closes that gap: it measures the scorer
rather than trusting it, and it establishes the ceiling as a measured 27/27
instead of an assumed one.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

# A single failing assertion. It reaches no project code at all, which is
# exactly the point: it is what "the test failed" looks like with no evidence
# behind it.
SABOTAGE_SOURCE = '''\
def test_sabotage():
    """Always fails, and reproduces nothing."""
    assert False, "this test fails unconditionally"
'''

VACUOUS_SOURCE = '''\
def test_vacuous():
    """Always passes, and reproduces nothing."""
    assert True
'''


def _git_show(repo_dir: Path, ref: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo_dir), "show", ref],
        capture_output=True, text=True, check=False,
    )
    return proc.stdout


def produce_control(variant: str, case: dict, repos_dir: Path) -> dict:
    """Return the same shape the agents return, built without a model."""
    if variant == "c_sabotage":
        return {
            "test_source": SABOTAGE_SOURCE,
            "test_rel_path": "tests/test_ratchat_control.py",
            "usage": {},
        }
    if variant == "c_vacuous":
        return {
            "test_source": VACUOUS_SOURCE,
            "test_rel_path": "tests/test_ratchat_control.py",
            "usage": {},
        }
    if variant == "c_gold":
        # The path the dataset validated, read straight out of the fix commit.
        # Written back to its original path so the project's own conftest and
        # fixtures resolve exactly as they do for the maintainer.
        test_path = case["validation"]["gold_test_path"]
        source = _git_show(repos_dir / case["repo_name"],
                           f"{case['fix_sha']}:{test_path}")
        # Select the tests the fix commit added. The file also contains every
        # sibling test that predates the fix, and those are not the reproduction
        # under measurement -- running them whole measures the file's health.
        # That is not hypothetical: on `rich__3577`, three unrelated tests in
        # `tests/test_ansi.py` are already red at the fix commit, so the
        # unfiltered file scores zero while the added test itself passes.
        names = case["validation"]["gold_test_names"]
        selector = " or ".join(names)
        return {
            "test_source": source,
            "test_rel_path": test_path,
            "extra_pytest_args": ("-k", f"'{selector}'"),
            "usage": {},
        }

    raise ValueError(f"not a control variant: {variant}")
