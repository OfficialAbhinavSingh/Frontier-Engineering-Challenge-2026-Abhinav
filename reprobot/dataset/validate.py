"""Validate mined cases by replaying the human's own regression test.

This is the load-bearing step of the whole project. Before Repro-Bot is allowed
to attempt a case, the *maintainer's* test for that case must demonstrate
Fail-to-Pass in our sandbox: fail at the parent commit, pass at the fix commit.

That single check does two jobs at once. It proves the case is a genuine
reproducible bug rather than a refactor or a flaky test, and it proves our
Docker environment can actually execute that repository's suite at that commit.
A case that cannot be validated is dropped, not worked around.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from reprobot.sandbox.run import build_image, image_exists, run_test

ADDED_TEST_DEF = re.compile(r"^\+\s*(?:async )?def (test_[A-Za-z0-9_]+)\s*\(", re.M)
# Not every project adds a new test function. Table-driven suites extend an
# existing one instead, and for those the enclosing function is what git prints
# in the hunk header. Ignoring that class of commit would have silently biased
# the dataset towards projects with one style of test.
ENCLOSING_TEST_DEF = re.compile(
    r"^@@[^@]*@@\s*(?:async )?def (test_[A-Za-z0-9_]+)\s*\(", re.M
)


def git_show(repo_dir: Path, ref: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo_dir), "show", ref],
        capture_output=True, text=True, check=False,
    )
    return proc.stdout


def added_test_names(patch: str) -> list[str]:
    names = ADDED_TEST_DEF.findall(patch)
    if not names:
        names = ENCLOSING_TEST_DEF.findall(patch)
    # Preserve order, drop duplicates.
    seen, out = set(), []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def validate_case(case: dict, repos_dir: Path, timeout_s: int) -> dict:
    """Replay the gold test at both commits and record what happened."""
    repo_name = case["repo_name"]
    repo_dir = repos_dir / repo_name

    names = added_test_names(case["gold_test_patch"])
    if not names:
        return {"valid": False, "reason": "no_added_test_functions"}

    # The gold test may span several files; we validate the first one that yields
    # added test functions, which is the file the regression actually lives in.
    test_path = case["gold_test_files"][0]
    gold_source = git_show(repo_dir, f"{case['fix_sha']}:{test_path}")
    if not gold_source.strip():
        return {"valid": False, "reason": "gold_test_file_unreadable"}

    selector = " or ".join(names)
    at_parent = run_test(
        repo_name, case["parent_sha"], test_path, gold_source,
        timeout_s=timeout_s, extra_pytest_args=("-k", f"'{selector}'"),
    )
    if at_parent.outcome != "failed":
        return {
            "valid": False,
            "reason": f"gold_test_not_failing_at_parent:{at_parent.outcome}",
            "parent": at_parent.to_dict(),
        }

    at_fix = run_test(
        repo_name, case["fix_sha"], test_path, gold_source,
        timeout_s=timeout_s, extra_pytest_args=("-k", f"'{selector}'"),
    )
    if at_fix.outcome != "passed":
        return {
            "valid": False,
            "reason": f"gold_test_not_passing_at_fix:{at_fix.outcome}",
            "parent": at_parent.to_dict(),
            "fix": at_fix.to_dict(),
        }

    return {
        "valid": True,
        "reason": "ok",
        "gold_test_names": names,
        "gold_test_path": test_path,
        # The exception the human test triggers is the bug's signature. We keep it
        # for analysis only -- it is never shown to the agent.
        "gold_failure_type": at_parent.exception_type,
        "parent": at_parent.to_dict(),
        "fix": at_fix.to_dict(),
    }


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default="data/cases/mined.json")
    ap.add_argument("--out", default="data/cases/validated.json")
    ap.add_argument("--repos-dir", default="data/repos")
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--build-missing", action="store_true",
                    help="build any per-repo image that does not exist yet")
    args = ap.parse_args()

    cases = json.loads(Path(args.cases).read_text())
    repos_dir = Path(args.repos_dir)

    if args.build_missing:
        for repo in sorted({c["repo"] for c in cases}):
            name = repo.split("/")[1]
            if image_exists(name):
                continue
            head = subprocess.run(
                ["git", "-C", str(repos_dir / name), "rev-parse", "HEAD"],
                capture_output=True, text=True, check=True,
            ).stdout.strip()
            print(f"building image for {repo} @ {head[:12]}")
            build_image(repo, head)

    kept, dropped = [], []
    for case in cases:
        result = validate_case(case, repos_dir, args.timeout)
        label = "OK " if result["valid"] else "DROP"
        print(f"{label} {case['case_id']:<24} {result['reason']}")
        if result["valid"]:
            case["validation"] = result
            kept.append(case)
        else:
            dropped.append({"case_id": case["case_id"], "reason": result["reason"]})

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(kept, indent=2))
    Path(out.parent / "dropped.json").write_text(json.dumps(dropped, indent=2))
    print(f"\nvalidated {len(kept)}/{len(cases)} cases -> {out}")


if __name__ == "__main__":
    main()
