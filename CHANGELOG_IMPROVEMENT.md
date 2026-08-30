# Improvement changelog

Each row is a measured run, not a story. Every variant is the same code with a
different set of switches, so the same evaluation can be re-run with one thing
changed and the difference attributed to that thing.

Iteration happened on the **development split** (13 cases). The **evaluation
split** (27 cases) was run at the end and was never used to choose anything.

Numbers below are filled from `results/REPORT.md`; nothing is quoted here that
does not appear in a result file in this repository.

---

## The ladder

| Stage | What changed, and why | Evidence | Decision |
| --- | --- | --- | --- |
| **B0** | One prompt, the report plus a file listing, no tools, no execution. The thing people actually do. | 5/27 (19%), 1.0 calls/case | Kept as the floor. |
| **B1** | One general-purpose agent: same model, same budget, same tools *including the sandbox*. | 6.0/27 (22%), range 6–6, 7.3 calls/case | Kept as the baseline every later claim is measured against. |
| **s1** | Structured pipeline: locate, author, run in the sandbox, repair. No repo map, no examples, generic repair text. | 8/27 (30%), 2.7 calls/case | Kept. |
| **s2** | Deterministic repo map, plus two of the project's own tests as examples. | 7/27 (26%), 2.6 calls/case | Kept — see the note on separability below. |
| **s3** | Repair instruction chosen by the failure class instead of one generic message. | 8/27 (30%), 2.6 calls/case | Kept. |
| **s4** | Per-repository memory carried across cases. | 9/27 (33%), 2.9 calls/case | Kept. |
| **s5** | Minimal-claim authoring and the `overspecified` verdict. | **8.7/27 (32%)**, range 8–9, 3.1 calls/case | Kept — pre-registered final system, and the shipped one. |
| **s6** | Signature grounding: a missing API the report itself names is a reproduction, not a misused call. | 9.3/27 (35%), range 8–11, 2.9 calls/case | **Not shipped.** Beat s5 overall but *lost* on the clean held-out subset. |
| **x1** | *Removed.* Deterministic verifier replaced by a model asked "did this reproduce the bug?" | **10.3/27 (38%)**, range 9–12, **4.3 calls/case** | Removed for cost and determinism, **not** because it lost. |

Headline claim, and the only comparison this sample size resolves:
**s5 beats B1 by 8.7 cases to 6.0, a 45% relative improvement, using 3.1 model
calls per case instead of 7.3.** Three runs each, ranges 8–9 against 6–6 — they
do not overlap.

Everything else in that table is a single run or has overlapping ranges. `s1`–`s4`
sit inside or beside `s5`'s range and **cannot be ranked against each other on 27
cases**, where one case is nearly four points. The ladder shows that the
structured pipeline as a whole clears the baseline; it does not show which rung
did the work.

---

## What actually drove each change

### Before anything: the harness had to be trustworthy

Three defects were found and fixed before a single agent number was taken
seriously. They are listed because each one produced results that looked
perfectly reasonable.

1. **Bind-mounting a test over a tracked path makes `git checkout` abort.** Two
   cases had been passing by luck — the file happened to be identical between the
   two commits, so the aborted checkout did not matter. Fixed by injecting the
   test after the checkout.
2. **A failed checkout exits 1, exactly like a genuine test failure.** Added a
   sentinel printed inside the container once checkout and injection succeed; its
   absence is now an `infra_error`, not a passing reproduction.
3. **Files above the read limit failed to AST-parse**, silently dropping the
   largest modules out of relevance ranking. `tomlkit/items.py` — the file the
   bug was actually in — was ranked at zero.

**Learning:** every one of these made the numbers *better-looking*, not worse.
A harness bug that produces implausible results gets found immediately; one that
produces plausible results is what you ship.

### The dataset filter is load-bearing

`arrow` was mined successfully and then lost every single case in validation: its
dependency pins have drifted far enough that the maintainers' own regression
tests no longer pass at their own fix commits in a current environment. Eight
cases would have entered the set as permanent, unwinnable failures.

**Learning:** validating the *ground truth* against the harness, before the agent
sees anything, is what stops a dataset from silently encoding environment rot.
`data/cases/dropped.json` records all 36 rejections and why.

### The controls, added last, and what they caught

