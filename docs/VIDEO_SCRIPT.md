# Solution video — script and shot list

Target: **under 5 minutes**. Recorded by Abhinav.

Every number below appears in `results/REPORT.md`. Regenerate with `make report`
before recording and do not read a number that is not in that file.

Record at 1920×1080, terminal font large enough to read at half size. Keep the
command and its output on screen together.

## What the brief asks for, and where each part lands

The brief: *begin with the problem and the simple baseline, then walk through one
realistic execution from start to finish. Show the final comparison and briefly
explain the changelog. Highlight the change that contributed most, and one
experiment you removed.*

Six requirements, in the order the brief gives them:

| # | Required | Section | Length |
| --- | --- | --- | ---: |
| 1 | The problem | `0:00–0:35` | 35s |
| 2 | The simple baseline | `0:35–1:10` | 35s |
| 3 | One realistic execution, start to finish | `1:10–2:25` | 75s |
| 4 | The final comparison, and the changelog explained | `2:25–3:00` | 35s |
| 5 | **The change that contributed most** | `3:00–3:25` | 25s |
| 6 | **One experiment you removed** | `3:25–4:15` | 50s |
| — | Failure mode and hot take (not required; cut first if long) | `4:15–5:00` | 45s |

Requirements 5 and 6 are the two most often skipped, and they are the two easiest
to check against the repository, so say them in plain words rather than implying
them.

---

## What you are actually showing — read this first

**The demo finishes in about 3 seconds.** Every model call is served from the
committed cache, so there is no live typing to watch and nothing to wait for. Do
not try to narrate over a running command; there is no running command. The shape
of this recording is:

> **run it once, then scroll back up through the output and talk over it.**

The scrollback is the real output of the real run. Nothing is staged.

**Say the quiet part out loud, because it is a strength.** The model calls are
replayed from cache — that is why it is instant and free. **The test execution is
not cached.** Every round genuinely builds a container, checks out the commit,
injects the test and runs pytest, and the Fail-to-Pass check runs the test twice
more, at the buggy commit and at the real fix. Four real container runs in that
three seconds.

**Prove it on camera.** Split the terminal. Left pane runs the demo, right pane
runs:

```bash
watch -n 0.3 'docker ps --format "{{.Image}}  {{.Names}}"'
```

Containers named `ratchat-<hex>` on image `ratchat-env:click` appear and vanish
while the demo runs. That one shot answers "is this real or a recording" better
than anything you can say.

### The five screens, in order

| # | On screen | Command | What appears |
| --- | --- | --- | --- |
| 1 | The bug report | `python3 -m ratchat.demo --case-id click__3105` | 137 lines, instantly. Scroll to the top. |
| 2 | The run | *(scroll down)* | `RATCHAT RUNNING`, the two rounds and their verdicts |
| 3 | The test | *(scroll down)* | `PROPOSED TEST` — the generated pytest file |
| 4 | The proof | *(scroll down)* | `GROUND TRUTH` — parent `failed`, fix `passed`, **Fail-to-Pass: YES** |
| 5 | The stop | *(scroll down)* | `HUMAN CHECKPOINT` — it proposes and stops |

Then two document screens: `results/REPORT.md` for the tables, and
`CHANGELOG_IMPROVEMENT.md` for the two results that went against you.

### There is no UI, and that is the correct answer

This is a developer tool and an evaluation. The deliverable is the agent system
and the evidence that it works, not a screen. Do not apologise for the terminal
and do not build a wrapper around it — a dashboard would add nothing a judge can
check, and the whole submission argues for checkable claims over presentation.

What replaces a UI is **artifacts a reviewer can act on**. Show them.

### Optional 20-second shot: the output is a real patch

Strong, concrete, and it costs nothing:

```bash
python3 -m ratchat.demo --case-id click__3105 --approve
ls proposals/click__3105/
```

```
REPRODUCTION.md   add-test.patch   test_reprobot_click__3105.py   trajectory.jsonl
```

Then prove the patch is real against the upstream project, not a toy:

