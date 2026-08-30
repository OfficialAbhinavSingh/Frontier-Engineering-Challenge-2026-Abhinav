# Solution video — script and shot list

Target: **under 5 minutes**. Recorded by Abhinav.

Every number below appears in `results/REPORT.md`. Regenerate with `make report`
before recording and do not read a number that is not in that file.

Record at 1920×1080, terminal font large enough to read at half size. Keep the
command and its output on screen together.

---

## 0:00–0:40 — The problem

**On screen:** `python3 -m ratchat.demo --case-id click__3105` — stop after the
bug report prints, before the run gets going.

> This is a real bug report on a real Python library. Prose, written by a user.
>
> Before anyone can fix it, somebody has to turn it into a failing test inside
> that project's own test suite. Find the module. Find the right test file. Match
> the project's fixtures and imports. Then iterate until the test fails — and
> fails *because of this bug*, not because you typo'd the call.
>
> That step is the bottleneck, and it's the step people skip. Bugs get patched
> with no regression test, so they come back. And it is genuinely hard: SWE-bench,
> the standard benchmark for automated software engineering, had to hand-curate
> its failing tests. The reproduction step couldn't be automated even by the
> people building a benchmark about it.

---

## 0:40–1:15 — The measurement, and two baselines

**On screen:** `results/REPORT.md`, headline table.

> I measure one thing: Fail-to-Pass. The generated test has to fail at the commit
> where the bug is still present, and pass at the real fix commit. No model scores
> anything. A test that always fails is caught by the second condition. One that
> never fails is caught by the first. The metric defends itself.
>
> And because no model is in the scoring, you don't have to take my word for any
> of it. `make verify-scores` re-runs every test my agents produced, in your
> Docker, and re-derives every number in this table — no API key, no model.
> 459 case-scores, zero mismatches.
>
> Twenty-seven evaluation cases, six libraries, and each case is pre-verified —
> the *maintainer's own* test has to demonstrate Fail-to-Pass before the case is
> allowed in.
>
> The naive baseline is what people actually do — paste the report into a model,
> take the test back. **Five out of twenty-seven.**
>
> But I don't want to beat that. The honest baseline is the second row: one
> general-purpose agent, same model, same budget, and the same tools — including
> the sandbox, so it can run its own test. That's **6.0 out of 27**, averaged over
> three runs.
>
> B1 already has the test runner. So everything after this has to come from how
> the work is organised, not from being the only side that can execute anything.

---

## 1:15–2:30 — One realistic execution

**On screen:** let the `click__3105` demo run. It takes two rounds: the first
attempt comes back `broken_test`, the repair fixes it, and the second is a
reproduction that goes on to pass Fail-to-Pass.

> Cartographer first — deterministic, no model. It ranks modules against the
> report and reads this project's real fixtures and import conventions out of its
> existing tests.
>
> The locator commits to a target module and a sibling test file before any code
> gets written.
>
> The author writes the test with two of this project's *own* tests in front of
> it, so the style and the fixtures come from the repository, not from the model's
> guesses about how tests usually look.
>
> Then it runs in a container with no network. And here's the part that matters.

**Pause on the verdict line.**

> The verifier does not return pass or fail. It reads the traceback and decides
> *where* the failure happened.
>
> A `TypeError` raised inside the project's code is a reproduction. The same
> `TypeError` raised in the test body, with no frame ever reaching project code,
> means the agent called the API wrong. Same exit code, same exception type,
> opposite meaning — and each one gets a different repair instruction. Telling a
> model "make it fail" when it has actually misused the API pushes it towards
> weakening the assertion, and that produces a test that fails at *both* commits
> and scores zero.

**On screen:** the Fail-to-Pass block, then the human checkpoint.

> Then it stops. It proposes; it never commits.

---

## 2:30–3:15 — The result, and what it does not say

**On screen:** `CHANGELOG_IMPROVEMENT.md`, then the headline table.

