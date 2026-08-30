# Reproduction guide

Written for someone starting from an empty machine who has never seen this
project. Take section 1 first: it costs nothing, needs no account and no model,
and it answers the question that matters — are the reported numbers real. Section
2 re-runs everything live against your own key.

---

## 0. What you need

| | |
| --- | --- |
| OS | Linux or macOS. Everything that executes untrusted test code runs in Docker. |
| Docker | 24 or newer, daemon running, able to run containers as your user. Built and measured on Docker 29.7.2. |
| Python | 3.10 or newer on the host. Measured on CPython 3.14.7. The sandbox is always Python 3.12 regardless of your host. |
| git | 2.30 or newer. |
| Disk | About 3 GB: ~400 MB of repository clones and ~2 GB of Docker images. |
| Network | Needed once, to clone the repositories and build the images. Test execution itself always runs with `--network none`. |
| `gh` CLI | Only for `make dataset`, which re-mines the case set from the GitHub API. Not needed to reproduce results. |

No API key is required for the replay path.

```bash
git clone https://github.com/OfficialAbhinavSingh/Frontier-Engineering-Challenge-2026-Abhinav.git
cd Frontier-Engineering-Challenge-2026-Abhinav
python3 -c "import sys; print(sys.version)"   # 3.10+
docker run --rm hello-world                   # docker works
```

There are no Python dependencies to install. The project uses only the standard
library on the host; everything else lives inside the sandbox images.

---

## 1. Verify the numbers, offline, for $0

There are two offline checks and they answer different questions. Take the first
one: it is exact, it needs no API key, and no model is involved in it at any
point.

### 1a. Re-derive every reported score yourself (exact)

Every result file records the exact `test_source` that run produced. Scoring a
test source is a *pure* operation — check out the parent commit, run the test,
check out the fix commit, run it again — so it can be repeated by anyone with
Docker, with no model, no key and no cache.

```bash
make repos          # clone the target repositories        (~8 min, ~700 MB)
make validate       # build sandbox images, re-verify cases (~25 min first time)
make controls       # the metric's ceiling and its two floors (~3 min)
make verify-scores  # re-derive every Fail-to-Pass flag in results/
```

`make controls` is the quickest thing here that tells you whether the metric is
real, and it is the one to run first if you only run one. It scores three inputs
whose answers are known in advance and calls no model:

| Control | Must score | Scored |
| --- | --- | ---: |
| `c_gold` — the maintainer's own regression test | 27/27 | **27/27** |
| `c_sabotage` — a test that always fails | 0/27 | **0/27** |
| `c_vacuous` — a test that always passes | 0/27 | **0/27** |

This is also what CI runs on every push, on a machine with no secrets, so you can
read the result rather than take the claim: the `checks` badge at the top of the
README is this table, re-derived in about a minute from a fresh clone.

The two floors must score zero for *different* reasons — `did_not_pass_at_fix`
and `did_not_fail_at_parent` — because Fail-to-Pass is a conjunction and each
floor tests one half of it. `make test` asserts all of this, so a control that
drifts fails the suite instead of sitting in the report looking like evidence.

This writes `results/SCORE_VERIFICATION.md`, re-deriving the flag for every case
in every result file and printing any disagreement by case. The measured result,
committed alongside this guide:

**20 result files, 540 case-scores, 0 mismatches.** Every Fail-to-Pass number in
the report was re-derived exactly from the committed test sources, with no model
and no API key. If your run does not come back clean, a number in the report is
wrong and should not be believed.

`make validate` is worth running for its own sake: before any case is allowed
into the dataset, the *maintainer's own* regression test has to demonstrate
Fail-to-Pass in your Docker, on your machine. That is the ground truth the whole
result rests on, and it is independently checkable.

### 1b. Replay the runs from the committed model cache (partial — measured)

Every model response behind every reported number is committed to
`data/cache/llm/`, keyed by a hash of the exact request. Replay mode serves them
from that cache and refuses to invent one it does not have.

```bash
make replay        # re-run the variants from cache
make replay-check  # measure how exactly that reproduced the recorded runs
```

**This does not reproduce every run, and the extent is measured rather than
claimed.** `make replay-check` writes `results/REPLAY_FIDELITY.md`; the measured
result on the 27 evaluation cases is:

| Variant | Runs reproduced byte-identically |
| --- | ---: |
| `b0` — one prompt, no tools | **27/27** |
| `s5` — the shipped system | 15/27 |
| `b1` — the general-purpose agent baseline | 8/27 |

**Why, precisely.** pytest prints its own runtime into its output
(`1 failed in 0.02s`). That output is quoted verbatim into repair prompts, and in
`b1`'s case into the agent's whole running conversation. A prompt that differs by
a few characters is a different cache key, so that lookup misses, and in replay
mode the run ends there rather than inventing a response. `b0` reproduces
perfectly because it never sees pytest output at all — it makes one call and
stops.

It compounds through repository memory: a case that ends early writes no lesson,
so every later case in that repository gets a different prompt too, and misses in
turn. That is why `b1`, which quotes the most execution output, degrades the
furthest.

**Why it is not fixed.** The fix is to normalise timings out of the text before it
enters a prompt. That changes every prompt, therefore every cache key, therefore
invalidates the entire committed cache — and regenerating it means re-running
every variant live, which costs more than this project's remaining budget. The
honest options were to ship a partial replay described accurately, or to quietly
drop the claim. This is the first.

**What that means for trusting the numbers.** Nothing, because 1a does not depend
on the cache. The reported scores are re-derivable exactly, by re-running the
committed test sources in your own sandbox. The cache replay is a convenience for
watching the agents work without paying, and it is honest about how far it goes.

What each step does, and what you should see:

- **`make repos`** clones sqlglot, tomlkit, click, jinja, rich and jsonschema
  into `data/repos/`.
  These are ordinary public repositories at full history; nothing is modified.
- **`make validate`** builds one Docker image per repository, then replays each
  case's *human-written* regression test to confirm it fails at the parent commit
  and passes at the fix commit. Cases that fail this check are dropped, and the
  reasons are written to `data/cases/dropped.json`. This is also the fastest way
  to confirm your Docker environment matches the one the results were produced
  in: if the harness cannot validate the maintainers' own tests, nothing
  downstream is meaningful.
- **`make replay`** runs every variant over the evaluation split, scoring each
  generated test against the real fix commit.

- **`make verify-scores`** re-runs every committed test source against both
  commits and compares the outcome with what `results/` reports. No model, no
  cache, no key.

If replay stops with `OfflineCacheMiss`, the cache does not contain that exact
request. Expect this: section 1b measures how often it happens and explains why.
It also happens if you changed a prompt, the model name or the case set. Use
`make verify-scores` for an exact check, or run live.

---

## 2. Live — run it yourself against your own key

```bash
mkdir -p ~/.config/openrouter
echo 'sk-or-v1-...' > ~/.config/openrouter/key
chmod 600 ~/.config/openrouter/key
# or: export OPENROUTER_API_KEY=sk-or-v1-...
```

```bash
make baseline    # b0 and b1
make solution    # the final systems, s5 and s6
make eval        # every variant, then rebuild the report
```

Override the model with `MODEL=`, and the split with `SPLIT=dev` or `SPLIT=all`:

```bash
make eval MODEL=google/gemini-2.5-flash SPLIT=eval
```

Live runs will not match the committed numbers exactly. The model is sampled at
temperature 0 but is not deterministic across time, and the repair loop amplifies
small differences: one different first attempt changes which repair path a case
takes. Expect the ordering of variants to hold and the rates to move by roughly
one case in either direction. This is stated plainly because it is the honest
limit of the result, and it is why the cache is committed.

Anything you run live is written into `data/cache/llm/`, so a repeat of the same
command is free.

---

## 3. One case, narrated

The run recorded in the solution video:

```bash
make demo                                   # click__3105, served from the cache
python3 -m ratchat.demo --case-id click__3105 --approve
```

It prints the bug report, each repair round with the verifier's verdict, the
proposed test, and the Fail-to-Pass check against the real fix commit. Without
`--approve` nothing is written anywhere; with it, the test is written under
`proposals/`. Ratchat never commits to a repository.

