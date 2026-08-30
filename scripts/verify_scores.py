"""Re-derive every reported Fail-to-Pass number without a model or an API key.

This is the strongest reproducibility claim the project can make, and it is
deliberately independent of the model-response cache.

Every result file records the exact `test_source` the run produced. Scoring that
source is pure: check out the parent commit, run the test, check out the fix
commit, run it again. No model is involved, nothing is sampled, and nothing is
read from the cache. So a reader can take the committed test sources, re-run them
in their own Docker, and confirm every `f2p` flag in `results/` for themselves.

If this reports anything other than a perfect match, a number in the report is
wrong and should not be believed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Run as `python3 scripts/verify_scores.py` from the repository root, which puts
# scripts/ on the path rather than the project, so add the project explicitly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ratchat.eval.run import score_case  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results-dir", default="results")
    ap.add_argument("--split", default="eval")
    ap.add_argument("--cases", default="data/cases/validated.json")
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--out", help="write a markdown table here")
    args = ap.parse_args()

    cases = {c["case_id"]: c for c in json.loads(Path(args.cases).read_text())}
    rows = ["| Result file | Cases | Fail-to-Pass reported | re-derived | Mismatches |",
            "| --- | ---: | ---: | ---: | ---: |"]
    mismatches: list[str] = []

    for path in sorted(Path(args.results_dir).glob(f"{args.split}_*.json")):
        data = json.loads(path.read_text())
        agree = redone = 0
        for record in data["results"]:
            case = cases.get(record["case_id"])
            if case is None:
                mismatches.append(f"{path.name}:{record['case_id']} case missing")
                continue
            scored = score_case(
                case,
                record.get("test_rel_path") or "tests/test_ratchat.py",
                record.get("test_source", ""),
                args.timeout,
            )
            redone += bool(scored["f2p"])
            if bool(scored["f2p"]) == bool(record["f2p"]):
                agree += 1
            else:
                mismatches.append(
                    f"{path.name}:{record['case_id']} "
                    f"reported {record['f2p']} re-derived {scored['f2p']}"
                )
        n = len(data["results"])
        rows.append(f"| `{path.name}` | {n} | {data['f2p_solved']} | {redone} | "
                    f"{n - agree} |")
        print(rows[-1], flush=True)

    text = "\n".join(rows)
    if mismatches:
        text += "\n\n**Mismatches**\n\n" + "\n".join(f"- {m}" for m in mismatches)
    else:
        text += ("\n\nEvery reported Fail-to-Pass flag was re-derived exactly from "
                 "the committed test sources, with no model and no API key.\n")
    text += "\n"
    if args.out:
        Path(args.out).write_text(text)
        print(f"wrote {args.out}")
    else:
        print(text)


if __name__ == "__main__":
    main()
