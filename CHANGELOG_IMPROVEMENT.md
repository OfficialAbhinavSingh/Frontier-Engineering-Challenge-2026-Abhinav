# Improvement changelog

Each row is a measured run, not a story. Every variant is the same code with a
different set of switches, so the same evaluation can be re-run with one thing
changed and the difference attributed to that thing.

Iteration happened on the **development split** (6 cases). The **evaluation
split** (14 cases) was run at the end and was never used to choose anything.

Numbers below are filled from `results/REPORT.md`; nothing is quoted here that
does not appear in a result file in this repository.

---

## The ladder

| Stage | What changed, and why | Evidence | Decision |
| --- | --- | --- | --- |
| **B0** | One prompt, the report plus a file listing, no tools, no execution. The thing people actually do. | 2/14 (14%), 1.0 calls/case | Kept as the floor. |
| **B1** | One general-purpose agent: same model, same budget, same tools *including the sandbox*. | 2.7/14 (19%), range 2–3, 7.2 calls/case | Kept as the baseline every later claim is measured against. |
| **s1** | Structured pipeline: locate, author, run in the sandbox, repair. No repo map, no examples, generic repair text. | 3/14 (21%), 2.7 calls/case | Kept. |
| **s2** | Deterministic repo map, plus two of the project's own tests as examples. | 3/14 (21%), 2.4 calls/case | Kept — see the note on separability below. |
| **s3** | Repair instruction chosen by the failure class instead of one generic message. | 3/14 (21%), 2.4 calls/case | Kept. |
| **s4** | Per-repository memory carried across cases. | 3/14 (21%), 2.6 calls/case | Kept. |
| **s5** | Minimal-claim authoring and the `overspecified` verdict. | **4.3/14 (31%)**, range 4–5, 2.9 calls/case | Kept — pre-registered final system. |
| **s6** | Signature grounding: a missing API the report itself names is a reproduction, not a misused call. | 5.0/14 (36%), range 4–6, 2.8 calls/case | Kept, but reported as post-hoc. |
| **x1** | *Removed.* Deterministic verifier replaced by a model asked "did this reproduce the bug?" | 5.0/14 (36%), range 4–6, **4.2 calls/case** | Removed — matched by s6 at a third fewer calls. |

Headline claim, and the only one that is a clean held-out result:
**s5 beats B1 by 4.3 cases to 2.7, a 59% relative improvement, using 2.9 model
calls per case instead of 7.2.**

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

On the development split, **every case self-verified as reproduced on the first
attempt, and half of them still failed Fail-to-Pass.** The repair loop never
fired, which is why s2, s3 and s4 were byte-identical — two of them cost
literally $0.00, because every prompt was a cache hit.

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

### The experiment that was removed

The obvious way to build the verifier is to hand the pytest output to a model and
ask whether the bug was reproduced. That is `x1`, identical to s5 apart from the
verifier. It is kept in the tree, switchable, so the claim can be re-run.

**It won, and that was the most useful result of the project.**

On the evaluation split x1 scored 5.0/14 against s5's 4.3/14. The entire gap was
a single case, `click__2817`, and diagnosing it found a bug in my verifier rather
than a virtue in x1.

That issue asks for `CliRunner` to accept `catch_exceptions`. The fix *adds* the
parameter, so the correct reproduction is `CliRunner(catch_exceptions=False)`
raising `TypeError` at the parent commit. `shallow_fail` rejected it, because no
traceback frame entered project code — and then the repair loop turned a correct
test into two worse ones. The rule had conflated two different things: when the
bug *is* a missing signature, the exception legitimately occurs at the call site
with no project frames, which by frames alone is indistinguishable from an agent
inventing an API.

The report separates them, and s6 uses the same grounding idea as the
over-specification check, run in the opposite direction. With that fixed
deterministically, **s6 matched x1 exactly — 5.0/14, range 4–6 for both — using
2.8 model calls per case against x1's 4.2.**

So x1 is removed on the evidence rather than on principle. It was paying a model,
on every attempt, to notice one thing a rule can notice for free. The structural
argument stands behind that: whether a frame entered project code is **already a
fact in the output**, and asking a model to infer it substitutes an opinion for a
fact at the exact point the pipeline depends on being right.

---

## On separability, stated plainly

The ladder steps s1 through s5 are **not separable on the development split**. At
6 cases one case is 17 percentage points, and a variant was observed moving by a
full case from a harness change alone. What the development split supports is
that the structured pipeline beats both baselines; it does not support ranking
s2 against s3.

This is why the evaluation split is reported with repeated runs and a range
rather than a single number. Over three independent runs each: B1 spanned 2–3
cases, s5 spanned 4–5, and s6 and x1 both spanned 4–6. **s5 and x1's ranges
overlap**, which is exactly the claim a single run would have let me overstate.

The gap that survives repetition is the one between the structured pipeline and
the baselines, not the gaps inside the ladder.

---

### A limitation found by testing the reproducibility claim itself

Replaying the final system offline reproduces all fourteen Fail-to-Pass verdicts
exactly, at zero cost, with every model call served from the committed cache.
One case reached that same verdict by a different route.

pytest prints its own runtime into its output, and that output is quoted into
repair prompts, so a repair prompt can differ by a few characters between runs.
A different prompt is a different cache key, and that lookup misses.

Normalising timings out of prompt text fixes it and was not shipped, on purpose:
changing prompt text changes every cache key, which would invalidate the whole
committed cache and break the offline replay it was meant to protect.
Regenerating the cache would have cost roughly another dollar and taken the
project past its budget. Shipping a working replay with a documented edge is the
better trade, and the edge is documented rather than left for a reader to find.

**Learning:** a cache keyed on prompt text inherits the determinism of everything
that text quotes. Anything a tool prints that varies between runs — a timing, a
temporary path, an address — becomes part of the key.

## What the numbers say about the central problem

The agent's own judgement of whether it reproduced the bug, checked against
ground truth:

| | `s1` | `s4` | `s5` | `s6` | `x1` |
| --- | ---: | ---: | ---: | ---: | ---: |
| False-confidence rate | 75% | 77% | 63% | 61% | 55% |

Every one of those attempts reported success. The minimal-claim rules and the
typed verdicts moved that from 77% to 61%; they did not solve it.

## Main failure mode

**The test asserts the wrong expected value.** 55% of the final system's
case-runs failed as `did_not_pass_at_fix` — failing at the buggy commit *and* at
the fixed one. Only 7% failed the opposite way by not failing at the buggy commit.

These tests reach the bug and then assert something the fixed code does not
produce either. The verifier's most common verdict on them is
`reproduced_assertion` (38% of all attempts), which is precisely the verdict
whose correctness cannot be checked structurally: an assertion that fails at the
buggy commit looks identical whether its expected value is right or wrong.

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
available is a paragraph of prose written by a stranger. That is 55% of the
remaining failures, and it is not a prompting problem.

What I would tell someone building the next agent: make your verifier return a
typed signal rather than a boolean, push everything you can into the part that
evidence can settle — it is more than you expect, and it is usually already in
the output you are throwing away — then put the human checkpoint exactly on the
part that is left. Repro-Bot proposes and stops for review because the last
question is the one it cannot answer for itself.
