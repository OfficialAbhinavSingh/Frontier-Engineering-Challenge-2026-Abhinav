# Reproduction guide

Written for someone starting from an empty machine who has never seen this
project. There are two paths. The first costs nothing and needs no account; take
it first, because it answers the question that matters — are the reported numbers
real. The second re-runs everything live against your own key.

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

## 1. Replay — reproduce every number, offline, for $0

Every model response behind every number in the report is committed to
`data/cache/llm/`, keyed by a hash of the exact request. Replay mode serves all
of them from that cache and refuses to invent one it does not have.

```bash
make repos      # clone the target repositories        (~5 min, ~400 MB)
make validate   # build sandbox images, re-verify cases (~25 min first time)
make replay     # re-run every variant from cache        (see timings below)
```

`make replay` writes `results/eval_*.json` and regenerates `results/REPORT.md`.
Compare that file to the one committed in the repository.

**What replay guarantees, precisely.** Verified on the final system over the
fourteen evaluation cases: **14 of 14 Fail-to-Pass verdicts reproduce
identically, at $0.00, with no API key**, and 43 of 43 model calls are served
from the committed cache.

**What it does not guarantee.** One case in fourteen took a different internal
path on replay while reaching the same verdict. The cause is worth stating
because it is a genuine limitation rather than flakiness: pytest prints its own
runtime into its output (`1 failed in 0.02s`), that output is quoted verbatim
into repair prompts, and so a repair prompt can differ by a few characters
between two runs. A different prompt is a different cache key, so that one
lookup misses; in replay mode the run then ends early for that case rather than
inventing a response.

The obvious fix is to normalise timings out of the text before it enters a
prompt. That is deliberately **not** applied here: it would change every prompt,
therefore every cache key, therefore invalidate the entire committed cache and
break the offline replay this section is about. Regenerating the cache costs
real money and would have exceeded this project's budget. The honest trade is to
ship a working replay with a documented edge, and to say which is which.

What each step does, and what you should see:

- **`make repos`** clones sqlglot, tomlkit, click and arrow into `data/repos/`.
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

If replay stops with `OfflineCacheMiss`, the cache does not contain that exact
request. That happens if you changed a prompt, the model name or the case set.
Restore those, or run live instead.

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
make demo                                   # first case of the eval split
python3 -m reprobot.demo --case-id click__2817
python3 -m reprobot.demo --case-id click__2817 --approve
```

It prints the bug report, each repair round with the verifier's verdict, the
proposed test, and the Fail-to-Pass check against the real fix commit. Without
`--approve` nothing is written anywhere; with it, the test is written under
`proposals/`. Repro-Bot never commits to a repository.

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
| `make replay` (every variant) | 25–40 min | **$0** |
| `make eval` live (every variant) | 60–90 min | see `results/REPORT.md` |
| `make demo` (one case) | 30–90 s | fractions of a cent |

Almost all of the wall clock is Docker, not the model: every attempt and every
score is a container start plus a pytest run, and the solver runs up to three
attempts per case. Cost per variant is measured, not estimated — OpenRouter
returns the dollar cost of each generation and it is recorded per call.

---

## 6. Layout

```
reprobot/
  dataset/mine.py       find candidate cases in merged bugfix commits
  dataset/validate.py   keep only cases whose human test provably reproduces
  sandbox/run.py        offline Docker execution, typed outcomes
  repo.py               read-only repository view, pinned at the buggy commit
  agents/cartographer.py  deterministic repo map (no model)
  agents/verifier.py    typed verdicts and the repair instruction for each
  agents/memory.py      per-repository lessons carried across cases
  agents/solver.py      the full pipeline
  agents/baselines.py   B0 and B1
  agents/memory.py      per-repository lessons carried across cases
  eval/run.py           runs a variant and scores it against the fix commit
  eval/report.py        builds results/REPORT.md
  demo.py               one case, narrated
data/cases/             mined and validated case sets
data/cache/llm/         committed model-response cache — this is what makes replay free
traces/                 one JSONL trajectory per case per variant
results/                per-variant results and the generated report
```

---

## 7. If something goes wrong

**`permission denied` from Docker.** Your user is not in the `docker` group. Add
it, log out and back in, or run the make targets with a Docker context you own.

**Every case fails validation.** Check `data/cases/dropped.json`. If the reason is
`gold_test_not_passing_at_fix`, the repository's dependency set has moved since
the images were built — rebuild them with `docker rmi reprobot-env:<repo>` and
re-run `make validate`.

**Replay raises `OfflineCacheMiss`.** The request is not in the cache. Confirm you
have not edited a prompt or changed `MODEL`, then re-run; otherwise run live.

**A case reports `timeout`.** The default per-run limit is 300 s. Slower machines
may need `--timeout 600` on `reprobot.eval.run`.
