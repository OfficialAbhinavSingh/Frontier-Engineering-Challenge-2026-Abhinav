"""Shared pieces between the baselines and the full solver.

Both sides of the comparison must run against exactly the same repository view,
the same sandbox, the same model and the same output contract. Anything they do
not share is a design difference under test; anything they do share is held
constant on purpose, and it lives here.
"""

from __future__ import annotations

import ast
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from ratchat.repo import RepoView
from ratchat.sandbox.run import RunResult, run_test
from ratchat.trace import Trace

CODE_FENCE = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.S)


def looks_like_python_test(block: str) -> bool:
    """Whether a fenced block is plausibly the test file rather than something else."""
    if "def test" not in block and "import " not in block:
        return False
    try:
        ast.parse(block)
    except SyntaxError:
        return False
    return True


def pick_code_block(blocks: list[str]) -> str | None:
    """Choose the block that is actually a test file.

    Taking the longest block outright is wrong: agents quote the pytest output
    back inside a fence, and that transcript is often longer than the test. One
    baseline run submitted a pytest failure report as its test file because of
    exactly that. Prefer blocks that parse as Python and look like a test, and
    only fall back to raw length when none do.
    """
    if not blocks:
        return None
    plausible = [b for b in blocks if looks_like_python_test(b)]
    return max(plausible or blocks, key=len).strip() + "\n"


def extract_code(text: str) -> str:
    """Pull a test file out of a model reply."""
    picked = pick_code_block(CODE_FENCE.findall(text or ""))
    if picked is not None:
        return picked
    return (text or "").strip() + "\n"


def default_test_dir(view: RepoView) -> str:
    """The directory this project actually keeps its tests in.

    Derived from the repository's own layout rather than from the case, so it
    carries no information about where the fix lives.
    """
    dirs = Counter()
    for path in view.test_files():
        if path.endswith(".py") and "/" in path:
            dirs[str(Path(path).parent)] += 1
    if not dirs:
        return "tests"
    return dirs.most_common(1)[0][0]


# Frozen at the project's former name, deliberately. This filename is quoted into
# every author prompt ("Your file will be saved as ..."), and the model cache is
# content-addressed on the prompt text, so renaming it changes all 885 committed
# cache keys at once. That would cost more to regenerate than the project's
# remaining budget and would break the $0 demo replay, in exchange for a cosmetic
# change to a generated filename. Measured before deciding: the string appears in
# 1425 recorded prompts. See "The rename that stopped at the cache" in
# CHANGELOG_IMPROVEMENT.md.
LEGACY_TEST_PREFIX = "test_reprobot_"


def test_path_for(view: RepoView, case_id: str) -> str:
    """A new, previously non-existent path, so the diff can only ever add a file."""
    safe = re.sub(r"[^A-Za-z0-9_]", "_", case_id)
    return f"{default_test_dir(view)}/{LEGACY_TEST_PREFIX}{safe}.py"


@dataclass
class Budget:
    """Hard caps. An agent that cannot finish inside them has failed the case."""

    max_steps: int = 12
    max_test_runs: int = 6
    max_repair_rounds: int = 3


@dataclass
class ToolBox:
    """The tools an agent may call, and the accounting for how it used them."""

    view: RepoView
    repo_name: str
    parent_sha: str
    test_rel_path: str
    trace: Trace
    budget: Budget
    test_runs: int = 0
    calls: Counter = field(default_factory=Counter)

    def spec(self) -> str:
        return (
            "read_file(path, start=null, end=null) -> file contents at the buggy commit\n"
            "list_files(subdir='') -> python files under a directory\n"
            "grep(pattern, glob=null) -> matching lines, with file and line number\n"
            "run_test(source) -> run a candidate test file in a sandbox at the buggy "
            "commit and return its outcome"
        )

    def call(self, name: str, args: dict) -> str:
        self.calls[name] += 1
        self.trace.tool_call(name, args)
        try:
            result = self._dispatch(name, args)
        except Exception as exc:  # a bad tool call is information, not a crash
            result = f"[tool error: {type(exc).__name__}: {exc}]"
        shown = result if len(result) <= 6000 else result[:6000] + "\n[... truncated ...]"
        self.trace.tool_result(name, shown, truncated=len(result) > 6000)
        return shown

    def _dispatch(self, name: str, args: dict) -> str:
        if name == "read_file":
            return self.view.read_file(args["path"], args.get("start"), args.get("end"))
        if name == "list_files":
            files = self.view.list_files(args.get("subdir", ""))
            return "\n".join(files[:400]) or "[no python files]"
        if name == "grep":
            return self.view.grep(args["pattern"], args.get("glob"))
        if name == "run_test":
            return self._run_test(args["source"])
        return f"[unknown tool: {name}]"

    def _run_test(self, source: str) -> str:
        if self.test_runs >= self.budget.max_test_runs:
            return "[test-run budget exhausted]"
        self.test_runs += 1
        result = run_candidate(
            self.repo_name, self.parent_sha, self.test_rel_path, source
        )
        return format_run_result(result)


def run_candidate(repo_name: str, sha: str, test_rel_path: str,
                  source: str) -> RunResult:
    return run_test(repo_name, sha, test_rel_path, source, timeout_s=180)


def format_run_result(result: RunResult) -> str:
    """What an agent is told after running a test.

    It gets the classification and the exception type, not a verdict on whether
    it has succeeded. Deciding that is the verifier's job, and handing it to the
    author agent invites it to argue itself into a false positive.
    """
    return json.dumps(
        {
            "outcome": result.outcome,
            "exception_type": result.exception_type,
            "exit_code": result.exit_code,
            "duration_s": result.duration_s,
            "pytest_output": result.stdout_tail[-2500:],
        },
        indent=2,
    )


FINAL_TEST_FIELD = re.compile(r'"final_test"\s*:\s*"(.*)"\s*[,}]', re.S)


def recover_final_test(text: str) -> str | None:
    """Recover a submitted test from a reply that is not valid JSON.

    Models routinely emit {"final_test": "..."} with real newlines inside the
    string, which is not valid JSON. Rejecting those replies does not measure the
    agent, it measures the parser -- and it penalised the baseline for a protocol
    the solver never has to use, since the solver's author agent answers with a
    plain code block.
    """
    if not text:
        return None

    picked = pick_code_block(CODE_FENCE.findall(text))
    if picked is not None:
        return picked

    match = FINAL_TEST_FIELD.search(text)
    if match:
        raw = match.group(1)
        # Undo JSON string escaping by hand; the value itself is not parseable.
        for escaped, plain in (("\\n", "\n"), ("\\t", "\t"),
                               ('\\"', '"'), ("\\\\", "\\")):
            raw = raw.replace(escaped, plain)
        return raw.strip() + "\n"
    return None


def issue_block(case: dict) -> str:
    return (
        f"Issue #{case['issue_number']}: {case['issue_title']}\n"
        f"Repository: {case['repo']}\n\n"
        f"{case['issue_body']}"
    )


def parse_json_object(text: str) -> dict | None:
    """Recover a JSON object from a model reply that may be wrapped in prose."""
    text = (text or "").strip()
    fenced = re.search(r"```(?:json)?\s*\n(.*?)```", text, re.S)
    if fenced:
        text = fenced.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