Every row above is a claim about the metric, and none of them tested the metric
on inputs whose answer was already known. Three controls now do, none of them
calling a model (`make controls`, $0.00):

| Control | What it runs | Must score | Scored |
| --- | --- | --- | ---: |
| `c_gold` | the maintainer's own regression test | 27/27 | **27/27** |
| `c_sabotage` | `assert False` — always fails | 0/27 | **0/27** |
| `c_vacuous` | `assert True` — always passes | 0/27 | **0/27** |

The two floors matter separately, because Fail-to-Pass is a conjunction and each
floor satisfies exactly one half of it. They score zero for different recorded
reasons — `did_not_pass_at_fix` and `did_not_fail_at_parent` — so both conditions
are demonstrably load-bearing. Had either scored above zero, agreement with one
condition would have been counting as evidence and every number in this changelog
would be inflated.

`c_gold` earned its place immediately by disagreeing. Scoring the maintainer's
*whole test file* gives **12/13 on the development split, not 13/13**: on
`rich__3577`, three unrelated tests in `tests/test_ansi.py` are already red at the
fix commit, while the test that commit added passes. `dataset.validate` never saw
this because it selects the added tests with `-k`; the scorer did not, and the two
had quietly diverged. The control is the only thing that runs both paths against
each other. Fixed by selecting the added tests and **recording that selector in
the result file**, so `make verify-scores` re-derives the control the same way it
re-derives everything else rather than special-casing a variant name.

**Learning:** a validator and a scorer that agree by construction are one code
path; when they are two, only a control that runs them against each other will
tell you they have drifted. The ceiling is worth as much as the floors — 27/27
says every case Ratchat misses is one that some test could have caught, so the
gap is the agent's, not the dataset's.

### The baseline was losing to my parser, twice

B1's first measured run made **zero tool calls across all six development
cases** — it answered on step one every time, which quietly collapsed the fair
baseline into the no-tools one. Fixed by requiring a test run before finishing.

Then two harness defects surfaced that penalised B1 specifically:

- B1 answers over a JSON protocol and routinely emits `final_test` containing
  real newlines, which is not valid JSON. Those replies were rejected until the
  budget ran out, and the raw JSON blob was then submitted as Python. The
  solver's author agent answers with a plain code block and never meets this.
- One run submitted a quoted **pytest transcript** as its test file, because
  "longest fenced block wins" and the transcript was longer than the test.

Both were fixed for both sides; code-block selection now prefers blocks that
parse as Python.

**Learning:** when a baseline loses, check whether it lost to the system under
test or to the scaffolding around it. Neither fix could flatter the solver, and
the second one helps the baseline more than it helps the solver.

### The finding that produced s5

On the development split as it stood then (6 cases; it is 13 now), **every case
self-verified as reproduced on the first attempt, and half of them still failed
Fail-to-Pass.** The repair loop never fired, which is why s2, s3 and s4 were
byte-identical — two of them cost literally $0.00, because every prompt was a
cache hit.

Reading the failing tests showed the cause was not missing the bug:

- `click__2263` — 13 assertions, 7 of them resting on invented help text such as
  `"[deprecated] This is the old name."`
- `click__2644` — a self-contradictory `pytest.warns(ResourceWarning)` block
  wrapping `assert not record.list`
- `sqlglot__5178` — an exact pretty-printed whitespace round-trip the report
  never mentions

Each test fails at the parent commit for the right reason and at the fix commit
for the wrong one. It caught the bug *and* a pile of incidental detail.

That is detectable without ever seeing the fix: a test whose assertions rest on
strings the reporter never wrote is asserting the agent's imagination. s5 adds a
deterministic `overspecified` verdict (assertion count plus literals absent from
the report) and minimal-claim authoring rules.

One deliberate trade: the first version of the check flagged
`assert x, "explanatory message"`. Assertion messages document rather than
constrain, and counting them punishes well-written tests, so they are excluded —
which *lowered* the detector's hit rate on the development split from 2 of 3 to
1 of 3. The principled version was kept over the one that scored better.

**Learning:** my own verifier was committing the exact error this project is
about. Accepting "the test failed" as "the bug was reproduced" is easy to write
and produces a plausible-looking 100% self-reported success rate.

### The experiment that was removed, and the story about it that did not survive

