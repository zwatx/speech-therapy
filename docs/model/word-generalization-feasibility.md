# Word-generalization feasibility

Metadata-only assessment, September 26, 2026. **Do not launch another training
study from this assessment.** A small word exclusion is technically possible,
but the child evaluation is too narrow to answer the broad pronunciation
question. Excluding the whole validation vocabulary almost eliminates fitting
data. No ratings, predictions, audio or feature arrays informed this assessment.

## Scope and fixed selection rule

Use the existing author-training cohort and five speaker splits. Retain only
word, utterance, speaker, age and target-identity metadata; discard rating fields
on load. Whole utterance text is already present in `cohort.clips`, so no score
file is needed. Normalize text with NFKC, uppercase and straight apostrophes;
tokenize alphanumeric words with internal apostrophes/hyphens. Do not stem words
or combine inflections. Every canonical target word matched its utterance text.

Before counting the results, fix two checks:

1. Purge every fitting utterance containing any target word in that split's
   inner validation vocabulary.
2. In fold zero, admit candidate words represented by at least three validation
   children aged 6–12 and five child target rows. Rank them by ascending SHA-256
   of `Cadence-word-purge-feasibility-v1:<WORD>` and take the first three. Apply
   that same set to the other four splits without reselection.

The second rule selects **WOULD, AND and YOU**. Ten words meet the candidate
support rule: WOULD, AND, YOU, THEN, NOT, SHE, IS, GO, HIM and THE, in hash order.
This rule was based on metadata support, not rating difficulty or model results.

For both checks, remove **every target row of a fitting clip** if the held-out
word occurs anywhere in its utterance. Evaluate only existing validation target
rows whose target word is held out. Retained fitting speakers and WAV hashes
remain disjoint from validation. The selected words are absent from every
retained fitting utterance, including contexts unrelated to the supervised target.

## Support

Purging the entire validation target vocabulary is not a viable multitarget fit:

| Inner split | Held-out word types | Remaining fit clips | Remaining fit target rows | Remaining fit speakers |
| --- | ---: | ---: | ---: | ---: |
| 0 | 610 | 20 | 101 | 13 |
| 1 | 541 | 11 | 53 | 7 |
| 2 | 629 | 12 | 72 | 10 |
| 3 | 604 | 9 | 39 | 6 |
| 4 | 605 | 8 | 35 | 5 |

For the fixed three-word set, fitting support remains substantial, while child
validation is small:

| Inner split | Retained fit clips / rows | Validation rows, all ages | Child validation rows / clips / speakers |
| --- | ---: | ---: | ---: |
| 0 | 1,243 / 7,234 | 88 | 27 / 20 / 4 |
| 1 | 1,236 / 7,337 | 89 | 42 / 35 / 8 |
| 2 | 1,248 / 7,421 | 88 | 40 / 33 / 6 |
| 3 | 1,215 / 7,107 | 79 | 15 / 14 / 6 |
| 4 | 1,223 / 7,240 | 79 | 33 / 28 / 9 |

Every selected validation slice covers only **D, N, W and Y**, four of the 23
eligible consonant targets. In fold zero, child support is D: 10 rows/3 speakers,
N: 2/2, W: 3/2 and Y: 12/3. These are target rows, not independent children.
The folds' inner validation sets overlap and must not be pooled as independent
observations.

Fold zero retains all 80 fitting speakers and all 23 target types. Its child fit
retains 3,359 rows in 628 clips from 38 speakers. Whole-utterance purging removes
354 of the original 1,597 fitting clips; **72 of those would survive a purge
based only on supervised target words**. Across splits, that missed-context
count is 72–80 clips. This confirms why the earlier unseen-target-word slice
does not establish word-disjoint evaluation.

## Interpretation and next step

The [earlier /R/ purge](local-training.md#speaker-and-target-word-purge-stress-test)
already warned that purging changes fit size and composition. It excluded only
the chosen /R/ target word; the whole-utterance check here is stricter. The
[multitarget plan](multiphone-training-plan.md#fixed-speaker-splits-and-lexical-limitations)
correctly requires removing exposure through other targets and audio contexts.

A fresh downstream head could support a narrow four-sound vocabulary stress
test, but this would not resolve the observed broad unseen-word reversal or
establish child pronunciation judgment. Rating-class support was deliberately
not examined, so even rare-rating metric feasibility is unknown. Do not select
replacement words by observed outcomes to make this slice look more informative.

Any future purged comparison would need fresh fit-only normalization, priors and
heads; current word-exposed warm starts cannot supply a purged baseline. The
upstream pretrained encoders may already have encountered these words, so the
claim would concern downstream fitting exposure only. Exact word-form purging
also leaves related inflections and other linguistic contexts available.

The useful next step is a deliberately designed speaker-and-word-separated
evaluation set with broader sound coverage and qualified production labels.
This feasibility check supplies no new clinical evidence and authorizes no
learner-facing correctness feedback.

## Audit provenance

Frozen inputs: cohort SHA-256
`33967da3dfb3e41a5c7b14dbd0355ceb36574ecbdcb042c8e99137f6344ec805`;
split SHA-256
`b480fa2550f240547565bfa9b0ca1e516ffc4b73e7770932dd94f006df702fcf`.
Both were checked before and after the audit. A read-only review inspected the
metadata-only diagnostic and reran it, reproducing the entire result exactly.
Byte-identical durable copies of the [diagnostic](../../research/audio-head/outputs/multiphone-20260926/word-generalization-feasibility-v1/feasibility.py)
and [detailed support artifact](../../research/audio-head/outputs/multiphone-20260926/word-generalization-feasibility-v1/feasibility.json)
are retained with the campaign outputs. The diagnostic writes its result to
`/tmp/cadence-word-generalization-feasibility.json`. Result SHA-256:
`15a70cd2e8c9479aa356a84219b0884b329a84957cea157d97a9a94d5ee54747`.
No existing study source, split, result, cache or model was changed.