> Every row is a measured run of the same evaluation with one thing switched.
>
> The headline is the structured pipeline against the fair baseline: **8.7 versus
> 6.0 out of 27** — a 45% relative improvement, using 3.1 model calls per case
> against its 7.3. Three runs each, and the ranges don't overlap: 8 to 9 against
> 6 to 6.
>
> That's the *only* comparison in this table I'll claim. The middle rungs were run
> once each and land inside that range. At 27 cases one case is nearly four
> points, so the ladder shows the pipeline clears the baseline — it does not show
> which rung did the work, and the changelog says so instead of dressing it up.
>
> The change I can point at came from reading traces, not scores. Every case was
> self-reporting success on the first attempt, and half were still wrong. The
> tests weren't missing the bug — they caught it and thirteen other things,
> including help text the agent invented.

---

## 3:15–4:15 — The two results that went against me

**On screen:** the held-out table, then the `x1` row.

> Two things here didn't go my way, and both were caught by checks I built to
> catch exactly this.
>
> First. I found a blind spot in my verifier and fixed it — that's `s6`, and it
> scores higher: 9.3 against 8.7. But I found that blind spot *on the evaluation
> split*, which means I tuned a rule against my own test set.
>
> So I added five more repositories afterwards. Thirteen cases the rule has never
> influenced. On those, **`s6` scores 4.3 against `s5`'s 4.7.** It's worse. The
> gain didn't generalise — I'd fitted a rule to the one case that motivated it.
> So `s6` is not the shipped system. `s5` is.
>
> Second, and this is the uncomfortable one. **The model-judged verifier I removed
> on principle is still beating me** — 10.3 against 8.7, and it wins held out too.
>
> On a smaller run those two tied exactly, and I wrote that up as: the model was
> only paying to notice one thing a rule notices for free. Doubling the dataset
> killed that story. So the claim I actually make is a trade, not a win: removing
> it costs about one case in 27, and buys 28% fewer model calls and a verifier
> that returns the same verdict every run. The switch is still in the tree so you
> can disagree with me by re-running it.

---

## 4:15–5:00 — Failure mode and hot take

**On screen:** failure breakdown and self-verification tables.

> Here's why that verifier still wins, and it's the most interesting thing I
> found. **57% of remaining failures assert the wrong expected value** — the test
> reaches the bug, then asserts something the fixed code doesn't produce either.
>
> So the hot take. **A test that fails is not a test that reproduces — and the
> difference splits into a part you can verify without the answer, and a part you
> can't.**
>
> Whether a frame entered project code. Whether the asserted strings appear
> anywhere in the report. Whether the missing parameter is one the reporter asked
> for. All facts, all sitting in output most pipelines throw away.
>
> But whether the *expected value* is the one the fix produces is an oracle
> question, and the only oracle is a paragraph of prose written by a stranger.
> That's the part no rule can touch — and it's most of what's left, which is
> exactly why a model can still beat my rules there. My false-confidence rate sits
> at 68%; the model verifier gets it to 48%.
>
> So: make your verifier return a typed signal instead of a boolean, push
> everything you can into the part evidence can settle — it's more than you'd
> think — and put the human checkpoint exactly on the part that's left. That's why
> this thing proposes and stops.

---

## Checklist before recording

- [ ] `make report` run, `results/REPORT.md` current
- [ ] `make verify-scores` run clean, `results/SCORE_VERIFICATION.md` current
- [ ] Every number above cross-checked against that file
- [ ] `click__3105` demo rehearsed once — it repairs, which shows more than a
      first-try success: round 1 `broken_test`, round 2 `reproduced_assertion`,
      Fail-to-Pass YES, `$0.0000`, every call served `from_cache`
- [ ] Record `click__3105` and nothing else. It is the only case whose demo run
      is cached end to end. `tomlkit__291` replays for free but ends
      Fail-to-Pass NO, `click__2817` misses the cache and spends, and
      `jinja__1573` has no recorded demo run at all — any of the three would
      make live API calls or show a failure on camera
- [ ] No rehearsal run is *needed* to warm anything: the demo's prompts are
      committed under `data/cache/llm` and it writes no memory, so the first run
      on a fresh clone replays exactly like the tenth
- [ ] Terminal cleared, font enlarged
- [ ] Runtime under 5:00

## Notes on what to keep if you run long

Cut from 1:15–2:30 (the pipeline walk-through) before cutting anything in
3:15–4:15. The falsified-result section is the part of this submission that is
hard to fake, and it is the reason the numbers are worth trusting.
