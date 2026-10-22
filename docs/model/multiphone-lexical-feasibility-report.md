# Canonical word- and speaker-disjoint feasibility

The existing corpus can support fresh-head baselines with held-out target words
excluded from every supervised fitting and selection utterance. All 23 phones
remain in every fitting and prospective refitting cell. This is a structural
feasibility finding, not evidence of model improvement or adequate statistical
power: child selection and rare-rating support are sparse.

The inventory crosses five existing speaker folds with five fixed word groups
for each age regime. Each original eligible outer position occurs exactly once
per regime across the 25 cells: 14,837 positions from 125 speakers, including
5,654 positions from 52 children aged 6–12. The source remains previously used
author-training development data. No model was trained or evaluated here.

## Canonical word identity and retained failure

The first [declared protocol](multiphone-lexical-feasibility-protocol.md) used
literal whitespace transcript tokens and stopped before grouping/support when
531 eligible rows in 305 clips failed word identity. For example, the transcript
has `QUARTER.` while the canonical target is `QUARTER`. Hashing those as different
words would permit lexical leakage.

The [canonical revision](multiphone-lexical-canonical-protocol.md) uses complete,
ordered word annotations from the previously verified position cohort, restricted
to the original 2,495 clips. It preserves the original cohort and the failed run.
It checks all 14,843 original canonical word/phone positions (including six
ineligible positions), all 14,837 eligible legacy identities and five-vote labels,
clip waveform hashes, speaker/age and complete canonical phone chains. The full
transcript differs from the canonical token sequence in 419 clips; 305 have the
observed target-row mismatch. Differences outside eligible target words are
retained too. No waveform was opened.

The hash seed, five groups and full crossing did not change after the input
failure. There was no support-based seed search, stopword removal or regrouping.

## Whole-utterance exclusion

The fixed mapping contains 1,884 uppercase canonical annotation word types.
A word belongs to the group given by SHA256 of the fixed seed, one NUL separator
and that token, interpreted as a big-endian integer modulo five. Entire fitting,
validation, selection and prospective refit recordings are excluded when any
canonical word belongs to that cell's held-out group. This includes words without
eligible target positions and every repeated occurrence. Outer evaluation keeps
only target positions in that word group; other words in an evaluation sentence
may be familiar.

| Word group | Word types | Blocked original recordings | Share blocked |
| --- | ---: | ---: | ---: |
| 0 | 370 | 1910 / 2,495 | 76.6% |
| 1 | 368 | 1732 / 2,495 | 69.4% |
| 2 | 383 | 2023 / 2,495 | 81.1% |
| 3 | 400 | 1858 / 2,495 | 74.5% |
| 4 | 363 | 1621 / 2,495 | 65.0% |

Frequently occurring blocked tokens include THE in group 0, A and YOU in
group 1, TO and I in group 2, IS and WAS in group 3, and IT and HE in group 4. These words were
retained in the exclusion rule. A later experiment would need 25 new heads per
regime per model family; the repeated fitting populations are not 25 independent
replications.

## Retained support

Ranges are across the 25 speaker×word cells in each regime. “Complete phone
inventory” counts cells containing at least one position for every phone. It
does not mean each phone has rare ratings or enough independent speakers.

| Regime / partition / population | Positions per cell | Speakers per cell | Complete phone inventory |
| --- | ---: | ---: | ---: |
| all-age / innerFit / all ages | 1647–3396 | 75–80 | 25 / 25 |
| all-age / selection / all ages | 384–870 | 19–20 | 25 / 25 |
| all-age / outerFit / all ages | 2098–4143 | 94–100 | 25 / 25 |
| child-only / innerFit / 6–12 | 848–1655 | 31–38 | 25 / 25 |
| child-only / selection / 6–12 | 143–475 | 5–11 | 18 / 25 |
| child-only / outerFit / 6–12 | 1096–1921 | 38–43 | 25 / 25 |
| either / outer / all ages | 421–738 | 25–25 | 20 / 25 |
| either / outer / 6–12 | 159–366 | 9–14 | 6 / 25 |

The seven child selection cells with missing phones are explicit below. Do not
drop them or change word grouping to obtain an easier comparison.

| Speaker fold | Word group | Child selection positions | Missing phones |
| --- | --- | ---: | --- |
| 0 | 1 | 191 | CH |
| 0 | 3 | 147 | JH, TH |
| 2 | 2 | 249 | TH |
| 2 | 3 | 199 | JH, TH |
| 2 | 4 | 263 | CH, TH |
| 3 | 2 | 205 | SH |
| 3 | 4 | 266 | CH |

