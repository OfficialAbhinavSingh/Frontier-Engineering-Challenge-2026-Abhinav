"""The thing a maintainer actually receives.

A verified test that only exists in a terminal is not a deliverable. What a
maintainer can act on is a patch they can apply, evidence they can check, and an
honest account of what was and was not established.

So a proposal carries four things: the test, a git-applyable patch that adds it
and touches nothing else, the verifier's evidence from the buggy commit, and the
attempts that were rejected on the way. The rejected attempts are included on
purpose -- they are the difference between a reviewer trusting the result and a
reviewer having to redo the work.

It also states its own limits. The pipeline can establish that a test fails at
the buggy commit and why; it cannot establish that the value being asserted is
the one a fix will produce, because that needs an oracle it does not have. A
report that quietly omits that is worse than useless to the person signing it
off.
"""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path

VERDICT_MEANING = {
    "reproduced_exception": (
        "the project's own code raised the error -- traceback frames enter "
        "project source, so the failure is in the library, not in the test"
    ),
    "reproduced_assertion": (
        "an assertion about an observed value failed, which is the shape a "
        "wrong-output bug takes"
    ),
    "reproduced_signature": (
        "the call failed on a name the report itself asks about, so the missing "
        "or wrong signature is the reported bug"
    ),
    "shallow_fail": (
        "the test failed without reaching project code, which usually means the "
        "API was called incorrectly"
    ),
    "overspecified": (
        "the test failed, but on more claims than the report makes, so it would "
        "keep failing after a fix"
    ),
    "broken_test": "the test could not run at all",
    "no_fail": "the test passed, so it demonstrates nothing",
    "timeout": "the test did not finish",
}


def blob_sha1(content: str) -> str:
    """Git's object id for a blob, so the patch header is real rather than faked."""
    data = content.encode("utf-8")
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def build_patch(test_rel_path: str, source: str) -> str:
    """A unified diff that adds one new file and changes nothing else.

    Add-only is not a formatting preference. It is what makes the proposal safe
    to apply: a reviewer can see at a glance that no existing test or source file
    is touched.
    """
    if not source.endswith("\n"):
        source += "\n"
    lines = source.split("\n")[:-1]
    body = "\n".join(f"+{line}" for line in lines)
    return (
        f"diff --git a/{test_rel_path} b/{test_rel_path}\n"
        f"new file mode 100644\n"
        f"index 0000000..{blob_sha1(source)[:7]}\n"
        f"--- /dev/null\n"
        f"+++ b/{test_rel_path}\n"
        f"@@ -0,0 +1,{len(lines)} @@\n"
        f"{body}\n"
    )


@dataclass
class Proposal:
    case: dict
    test_rel_path: str
    test_source: str
    attempts: list[dict]
    verdict: str | None
    located: dict
    usage: dict
    trace_path: Path | None = None

    @property
    def accepted(self) -> bool:
        return self.verdict in (
            "reproduced_exception", "reproduced_assertion", "reproduced_signature"
        )


def _evidence_block(attempt: dict) -> str:
    verdict = attempt.get("verdict", "unknown")
    meaning = VERDICT_MEANING.get(verdict, "")
    out = [f"**Verdict: `{verdict}`** — {meaning}.", ""]
    if attempt.get("exception_type"):
        out.append(f"Exception: `{attempt['exception_type']}`")
        out.append("")
    output = (attempt.get("output") or "").strip()
    if output:
        out.append("````")
        out.append(output[-1200:])
        out.append("````")
    return "\n".join(out)


def render_report(proposal: Proposal) -> str:
    case = proposal.case
    final = proposal.attempts[-1] if proposal.attempts else {}
    rejected = proposal.attempts[:-1] if len(proposal.attempts) > 1 else []

    status = (
        "A reproduction was established." if proposal.accepted
        else "**No reproduction was established.** This proposal is included so the "
             "attempts can be reviewed, not because it is ready to apply."
    )

    parts = [
        f"# Reproduction for {case['repo']}#{case['issue_number']}",
        "",
        f"> {case['issue_title']}",
        "",
        f"{status}",
        "",
        "| | |",
        "| --- | --- |",
        f"| Repository | `{case['repo']}` |",
        f"| Issue | #{case['issue_number']} |",
        f"| Commit tested | `{case['parent_sha'][:12]}` |",
        f"| Adds | `{proposal.test_rel_path}` (new file) |",
        f"| Files modified | none |",
        f"| Attempts | {len(proposal.attempts)} |",
        "",
        "## The test",
        "",
        "```python",
        proposal.test_source.strip(),
        "```",
        "",
        "## Evidence at the reported commit",
        "",
        "Run in an offline container at "
        f"`{case['parent_sha'][:12]}`, where the reported behaviour is still present.",
        "",
        _evidence_block(final) if final else "_No run recorded._",
        "",
        "## How to check this yourself",
        "",
        "```bash",
        f"git clone https://github.com/{case['repo']}.git && cd {case['repo_name']}",
        f"git checkout {case['parent_sha']}",
        "pip install -e . && pip install pytest",
        f"git apply add-test.patch",
        f"python -m pytest {proposal.test_rel_path} -q    # expected: fails",
        "```",
        "",
    ]

    if rejected:
        parts += [
            "## Attempts that were rejected",
            "",
            "Included so a reviewer can see what was ruled out rather than "
            "re-deriving it.",
            "",
        ]
        for attempt in rejected:
            parts += [
                f"### Attempt {attempt.get('round')} — `{attempt.get('verdict')}`",
                "",
                f"{attempt.get('reason', '').strip()}",
                "",
            ]

    parts += [
        "## What this does and does not establish",
        "",
        "**Established, by execution:** the test runs against the reported commit "
        "and fails there, and the verifier classified *where* it failed — the "
        "verdict above is read from the traceback, not asserted.",
        "",
        "**Not established:** that the value this test asserts is the one a correct "
        "fix will produce. Confirming that requires knowing the intended behaviour, "
        "and the only statement of intent available is the report itself. This is "
        "the single most common way a generated reproduction is wrong, so it is "
        "the thing to check first.",
        "",
        "**Reviewer's checklist**",
        "",
        "- [ ] The test triggers the behaviour the reporter actually described",
        "- [ ] The asserted expected value is what the library *should* return",
        "- [ ] The test asserts one thing, not several incidental ones",
        "- [ ] It belongs in this file, and follows the project's conventions",
        "",
        "---",
        "",
        f"Generated by Ratchat. {proposal.usage.get('calls', 0)} model calls, "
        f"${proposal.usage.get('cost_usd', 0):.4f}. "
        f"Nothing was committed or pushed; this proposal required explicit approval "
        f"to be written.",
    ]
    return "\n".join(parts) + "\n"


def write_proposal(proposal: Proposal, out_dir: Path | str = "proposals") -> Path:
    """Write the reviewable bundle. Only ever called after explicit approval."""
    target = Path(out_dir) / proposal.case["case_id"]
    target.mkdir(parents=True, exist_ok=True)

    (target / "REPRODUCTION.md").write_text(render_report(proposal))
    (target / "add-test.patch").write_text(
        build_patch(proposal.test_rel_path, proposal.test_source)
    )
    test_file = target / Path(proposal.test_rel_path).name
    test_file.write_text(proposal.test_source)

    if proposal.trace_path and Path(proposal.trace_path).exists():
        shutil.copy(proposal.trace_path, target / "trajectory.jsonl")
    return target
