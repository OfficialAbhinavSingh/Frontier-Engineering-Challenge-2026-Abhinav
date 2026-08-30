"""Build the per-repository sandbox images, and nothing else.

`make validate` builds whatever is missing as a side effect of validating, but
that also mines, replays gold tests and rewrites the dataset. CI and anyone who
only wants to run the controls needs the images alone -- and usually only one of
them, because a control is a per-case fact and one repository checks the same
property as six.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ratchat.sandbox.run import build_image, image_exists, pin_sha_for  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default="data/cases/validated.json")
    ap.add_argument("--repo", action="append", default=[],
                    help="repo_name to build; may be repeated. Default: all of them.")
    ap.add_argument("--repos-dir", default="data/repos")
    ap.add_argument("--force", action="store_true", help="rebuild images that exist")
    args = ap.parse_args()

    cases = json.loads(Path(args.cases).read_text())
    # `repo` is the owner/name the image is built from; any case of a repository
    # carries it.
    repos: dict[str, str] = {}
    for case in sorted(cases, key=lambda c: c["case_id"]):
        repos.setdefault(case["repo_name"], case["repo"])

    wanted = args.repo or sorted(repos)
    unknown = [r for r in wanted if r not in repos]
    if unknown:
        print(f"no cases for: {', '.join(unknown)}. Known: {', '.join(sorted(repos))}")
        return 1

    repos_dir = Path(args.repos_dir)
    for repo_name in wanted:
        if image_exists(repo_name) and not args.force:
            print(f"have  {repo_name}")
            continue
        clone = repos_dir / repo_name
        if not clone.exists():
            print(f"no clone at {clone} -- run `make repos` first")
            return 1
        # The same pin `dataset.validate` uses. Anything else installs a different
        # dependency generation, and the repository's own tests then fail or do
        # not collect -- which is exactly how CI caught this.
        pin = pin_sha_for(repos_dir, repo_name)
        print(f"build {repo_name} @ {pin[:10]}")
        build_image(repos[repo_name], pin)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