The obvious way to build the verifier is to hand the pytest output to a model and
ask whether the bug was reproduced. That is `x1`, identical to s5 apart from the
verifier. It is kept in the tree, switchable, so the claim can be re-run.

**It won, and it is still winning.** That is the most useful result of the
project, and the section it replaced is worth recording because it was wrong.

On a 14-case evaluation split x1 scored 5.0 against s5's 4.3. The entire gap was
a single case, `click__2817`, and diagnosing it found a real bug in my verifier.
That issue asks for `CliRunner` to accept `catch_exceptions`. The fix *adds* the
parameter, so the correct reproduction is `CliRunner(catch_exceptions=False)`
raising `TypeError` at the parent commit. `shallow_fail` rejected it, because no
traceback frame entered project code — and then the repair loop turned a correct
test into two worse ones. The rule had conflated two things: when the bug *is* a
missing signature, the exception legitimately occurs at the call site with no
project frames, which by frames alone is indistinguishable from an agent
inventing an API. The report separates them, and s6 uses the same grounding idea
as the over-specification check run in the opposite direction.

With that fixed, s6 matched x1 exactly on 14 cases — same mean, same range, a
third fewer calls. The conclusion written at the time was that x1's whole
advantage had been one blind spot, and that a rule could buy it back for free.

**Doubling the dataset falsified that.** On 27 cases:

| | s5 | s6 | x1 |
| --- | ---: | ---: | ---: |
| Overall | 8.7/27 | 9.3/27 | **10.3/27** |
| Held-out (13 later cases) | 4.7/13 | 4.3/13 | **5.3/13** |
| Calls/case | 3.1 | 2.9 | 4.3 |

x1 leads on both, and s6 does not reproduce its own gain on cases it was not
derived from. The tidy story was an artefact of a 14-case sample where one case is
seven points.

**What remains true is narrower and is what is claimed now:** removing x1 is a
trade, not a win. It costs roughly one case in 27 and buys back 28% fewer model
calls (3.1 per case against 4.3) and a verifier whose verdicts are identical across runs. The structural
argument stands on its own terms — whether a frame entered project code is
**already a fact in the output**, and asking a model to infer it substitutes an
opinion for a fact at the point the pipeline depends on being right — but it is a
principled choice made against the measurement, not vindicated by it, and the
switch stays in the tree so anyone can disagree by re-running it.

### The check that caught me overfitting

s6's rule was designed in response to `click__2817`, a case on the evaluation
split. That is fitting to the test set, and the fix is to test on data the rule
has never influenced. Five repositories were added to the dataset afterwards,
contributing 13 evaluation cases that did not exist when the rule was written.

`held_out_subset()` in `ratchat/eval/report.py` reports every variant restricted
to those cases. On them **s6 scores 4.3/13 against s5's 4.7/13** — the gain does
not merely shrink, it inverts.

So s6 is not shipped. `s5` is the final system, in the README, in
`ratchat/demo.py`, and in `make solution`.

**Learning:** the honest version of "I found a blind spot and fixed it" is
indistinguishable from "I tuned a rule until one case passed" *until you test on
data the rule never touched*. Building that check before it was needed is the
only reason this was caught rather than shipped as the headline. The dataset split
is a pure function of the case id, so adding repositories could only add cases to
each side — every earlier evaluation case stays an evaluation case, which is what
makes the before-and-after comparable at all.

---

## On separability, stated plainly

The ladder steps s1 through s5 are **not separable**, on either split. At 27
cases one case is 3.7 percentage points, and a variant was observed moving by a
full case from a harness change alone. s1 through s4 were run once each and land
inside or beside s5's range. What the data supports is that the structured
pipeline beats both baselines; it does not support ranking s2 against s3, and no
such ranking is claimed.

This is why the evaluation split is reported with repeated runs and a range
rather than a single number. Over three independent runs each: **B1 spanned 6–6,
s5 spanned 8–9** — no overlap, which is the one comparison here that survives
repetition. s6 spanned 8–11 and x1 spanned 9–12, both overlapping s5, so neither
is claimed to beat it on the strength of a mean.

The gap that survives repetition is the one between the structured pipeline and
the baselines, not the gaps inside the ladder.

---

### The reproducibility claim was wrong, and the check I wrote for it said so

