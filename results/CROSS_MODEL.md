# Does the advantage survive a change of model?

Every other number in this project was measured on one model. That leaves the obvious objection open: maybe the structure is incidental and the model is doing the work.

The test has to move **both** sides. `b1` is one general-purpose agent with the same tools, including the sandbox; `s5` is the shipped pipeline. Both are re-run on a second model from a different vendor, and what is compared is the **gap between them on the same model** -- absolute scores across different models are not comparable and are not presented as if they were.

| Model | Price in/out per M | `b1` same tools | `s5` Ratchat | Gap |
| --- | --- | ---: | ---: | ---: |
| `google/gemini-2.5-flash` | $0.300 / $2.50 | 6.0/27 (range 6-6) | **8.7/27 (range 8-9)** | **+2.7** (+44%) |
| `mistralai/mistral-small-3.2-24b-instruct` | $0.075 / $0.20 | 2.7/27 (range 2-3) | **6.3/27 (range 5-7)** | **+3.7** (+138%) |

The pipeline beats the same-tools baseline on both models: **+2.7 cases (+44%)** on `gemini-2.5-flash` and **+3.7 cases (+138%)** on `mistral-small-3.2-24b-instruct`. The architecture, not the model, is what the improvement is attributable to.


## The pipeline on the cheap model against the agent on the dear one

`s5` on `mistral-small-3.2-24b-instruct` scores 6.3/27 (range 5-7) against `b1` on `gemini-2.5-flash` at 6.0/27 (range 6-6), for $0.0101 a run against $0.2373 -- **24x cheaper**.

Those ranges overlap (5-7 against 6-6), so this **matches** rather than wins. A single run of the cheap pipeline scored 7 and looked like a clean win; two more runs turned it into a tie. The claim is that structure buys you as much as an order of magnitude of model price, not that it buys you more.

The dollar figures are not like-for-like in the cautious direction: the primary model's runs were partly served from the committed cache and so understate its true cost, while every cross-model call was live. The real ratio is larger than the one printed above.

Model calls per case, same order: `gemini-2.5-flash` b1 7.3, s5 3.1; `mistral-small-3.2-24b-instruct` b1 7.6, s5 2.9
