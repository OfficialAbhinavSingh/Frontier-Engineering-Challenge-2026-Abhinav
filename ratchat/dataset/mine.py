"""Mine reproduction cases from real merged bugfix PRs.

A case is only useful if it looks exactly like the situation a maintainer is in:
a natural-language bug report exists, and somewhere ahead of it there is a commit
that both fixes source code and adds a regression test. We recover that pairing
from git history plus the GitHub API, and keep the human-written test aside as
ground truth for harness validation -- never as input to the agent.

Mining is deliberately conservative. Every filter here exists to stop a case from
leaking the answer or from being unreproducible later.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path

PR_IN_SUBJECT = re.compile(r"\(#(\d+)\)\s*$")
# Some projects keep the merge commit's wording instead of squashing.
PR_IN_MERGE = re.compile(r"^Merge pull request #(\d+) ")

# Anything that would hand the agent the fix rather than the symptom.
LEAK_MARKERS = (
    "diff --git",
    "+++ b/",
    "--- a/",
    "```diff",
)

TEST_PATH = re.compile(r"(^|/)tests?/|(^|/)test_[^/]+\.py$|_test\.py$")


@dataclass
class Case:
    case_id: str
    repo: str
    repo_name: str
    fix_sha: str
    parent_sha: str
    pr_number: int
    issue_number: int
    issue_title: str
    issue_body: str
    source_files: list[str]
    gold_test_files: list[str]
    gold_test_patch: str
    commit_date: str
    notes: dict = field(default_factory=dict)


def _git(repo_dir: Path, *args: str) -> str:
    out = subprocess.run(
        ["git", "-C", str(repo_dir), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    return out.stdout


def is_test_file(path: str) -> bool:
    return bool(TEST_PATH.search(path))


def is_python_source(path: str, repo_name: str) -> bool:
    if not path.endswith(".py"):
        return False
    if is_test_file(path):
        return False
    # Setup and packaging files are not where bugs live.
    return Path(path).name not in {"setup.py", "conftest.py", "noxfile.py"}


def candidate_commits(repo_dir: Path, limit: int) -> list[dict]:
    """Commits that fix source and add tests in the same change."""
    # git log --name-only puts a blank line between the header and the file list,
    # so a record separator is the only safe way to split commits apart.
    sep = "\x1f"
    rec = "\x1e"
    raw = _git(
        repo_dir,
        "log",
        f"-{limit}",
        "--no-merges",
        f"--format={rec}%H{sep}%ct{sep}%aI{sep}%s",
        "--name-only",
    )
    out: list[dict] = []
    for block in raw.split(rec):
        block = block.strip("\n")
        if not block:
            continue
        head, _, files_blob = block.partition("\n")
        parts = head.split(sep)
        if len(parts) != 4:
            continue
        sha, _ts, iso, subject = parts
        files = [f for f in files_blob.split("\n") if f.strip()]
        tests = [f for f in files if is_test_file(f) and f.endswith(".py")]
        srcs = [f for f in files if is_python_source(f, repo_dir.name)]
        if not tests or not srcs:
            continue
        m = PR_IN_SUBJECT.search(subject) or PR_IN_MERGE.match(subject)
        out.append(
            {
                "sha": sha,
                "date": iso,
                "subject": subject,
                # None means the subject does not name a PR. The number can still
                # be recovered from the API, which is what a project that neither
                # squashes nor keeps merge wording requires -- and excluding those
                # projects silently biased the dataset towards one merge style.
                "pr": int(m.group(1)) if m else None,
                "tests": tests,
                "sources": srcs,
            }
        )
    return out


def pr_for_commit(repo: str, sha: str) -> int | None:
    """Ask GitHub which pull request introduced a commit."""
    proc = subprocess.run(
        ["gh", "api", f"repos/{repo}/commits/{sha}/pulls",
         "--jq", ".[0].number"],
        capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        return None
    text = proc.stdout.strip()
    return int(text) if text.isdigit() else None


GRAPHQL_QUERY = """
query($owner:String!, $name:String!, $number:Int!) {
  repository(owner:$owner, name:$name) {
    pullRequest(number:$number) {
      number
      closingIssuesReferences(first: 5) {
        nodes { number title body }
      }
    }
  }
}
"""


def linked_issue(repo: str, pr_number: int) -> dict | None:
    """Return the single issue this PR closes, or None."""
    owner, name = repo.split("/")
    proc = subprocess.run(
        [
            "gh", "api", "graphql",
            "-f", f"query={GRAPHQL_QUERY}",
            "-F", f"owner={owner}",
            "-F", f"name={name}",
            "-F", f"number={pr_number}",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None
    pr = (data.get("data") or {}).get("repository", {}).get("pullRequest")
    if not pr:
        return None
    nodes = pr["closingIssuesReferences"]["nodes"]
    # Exactly one linked issue keeps the task unambiguous.
    if len(nodes) != 1:
        return None
    return nodes[0]


def body_is_usable(body: str | None) -> tuple[bool, str]:
    if not body:
        return False, "empty"
    text = body.strip()
    if len(text) < 100:
        return False, "too_short"
    if len(text) > 8000:
        return False, "too_long"
    low = text.lower()
    for marker in LEAK_MARKERS:
        if marker in low:
            return False, f"leaks_fix:{marker}"
    return True, "ok"


def test_only_patch(repo_dir: Path, sha: str, test_files: list[str]) -> str:
    return _git(repo_dir, "show", sha, "--", *test_files)


def mine_repo(repo: str, repo_dir: Path, limit: int, want: int,
              max_lookups: int = 250) -> list[Case]:
    cases: list[Case] = []
    rejected: dict[str, int] = {}
    lookups = 0

    for cand in candidate_commits(repo_dir, limit):
        if len(cases) >= want:
            break
        if cand["pr"] is None:
            # Each recovery is an API call, so it is capped rather than unbounded.
            if lookups >= max_lookups:
                rejected["pr_lookup_budget"] = rejected.get("pr_lookup_budget", 0) + 1
                continue
            lookups += 1
            cand["pr"] = pr_for_commit(repo, cand["sha"])
            if cand["pr"] is None:
                rejected["no_pr_for_commit"] = rejected.get("no_pr_for_commit", 0) + 1
                continue
        issue = linked_issue(repo, cand["pr"])
        if issue is None:
            rejected["no_linked_issue"] = rejected.get("no_linked_issue", 0) + 1
            continue
        ok, why = body_is_usable(issue.get("body"))
        if not ok:
            rejected[why] = rejected.get(why, 0) + 1
            continue
        parent = _git(repo_dir, "rev-parse", f"{cand['sha']}^").strip()
        if not parent:
            rejected["no_parent"] = rejected.get("no_parent", 0) + 1
            continue
        repo_name = repo.split("/")[1]
        cases.append(
            Case(
                case_id=f"{repo_name}__{issue['number']}",
                repo=repo,
                repo_name=repo_name,
                fix_sha=cand["sha"],
                parent_sha=parent,
                pr_number=cand["pr"],
                issue_number=issue["number"],
                issue_title=issue["title"],
                issue_body=issue["body"].strip(),
                source_files=cand["sources"],
                gold_test_files=cand["tests"],
                gold_test_patch=test_only_patch(repo_dir, cand["sha"], cand["tests"]),
                commit_date=cand["date"],
                notes={"subject": cand["subject"]},
            )
        )
    print(f"[{repo}] kept={len(cases)} rejected={rejected}")
    return cases


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", action="append", required=True,
                    help="owner/name, may be repeated")
    ap.add_argument("--repos-dir", default="data/repos")
    ap.add_argument("--out", default="data/cases/mined.json")
    ap.add_argument("--limit", type=int, default=1200,
                    help="how many commits back to scan per repo")
    ap.add_argument("--want", type=int, default=12,
                    help="max cases to keep per repo")
    ap.add_argument("--max-lookups", type=int, default=250,
                    help="cap on API calls used to recover PR numbers per repo")
    args = ap.parse_args()

    all_cases: list[Case] = []
    for repo in args.repo:
        repo_dir = Path(args.repos_dir) / repo.split("/")[1]
        if not repo_dir.exists():
            print(f"[{repo}] missing clone at {repo_dir}, skipping")
            continue
        all_cases.extend(mine_repo(repo, repo_dir, args.limit, args.want,
                                   args.max_lookups))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps([asdict(c) for c in all_cases], indent=2))
    print(f"wrote {len(all_cases)} candidate cases -> {out}")


if __name__ == "__main__":
    main()
