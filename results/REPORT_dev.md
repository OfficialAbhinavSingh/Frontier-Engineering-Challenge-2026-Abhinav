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
| `s4` | adds cross-case repository memory (full Ratchat) | 1 | 4/13 | 31% | 2.2 | $0.0250 |
| `s5` | adds minimal-claim authoring and over-specification repair (full Ratchat) | 1 | 3/6 | 50% | 2.7 | $0.0065 |
| `s6` + | adds signature grounding: a missing API the report names is a reproduction | 1 | 7/13 | 54% | 2.7 | $0.0206 |
| `x1` + | REMOVED: model-judged verification instead of traceback analysis | 1 | 3/6 | 50% | 4.5 | $0.0101 |

**+ `s6`** — Post-hoc and not shipped. The blind spot this fixes was found on the evaluation split, so this row is not a clean held-out result. On the cases added afterwards it scores below s5, so the rule did not generalise and s5 remains the shipped system.

**+ `x1`** — Removed for determinism and cost, not because it lost -- it leads both overall and held out. Kept switchable so the claim can be re-run.

Model calls per case is the honest efficiency measure here. The dollar column is deflated for any variant whose prompts were already in the committed cache from an earlier run, so it understates what a cold run costs; the call count is not affected by caching.


## Per-case outcomes

First run of each variant.

| Case | `b0` | `b1` | `s1` | `s2` | `s3` | `s4` | `s5` | `s6` | `x1` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `click__2263` | · | · | · | · | · | · | · | · | · |
| `click__2644` | · | · | · | · | · | · | · | **pass** | · |
| `jinja__1253` | — | — | — | — | — | · | — | **pass** | — |
| `jinja__1413` | — | — | — | — | — | · | — | · | — |
| `jinja__1430` | — | — | — | — | — | · | — | · | — |
| `jsonschema__1389` | — | — | — | — | — | · | — | · | — |
| `rich__3569` | — | — | — | — | — | · | — | **pass** | — |
| `rich__3577` | — | — | — | — | — | **pass** | — | **pass** | — |
| `rich__3740` | — | — | — | — | — | · | — | · | — |
| `sqlglot__5178` | · | · | **pass** | · | · | · | **pass** | **pass** | **pass** |
| `tomlkit__291` | · | · | · | **pass** | **pass** | **pass** | · | · | · |
| `tomlkit__352` | · | · | **pass** | **pass** | **pass** | **pass** | **pass** | **pass** | **pass** |
| `tomlkit__439` | **pass** | **pass** | **pass** | **pass** | **pass** | **pass** | **pass** | **pass** | **pass** |

## What the verifier saw

Every attempt the final system made, classified at the buggy commit with no access to the fix.

| Verdict at the buggy commit | Attempts | Share |
| --- | ---: | ---: |
| `reproduced_assertion` | 4 | 50% |
| `reproduced_exception` | 2 | 25% |
| `overspecified` | 1 | 12% |
| `no_fail` | 1 | 12% |

## Where the final system still fails

| Outcome | Cases | Share |
| --- | ---: | ---: |
| `did_not_pass_at_fix` | 3 | 50% |
| `solved` | 3 | 50% |

## Clean held-out check

The signature-grounding rule in `s6` was written in response to a case on the first evaluation split, so that split is no longer held out for it. These repositories were added to the dataset afterwards and were never seen when the rule was designed.

| Variant | Fail-to-Pass on later repositories | Rate |
| --- | ---: | ---: |
| `s4` | 1.0/7 | 14% |
| `s6` | 3.0/7 | 43% |

## Self-verification gap

The agent decides for itself whether it reproduced the bug. This is how often that judgement was wrong.

| Variant | Claimed reproduced | Actually Fail-to-Pass | False-confidence rate |
| --- | ---: | ---: | ---: |
| `s1` | 6 | 3 | 50% |
| `s2` | 6 | 3 | 50% |
| `s3` | 6 | 3 | 50% |
| `s4` | 12 | 4 | 67% |
| `s5` | 6 | 3 | 50% |
| `s6` | 12 | 7 | 42% |
| `x1` | 5 | 3 | 40% |
