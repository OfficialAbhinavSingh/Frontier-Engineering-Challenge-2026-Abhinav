# Results — `eval` split

Model: `google/gemini-2.5-flash`. Cases: 14. Primary metric: Fail-to-Pass, measured in a sandbox against the real fix commit, with no model involved in scoring.

## Headline comparison

| Variant | What it is | Runs | Fail-to-Pass | Rate | Model calls/case | Cost/run |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `b0` | one prompt, no tools, no execution | 1 | 2/14 | 14% | 1.0 | $0.0179 |
| `b1` | one general-purpose agent with tools and a test runner | 3 | 2.7/14 (range 2-3) | 19% | 7.2 | $0.1398 |
| `s1` | structured pipeline with sandbox verification and a repair loop | 1 | 3/14 | 21% | 2.7 | $0.0594 |
| `s2` | adds the deterministic repo map and in-repo example tests | 1 | 3/14 | 21% | 2.4 | $0.0440 |
| `s3` | adds failure-class-specific repair instructions | 1 | 3/14 | 21% | 2.4 | $0.0091 |
| `s4` | adds cross-case repository memory (full Repro-Bot) | 1 | 3/14 | 21% | 2.6 | $0.0159 |
| `s5` | adds minimal-claim authoring and over-specification repair (full Repro-Bot) | 3 | 4.3/14 (range 4-5) | 31% | 2.9 | $0.0467 |
| `s6` + | adds signature grounding: a missing API the report names is a reproduction | 3 | 5.0/14 (range 4-6) | 36% | 2.8 | $0.0122 |
| `x1` + | REMOVED: model-judged verification instead of traceback analysis | 3 | 5.0/14 (range 4-6) | 36% | 4.2 | $0.0447 |

**+ `s6`** — Post-hoc. The blind spot this fixes was found on the evaluation split, so this row is not a clean held-out result and is reported separately from the pre-registered comparison.

**+ `x1`** — Removed. Kept switchable so the claim can be re-run.

Model calls per case is the honest efficiency measure here. The dollar column is deflated for any variant whose prompts were already in the committed cache from an earlier run, so it understates what a cold run costs; the call count is not affected by caching.


## Per-case outcomes

First run of each variant.

| Case | `b0` | `b1` | `s1` | `s2` | `s3` | `s4` | `s5` | `s6` | `x1` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `click__2703` | · | · | · | · | · | · | · | · | · |
| `click__2817` | · | · | **pass** | · | · | · | · | **pass** | **pass** |
| `click__2968` | · | · | · | · | · | · | · | · | · |
| `click__3043` | · | · | · | · | · | · | · | · | · |
| `click__3105` | **pass** | · | **pass** | · | · | · | **pass** | · | **pass** |
| `sqlglot__7949` | · | · | · | · | · | · | · | · | · |
| `sqlglot__8225` | · | **pass** | · | **pass** | **pass** | **pass** | **pass** | **pass** | **pass** |
| `sqlglot__8244` | · | · | · | **pass** | **pass** | **pass** | **pass** | **pass** | **pass** |
| `tomlkit__440` | **pass** | **pass** | **pass** | **pass** | **pass** | **pass** | **pass** | **pass** | **pass** |
| `tomlkit__523` | · | · | · | · | · | · | · | · | · |
| `tomlkit__531` | · | **pass** | · | · | · | · | · | · | · |
| `tomlkit__542` | · | · | · | · | · | · | · | · | · |
| `tomlkit__543` | · | · | · | · | · | · | · | · | · |
| `tomlkit__562` | · | · | · | · | · | · | · | · | · |

## What the verifier saw

Every attempt the final system made, classified at the buggy commit with no access to the fix.

| Verdict at the buggy commit | Attempts | Share |
| --- | ---: | ---: |
| `reproduced_assertion` | 23 | 38% |
| `reproduced_exception` | 12 | 20% |
| `broken_test` | 11 | 18% |
| `no_fail` | 7 | 11% |
| `overspecified` | 5 | 8% |
| `reproduced_signature` | 3 | 5% |

## Where the final system still fails

| Outcome | Cases | Share |
| --- | ---: | ---: |
| `did_not_pass_at_fix` | 23 | 55% |
| `solved` | 15 | 36% |
| `did_not_fail_at_parent` | 3 | 7% |
| `empty_test` | 1 | 2% |

## Self-verification gap

The agent decides for itself whether it reproduced the bug. This is how often that judgement was wrong.

| Variant | Claimed reproduced | Actually Fail-to-Pass | False-confidence rate |
| --- | ---: | ---: | ---: |
| `s1` | 12 | 3 | 75% |
| `s2` | 13 | 3 | 77% |
| `s3` | 13 | 3 | 77% |
| `s4` | 13 | 3 | 77% |
| `s5` | 35 | 13 | 63% |
| `s6` | 38 | 15 | 61% |
| `x1` | 33 | 15 | 55% |
