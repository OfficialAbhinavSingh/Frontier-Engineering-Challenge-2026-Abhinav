# Solution video — script and shot list

Target: **under 5 minutes**. Recorded by Abhinav.

Every number below appears in `results/REPORT.md`. Regenerate with `make report`
before recording and do not read a number that is not in that file.

Record at 1920×1080, terminal font large enough to read at half size. Keep the
command and its output on screen together.

---

## 0:00–0:40 — The problem

**On screen:** `python3 -m reprobot.demo --case-id click__2817` — stop after the
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
> The naive baseline is what people actually do — paste the report into a model,
> take the test back. **Two out of fourteen.**
>
> But I don't want to beat that. The honest baseline is the second row: one
> general-purpose agent, same model, same budget, and the same tools — including
> the sandbox, so it can run its own test. That's **2.7 out of 14**, averaged over
> three runs.
>
> B1 already has the test runner. So everything after this has to come from how
> the work is organised, not from being the only side that can execute anything.

---

## 1:15–2:45 — One realistic execution

**On screen:** let the `click__2817` demo run.

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

## 2:45–3:30 — The changelog

**On screen:** `CHANGELOG_IMPROVEMENT.md`, then the headline table.

> Every row is a measured run of the same evaluation with one thing switched.
>
> The structured pipeline with sandbox verification took the baseline's 2.7 to 3.
> The repo map, the in-repo examples, the typed repair prompts, the memory — each
> stayed at 3. On fourteen cases those steps are not separable, and I say that in
> the changelog rather than dressing it up as a ladder.
>
> The change that mattered was minimal-claim authoring: **3 to 4.3 out of 14**.
> That's the headline — a 59% relative improvement over the fair baseline, using
> 2.9 model calls per case against its 7.2.
>
> It came from reading traces, not scores. Every single case was self-reporting
> success on the first attempt, and half were still wrong. The tests weren't
> missing the bug — they caught it and thirteen other things, including help text
> the agent invented. So they failed at the buggy commit for the right reason and
> at the fixed commit for the wrong one.

---

## 3:30–4:20 — The experiment I removed, and why it's interesting

**On screen:** the `x1` and `s6` rows.

> Here's the one I removed — and it beat me first.
>
> The obvious way to build the verifier is to hand the pytest output to a model
> and ask "did this reproduce the bug?" I built it. It scored **5.0 against my
> 4.3**. My deterministic verifier lost.
>
> The whole gap was one case — this one. It asks for `CliRunner` to accept
> `catch_exceptions`. The fix *adds* that parameter. So the correct reproduction
> is calling it and getting a `TypeError` at the call site, with no project frame
> anywhere — which my `shallow_fail` rule threw out as a misused API, and then
> the repair loop turned a correct test into two worse ones.
>
> When the bug *is* a missing signature, that error is the symptom. So I fixed it
> deterministically: if the identifier the interpreter complained about is one the
> reporter asked for, that's a reproduction.
>
> After that fix, **5.0 against 5.0 — same mean, same range — at 2.8 model calls
> per case instead of 4.2.** The model verifier wasn't better. It was paying, on
> every attempt, to notice one thing a rule notices for free.
>
> That fix was found on the held-out split, so I report it as post-hoc and keep
> the pre-registered number as the headline instead of quietly swapping it in.

---

## 4:20–5:00 — Failure mode and hot take

**On screen:** failure breakdown and self-verification tables.

> Where it still fails: 55% of remaining failures assert the wrong expected value.
> The test reaches the bug and then asserts something the fixed code doesn't
> produce either.
>
> So the hot take. **A test that fails is not a test that reproduces — and the
> difference splits into a part you can verify without the answer, and a part you
> can't.**
>
> Whether a frame entered project code. Whether the asserted strings appear
> anywhere in the report. Whether the missing parameter is one the reporter asked
> for. All facts, all sitting in output most pipelines throw away. Typing those
> verdicts moved false confidence from 77% to 61% and beat a model-judged verifier
> using a third fewer calls.
>
> What's left doesn't yield to that. Whether the expected value is the one the fix
> produces is an oracle question, and the only oracle is a paragraph of prose
> written by a stranger.
>
> So: make your verifier return a typed signal instead of a boolean, push
> everything you can into the part evidence can settle — it's more than you'd
> think, and it's usually already in the output you discarded — and put the human
> checkpoint exactly on the part that's left. That's why this thing proposes and
> stops.

---

## Checklist before recording

- [ ] `make report` run, `results/REPORT.md` current
- [ ] Every number above cross-checked against that file
- [ ] `click__2817` demo rehearsed once — it repairs, which shows more than a
      first-try success
- [ ] `data/cache/llm` populated so the demo replays fast on camera
- [ ] Terminal cleared, font enlarged
- [ ] Runtime under 5:00
