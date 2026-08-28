# Results — `dev` split

Model: `google/gemini-2.5-flash`. Cases: 6. Primary metric: Fail-to-Pass, measured in a sandbox against the real fix commit, with no model involved in scoring.

## Headline comparison

| Variant | What it is | Runs | Fail-to-Pass | Rate | Model calls/case | Cost/run |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `b0` | one prompt, no tools, no execution | 1 | 1/6 | 17% | 1.0 | $0.0000 |
| `b1` | one general-purpose agent with tools and a test runner | 1 | 1/6 | 17% | 8.5 | $0.0070 |
| `s1` | structured pipeline with sandbox verification and a repair loop | 1 | 3/6 | 50% | 2.3 | $0.0022 |
| `s2` | adds the deterministic repo map and in-repo example tests | 1 | 3/6 | 50% | 2.0 | $0.0000 |
| `s3` | adds failure-class-specific repair instructions | 1 | 3/6 | 50% | 2.0 | $0.0000 |
| `s4` | adds cross-case repository memory (full Repro-Bot) | 1 | 3/6 | 50% | 2.0 | $0.0000 |
| `s5` | adds minimal-claim authoring and over-specification repair (full Repro-Bot) | 1 | 3/6 | 50% | 2.7 | $0.0065 |
| `s6` + | adds signature grounding: a missing API the report names is a reproduction | 1 | 3/6 | 50% | 2.8 | $0.0112 |
| `x1` + | REMOVED: model-judged verification instead of traceback analysis | 1 | 3/6 | 50% | 4.5 | $0.0101 |

**+ `s6`** — Post-hoc. The blind spot this fixes was found on the evaluation split, so this row is not a clean held-out result and is reported separately from the pre-registered comparison.

**+ `x1`** — Removed. Kept switchable so the claim can be re-run.

Model calls per case is the honest efficiency measure here. The dollar column is deflated for any variant whose prompts were already in the committed cache from an earlier run, so it understates what a cold run costs; the call count is not affected by caching.


## Per-case outcomes

First run of each variant.

| Case | `b0` | `b1` | `s1` | `s2` | `s3` | `s4` | `s5` | `s6` | `x1` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `click__2263` | · | · | · | · | · | · | · | · | · |
| `click__2644` | · | · | · | · | · | · | · | · | · |
| `sqlglot__5178` | · | · | **pass** | · | · | · | **pass** | **pass** | **pass** |
| `tomlkit__291` | · | · | · | **pass** | **pass** | **pass** | · | · | · |
| `tomlkit__352` | · | · | **pass** | **pass** | **pass** | **pass** | **pass** | **pass** | **pass** |
| `tomlkit__439` | **pass** | **pass** | **pass** | **pass** | **pass** | **pass** | **pass** | **pass** | **pass** |

## What the verifier saw

Every attempt the final system made, classified at the buggy commit with no access to the fix.

| Verdict at the buggy commit | Attempts | Share |
| --- | ---: | ---: |
| `reproduced_assertion` | 4 | 44% |
| `reproduced_exception` | 2 | 22% |
| `no_fail` | 2 | 22% |
| `overspecified` | 1 | 11% |

## Where the final system still fails

| Outcome | Cases | Share |
| --- | ---: | ---: |
| `did_not_pass_at_fix` | 3 | 50% |
| `solved` | 3 | 50% |

## Self-verification gap

The agent decides for itself whether it reproduced the bug. This is how often that judgement was wrong.

| Variant | Claimed reproduced | Actually Fail-to-Pass | False-confidence rate |
| --- | ---: | ---: | ---: |
| `s1` | 6 | 3 | 50% |
| `s2` | 6 | 3 | 50% |
| `s3` | 6 | 3 | 50% |
| `s4` | 6 | 3 | 50% |
| `s5` | 6 | 3 | 50% |
| `s6` | 6 | 3 | 50% |
| `x1` | 5 | 3 | 40% |
