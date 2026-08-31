# Does the advantage survive a change of model?

Every other number in this project was measured on one model. That leaves the obvious objection open: maybe the structure is incidental and the model is doing the work.

The test has to move **both** sides. `b1` is one general-purpose agent with the same tools, including the sandbox; `s5` is the shipped pipeline. Both are re-run on further models from other vendors, and what is compared is the **gap between them on the same model** -- absolute scores across different models are not comparable and are not presented as if they were.

| Model | Price in/out per M | `b1` same tools | `s5` Ratchat | Gap |
| --- | --- | ---: | ---: | ---: |
| `google/gemini-2.5-flash` | $0.300 / $2.50 | 6.0/27 (range 6-6) | **8.7/27 (range 8-9)** | **+2.7** (+44%) |
| `mistralai/mistral-small-3.2-24b-instruct` | $0.075 / $0.20 | 2.7/27 (range 2-3) | **6.3/27 (range 5-7)** | **+3.7** (+138%) |
| `openai/gpt-4o-mini` | $0.150 / $0.60 | 1.0/27 (range 1-1) | **2.0/27 (range 2-2)** | **+1.0** (at noise floor) |

The pipeline is ahead of the same-tools baseline on all 3 models, from 3 different vendors. It is ahead by more than the noise floor on 2 of them: **+2.7 (+44%)** on `gemini-2.5-flash`; **+3.7 (+138%)** on `mistral-small-3.2-24b-instruct`.

On `gpt-4o-mini` the margin is a single case, which is at the noise floor and is not evidence of anything on its own. What that run does show is a **bound on the claim**: both systems collapse to near zero there, so structure does not rescue a model that cannot write a working test in the first place. It widens the gap where the model is capable enough to act on instruction, and it cannot manufacture capability that is absent.


## The pipeline on the cheap model against the agent on the dear one

`s5` on `mistral-small-3.2-24b-instruct` scores 6.3/27 (range 5-7) against `b1` on `gemini-2.5-flash` at 6.0/27 (range 6-6), for $0.0101 a run against $0.2373 -- **24x cheaper**.

Those ranges overlap (5-7 against 6-6), so this **matches** rather than wins. A single run of the cheap pipeline scored 7 and looked like a clean win; two more runs turned it into a tie. The claim is that structure buys you as much as an order of magnitude of model price, not that it buys you more.

The dollar figures are not like-for-like in the cautious direction: the primary model's runs were partly served from the committed cache and so understate its true cost, while every cross-model call was live. The real ratio is larger than the one printed above.

Model calls per case, same order: `gemini-2.5-flash` b1 7.3, s5 3.1; `mistral-small-3.2-24b-instruct` b1 7.6, s5 2.9; `gpt-4o-mini` b1 8.2, s5 3.3
