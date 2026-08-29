# Repro-Bot

**Turns a bug report into a failing test that is proven to reproduce the bug.**

Built for the micro1 Frontier Engineering Challenge 2026 (Agentic Workflows).
Everything in this repository was written during the competition; see
[What existed before](#what-existed-before) for the dependency and data
provenance.

- [Reproduction guide](REPRODUCTION.md) — clean-environment setup, exact commands, runtimes, cost
- [Improvement changelog](CHANGELOG_IMPROVEMENT.md) — every iteration, with the evidence that drove the next one
- [Results](results/REPORT.md) — the generated comparison tables
- [Agent trajectories](agent-trajectories/) — the runs, end to end

---

## The user and the bottleneck

The user is a maintainer of a Python library with an issue queue. Somebody
reports that `len()` on a float value raises `TypeError`, or that a parser
swallows a key it should not. The report is prose. Before anyone can fix it,
somebody has to turn it into a **runnable failing test inside that project's own
test suite**.

That step is small to describe and expensive to do. It means finding the module
involved, finding the test file it belongs in, matching the project's fixtures
and import conventions, and then iterating until the test fails — and fails
*because of the reported bug*, not because of a typo in the call.

It is also the step people skip. The consequences are ordinary and familiar:
bugs get patched with no regression test, so they come back; reports sit
unreproduced for months; and a maintainer's scarcest resource goes into
rebuilding a reproduction the reporter already had.

The strongest evidence that this is genuinely hard is that SWE-bench, the
standard benchmark for automated software engineering, had to **hand-curate** its
Fail-to-Pass tests. The reproduction step could not be automated even at dataset
construction time, by people building a benchmark about exactly this.

**Why solving it is valuable.** A verified failing test converts an unactionable
report into a well-posed task, and it does so for a human and for a coding agent
equally. It is the precondition for safe autonomous bug fixing: without a test
that is known to fail for the right reason, "the agent fixed it" is unfalsifiable.
Repro-Bot produces the artifact that makes the rest checkable.

---

## What it does

```
bug report (natural language)   →   Repro-Bot   →   reviewable bundle
                                                      ├── the test
                                                      ├── a git-applyable patch
                                                      ├── the verifier's evidence
                                                      ├── the attempts rejected
                                                      └── what is NOT established
```

Repro-Bot sees the repository **at the commit where the bug is still present**.
It never sees the fix. It writes a test, runs it in a sandbox, reads *where* it
failed, and repairs it under an instruction chosen by that verdict.

### What the maintainer actually receives

Approving a proposal writes a bundle, not a printout:

- **`add-test.patch`** — a unified diff that adds one new file and modifies
  nothing. Verified to pass `git apply --check` against the upstream repository
  at the reported commit, so a reviewer can see at a glance that no existing test
  or source file is touched.
- **`REPRODUCTION.md`** — the test, the verifier's verdict with the traceback it
  was read from, the exact commands to reproduce the run, and **the attempts that
  were rejected**. Those are included on purpose: they are the difference between
  a reviewer trusting the result and a reviewer redoing the work.
- **`trajectory.jsonl`** — every prompt, tool call and verdict, in order.

The report states its own limits. It separates what was established *by
execution* — the test fails at the reported commit, and the verdict says where —
from what was not: that the asserted value is the one a fix will produce. That
needs an oracle the pipeline does not have, and it is the most common way a
generated reproduction is wrong, so the reviewer's checklist starts there.

Nothing is written without `--approve`. Repro-Bot proposes; it never commits.

---

## How it is measured

The primary metric is **Fail-to-Pass (F2P)**, and it needs no judgement:

> the generated test must **fail** at the parent commit — it demonstrates the bug
> — and **pass** at the real fix commit — the maintainer's fix resolves it.

No model scores anything. A test that always fails is caught by the second
condition; a test that never fails is caught by the first; a test that touches
existing files is rejected outright, because the generated file is a new path
that did not previously exist. The metric defends itself.

**The cases are real and pre-verified.** Each one comes from a merged commit that
fixed source code and added a regression test, and that closed exactly one linked
issue whose body does not contain the fix. Before a case enters the set, the
*maintainer's own test* is replayed in the sandbox and must itself demonstrate
Fail-to-Pass. Cases that fail that check are dropped, not worked around —
`data/cases/dropped.json` records every one and why.

The cases are split into a development set and an evaluation set by a pure
function of the case ids, fixed before any result was seen. Iteration happened on
the development set.

---

## The two baselines

A single baseline would have made the result easy to dismiss, so there are two.

**B0 — the naive floor.** One prompt containing the report and the repository's
file listing; take the test that comes back. No tools, no execution. This is what
people actually do today, and it is the reason the problem looks easy.

**B1 — the fair baseline.** One general-purpose agent, the **same model**, the
**same budget**, and the **same tools** the solver gets — including the sandbox
and the ability to run its test — driven by a single generic instruction.

B1 exists to close off the obvious objection: *your gain is just that you added a
test runner*. B1 already has the test runner. Everything the solver gains over B1
has to come from how the work is organised.

---

## Design

Five stages. Two of them never call a model, because they do not require
judgement and a model would only add cost and variance.

### 1. Cartographer — deterministic, no model

Ranks source modules and test files against the report's vocabulary, and reads
the project's **real** conftest fixtures and import idiom out of its existing
tests.

*Why:* a cheap model does not fail here because its context is too small. It
fails because the context is full of the wrong things. A flat file listing says
nothing about how this project writes tests, so the model invents a fixture and
an import path that never existed.

### 2. Locator — model

Commits to a target module and a sibling test file, with a stated reason, before
any code is written. Its answer is schema-checked and every path is verified to
exist; a hallucinated path falls back to the cartographer's top-ranked candidate.

*Why:* forcing the commitment early means the author stage starts from a decision
on the record instead of drifting.

### 3. Author — model

Writes the test with the located source in front of it and **two real tests from
that project's own suite** as examples.

*Why:* style, fixtures and helper usage then come from the repository rather than
from the model's priors about how tests are usually written.

### 4. Verifier — deterministic, no model

Runs the test in an offline container at the buggy commit and returns a **typed
verdict**, never a boolean:

| Verdict | What it means |
| --- | --- |
| `reproduced_exception` | the project's own code raised — traceback frames enter project source |
| `reproduced_assertion` | an assertion about a value failed inside the test — what a wrong-output bug looks like |
| `reproduced_signature` | it failed on a name the report itself asks about — the missing API *is* the bug |
| `shallow_fail` | it blew up in the test body without reaching project code, on a name the report never mentions — a misused API |
| `overspecified` | it failed, but on more claims than the report makes, so it will fail after the fix too |
| `broken_test` | import, syntax or fixture problem; the test never ran |
| `no_fail` | it passed, so it reproduces nothing |
| `timeout` | it hung |

The distinction that carries the weight is `shallow_fail` against the three
`reproduced_*` verdicts. Every one of them is "the test failed" with the same
exit code. Only three are evidence.

`reproduced_signature` and `shallow_fail` are the sharpest version of that: both
are an exception raised at the call site with no project frame at all. What
separates them is whether the identifier the interpreter complained about is one
the reporter asked for. If the report says `CliRunner` should accept
`catch_exceptions`, then `TypeError: unexpected keyword argument
'catch_exceptions'` is the bug. If the report is about whitespace in dotted keys,
the same shape of error is the agent inventing a parameter.

### 5. Repair — model, instruction chosen by the verdict

`no_fail` and `shallow_fail` require opposite corrections. Telling a model "your
test passed, make it fail" when it has actually misused the API pushes it towards
weakening the assertion — which produces a test that fails at the parent commit
*and* at the fix commit, and scores zero.

### Carried across cases: repository memory

Lessons about a repository — its import paths, its helpers, the fixture that does
not exist — are written after a case that went wrong and reused on later cases in
the same repository. Memory is reset per evaluation run and cases run in a fixed
order, so two runs of the same variant stay comparable.

### The human gate

Repro-Bot never writes to a repository. It emits a proposal, the trajectory, and
the verifier's evidence; `--approve` is required before a file is written even
locally. Test execution runs with `--network none`, memory and CPU capped, in a
container built from a digest-pinned base image.

---

## Reproducibility

**The model-response cache is committed.** Every model call behind every reported
number is stored in `data/cache/llm/`, keyed by a hash of the exact request. A
reader can reproduce the headline table offline, with no API key and no spend:

```bash
make repos && make validate && make replay
```

Live runs will not match exactly — the model is not deterministic across time and
the repair loop amplifies small differences. That is stated in
[REPRODUCTION.md](REPRODUCTION.md) rather than glossed, and it is precisely why
the cache ships.

---

## Results

Evaluation split, 14 cases never used to choose anything, `google/gemini-2.5-flash`.
Repeated variants are the mean of three independent runs with the range they spanned.

| Variant | Fail-to-Pass | Rate | Model calls/case |
| --- | --- | ---: | ---: |
| `b0` — one prompt, no tools | 2/14 | 14% | 1.0 |
| `b1` — general-purpose agent with the same tools | 2.7/14 (2–3) | 19% | 7.2 |
| `s1`–`s4` — structured pipeline | 3/14 | 21% | 2.4–2.7 |
| **`s5` — pre-registered final system** | **4.3/14 (4–5)** | **31%** | 2.9 |
| `s6` — plus signature grounding (post-hoc) | 5.0/14 (4–6) | 36% | 2.8 |
| `x1` — removed: model-judged verification | 5.0/14 (4–6) | 36% | 4.2 |

**The headline claim is `s5` against `b1`: 4.3 versus 2.7 cases, a 59% relative
improvement, using 2.9 model calls per case instead of 7.2.**

`s6` is reported separately and deliberately. The blind spot it fixes was found
on the evaluation split, so it is a post-hoc result and is not offered as a clean
held-out number. It is included because it settles what `x1` meant: the
model-judged verifier's entire advantage came from one blind spot in the
deterministic rule, and once that was fixed deterministically, `s6` matched `x1`
exactly — same mean, same range — using a third fewer model calls. `x1` is not
better; it was paying a model to notice one thing a rule can notice for free.

Model calls per case is the efficiency measure to read. The dollar figures in
[results/REPORT.md](results/REPORT.md) are deflated for variants whose prompts
were already cached, whereas call counts are not affected by caching.

Full tables, per-case outcomes and the verdict distribution:
[results/REPORT.md](results/REPORT.md). What each change bought:
[CHANGELOG_IMPROVEMENT.md](CHANGELOG_IMPROVEMENT.md).

### The number this project is really about

The agent decides for itself whether it reproduced the bug. How often that
judgement is wrong is the quantity worth reducing:

| | `s4` | `s5` | `s6` |
| --- | ---: | ---: | ---: |
| False-confidence rate | 77% | 63% | 61% |

Every one of those runs reported success. Between a third and a quarter of them
were right.

---

## Main failure mode

**The test asserts the wrong expected value.** Across the final system's runs,
55% of case-runs failed as `did_not_pass_at_fix` — the test failed at the buggy
commit *and* at the fixed one. Only 7% failed the other way, by not failing at
the buggy commit at all.

These tests are not missing the bug. They reach it, and then assert something the
fixed code does not produce either: invented help text, an exact whitespace
round-trip, an error message the reporter never quoted. The verifier's most
common verdict on them is `reproduced_assertion` — the one verdict whose
correctness cannot be checked structurally, because an assertion that fails at
the buggy commit looks identical whether the expected value is right or wrong.

## Hot take

**A test that fails is not a test that reproduces — and the difference splits
cleanly into a part you can verify without the answer and a part you cannot.**

Most of what makes a generated test wrong is structural, and structure is
readable from evidence already in hand. Did a traceback frame enter the project's
code, or did it blow up at the call site? Do the asserted strings appear anywhere
in the report, or did the agent invent them? Is the missing parameter one the
reporter asked for? Each of those is a fact sitting in output that most pipelines
throw away, and each converts a boolean "it failed" into an instruction for what
to do next. Typing those verdicts moved false confidence from 77% to 61% and beat
a model-judged verifier at a third fewer calls.

The residue does not yield to that treatment. Whether the asserted expected value
is the one the fixed code will produce cannot be checked without the fix — that
is an oracle question, and the only oracle available is a paragraph of prose
written by a stranger. It is 55% of the remaining failures and it is not a
prompting problem.

So: build verification that returns a typed signal rather than a boolean, and
push everything you can into the part that evidence can settle. Then be honest
that what is left needs an oracle, and design the human checkpoint around exactly
that. Repro-Bot proposes and stops for review precisely because the last question
is the one it cannot answer for itself.

---

## What existed before

Written during the competition: everything under `reprobot/`, `scripts/`,
`envs/`, `Makefile`, and all documentation.

Not written by me, and used under their own licences:

- **The target repositories** — [sqlglot](https://github.com/tobymao/sqlglot),
  [tomlkit](https://github.com/python-poetry/tomlkit),
  [click](https://github.com/pallets/click),
  [arrow](https://github.com/arrow-py/arrow). Public, unmodified, cloned at
  pinned commits. The bug reports and the maintainers' regression tests are
  theirs; they are used as ground truth and are never shown to the agent.
- **pytest** and **Python 3.12**, inside the sandbox image.
- **OpenRouter** as the model gateway.

No third-party agent framework is used. The agent loop is written here so that
the trajectories are literally the calls that happened.

Host-side code has **no Python dependencies** — standard library only.

## Coding agents used

Disclosed as required. See [agent-trajectories/](agent-trajectories/).

- **Claude Code (Claude Opus 5)** — wrote this project. Session exported with
  harness-injected context removed and credential-shaped strings redacted.
- **Repro-Bot's own agents** (locator, author, memory) — every run writes its own
  JSONL trajectory as it happens, under `traces/`.
