# First real Colab pronunciation-training pilot

Completed September 27, 2026. **The run worked; final-layer adaptation did not pass the improvement screen.** Keep the existing research reference and do not expand this particular recipe based on this result. Learner feedback, clinical eligibility and promotion remain disabled.

The [protocol](colab-expanded-pilot-protocol.md) was fixed before allocation. This was actual learning on permitted SpeechOcean recordings, not the earlier synthetic setup test.

## What ran

A Tesla T4 fitted a fresh rating head, then ran two matched continuations: head-only and head plus the final acoustic-encoder layer. Each continuation completed two epochs, 118 optimizer updates and 3,994 target-position exposures. Both selected epoch 1 using separate selection children; the cached baseline selected epoch 2. The selected adaptation therefore contains real encoder updates rather than silently reverting to epoch zero.

Training used 1,997 positions from 38 children, selection used 150 original positions from five other children, and the later comparison used 209 original positions from nine other children. Entire fitting/selection utterances containing the held-out word group were excluded. The comparison contains 22 consonants; JH has zero support and remains explicitly unevaluated. These are reused development data, not an untouched independent test.

## Results on the 209 comparison positions

Lower NLL, macro-phone NLL and Brier are better. Higher average precision (AP) is better; AP here ranks subjective rater outcomes and is not pronunciation accuracy.

| Candidate | NLL ↓ | Macro-phone NLL ↓ | Per-rater Brier ↓ | Rating-0 AP ↑ | Below-2 AP ↑ |
| --- | ---: | ---: | ---: | ---: | ---: |
| Frozen encoder | 0.168206 | 0.158318 | 0.075220 | 0.018854 | 0.159273 |
| Head-only continuation | 0.169703 | 0.155430 | 0.075789 | 0.022017 | 0.161806 |
| Final-layer adaptation | 0.169821 | 0.155464 | 0.075805 | 0.022017 | 0.161342 |
| Existing expanded mixture¹ | 0.165774 | 0.144730 | 0.075193 | 0.035237 | 0.187119 |

¹ Descriptive context only: the existing mixture uses a different seed, architecture and refit population, including its inner-selection rows. It is evaluated on identical comparison positions but is not a matched causal control.

Against the matched head-only control, adaptation increased NLL by 0.00011848, macro-phone NLL by 0.00003380 and Brier by 0.00001685. Rating-0 AP tied; below-2 AP decreased by 0.00046385. It therefore fails the declared primary screen. It also fails the required frozen-control screen because pooled NLL and Brier worsened, despite better macro-phone NLL and event ranking. These are small descriptive differences; this pilot does not establish statistical superiority or inferiority.

All 23 per-sound support cells and deltas are retained in the [independent evaluation](../../work/colab-expanded-pilot-20260927/evaluation.json), including improvements and regressions. No seed, epoch, threshold or held-out subset was changed after seeing these results.

## Compute and verification

The training/evaluation process took 186.7 seconds; the supervised allocation-through-shutdown window was 302.9 seconds. The observed rate was 1.07 units/hour. Colab displayed a balance change from 300.00 to 299.97 units; a follow-up check still reported 299.97, zero assignments and zero usage rate. The displayed 0.03-unit deduction may lag billing. Conservatively budgeting the full supervised window at the observed rate gives about **0.09 units**, comfortably below the five-unit pilot cap. This estimate is not a final invoice. The monthly authorization is 300 existing units across the work, with no purchases.

The run recorded Python 3.13.15, PyTorch 2.11.0+cu128, CUDA 12.8, Transformers 4.57.6 and NumPy 2.2.6. Peak allocated GPU memory was 1.70 GB. The runtime remains stopped.

- Eleven trainer tests passed locally, independently and on Colab; two mocked controller lifecycle tests passed.
- All 382 upload files were reviewed. The downloaded archive and all 19 result files passed hash checks.
- Cached/raw feature differences were at most 0.00001050 and probability differences at most 0.000000239 on the two declared fitting clips, within the fixed numerical tolerances.
- All three selected checkpoints replayed their selection predictions exactly. The reviewed trainer completed its nonzero-update and frozen-parameter checks; local evaluation independently rechecked prediction IDs, votes, metrics and artifact hashes.
- One observation timeout recovered while the same remote process continued. No restart or duplicate training allocation occurred.

Evidence: [session and shutdown ledger](../../work/colab-expanded-pilot-20260927/session-ledger.json), [post-shutdown usage](../../work/colab-expanded-pilot-20260927/post-shutdown-usage.json), [remote report](../../work/colab-expanded-pilot-20260927/results/training/report.json), [launch review](../../work/colab-expanded-pilot-20260927/launch-review.json), [evaluator review](../../work/colab-expanded-pilot-20260927/evaluator-review.json). The local recomputation does not independently replay the full CUDA optimizer trajectory.

## What changes next

This establishes a working, inexpensive route for real GPU experiments. It does not justify spending the remaining allowance on more of this final-layer recipe or cherry-picking another seed. The harder gap remains representative child error/produced-phone supervision and independent evaluation, especially younger children and speech-sound disorders.

The [new dataset search](dataset-refresh-20260927.md) identified a public 11-child microphone corpus as a concrete next recording-robustness resource, plus reference-speech and quality-label sources. Those datasets answer different questions and do not create missing pronunciation-error labels. No additional audio was acquired in that search. A next GPU study should first declare a materially different learning question or data source and appropriate held-out evaluation; no larger study was launched automatically.