I claimed offline replay reproduced the reported runs exactly. Building a check
for it — `scripts/replay_fidelity.py`, `make replay-check` — showed it does not,
and by a wide margin. Measured over the 27 evaluation cases: **`b0` 27/27,
`s6` 17/27, `s5` 15/27, `b1` 8/27** reproduced byte-identically.

pytest prints its own runtime into its output (`1 failed in 0.02s`), that output
is quoted verbatim into repair prompts, and in `b1`'s case into the agent's whole
running conversation. A prompt that differs by a few characters is a different
cache key, so that lookup misses and the run ends there. `b0` is perfect because
it never sees pytest output — one call, no loop. It then compounds through
repository memory: a case that ends early writes no lesson, so every later case in
that repository gets a different prompt and misses in turn.

Normalising timings out of prompt text fixes it and is deliberately not shipped:
it changes every prompt, therefore every cache key, therefore invalidates the
entire committed cache, and regenerating it means re-running every variant live
for more than the budget left. So the claim was replaced rather than repaired.

**The claim that replaced it is stronger.** Scoring a test source is pure — run it
at the parent commit, run it at the fix commit, compare — and every result file
records the exact source its run produced. So `make verify-scores` re-derives
every reported Fail-to-Pass flag from committed data with **no model, no cache and
no API key**, and prints any disagreement by case. Measured over everything
reported: **20 result files, 540 case-scores, 0 mismatches**. The reproducibility
of the results never depended on the cache; only the convenience of watching the
agents work for free did.

**Learning:** a reproducibility claim that is asserted rather than checked is just
a sentence. The check took an hour to write and immediately falsified the sentence
I had been shipping for days.

**Learning:** a cache keyed on prompt text inherits the determinism of everything
that text quotes. Anything a tool prints that varies between runs — a timing, a
temporary path, an address — becomes part of the key.

### The rename that stopped at the cache

The project was called Repro-Bot and is now **Ratchat**. Renaming it turned out to
be a third instance of the same lesson, so it is recorded here rather than done
silently.

A content-addressed cache makes some strings expensive to rename. Two internal
identifiers are quoted into prompts: the generated test's filename
(`test_reprobot_<case>.py`, which the author prompt states verbatim) and the
sandbox's readiness sentinel (`__REPROBOT_SANDBOX_READY__`, which appears in the
pytest output quoted back into repair prompts). Renaming either changes every
affected prompt, therefore every cache key.

Rather than guess at the blast radius, it was measured — scanning all 530 recorded
trace files for what the models actually saw:

| String | Recorded prompt occurrences | Decision |
| --- | ---: | --- |
| `test_reprobot_` | 1425 | **frozen** |
| `__REPROBOT_SANDBOX_READY__` | 981 | **frozen** |
| the display name "Repro-Bot" | 0 | renamed |
| `reprobot.` (package) | 0 | renamed |
| `reprobot-env` (image prefix) | 0 | renamed |
| `reprobot_inject`, container names | 0 | renamed |

So the rename covers everything a reader, judge or user sees — the package, the
Docker images, the CLI banner, every document — and stops at the two strings that
are load-bearing for the cache. Freezing them costs a cosmetic inconsistency in a
generated filename. Renaming them would have cost the entire committed cache: the
`$0` demo replay, the partial run replay, and more than the remaining budget to
regenerate.

The images were retagged rather than rebuilt (`docker tag`), so nothing had to be
rebuilt to match the new name. `make verify-scores` is unaffected either way — it
never touches the cache.

**Learning:** in a system that hashes its own inputs, a rename is a schema
migration, not a find-and-replace. The cheap way to find out which strings are
load-bearing is to ask the recorded data instead of reasoning about the code.

### The demo destroyed its own recording, and said it hadn't

The same lesson had one more layer, and I found it by re-running the demo during a
final check rather than trusting that it still worked.

`make demo` ships a committed cache so the narrated run replays for free and shows
the same thing every time. It came back **Fail-to-Pass NO**, on one attempt instead
of two, having spent real money. The committed trace said `from_cache=False` on
both author calls, so the recording had never actually replayed — not once.

