# Ratchat

**Turns a bug report into a failing test that is proven to reproduce the bug.**

[![checks](https://github.com/OfficialAbhinavSingh/Frontier-Engineering-Challenge-2026-Abhinav/actions/workflows/checks.yml/badge.svg)](https://github.com/OfficialAbhinavSingh/Frontier-Engineering-Challenge-2026-Abhinav/actions/workflows/checks.yml)

That badge is the metric's controls, not a test suite. On every push a runner
with no secrets rebuilds the sandbox from the pinned base image and re-checks
that a test which always fails and a test which always passes both score zero,
while the maintainer's own regression test scores every case. The central claim
is therefore verified on a machine that is not mine.

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
Ratchat produces the artifact that makes the rest checkable.

---

## What it does

```
bug report (natural language)   →   Ratchat   →   reviewable bundle
                                                      ├── the test
                                                      ├── a git-applyable patch
                                                      ├── the verifier's evidence
                                                      ├── the attempts rejected
                                                      └── what is NOT established
```

Ratchat sees the repository **at the commit where the bug is still present**.
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

Nothing is written without `--approve`. Ratchat proposes; it never commits.

---

## How it is measured

The primary metric is **Fail-to-Pass (F2P)**, and it needs no judgement:

> the generated test must **fail** at the parent commit — it demonstrates the bug
> — and **pass** at the real fix commit — the maintainer's fix resolves it.

No model scores anything. A test that always fails is caught by the second
condition; a test that never fails is caught by the first; a test that touches
existing files is rejected outright, because the generated file is a new path
that did not previously exist.

### Controls, so the claim above is measured rather than asserted

Everything above is a claim about the metric, and a claim about a metric is worth
nothing until you have run the inputs whose answer you already know. Three
controls do that. None of them calls a model, so they cost nothing and return the
same thing on every machine: `make controls`.

| Control | What it runs | Must score | Scored |
| --- | --- | --- | ---: |
| `c_gold` | the maintainer's own regression test | 27/27 | **27/27** |
| `c_sabotage` | `assert False` — a test that always fails | 0/27 | **0/27** |
| `c_vacuous` | `assert True` — a test that always passes | 0/27 | **0/27** |

Fail-to-Pass is a conjunction, and each floor satisfies exactly one half of it
and nothing else. They score zero for *different* recorded reasons —
`did_not_pass_at_fix` for the saboteur, `did_not_fail_at_parent` for the vacuous
test — which is what shows both conditions are load-bearing rather than one
carrying the other. If either floor scored above zero, agreement with a single
condition would be counting as evidence, and every number in this README would be
inflated.

These three run on every push in GitHub Actions, on a runner with no secrets and
no committed cache — it clones the repository, rebuilds the sandbox image from
the pinned base and re-derives the table above in about a minute. It has already
paid for itself: it caught a pin mismatch between `dataset.validate` and
`scripts/build_images.py` that made `c_gold` score 0/5 on the runner while
scoring 5/5 locally, because the two were installing different dependency
generations. The pin is now one function used by both.

`c_gold` is the ceiling, and its value is that it measures the scorer instead of
trusting it. A case is admitted to the dataset only after `dataset.validate`
replays the maintainer's test at both commits — but that is a different code path
from the one that produces the headline number. Running gold back through the
scorer closes the gap, and 27/27 says the ceiling is the whole set: every case
Ratchat misses is a case some test could have caught.

Building the ceiling found a real discrepancy, which is the reason to build it.
Scoring the maintainer's *whole file* gives 12/13 on the development split, not
13/13: on `rich__3577`, three unrelated tests in `tests/test_ansi.py` are already
red at the fix commit, while the test the fix actually added passes. The agent is
scored on a file containing only its own test, so the honest comparison selects
the tests the fix added — and that selector is recorded in the result file, not
applied by special-casing a variant name, so `make verify-scores` re-derives the
control exactly the way it re-derives everything else.

**The cases are real and pre-verified.** Each one comes from a merged commit that
fixed source code and added a regression test, and that closed exactly one linked
issue whose body does not contain the fix. Before a case enters the set, the
*maintainer's own test* is replayed in the sandbox and must itself demonstrate
Fail-to-Pass. Cases that fail that check are dropped, not worked around —
`data/cases/dropped.json` records every one and why.

**40 cases survive that check**, mined from six libraries (jinja 10, tomlkit 9,
rich 9, click 7, sqlglot 4, jsonschema 1). They are split into a development set
(13) and an evaluation set (27) by a pure function of the case ids, fixed before
any result was seen, and stratified per repository. Iteration happened on the
development set. Because the split is a function of the id and not of the set,
adding repositories later could only add cases to each side — every earlier
evaluation case is still an evaluation case, so results before and after the
dataset grew remain comparable.

---

## Does the advantage survive a change of model?

Every other number here was measured on one model, which leaves the obvious
objection open: that the structure is incidental and the model is doing the work.
So both sides were re-run on a second model from a different vendor — the same
`b1` agent and the same `s5` pipeline — and what is compared is the **gap between
them on the same model**. Absolute scores across models are not comparable and
are not presented as if they were.

| Model | Price in/out per M | `b1` same tools | `s5` Ratchat | Gap |
| --- | --- | ---: | ---: | ---: |
| `gemini-2.5-flash` | $0.300 / $2.50 | 6.0/27 (range 6-6) | **8.7/27 (range 8-9)** | **+2.7** (+44%) |
| `mistral-small-3.2-24b` | $0.075 / $0.20 | 2.7/27 (range 2-3) | **6.3/27 (range 5-7)** | **+3.7** (+138%) |

Three runs each, and within each model the ranges do not overlap. The pipeline
wins on both, and wins by more on the weaker model: a general-purpose agent
degrades sharply when the model gets worse, while the structured one degrades
gently. That is the strongest evidence in this repository that the improvement is
attributable to the architecture rather than to the model.

**The cross-comparison, stated carefully.** `s5` on the cheap model scores
6.3/27 against `b1` on the expensive model at 6.0/27, for $0.0101 a run against
$0.2373 — 24x cheaper. Those ranges overlap (5-7 against 6-6), so it **matches**
rather than beats. A single run scored 7 and looked like a clean win; two more
runs turned it into a tie, and the tie is what is reported. Structure buys about
an order of magnitude of model price here, not more than that.

Full detail, generated from the result files: [results/CROSS_MODEL.md](results/CROSS_MODEL.md).
Re-run with `make cross-model` (needs a key; about $0.05 a pair).

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

Ratchat never writes to a repository. It emits a proposal, the trajectory, and
the verifier's evidence; `--approve` is required before a file is written even
locally. Test execution runs with `--network none`, memory and CPU capped, in a
container built from a digest-pinned base image.

---

## Reproducibility

**Every reported score can be re-derived without a model.** Each result file
records the exact test source the run produced, and scoring a test source is a
pure operation: run it at the parent commit, run it at the fix commit, compare.
No API key, no cache, no sampling.

```bash
make repos && make validate && make verify-scores
```

That writes `results/SCORE_VERIFICATION.md` and prints any case where the
re-derived flag disagrees with the reported one. As committed:
**20 result files, 540 case-scores, 0 mismatches.** `make validate` is the same idea
one level down: before a case is allowed into the dataset, the *maintainer's own*
regression test has to demonstrate Fail-to-Pass in your Docker.

**The model-response cache is also committed**, so the agents can be watched
working without paying, but it reproduces the recorded runs only partially and
the shortfall is measured rather than glossed: 27/27 for `b0`, 15/27 for `s5`,
8/27 for `b1`. pytest prints its own runtime into output that gets quoted into
prompts, so those prompts are not byte-stable between runs and their cache
lookups miss. `make replay-check` measures it, and
[REPRODUCTION.md](REPRODUCTION.md) explains why fixing it would invalidate the
entire cache for more than this project's remaining budget.

`make demo` is the exception that does replay exactly: its one case
(`click__3105`) is cached end to end, so it runs at **$0.00 with no API key**,
always showing the same two rounds and the same Fail-to-Pass YES.

Getting there required fixing a bug worth naming, because it is the same bug the
cache section above describes, one layer deeper. The demo used repository memory,
memory is injected into the author's prompt, and the demo *saved* what it learned.
The saved lesson changed the next run's prompt, which changed its cache key, so the
recorded demo missed its own cache on the first replay — while printing "nothing
was written". The demo now learns within a run and persists nothing;
`tests/test_memory.py` pins it, including a guard that `data/memory/demo/` stays
empty. A component that both reads and writes the same state cannot be recorded by
capturing its inputs alone.

**Why generated tests are still named `test_reprobot_<case>.py`.** The project was
renamed from Repro-Bot to Ratchat late, and that filename is quoted verbatim into
every author prompt, so it is part of the cache key — as is the sandbox sentinel
`__REPROBOT_SANDBOX_READY__`, which reaches prompts through captured pytest output.
Measured across the 530 recorded traces, those two strings appear in 1425 and 981
prompts; the display name appears in none. Renaming them would invalidate all 885
committed cache entries to change a cosmetic detail, so they are frozen and
everything else was renamed. `make verify-scores` is unaffected — it never reads
the cache. The full accounting is in
[CHANGELOG_IMPROVEMENT.md](CHANGELOG_IMPROVEMENT.md).

Live runs will not match exactly either — the model is not deterministic across
time and the repair loop amplifies small differences. That is why the scores, not
the trajectories, are what the reproducibility claim rests on.

---

## Results

Evaluation split, 27 cases across six repositories, `google/gemini-2.5-flash`.
Repeated variants are the mean of three independent runs with the range they spanned.

| Variant | Fail-to-Pass | Rate | Model calls/case |
| --- | --- | ---: | ---: |
| `b0` — one prompt, no tools | 5/27 | 19% | 1.0 |
| **`b1` — general-purpose agent with the same tools** | **6.0/27 (6–6)** | **22%** | 7.3 |
| `s1`–`s4` — structured pipeline, one run each | 7–9/27 | 26–33% | 2.6–2.9 |
| **`s5` — pre-registered final system** | **8.7/27 (8–9)** | **32%** | 3.1 |
| `s6` — plus signature grounding (post-hoc) | 9.3/27 (8–11) | 35% | 2.9 |
| `x1` — removed: model-judged verification | 10.3/27 (9–12) | 38% | 4.3 |

**The headline claim is `s5` against `b1`: 8.7 versus 6.0 cases, a 45% relative
improvement, using 3.1 model calls per case instead of 7.3.** Their ranges do not
overlap across three runs each (8–9 against 6–6), which is the only comparison in
this table the sample size actually resolves.

Everything else in the table is honest about being unresolved. `s1`–`s4` were run
once each and land inside or beside `s5`'s range, so **the rungs of the ablation
ladder are not separable at this sample size** — the structured pipeline as a
whole beats the baseline, but this data cannot rank its individual pieces. Twenty-seven
cases means one case is nearly four points.

### Two results that went against me

Both were produced by checks built specifically to catch this kind of thing, and
both are reported because they fired.

**`s6` fails its clean held-out test.** Signature grounding was designed in
response to a case on the first evaluation split, so that split stopped being
held out for it. Five repositories were added to the dataset afterwards. On those
13 unseen cases `s6` scores **4.3/13 against `s5`'s 4.7/13** — no better, slightly
worse. The rule earned its gain on the split it was derived from and does not
carry. It stays in the repository as a switchable variant and is **not** the
shipped system.

**`x1` — the model-judged verifier I removed on principle — leads.** 10.3/27
against `s5`'s 8.7/27, and 5.3/13 against 4.7/13 held out. An earlier, smaller
run had `s6` matching it exactly, which supported a tidy story that the model was
only paying to notice one thing a rule could notice for free. **At 27 cases that
story is dead.** The remaining honest framing is a trade: `x1` buys roughly one
extra case for 39% more model calls and a verifier whose verdicts are not
reproducible across runs. Removing it is a defensible choice about determinism and
cost, not a win on accuracy, and the switch is kept so the claim can be re-run.

Full tables, per-case outcomes and the verdict distribution:
[results/REPORT.md](results/REPORT.md). What each change bought, including what it
did not buy: [CHANGELOG_IMPROVEMENT.md](CHANGELOG_IMPROVEMENT.md).

Model calls per case is the efficiency measure to read. The dollar figures in
[results/REPORT.md](results/REPORT.md) are deflated for variants whose prompts
were already cached, whereas call counts are not affected by caching.

### The number this project is really about

The agent decides for itself whether it reproduced the bug. How often that
judgement is wrong is the quantity worth reducing:

| | `s4` | `s5` | `s6` | `x1` |
| --- | ---: | ---: | ---: | ---: |
| False-confidence rate | 65% | 68% | 62% | **48%** |

Every one of those runs reported success. Roughly a third of them were right.

**The deterministic verifier does not move this number much, and the model-judged
one does.** That is the sharpest finding here, and it points straight at the
reason: the structural checks catch the errors that are visible in structure —
a traceback that never entered the project, an invented parameter, an assertion
stack too specific to be a claim about one bug. What they cannot catch is an
assertion that reaches the bug and then expects the wrong value, because at the
buggy commit that is byte-for-byte identical to a correct one. A model reading the
report can partly judge it. A rule reading the traceback cannot. That failure class
is 57% of all remaining failures, which is why it dominates the gap.

---

## Main failure mode

**The test asserts the wrong expected value.** Across the final system's runs,
57% of case-runs failed as `did_not_pass_at_fix` — the test failed at the buggy
commit *and* at the fixed one. Only 10% failed the other way, by not failing at
the buggy commit at all, and 1% produced no test.

These tests are not missing the bug. They reach it, and then assert something the
fixed code does not produce either: invented help text, an exact whitespace
round-trip, an error message the reporter never quoted. The verifier's most
common verdict on them is `reproduced_assertion` (30% of all attempts) — the one
verdict whose correctness cannot be checked structurally, because an assertion
that fails at the buggy commit looks identical whether the expected value is
right or wrong.

This is the class the deterministic verifier is blind to by construction, and
closing it is the obvious next piece of work rather than something this
submission claims to have solved.

## Hot take

**A test that fails is not a test that reproduces — and the difference splits
cleanly into a part you can verify without the answer and a part you cannot.**

Most of what makes a generated test wrong is structural, and structure is
readable from evidence already in hand. Did a traceback frame enter the project's
code, or did it blow up at the call site? Do the asserted strings appear anywhere
in the report, or did the agent invent them? Is the missing parameter one the
reporter asked for? Each of those is a fact sitting in output that most pipelines
throw away, and each converts a boolean "it failed" into an instruction for what
to do next. Typing those verdicts is what lets the repair loop give the opposite
advice to two failures that look identical, and it is why the pipeline clears a
baseline holding the same tools.

The residue does not yield to that treatment, and the measurements say so
bluntly. Whether the asserted expected value is the one the fixed code will
produce cannot be checked without the fix — that is an oracle question, and the
only oracle available is a paragraph of prose written by a stranger. It is 57% of
the remaining failures, it is not a prompting problem, and it is the reason a
model-judged verifier still outscores the deterministic one I shipped.

So: build verification that returns a typed signal rather than a boolean, and
push everything you can into the part that evidence can settle. Then be honest
that what is left needs an oracle, and design the human checkpoint around exactly
that. Ratchat proposes and stops for review precisely because the last question
is the one it cannot answer for itself.

---

## What existed before

Written during the competition: everything under `ratchat/`, `scripts/`,
`envs/`, `Makefile`, and all documentation.

Not written by me, and used under their own licences:

- **The target repositories** — [sqlglot](https://github.com/tobymao/sqlglot),
  [tomlkit](https://github.com/python-poetry/tomlkit),
  [click](https://github.com/pallets/click),
  [jinja](https://github.com/pallets/jinja),
  [rich](https://github.com/Textualize/rich),
  [jsonschema](https://github.com/python-jsonschema/jsonschema). Public,
  unmodified, cloned at pinned commits. The bug reports and the maintainers'
  regression tests are theirs; they are used as ground truth and are never shown
  to the agent.
- **pytest** and **Python 3.12**, inside the sandbox image.
- **OpenRouter** as the model gateway.

No third-party agent framework is used. The agent loop is written here so that
the trajectories are literally the calls that happened.

Host-side code has **no Python dependencies** — standard library only.

## Coding agents used

Disclosed as required. See [agent-trajectories/](agent-trajectories/).

- **Claude Code (Claude Opus 5)** — wrote this project. Session exported with
  harness-injected context removed and credential-shaped strings redacted.
- **Ratchat's own agents** (locator, author, memory) — every run writes its own
  JSONL trajectory as it happens, under `traces/`.
