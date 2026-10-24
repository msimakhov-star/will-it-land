# Pre-registration: does Qloo grounding beat a language model guessing alone?

Written on 24 Oct 2026, before any real Qloo data was available (the hackathon API key had not arrived).
Committed to git so the timestamp is public. Whatever the numbers turn out to be, they go in the README and the submission.

## Ground truth
YouGov Ratings "fame": the share of US adults in each generation (millennials, Gen X, baby boomers) who say they have heard of a thing.
Public figures from yougov.com, fetched by `eval/yougov.py` into `eval/data/yougov_fame.csv` (1,827 TV shows, films, artists, brands, people, books and podcasts).

## Sample
`python -m eval.kill_test --n 300 --seed 7`: about 300 entities, balanced across Qloo entity types. Within each type, half the entities are random and half come from the top quarter by |millennial fame minus boomer fame|, so references that split by generation (what the product exists to catch) are represented. (Amended 24 Oct before any data: the first draft sampled only randomly, which an audit showed under-samples exactly those references.)
The language-model baseline is Claude Sonnet, asked for each generation's "% who have heard of it" with no data; guesses are cached per entity in `eval/out/llm_guesses.json` (the first batch on 22 Oct) and generated for any newly sampled entity before the Qloo side runs.

## Metrics (fixed now)
1. Pooled Spearman rank correlation between predicted and actual fame, over entity x generation, out-of-fold (5-fold CV by entity, seed 11), for:
   - `qloo`: the score model in `server/scoring.py` refitted on the training folds (popularity rarity + age affinity),
   - `llm`: the cached model guess,
   - `blend`: sum of the two z-scores,
   - `no_age`: Qloo model without age affinity (ablation: does the audience signal carry weight?).
2. Within-type versions of 1 (the correlation computed inside each entity type, then averaged), so neither side scores well merely by knowing that TV shows are more famous than podcasts.
3. Gap metric: Spearman between predicted and actual (millennial fame minus boomer fame), per entity. This is what an audience switch changes, so it is the headline for the product's core claim.

## What we will say for each outcome
- Qloo beats the model on the gap metric: headline it.
- Only the blend beats the model: "grounding adds X points over the model alone", and the product uses the blend.
- The model beats Qloo on both: say so plainly, keep the "AI alone" comparison in the product, and present where Qloo still adds what a model cannot (location, freshness after the model's training cut-off, stand-ins that exist in a real taste graph).

## Not claimed
Fame is "heard of", not "will laugh". No claim is made about whether a joke is funnier, and no claim about any individual.