**`make demo` needs no API key and costs nothing.** Every model call in that run
is in `data/cache/llm/`, so it replays identically on a fresh clone: two rounds,
`broken_test` then `reproduced_assertion`, Fail-to-Pass **YES**, `$0.0000`.

That is true only of `click__3105`, which is why it is the default. Any other
`--case-id` is a **live run** that needs a key and costs a fraction of a cent —
including the other cases with recorded traces, which either miss the cache
partway (`click__2817`) or replay for free but end Fail-to-Pass NO
(`tomlkit__291`).

The demo deliberately does not save what it learns. Repository memory is injected
into the author's prompt, so a demo that wrote a lesson would change its own next
prompt, miss its own cache, and stop replaying — which is exactly what it used to
do. `tests/test_memory.py` guards this, `data/memory/demo/` must stay empty.

---

## 4. Rebuilding the dataset from scratch

Not needed to reproduce results, and it needs an authenticated `gh` CLI because
it reads linked issues through the GitHub API.

```bash
gh auth status
make dataset     # mine candidates from merged bugfix commits
make validate    # keep only the ones that provably reproduce
```

The case set will differ from the committed one: these repositories keep moving,
so a later mine sees commits that did not exist when this was built.
`data/cases/validated.json` is committed so results stay comparable.

---

## 5. Runtime and cost

Measured on an 8-core Linux host, Docker 29.7.2, from a cold start.

| Step | Wall clock | Cost |
| --- | --- | --- |
| `make repos` | 4–6 min | free |
| `make validate` (first run, includes image builds) | 25–40 min | free |
| `make validate` (images already built) | 10–20 min | free |
| `make verify-scores` (every recorded run, 20 result files) | 45–70 min | **$0** |
| `make replay` (every variant) | 25–40 min | **$0** |
| `make replay-check` (five variants) | 25–40 min | **$0** |
| `make eval` live (every variant) | 60–90 min | see `results/REPORT.md` |
| `make demo` (`click__3105`, cached) | 30–90 s | **$0.00, no key needed** |
| `--case-id` anything else (live) | 30–90 s | fractions of a cent |

Almost all of the wall clock is Docker, not the model: every attempt and every
score is a container start plus a pytest run, and the solver runs up to three
attempts per case. Cost per variant is measured, not estimated — OpenRouter
returns the dollar cost of each generation and it is recorded per call.

---

## 6. Layout

```
ratchat/
  dataset/mine.py       find candidate cases in merged bugfix commits
  dataset/validate.py   keep only cases whose human test provably reproduces
  sandbox/run.py        offline Docker execution, typed outcomes
  repo.py               read-only repository view, pinned at the buggy commit
  agents/cartographer.py  deterministic repo map (no model)
  agents/verifier.py    typed verdicts and the repair instruction for each
  agents/memory.py      per-repository lessons carried across cases
  agents/solver.py      the full pipeline
  agents/baselines.py   B0 and B1
  artifact.py           the reviewable bundle: patch, report, evidence
  eval/run.py           runs a variant and scores it against the fix commit
  eval/report.py        builds results/REPORT.md
  demo.py               one case, narrated
scripts/verify_scores.py    re-derives every reported score, no model involved
scripts/replay_fidelity.py  measures how exactly the cache reproduces the runs
scripts/build_trajectories.py  renders traces into the trajectory deliverable
data/cases/             mined and validated case sets
data/cache/llm/         committed model-response cache — what makes replay free
traces/                 one JSONL trajectory per case per variant
results/                per-variant results, the generated report, and the two
                        verification outputs
```

---

## 7. If something goes wrong

**`permission denied` from Docker.** Your user is not in the `docker` group. Add
it, log out and back in, or run the make targets with a Docker context you own.

**Every case fails validation.** Check `data/cases/dropped.json`. If the reason is
`gold_test_not_passing_at_fix`, the repository's dependency set has moved since
the images were built — rebuild them with `docker rmi ratchat-env:<repo>` and
re-run `make validate`.

**Replay raises `OfflineCacheMiss`.** The request is not in the cache. Confirm you
have not edited a prompt or changed `MODEL`, then re-run; otherwise run live.

**A case reports `timeout`.** The default per-run limit is 300 s. Slower machines
may need `--timeout 600` on `ratchat.eval.run`.
