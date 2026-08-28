# Solution video — script and shot list

Target: **under 5 minutes**. Recorded by Abhinav. Numbers marked `<N>` are filled
from `results/REPORT.md` before recording — do not read a number that is not in
that file.

Record at 1920×1080. Terminal font large enough to read at half size. Two things
should be visible on screen at all times: the command being run and its output.

---

## 0:00–0:35 — The problem

**On screen:** a real issue from the dataset, in the browser or in the terminal
(`python3 -m reprobot.demo --case-id tomlkit__562` shows it in the first block).

**Say:**

> This is a bug report on a real Python library. Prose, written by a user.
> Before anyone can fix it, somebody has to turn it into a failing test inside
> that project's test suite — find the module, find the right test file, match
> the project's fixtures, and get the test to fail *because of this bug*.
>
> That step is the bottleneck, and it's the step people skip. Bugs get patched
> with no regression test and come back. And it's genuinely hard: SWE-bench, the
> standard benchmark for automated software engineering, had to hand-curate its
> failing tests. This couldn't be automated even by the people building a
> benchmark about it.

---

## 0:35–1:10 — The measurement, and the naive baseline

**On screen:** `results/REPORT.md`, headline table, B0 row highlighted.

**Say:**

> I measure one thing: Fail-to-Pass. The generated test has to fail at the
> commit where the bug is still present, and pass at the real fix commit. No
> model scores anything. A test that always fails is caught by the second
> condition; one that never fails is caught by the first.
>
> The naive baseline is what people actually do — paste the report into a model
> and take the test back. That scores `<B0>` out of `<N>`.
>
> But the honest baseline is the second one: one general-purpose agent, the same
> model, the same budget, and the same tools — including the sandbox, so it can
> run its own test. That's `<B1>`. Everything after this has to beat *that*.

---

## 1:10–2:40 — One realistic execution, end to end

**On screen:** live terminal.

```bash
python3 -m reprobot.demo --case-id <CASE>
```

Let it run. Talk over it.

**Say:**

> The cartographer is deterministic — no model. It ranks modules against the
> report and reads the project's real fixtures and import conventions out of its
> existing tests.
>
> The locator commits to a target module and a sibling test file before any code
> is written.
>
> The author writes the test with two of that project's *own* tests in front of
> it, so the style and the fixtures come from the repository rather than from the
> model's priors.
>
> Then it runs in a container with no network — and this is the part that
> matters.

**Pause on the verdict line.**

> The verifier doesn't return pass or fail. It reads the traceback and decides
> *where* the failure happened. A `TypeError` raised inside the project's code is
> a reproduction. The same `TypeError` raised in the test body, with no frame
> ever reaching project code, means the agent called the API wrong. Same exit
> code, same exception, opposite meaning — and each one gets a different repair
> instruction, because telling a model "make it fail" when it has misused the API
> pushes it towards weakening the assertion, which scores zero.

**On screen:** the Fail-to-Pass block at the end, then the human checkpoint.

> And it stops there. It proposes; it doesn't commit.

---

## 2:40–3:40 — The changelog and the final comparison

**On screen:** `CHANGELOG_IMPROVEMENT.md`, then the headline table again.

**Say:**

> Every row here is a measured run of the same evaluation with one thing changed.
>
> `<walk the ladder: s1 → s2 → s3 → s4 with the actual deltas>`
>
> The change that contributed most was `<BIGGEST>` — `<from X to Y>`.

---

## 3:40–4:20 — The experiment I removed

**On screen:** the s5 row.

**Say:**

> Here's the one I deleted. The obvious way to build the verifier is to hand the
> pytest output to a model and ask "did this reproduce the bug?" I built that,
> ran it, and it scored `<S5>` against `<S4>`.
>
> The reason is structural, not a prompting problem. Whether a traceback frame
> entered the project's code is already a fact in the output. Asking a model to
> infer it replaces a fact with an opinion at exactly the point the pipeline
> depends on being right. `<cite the false-confidence table>`

---

## 4:20–5:00 — Failure mode and hot take

**On screen:** the failure breakdown table.

**Say:**

> Where it still fails: `<MAIN FAILURE MODE>`.
>
> The hot take: **a test that fails is not a test that reproduces.** The
> interesting failure was never the model refusing to write a test — it was
> writing one that fails for the wrong reason, which is indistinguishable from
> success to any boolean check, and which a repair loop will then happily spend
> its whole budget polishing.
>
> If you're building agents, that generalises. Verification that returns a
> boolean tells your agent that something went wrong. Verification that returns a
> *typed* signal tells it what to do next — and it's usually already sitting in
> the output you threw away.

---

## Checklist before recording

- [ ] `results/REPORT.md` is current — regenerate with `make report`
- [ ] Every `<N>` above replaced with a number that appears in that file
- [ ] Demo case chosen and rehearsed once (pick one that repairs at least once —
      a first-try success shows less)
- [ ] Terminal cleared, font enlarged, `data/cache/llm` populated so the demo
      runs fast on camera
- [ ] Under 5:00
