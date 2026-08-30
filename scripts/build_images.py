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

from ratchat.sandbox.run import build_image, image_exists  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default="data/cases/validated.json")
    ap.add_argument("--repo", action="append", default=[],
                    help="repo_name to build; may be repeated. Default: all of them.")
    ap.add_argument("--force", action="store_true", help="rebuild images that exist")
    args = ap.parse_args()

    cases = json.loads(Path(args.cases).read_text())
    # One image per repository, pinned at the fix commit of its first case, which
    # is what the dataset validated against.
    pins: dict[str, dict] = {}
    for case in sorted(cases, key=lambda c: c["case_id"]):
        pins.setdefault(case["repo_name"], case)

    wanted = args.repo or sorted(pins)
    unknown = [r for r in wanted if r not in pins]
    if unknown:
        print(f"no cases for: {', '.join(unknown)}. Known: {', '.join(sorted(pins))}")
        return 1

    for repo_name in wanted:
        case = pins[repo_name]
        if image_exists(repo_name) and not args.force:
            print(f"have  {repo_name}")
            continue
        print(f"build {repo_name} @ {case['fix_sha'][:10]}")
        build_image(case["repo"], case["fix_sha"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
