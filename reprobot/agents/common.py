"""Shared pieces between the baselines and the full solver.

Both sides of the comparison must run against exactly the same repository view,
the same sandbox, the same model and the same output contract. Anything they do
not share is a design difference under test; anything they do share is held
constant on purpose, and it lives here.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from reprobot.repo import RepoView
from reprobot.sandbox.run import RunResult, run_test
from reprobot.trace import Trace

CODE_FENCE = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.S)


def extract_code(text: str) -> str:
    """Pull a test file out of a model reply.

    Models wrap code in fences most of the time and prose around it some of the
    time. Taking the longest fenced block is more reliable than taking the first,
    because explanatory snippets tend to be short and the real file tends to be
    long.
    """
    blocks = CODE_FENCE.findall(text or "")
    if blocks:
        return max(blocks, key=len).strip() + "\n"
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


def test_path_for(view: RepoView, case_id: str) -> str:
    """A new, previously non-existent path, so the diff can only ever add a file."""
    safe = re.sub(r"[^A-Za-z0-9_]", "_", case_id)
    return f"{default_test_dir(view)}/test_reprobot_{safe}.py"


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
