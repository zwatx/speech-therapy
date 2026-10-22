# Assessment engineering content decisions

Model-reviewed engineering decisions and original illustrations for the 15 prompts in the pinned public pack `docs/consumer-assessment/proposed-engineering-pack.json` (SHA-256 `a957a9e3291f0d90b275d40cd914890836ee7e6fc4fd361f7589cd1444587ef3`).

Written by Opus 5.5 (`claude-opus-5-5`). The decisions are accepted for **engineering prototyping only**. Professional review is deferred until the product is finished (`professionalReview: "deferred_until_finished_product"`) and is not required for engineering prototyping. Nothing here is expert approval, clinical validity, a learner finding or production readiness.

## Files

| Path | Contents |
| --- | --- |
| `content-decisions.json` | One decision record per prompt (15) |
| `illustrations.json` | Registry mapping each of the 13 distinct words to its SVG |
| `illustrations/*.svg` | 13 original vector illustrations |

## Counts

15 prompts, 13 distinct source words, 17 variants, 23 target occurrences in total, 18 selected-position occurrences, 17 chosen occurrences (one per accepted variant).

## Decision record fields

Fields ending in `ByVariant` are objects keyed by variant ID (`"variant-1"`, `"variant-2"`). Index values are 0-based positions in that variant's source phone list.

| Field | Meaning |
| --- | --- |
| `promptId` | Source pack prompt `id` |
| `acceptedVariantIds` | Every dictionary variant; all are accepted for engineering exercise |
| `preferredVariantId` | Always `variant-1` (first listed dictionary form) |
| `chosenOccurrenceIndexByVariant` | The single engineering target index in each variant |
| `allTargetIndexesByVariant` | Every source occurrence of the target phone, copied unchanged |
| `selectedPositionIndexesByVariant` | Source selected-position indexes, copied unchanged |
| `modelSupport` | Model inventory support, model target ID and assessment availability |
| `decisionRationale` | Plain-language reason for the decision |
| `professionalReview` | `deferred_until_finished_product` |
| `instruction` | Neutral say-the-word, record and replay wording |
| `adultSupport` | Caregiver may read aloud and operate controls |
| `ageReadinessEngineeringBasis` | Engineering inclusion basis for the declared 6–12 scope; `developmentalNormClaimed: false` |

Extra context fields: `word`, `sourceWord`, `targetPhone`, `position`, `phonesByVariant` (source phones, unchanged), `retainedContextIndexesByVariant` (target occurrences that were not chosen), `occurrenceRule`, `preparationIssueCodes` (issue codes from the content-review packet, excluding the two pack-wide pending codes), `modelEngineeringReview` and `illustration`.

The root holds `schemaVersion: 1`, `sourcePackSha256`, `modelEngineeringReview: "accepted"`, `professionalReview`, `referenceVariety`, policies, counts and `claimLimits`. Every `claimLimits` flag is `false`.

## Decisions

- **Reference variety.** The baseline is a descriptive US-English engineering convention taken from the pack's dictionary pronunciations. It is not a standard of correctness. When the reference register is joined, acquired references may turn out to have a different variety label, or none; until then their labels are unknown. Reference-asset metadata did not exist when these decisions were written.
- **Variants.** All 17 dictionary variants are accepted for engineering exercise. They describe intended targets, not the phones a speaker actually produced. `variant-1` is preferred for every prompt. No source phones were changed.
- **Occurrences.** Each selected position maps to its exact source index. Banana is the only prompt where a first-occurrence rule is needed: index 2 (the first middle N) is chosen, index 4 is kept as context, and the rule is flagged `ruleSpecificFutureClinicalReviewRequired: true`.
- **Repeated targets** (baby, backpack, yo-yo). The chosen index follows the prompt's position. The other occurrence is kept as context.
- **Clusters** (bread B-R, sky S-K). These are recorded as context only, with no clinical inference drawn from them.
- **Alias.** The display word `yo-yo` maps to the source word `yoyo`, and the phones are unchanged.
- **Treasure / ZH.** The model inventory does not support ZH. The prompt is kept as content and as a negative case, and its assessment must be unavailable. No proxy phone is assigned.
- **Instructions.** These are limited to saying the word, recording and replaying. A caregiver may read aloud and operate the controls. There is no diagnosis, no corrective cue specific to any exercise, and no advice about mouth, tongue or lips.

## Illustrations

There are 13 self-contained SVGs, each with `viewBox="0 0 240 200"`. They share one style: 5 px black rounded outlines, white and light grey fills, and a single warm yellow accent used only where it helps the meaning (banana, sun, gold ring, coins, highlighted thumb). Each file has a `<title>` and a plain-meaning `<desc>`. They contain no text elements, fonts, scripts, event handlers, `foreignObject`, links or external references.

All geometry was newly drawn for this project. Nothing was traced or copied, and no third-party assets were used. The thumb picture is an open hand with the thumb highlighted. It identifies the word only and is not a therapy or placement instruction. The baby is a generic face with no identity. The registry records `origin: "generated_original_for_project"`, `thirdPartyAssetsUsed: false`, `meaningReview: "model_engineering_review"` and `professionalReview: "deferred_until_finished_product"`. It makes no copyright guarantee for any jurisdiction.

## Limits

- The author model accepted these decisions. They have not been independently reviewed yet.
- No professional, clinical or qualified approval exists. Age readiness is an engineering inclusion basis, not a developmental norm.
- Accepted variants are not a record of produced phones. Model outputs on these prompts are not clinical accuracy.
- Reference audio and rights are not verified, and the reference variety labels are still unknown.
- The illustrations have not been rendered or tested here. Gallery display and SVG parsing are left to the parent workflow.
- No mobile sources were opened. The pack's catalog source-hash declarations were not followed or reproduced.
