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
bug report (natural language)   →   Repro-Bot   →   a new test file
                                                    + the evidence it reproduces
                                                    + a human approval gate
```

Repro-Bot sees the repository **at the commit where the bug is still present**.
It never sees the fix. It writes a test, runs it in a sandbox, reads *where* it
failed, and repairs it under an instruction chosen by that verdict. It proposes;
it never commits.

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
| `shallow_fail` | it blew up in the test body without ever reaching project code — almost always a misused API |
| `broken_test` | import, syntax or fixture problem; the test never ran |
| `no_fail` | it passed, so it reproduces nothing |
| `timeout` | it hung |

The distinction that carries the weight is `shallow_fail` versus the two
`reproduced_*` verdicts. All three are "the test failed". Only two of them are
evidence.

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

See [results/REPORT.md](results/REPORT.md) for the generated tables, and
[CHANGELOG_IMPROVEMENT.md](CHANGELOG_IMPROVEMENT.md) for what each change bought
and what it cost.

---

## Main failure mode

<!-- filled from measured results -->

## Hot take

<!-- filled from measured results -->

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
