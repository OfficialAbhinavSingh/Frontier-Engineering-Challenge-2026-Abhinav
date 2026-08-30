# Results — `eval` split

Model: `google/gemini-2.5-flash`. Cases: 27. Primary metric: Fail-to-Pass, measured in a sandbox against the real fix commit, with no model involved in scoring.

## Headline comparison

| Variant | What it is | Runs | Fail-to-Pass | Rate | Model calls/case | Cost/run |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `b0` | one prompt, no tools, no execution | 1 | 5/27 | 19% | 1.0 | $0.0258 |
| `b1` | one general-purpose agent with tools and a test runner | 3 | 6.0/27 (range 6-6) | 22% | 7.3 | $0.2373 |
| `s1` | structured pipeline with sandbox verification and a repair loop | 1 | 8/27 | 30% | 2.7 | $0.0650 |
| `s2` | adds the deterministic repo map and in-repo example tests | 1 | 7/27 | 26% | 2.6 | $0.0979 |
| `s3` | adds failure-class-specific repair instructions | 1 | 8/27 | 30% | 2.6 | $0.0366 |
| `s4` | adds cross-case repository memory (full Repro-Bot) | 1 | 9/27 | 33% | 2.9 | $0.0668 |
| `s5` | adds minimal-claim authoring and over-specification repair (full Repro-Bot) | 3 | 8.7/27 (range 8-9) | 32% | 3.1 | $0.0770 |
| `s6` + | adds signature grounding: a missing API the report names is a reproduction | 3 | 9.3/27 (range 8-11) | 35% | 2.9 | $0.0264 |
| `x1` + | REMOVED: model-judged verification instead of traceback analysis | 3 | 10.3/27 (range 9-12) | 38% | 4.3 | $0.0678 |

**+ `s6`** — Post-hoc and not shipped. The blind spot this fixes was found on the evaluation split, so this row is not a clean held-out result. On the cases added afterwards it scores below s5, so the rule did not generalise and s5 remains the shipped system.

**+ `x1`** — Removed for determinism and cost, not because it lost -- it leads both overall and held out. Kept switchable so the claim can be re-run.

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
| `jinja__1463` | · | · | · | · | · | **pass** | · | · | · |
| `jinja__1510` | · | **pass** | **pass** | **pass** | **pass** | **pass** | · | · | **pass** |
| `jinja__1521` | · | · | · | **pass** | **pass** | **pass** | · | · | **pass** |
| `jinja__1573` | · | · | · | · | · | · | **pass** | **pass** | · |
| `jinja__1612` | **pass** | · | **pass** | · | **pass** | · | **pass** | **pass** | **pass** |
| `jinja__1701` | · | · | · | · | · | · | · | · | · |
| `jinja__2027` | **pass** | · | **pass** | **pass** | **pass** | **pass** | **pass** | **pass** | **pass** |
| `rich__3796` | · | · | · | · | · | · | · | · | · |
| `rich__3838` | · | · | · | · | · | **pass** | · | · | · |
| `rich__3881` | · | · | **pass** | **pass** | **pass** | · | **pass** | · | · |
| `rich__3943` | · | **pass** | **pass** | · | · | · | · | · | · |
| `rich__4041` | **pass** | **pass** | · | · | · | **pass** | **pass** | **pass** | **pass** |
| `rich__5090` | · | · | · | · | · | · | · | · | · |
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
| `reproduced_assertion` | 41 | 30% |
| `no_fail` | 29 | 21% |
| `shallow_fail` | 27 | 20% |
| `reproduced_exception` | 22 | 16% |
| `broken_test` | 14 | 10% |
| `overspecified` | 2 | 1% |

## Where the final system still fails

| Outcome | Cases | Share |
| --- | ---: | ---: |
| `did_not_pass_at_fix` | 46 | 57% |
| `solved` | 26 | 32% |
| `did_not_fail_at_parent` | 8 | 10% |
| `empty_test` | 1 | 1% |

## Clean held-out check

The signature-grounding rule in `s6` was written in response to a case on the first evaluation split, so that split is no longer held out for it. These repositories were added to the dataset afterwards and were never seen when the rule was designed.

| Variant | Fail-to-Pass on later repositories | Rate |
| --- | ---: | ---: |
| `b0` | 3.0/13 | 23% |
| `b1` | 3.3/13 | 26% |
| `s1` | 5.0/13 | 38% |
| `s2` | 4.0/13 | 31% |
| `s3` | 5.0/13 | 38% |
| `s4` | 6.0/13 | 46% |
| `s5` | 4.7/13 | 36% |
| `s6` | 4.3/13 | 33% |
| `x1` | 5.3/13 | 41% |

## Self-verification gap

The agent decides for itself whether it reproduced the bug. This is how often that judgement was wrong.

| Variant | Claimed reproduced | Actually Fail-to-Pass | False-confidence rate |
| --- | ---: | ---: | ---: |
| `s1` | 20 | 6 | 70% |
| `s2` | 24 | 7 | 71% |
| `s3` | 23 | 8 | 65% |
| `s4` | 23 | 8 | 65% |
| `s5` | 63 | 20 | 68% |
| `s6` | 74 | 28 | 62% |
| `x1` | 60 | 31 | 48% |
