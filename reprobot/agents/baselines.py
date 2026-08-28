"""The two baselines the solver is measured against.

B0 is the naive floor: paste the bug report and the file listing into a model and
use whatever test comes back. It is what people actually do, and it is the reason
this problem looks easy until you check the results.

B1 is the fair baseline: one general-purpose agent, the same model, the same
tools the solver gets -- including the ability to run the test in the sandbox --
and the same budget, driven by a single generic instruction. B1 exists so that no
part of the reported improvement can be attributed to simply giving the agent a
test runner. Every gain over B1 has to come from how the work is organised.
"""

from __future__ import annotations

import json

from reprobot.agents.common import (
    Budget,
    ToolBox,
    extract_code,
    issue_block,
    parse_json_object,
    test_path_for,
)
from reprobot.llm.client import LLMClient
from reprobot.repo import RepoView
from reprobot.trace import Trace

B0_SYSTEM = """You are helping a maintainer reproduce a reported bug.
Write a single pytest test file that fails because of the bug described in the issue.
Reply with one Python code block and nothing else."""

B1_SYSTEM = """You are an autonomous agent working in a Python repository.

Your goal: write a pytest test file that FAILS at the current commit because of the
bug described in the issue, and that would PASS once the bug is fixed.

You have these tools:
{tools}

Reply with a single JSON object and nothing else. Either call a tool:
  {{"thought": "...", "tool": "<name>", "args": {{...}}}}
or finish:
  {{"thought": "...", "final_test": "<complete python file source>"}}

You have at most {max_steps} steps. Use them as you see fit."""


def run_b0(case: dict, view: RepoView, client: LLMClient, trace: Trace) -> dict:
    """One prompt, one reply, no execution."""
    test_rel_path = test_path_for(view, case["case_id"])
    source_files = view.list_files()
    listing = "\n".join(source_files[:300])

    user = (
        f"{issue_block(case)}\n\n"
        f"Python files in the repository:\n{listing}\n\n"
        f"Write the test file. It will be saved as {test_rel_path}."
    )
    trace.agent_start("b0", B0_SYSTEM, user)
    reply = client.chat([
        {"role": "system", "content": B0_SYSTEM},
        {"role": "user", "content": user},
    ])
    trace.llm_reply("b0", reply.text, reply.usage.to_dict(), reply.from_cache)

    return {
        "test_source": extract_code(reply.text),
        "test_rel_path": test_rel_path,
        "steps": 1,
        "test_runs": 0,
        "usage": client.total.to_dict(),
    }


def run_b1(case: dict, view: RepoView, client: LLMClient, trace: Trace,
           budget: Budget | None = None) -> dict:
    """A single general-purpose agent with tools, including the sandbox."""
    budget = budget or Budget()
    test_rel_path = test_path_for(view, case["case_id"])
    tools = ToolBox(
        view=view,
        repo_name=case["repo_name"],
        parent_sha=case["parent_sha"],
        test_rel_path=test_rel_path,
        trace=trace,
        budget=budget,
    )
    system = B1_SYSTEM.format(tools=tools.spec(), max_steps=budget.max_steps)
    user = (
        f"{issue_block(case)}\n\n"
        f"The test file will be saved as {test_rel_path}.\n"
        f"Begin."
    )
    trace.agent_start("b1", system, user)

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    last_test = ""
    steps = 0

    for step in range(budget.max_steps):
        steps = step + 1
        reply = client.chat(messages)
        trace.llm_reply("b1", reply.text, reply.usage.to_dict(), reply.from_cache)
        messages.append({"role": "assistant", "content": reply.text})

        action = parse_json_object(reply.text)
        if action is None:
            # A cheap model will occasionally answer in prose. Treat that as a
            # malformed action and say so, rather than silently ending the run.
            messages.append({
                "role": "user",
                "content": "That was not a JSON object. Reply with exactly one JSON "
                           "object: either a tool call or final_test.",
            })
            continue

        if "final_test" in action:
            last_test = extract_code(action["final_test"])
            break

        tool_name = action.get("tool")
        if not tool_name:
            messages.append({
                "role": "user",
                "content": 'Missing "tool" and "final_test". Provide one of them.',
            })
            continue

        args = action.get("args") or {}
        if tool_name == "run_test" and "source" in args:
            last_test = extract_code(args["source"])
        result = tools.call(tool_name, args)
        messages.append({"role": "user", "content": f"Tool result:\n{result}"})

    return {
        "test_source": last_test,
        "test_rel_path": test_rel_path,
        "steps": steps,
        "test_runs": tools.test_runs,
        "tool_calls": dict(tools.calls),
        "usage": client.total.to_dict(),
    }