The cause is the feature two sections above. Repository memory is injected into the
author's prompt. At the end of the recorded run, memory distilled two lessons about
Click and *saved them*, and those lessons were committed alongside the cache. Every
later run — mine, and a judge's on a fresh clone — rebuilt the author prompt with a
`Notes from earlier bugs in this same repository:` block that was absent when the
cache was recorded. Different prompt, different key, guaranteed miss. The artifact
of the run invalidated the replay of that same run, deterministically and forever.

Two things made it worse than a stale cache. A judge without an API key gets a hard
`OfflineCacheMiss` rather than a demo. And the run ends by printing *"Not approved,
so nothing was written. Ratchat never commits."* while it had just written to
`data/memory/demo/click.json` — the one sentence in the program that promises
restraint was false.

The fix is that the demo learns within its run and persists nothing
(`RepoMemory(..., persist=False)`); the evaluation harness, which genuinely does
carry lessons from case to case, keeps the saving default. `tests/test_memory.py`
pins both halves, including a guard asserting `data/memory/demo/` stays empty,
because a single committed lesson silently breaks the replay again. The demo now
runs twice in a row at **$0.0000**, every call `from_cache`, `broken_test` then
`reproduced_assertion`, Fail-to-Pass **YES**.

**Learning:** a component that both reads and writes the same state cannot be
recorded by capturing its inputs alone — replaying it re-runs the write, and the
write is an input to the next replay. Memory made the system better at its task and
silently non-reproducible at the same time, which is exactly the trade this project
claims to measure rather than assume.

**Learning:** "it worked when I recorded it" decays. This was caught only because
the last thing I did before submitting was run the demo again instead of trusting
the commit message that said it was cached.

## What the numbers say about the central problem

The agent's own judgement of whether it reproduced the bug, checked against
ground truth:

| | `s1` | `s4` | `s5` | `s6` | `x1` |
| --- | ---: | ---: | ---: | ---: | ---: |
| False-confidence rate | 70% | 65% | 68% | 62% | **48%** |

Every one of those attempts reported success. **The deterministic variants sit in
a band between 62% and 70% and do not clearly separate from one another; the
model-judged verifier is the only thing that moves the number materially, to
48%.**

An earlier, smaller run showed the minimal-claim rules driving this down a ladder
from 77% to 61%. That ordering did not hold at 27 cases either, and it is not
claimed any more. What the deterministic checks demonstrably do is change *which*
errors survive — they eliminate the structurally-detectable ones, and the residue
is concentrated in the single class no rule can see.

## Main failure mode

**The test asserts the wrong expected value.** 57% of the final system's
case-runs failed as `did_not_pass_at_fix` — failing at the buggy commit *and* at
the fixed one. Only 10% failed the opposite way by not failing at the buggy
commit, and 1% produced no test at all.

These tests reach the bug and then assert something the fixed code does not
produce either. The verifier's most common verdict on them is
`reproduced_assertion` (30% of all attempts), which is precisely the verdict
whose correctness cannot be checked structurally: an assertion that fails at the
buggy commit looks identical whether its expected value is right or wrong.

This is also the cleanest explanation of why x1 still leads. The class the
deterministic verifier is blind to by construction is the majority of what is
left, and a model reading the report can form a partial opinion about it where a
rule reading the traceback has nothing to work with.

## Hot take

**A test that fails is not a test that reproduces — and the difference splits
cleanly into a part you can verify without the answer and a part you cannot.**

Most of what makes a generated test wrong is structural, and structure is
readable from evidence already in hand: whether a frame entered project code,
whether the asserted strings appear anywhere in the report, whether the missing
parameter is one the reporter asked for. Every one of those is a fact sitting in
output that most pipelines discard, and every one converts a boolean "it failed"
into an instruction for what to do next.

The residue does not yield to that treatment. Whether the asserted expected value
is what the fixed code will produce is an oracle question, and the only oracle
available is a paragraph of prose written by a stranger. That is 57% of the
remaining failures, it is not a prompting problem, and it is the reason the
verifier I removed on principle still outscores the one I shipped.

What I would tell someone building the next agent: make your verifier return a
typed signal rather than a boolean, push everything you can into the part that
evidence can settle — it is more than you expect, and it is usually already in
the output you are throwing away — then put the human checkpoint exactly on the
part that is left. Ratchat proposes and stops for review because the last
question is the one it cannot answer for itself.