```bash
cd data/repos/click
git checkout 5b9630f50fde          # the commit where the bug is still present
git apply --check ../../../proposals/click__3105/add-test.patch && echo APPLIES
```

It prints `APPLIES`. That is the maintainers' actual repository, at the actual
buggy commit, accepting the generated test as a clean patch that adds one file and
touches nothing else.

> This is what it hands a maintainer: the test, a patch that applies to their
> repository, the verifier's evidence, the attempts it rejected, and the part it
> could not establish. Then it stops and asks.

Afterwards put the clone back with `git checkout main`.

### Landmarks in the demo output

Run once, then scroll to these. Line numbers are from the current committed run.

- **lines 2–52** — `THE BUG REPORT`: the real issue text, prose, unedited
- **lines 54–64** — `RATCHAT RUNNING`: the pipeline line, then
  `round 1: broken_test (AttributeError)` and
  `round 2: reproduced_assertion (no exception)`, each with the verifier's reason
- **lines 66–95** — `PROPOSED TEST`: the actual generated test file
- **lines 97–108** — `GROUND TRUTH`: `at parent … failed`, `at fix … passed`,
  `Fail-to-Pass: YES`, then `4 model calls, 8956 tokens, $0.0000`
- **lines 110–137** — `HUMAN CHECKPOINT`

**Pause longest on the two verdict lines and on the Fail-to-Pass block.** Those
are the argument. Everything else is context.

**One thing not to dwell on:** the generated file is named
`tests/test_reprobot_click__3105.py`. The project was renamed late and that string
is frozen because it is part of the model cache key — the README explains it. Do
not read it aloud; if you want to pre-empt it, one clause is enough: "the filename
still carries the old project name, and the README explains why that string is
load-bearing."

### What you cannot run live

`make verify-scores` takes about **10 minutes** — it re-runs 459 case-scores in
Docker. Do not run it on camera. Show the committed
`results/SCORE_VERIFICATION.md` instead, and say it is reproducible by anyone with
Docker and no API key.

---

## 0:00–0:35 — Requirement 1: the problem

**On screen:** run `python3 -m ratchat.demo --case-id click__3105`. It completes
in about three seconds. Scroll back to the top and hold on `THE BUG REPORT` while
you talk.

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

## 0:35–1:10 — Requirement 2: the simple baseline (and a fairer one)

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

## 1:10–2:25 — Requirement 3: one realistic execution, start to finish

**On screen:** scroll from the bug report down into `RATCHAT RUNNING` and stop on
the two round lines. The run took two rounds: the first attempt comes back
`broken_test`, the repair fixes it, and the second is a reproduction that goes on
to pass Fail-to-Pass. If you are using the split pane, this is where the
`docker ps` side already showed containers appearing.

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

## 2:25–3:00 — Requirement 4: the final comparison, and the changelog

**On screen:** the headline table in `results/REPORT.md`, then scroll
`CHANGELOG_IMPROVEMENT.md` so the ladder table is visible.

> Here is the final comparison. **8.7 out of 27 against the fair baseline's 6.0** —
> a 45% relative improvement, using 3.1 model calls per case against its 7.3.
> Three runs each, and the ranges don't overlap: 8 to 9 against 6 to 6.
>
> The changelog is this table plus the evidence for every row. Each row is the
> same evaluation re-run with exactly one thing switched, so a difference can be
> attributed to that thing — and where it can't, it says so.
>
> Because that's the *only* comparison here I'll actually claim. The middle rungs
> were run once each and land inside that range. At 27 cases one case is nearly
> four percentage points.

---

## 3:00–3:25 — Requirement 5: the change that contributed most

**On screen:** stay on the ladder table. Point at the `b1` row, then the `s1` row.