Only six of 25 child outer cells contain all 23 phones. The all-age outer inventory
is missing DH in five cells. Pooling all crossed outer cells restores exact
original coverage, but must not conceal empty per-cell phone metrics.

## Rare-rating support

There are 575 phone×cell pairs per partition. The counts below lack at least one
of the event-positive or event-negative vote classes, so a discrimination metric
requiring both classes is undefined there. Votes from the same position or
speaker are not independent participants. These rows all use children aged 6–12.

| Child-only partition | Rating-0 pairs without both vote classes | Below-2 pairs without both vote classes |
| --- | ---: | ---: |
| innerFit | 86 / 575 | 73 / 575 |
| selection | 344 / 575 | 240 / 575 |
| outer | 376 / 575 | 302 / 575 |

No child-only fitting cell and no child outer cell has both rating-0 vote
classes for every phone. Pooled outer child data contain both event classes for
all 23 phones, but that fact does not repair sparse within-cell support. All
positive/negative vote totals and contributing speaker counts remain in the
machine inventory, with empty cells explicit.

## Verification

Fourteen distinct tests passed, covering non-target words, repeated occurrences,
whole-recording removal, empty support, speaker/age guards, full outer coverage,
canonical/legacy mismatches and preserved raw text. Independent GPT-6 Astra
review cleared both versions before declaration. The revised run and offline
reconstruction completed with exit zero. Independent artifact reconstruction,
without importing project code, passed 6,054,896 checks across annotation
identity, all 50 cells, every retained/excluded partition and all age/phone/event
support fields. No model, prediction or audio payload was opened.

Independent narrative review passed, including all 23 numerical table rows
and the sparse-support and interpretation limits. The failed literal-token run remains
recorded as a rejected input assumption, not a completed support inventory.
App builds/UI tests were not run because app behavior did not change. No Colab
allocation, author-test access or learner-feedback change occurred.

## Decision and next experiment

Proceed to a separately declared fresh-head baseline experiment on these fixed
memberships. Compare the combined phonetic/scalar representation with a matched
scalar-confidence baseline and fit-only priors. Initialize new heads; existing
supervised checkpoints may have seen held-out words. Compute normalization and
priors solely on each purged fit partition. Use a fixed per-rater NLL selection
criterion on the retained inner selection rows, which is defined even where a
phone is absent; do not select on sparse rare-event AP or silently shrink the
reported 23-phone inventory. Freeze all choices before outer predictions and
retain every missing/undefined metric.

This establishes downstream supervised-head word separation only. Encoder
pretraining exposure is unknown, and the architecture/hyperparameters have been
developed on this corpus before. It does not establish completely new words to
the whole model, independent final testing, clinical validity or reliable
pronunciation judgments. The broader improvement goal remains active and all
learner pronunciation judgments remain disabled.

## Artifacts

- [Failed literal-token declaration](../../research/audio-head/outputs/multiphone-20260927/lexical-feasibility-v1/plan.json): `206bd607bb5e553058be65afa9c04088105c71074bd54cad0d0c8a2c5f6fb1f5`.
- [Preserved failure](../../research/audio-head/outputs/multiphone-20260927/lexical-feasibility-v1/failure.json).
- [Canonical declaration](../../research/audio-head/outputs/multiphone-20260927/lexical-canonical-v1/plan.json): `c4484f79500bcba049a5b192aa8ec3935e01b44e48dbe99526c9b9c7ab097e8e`.
- [Complete inventory](../../research/audio-head/outputs/multiphone-20260927/lexical-canonical-v1/report.json): `1cb2953ef78cfba10f004598c84f4f1f8a43c66881dee36d5daf506880a731c4`.
- [Independent audit](../../work/lexical-feasibility-audit-20260927/audit-result.jsonl): `3598df83e15137f1cfa5ec33494e7115760ac2d494f2816906264ca2af8191a0`.

Reconstruct from `research/audio-head`, without model or audio access:

```sh
.venv/bin/python -m lexical_canonical.study verify \
  --plan outputs/multiphone-20260927/lexical-canonical-v1/plan.json \
  --plan-sha256 c4484f79500bcba049a5b192aa8ec3935e01b44e48dbe99526c9b9c7ab097e8e
```
