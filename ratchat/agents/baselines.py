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

from ratchat.agents.common import (
    Budget,
    ToolBox,
    extract_code,
    issue_block,
    parse_json_object,
    recover_final_test,
    test_path_for,
)
from ratchat.llm.client import LLMClient
from ratchat.repo import RepoView
from ratchat.trace import Trace

B0_SYSTEM = """You are helping a maintainer reproduce a reported bug.
Write a single pytest test file that fails because of the bug described in the issue.
Reply with one Python code block and nothing else."""

B1_SYSTEM = """You are an autonomous agent working in a Python repository.

Your goal: write a pytest test file that FAILS at the current commit because of the
bug described in the issue, and that would PASS once the bug is fixed.

You have these tools:
{tools}

Work before you answer. Read the source you are testing so you use its real API,
and run your test with run_test to see what it actually does. You must run your
test at least once before you finish.

Reply with a single JSON object and nothing else. Either call a tool:
  {{"thought": "...", "tool": "<name>", "args": {{...}}}}
or finish:
  {{"thought": "...", "final_test": "<complete python file source>"}}

You have at most {max_steps} steps and {max_test_runs} test runs."""


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
    system = B1_SYSTEM.format(tools=tools.spec(), max_steps=budget.max_steps,
                              max_test_runs=budget.max_test_runs)
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
    pushed_back = False
    last_reply = ""

    for step in range(budget.max_steps):
        steps = step + 1
        reply = client.chat(messages)
        trace.llm_reply("b1", reply.text, reply.usage.to_dict(), reply.from_cache)
        messages.append({"role": "assistant", "content": reply.text})
        last_reply = reply.text

        action = parse_json_object(reply.text)
        if action is None:
            # Before treating this as a protocol violation, try to recover a test
            # from it. A reply that contains a complete test but breaks JSON on a
            # newline is a formatting failure, not a failure to do the task, and
            # scoring it as the latter would understate the baseline.
            recovered = recover_final_test(reply.text)
            if recovered:
                action = {"final_test": recovered}
            else:
                messages.append({
                    "role": "user",
                    "content": "That was not a JSON object. Reply with exactly one "
                               "JSON object: either a tool call or final_test. If "
                               "your test contains newlines, escape them as \\n.",
                })
                continue

        if "final_test" in action:
            candidate = extract_code(action["final_test"])
            # Left to itself the agent answers on step one and never touches a
            # tool, which quietly turns this baseline into the no-tools one and
            # makes any comparison against it meaningless. It is pushed back
            # exactly once; after that its answer stands, so it can still finish.
            if tools.test_runs == 0 and not pushed_back:
                pushed_back = True
                last_test = candidate
                messages.append({
                    "role": "user",
                    "content": "You have not run your test yet. Call run_test with "
                               "this source and look at what pytest actually says "
                               "before you finish.",
                })
                continue
            last_test = candidate
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

    # An agent that spent its whole budget without ever emitting final_test still
    # usually wrote a test somewhere. Scoring it as an empty submission would
    # understate the baseline rather than measure it.
    if not last_test.strip() and last_reply:
        last_test = recover_final_test(last_reply) or extract_code(last_reply)

    return {
        "test_source": last_test,
        "test_rel_path": test_rel_path,
        "steps": steps,
        "test_runs": tools.test_runs,
        "tool_calls": dict(tools.calls),
        "usage": client.total.to_dict(),
    }