> So which change actually did the work? The table answers it, and the answer is
> the first structural one.
>
> **Going from the general-purpose agent to the structured pipeline is worth two
> whole cases — 6.0 to 8.** That's the largest single step in this table, and the
> only one bigger than the noise floor. Every rung after it moves by one case or
> less.
>
> And it isn't more tool access — B1 already had the sandbox and the test runner.
> What changed is that the verifier stopped returning pass-or-fail and started
> returning *where* the failure happened, and that verdict is what drives the
> repair. Structure over access. That's the contribution.
>
> I'll be straight about the rest: on 27 cases I cannot rank the later rungs
> against each other, and the changelog says that rather than dressing it up.

**Pause here.** If the recording runs long, this is the last section to cut, not
the first.

---

## 3:25–4:15 — Requirement 6: the experiment I removed

**On screen:** the `x1` row in the headline table, then the held-out table.

Lead with `x1` — that is the removed experiment the brief asks for. `s6` is a
bonus and goes second; drop it entirely if you are running long.

> The experiment I removed is `x1`, and it's the uncomfortable one, so I'll put it
> plainly. `x1` replaces my deterministic verifier with a model asked "did this
> reproduce the bug?" **I removed it, and it is still beating me** — 10.3 against
> 8.7, and it wins on the held-out cases too.
>
> On a smaller run the two tied exactly, and I wrote that up as: the model was only
> paying to notice one thing a rule notices for free. Doubling the dataset killed
> that story, so I killed the write-up.
>
> The claim I actually make is a trade, not a win. Removing it costs about one case
> in 27, and buys 28% fewer model calls and a verifier that returns the same
> verdict every run — the thing this whole project is about. The switch is still in
> the tree, so you can disagree with me by re-running it.
>
> There's a second one on this slide. I found a blind spot in my verifier and fixed
> it — `s6` — and it scores higher, 9.3 against 8.7. But I found that blind spot
> *on the evaluation split*, so I'd tuned a rule against my own test set. I added
> five repositories afterwards: thirteen cases the rule never influenced. On those
> **`s6` scores 4.3 against `s5`'s 4.7.** Worse. It didn't generalise, so it didn't
> ship.

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

## Every command, in order

Tested end to end. Run the whole thing once as a rehearsal before recording; it
takes under a minute and costs nothing.

**Before you hit record** — confirm the machine is camera-ready:

```bash
cd /data/Projects/ratchat
make test                      # expect: 28 passed
git status --short             # expect: no output
docker images | grep ratchat-env | wc -l    # expect: 9
```

**Split pane, right side** — start this first and leave it running:

```bash
watch -n 0.3 'docker ps --format "{{.Image}}  {{.Names}}"'
```

**Left side, shot 1 — the run (screens 1 to 5).** Clear, run, then scroll up:

```bash
clear
python3 -m ratchat.demo --case-id click__3105
```

Expect: 137 lines in ~3 seconds, `Fail-to-Pass: YES  (ok)`, `$0.0000`, and
containers flashing in the right pane. Scroll to the top and walk down through
the five screens.

**Shot 2 — the tables.** `-l md` gives syntax colouring; plain `cat` is fine too:

```bash
bat -l md --paging=never results/REPORT.md
bat -l md --paging=never results/SCORE_VERIFICATION.md
bat -l md --paging=never CHANGELOG_IMPROVEMENT.md
```

**Shot 3 — the output is a real patch (optional, ~20s):**

```bash
python3 -m ratchat.demo --case-id click__3105 --approve
ls -1 proposals/click__3105/
bat --paging=never proposals/click__3105/add-test.patch
```

```bash
cd data/repos/click
git checkout 5b9630f50fde
git apply --check ../../../proposals/click__3105/add-test.patch && echo APPLIES
git checkout main          # put the clone back
cd ../../..
```

Expect `APPLIES`. Do not skip the `git checkout main` at the end.

**What each command is for:**

