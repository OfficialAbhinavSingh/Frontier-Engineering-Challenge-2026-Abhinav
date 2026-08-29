# Agent trajectories

Two kinds of agent were used, and both are represented here.

**Repro-Bot's own agents** — the locator, the author, the memory writer, and the
model-judged verifier in the removed experiment. Each run writes its trajectory
as it happens, in order, to `traces/<variant>/<case>.jsonl`: every prompt, every
model reply, every tool call and its response, every verdict, and the human
checkpoint at the end. The files below are those logs rendered as markdown.

**Claude Code (Claude Opus 5)** — the coding agent that built the project. Its
session is in [`claude-code-build.md`](claude-code-build.md), exported with
harness-injected context removed, credential-shaped strings redacted and home
paths rewritten.

Every trajectory here is complete from the agent's instructions through to the
scored result. Nothing is summarised or reordered.

## What to read, and why


### `s5` — Repro-Bot, the final system

- [`click__3105`](s5/click__3105.md) — solved, but only after verification rejected the first attempt and the typed repair instruction sent it back.  
  3 model calls, 2 tool calls, verdicts: broken_test → reproduced_assertion. Result: Fail-to-Pass.
- [`click__2263`](s5/click__2263.md) — the over-specification check firing: the test failed, but on claims the report never made.  
  3 model calls, 2 tool calls, verdicts: overspecified → reproduced_exception. Result: did not reach Fail-to-Pass.
- [`click__2644`](s5/click__2644.md) — a genuine failure, kept because the failure modes are the point.  
  3 model calls, 2 tool calls, verdicts: no_fail → reproduced_assertion. Result: did not reach Fail-to-Pass.

### `x1` — the removed experiment — verification by model instead of traceback (it outscores the shipped system; removed for cost and determinism)

- [`click__3105`](x1/click__3105.md) — solved, but only after verification rejected the first attempt and the typed repair instruction sent it back.  
  5 model calls, 2 tool calls, verdicts: no_fail → reproduced_assertion. Result: Fail-to-Pass.
- [`click__3043`](x1/click__3043.md) — the over-specification check firing: the test failed, but on claims the report never made.  
  6 model calls, 3 tool calls, verdicts: no_fail → overspecified → no_fail. Result: did not reach Fail-to-Pass.
- [`click__2263`](x1/click__2263.md) — a genuine failure, kept because the failure modes are the point.  
  6 model calls, 3 tool calls, verdicts: no_fail → no_fail → reproduced_assertion. Result: did not reach Fail-to-Pass.

### `b1` — the fair baseline — one general-purpose agent with the same tools

- [`click__2263`](b1/click__2263.md) — a genuine failure, kept because the failure modes are the point.  
  6 model calls, 1 tool calls, verdicts: no verdict recorded. Result: did not reach Fail-to-Pass.
- [`jinja__1510`](b1/jinja__1510.md) — a clean first-attempt reproduction.  
  8 model calls, 7 tool calls, verdicts: no verdict recorded. Result: Fail-to-Pass.
- [`click__2644`](b1/click__2644.md) — additional run.  
  11 model calls, 0 tool calls, verdicts: no verdict recorded. Result: did not reach Fail-to-Pass.

