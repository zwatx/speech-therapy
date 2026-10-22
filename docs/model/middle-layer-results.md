# Middle-layer pronunciation comparison

Completed September 27, 2026. **The fixed middle-layer mixture passes every
declared consistency check and is a candidate for confirmation.** Its gain is
modest: 0.84% lower pooled loss than the retained mixture. It does not meet the
stronger material-improvement target, and no production or learner policy changes.

The [protocol](middle-layer-protocol.md) fixed normalized block-12 features
against a fresh final-layer control, with the same scalar inputs, PCA16,
training recipe and 25 speaker/word cells. The [feature audit](middle-layer-feature-results.md)
verified all 9,891 final-layer vectors exactly matched the old cache. Only the
acoustic representation changes in the matched comparison.

## Original child evaluation

All comparisons use the same 5,654 original positions, 1,037 recordings and
52 children ages 6–12, across 23 consonants. Votes are 532/705/27,033 for ratings
0/1/2. These are repeatedly used development cells, not a new independent test.
Lower NLL and Brier are better; higher average precision (AP) is better.

| Model | NLL | Macro-phone NLL | Brier | Rating-0 AP | Below-2 AP |
| --- | ---: | ---: | ---: | ---: | ---: |
| Retained mixture | 0.177459 | 0.189095 | 0.080372 | 0.092080 | 0.169876 |
| Fresh final-layer mixture | 0.177459 | 0.189095 | 0.080372 | 0.092080 | 0.169876 |
| Middle-layer mixture | **0.175968** | **0.188799** | **0.079702** | **0.094350** | **0.182523** |
| Fresh final-layer compact head | 0.179231 | 0.190216 | 0.080453 | 0.088972 | 0.173905 |
| Middle-layer compact head | 0.177245 | 0.190200 | 0.079635 | 0.092634 | 0.192146 |

The middle-layer mixture improves pooled NLL by 0.001491, macro-phone NLL by
0.000297, Brier by 0.000670, rating-0 AP by 0.002271, and below-2 AP by 0.012647
versus the retained mixture. It also passes the primary comparison with the
fresh final-layer mixture. The compact-head NLL co-condition passes, so the
mixture result is accompanied by a gain in the changed component itself.

Each speaker fold improves NLL versus the retained mixture:

| Fold | NLL change |
| --- | ---: |
| 0 | −0.001995 |
| 1 | −0.002147 |
| 2 | −0.000250 |
| 3 | −0.000489 |
| 4 | −0.002967 |

The stronger material target requires both at least 5% relative NLL reduction
and 0.01 absolute rating-0 AP gain. Observed gains are 0.84% and 0.002271;
that target fails. Below-2 AP measures ranking of subjective non-top-rating
votes, not diagnostic sensitivity, pronunciation accuracy or an operating
threshold. Aggregate and fold gains do not establish improvement for every
phone, child or age. NLL worsens for 13 of 23 phones and 20 of 52 children.
Age 6 is the one age group with worse NLL (+0.001059); the other six age groups
improve. Full subgroup results and support remain in the evidence. Ages 8 and
10 each contain only two children. These uneven gains matter for confirmation.

## Controls and execution

All 50 selection fits completed before their choices were frozen, followed by
50 fresh refits and then all 50 outer prediction sets. Selection fitting took
90.70 seconds and refitting 39.92 seconds on CPU, excluding the preparation and
earlier-freeze checks outside those phase timers. No Colab allocation was needed.
All 25 reused scalar reference cells replayed exactly with their original full
row ordering and batch grouping.

The fresh final-layer mixture and retained mixture differ in NLL, macro NLL and
Brier by less than 8e-12, with identical AP values. This is an implementation
control; it is not a statistical uncertainty estimate. All final-layer feature
vectors were exact, while very small downstream floating-point differences
remain possible when projecting and batching a subset of the original rows.

Across all inner/refit transforms, PCA16 retains 52.43–54.35% of variance in the
middle representation and 85.22–86.54% in the final representation. The largest
individual channel accounts for 2.09–2.48% and 1.85–2.14%, respectively. These
fit-only diagnostics are descriptive; they did not change component count,
normalization or selection. Every run's fitted rows and values are preserved.

The saved result was reconstructed separately from frozen predictions and
references. Independent source and feature reviews passed; the post-fit artifact
audit is recorded separately. No author-test audio was opened, encoder tuned,
threshold chosen, mixture weight searched or alternate layer tried.

The result supports a separately declared confirmation of this fixed candidate.
It does not finish the broader model-quality goal or justify learner judgments.
The current packaged research model remains retained pending confirmation;
clinical, learner-feedback and promotion flags remain false.

Evidence: [head plan](../../research/audio-head/outputs/multiphone-20260927/middle-layer-heads-v1/plan.json),
[selection freeze](../../research/audio-head/outputs/multiphone-20260927/middle-layer-heads-v1/inner-freeze.json),
[refit freeze](../../research/audio-head/outputs/multiphone-20260927/middle-layer-heads-v1/refit-freeze.json),
[outer freeze](../../research/audio-head/outputs/multiphone-20260927/middle-layer-heads-v1/outer-freeze.json),
[full results and subgroup tables](../../research/audio-head/outputs/multiphone-20260927/middle-layer-heads-v1/results.json),
and [head source review](../../work/middle-layer-heads-review-20260927/review.json).