| Command | The feature it demonstrates |
| --- | --- |
| `python3 -m ratchat.demo --case-id click__3105` | the whole pipeline, the typed verdicts, the repair loop, and the Fail-to-Pass check |
| the `watch docker ps` pane | the sandbox is real — every round runs in a container with no network |
| `--approve` + `ls proposals/...` | it produces a reviewable bundle, not just a string |
| `git apply --check` | the patch applies to the maintainers' own repository at the buggy commit |
| `results/REPORT.md` | the measured comparison against a baseline holding the same tools |
| `results/SCORE_VERIFICATION.md` | every number re-derivable with no model and no API key |
| `CHANGELOG_IMPROVEMENT.md` | the results that went against me, with the evidence |

## Actually recording it

Hyprland is Wayland, so `wf-recorder` is the tool. Verified on this machine:
1920×1080 h264 video with 48 kHz stereo AAC audio.

**Check the microphone first.** The default input here is a Bluetooth headset, and
Bluetooth mics switch the headset into HFP/HSP mode, which is narrow-band and
sounds noticeably worse than the built-in mic. List the options and pick
deliberately:

```bash
pactl list short sources
pactl get-default-source
```

Prefer the built-in analog input over `bluez_input.*`, or use a wired mic:

```
alsa_input.pci-0000_05_00.6.analog-stereo     # built-in, 48 kHz
```

**Twenty-second mic test, then listen back.** Speak normally, `Ctrl+C` to stop:

```bash
cd ~/Videos
wf-recorder -o eDP-2 --audio=alsa_input.pci-0000_05_00.6.analog-stereo -f miccheck.mp4
ffmpeg -i miccheck.mp4 -af volumedetect -f null - 2>&1 | grep -E "mean_volume|max_volume"
```

`mean_volume` around **-25 to -15 dB** is right. Below -40 dB means the mic is not
picking you up. Above -6 dB will clip.

**The real take.** Put the terminal fullscreen on the monitor you name with `-o`
(`hyprctl monitors` lists them; `eDP-2` is the laptop panel, `HDMI-A-1` the
external). Recording one output keeps the other screen out of frame:

```bash
cd ~/Videos
wf-recorder -o eDP-2 --audio=alsa_input.pci-0000_05_00.6.analog-stereo \
  -c libx264 -p crf=20 -p preset=veryfast -f ratchat-demo.mp4
```

`Ctrl+C` in that terminal stops the recording and finalises the file. Run it in a
*second* terminal on the other monitor, or the stop keystroke lands in the shot.

**Check the take before you trust it:**

```bash
ffprobe -v error -show_entries format=duration -of csv=p=0 ratchat-demo.mp4   # < 300
ffprobe -v error -show_entries stream=codec_type -of csv=p=0 ratchat-demo.mp4 # video + audio
```

If it is over 5:00, see "Notes on what to keep if you run long" at the bottom —
cut the hot take first, never requirements 5 and 6.

**If you would rather have scenes, webcam or a pause key**, OBS is installed and
works on Hyprland through PipeWire; pick "Screen Capture (PipeWire)" as the
source. `wf-recorder` is the faster path if you are recording one straight take.

**The form wants a URL, not a file.** Upload to YouTube (unlisted is fine) or
Google Drive with link sharing on, and check the link in a private window before
submitting.

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
- [ ] Scrollback long enough to hold 137 lines (the demo prints it all at once)
- [ ] Optional split pane running
      `watch -n 0.3 'docker ps --format "{{.Image}}  {{.Names}}"'` — the strongest
      single shot in the recording, because it shows the sandbox is real
- [ ] Runtime under 5:00

## Notes on what to keep if you run long

Sections 1–6 are all required by the brief. Cut in this order:

1. **`4:15–5:00`, failure mode and hot take** — not required by the brief. Losing
   it costs nothing against the rubric.
2. **The `s6` half of `3:25–4:15`** — the brief asks for *one* removed experiment,
   and `x1` is that one. `s6` is a bonus.
3. **Narration inside `1:10–2:25`** — trim the pipeline walk-through, but keep the
   two verdict lines and the Fail-to-Pass block on screen. That is requirement 3.

Do not cut `3:00–3:25` or the `x1` part of `3:25–4:15`. Those are requirements 5
and 6, they are the two most commonly skipped, and they are the parts of this
submission that are hardest to fake.
