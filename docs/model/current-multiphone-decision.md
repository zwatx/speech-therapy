# Current multi-sound research decision

Updated September 27, 2026. **Learner pronunciation judgments remain disabled.**
The models predict distributions of five subjective corpus ratings (0/1/2) at
requested canonical consonant positions. They do not establish which sound a
child produced or whether a pronunciation is clinically correct.

## Current experiment and retained candidates

The [fixed seed replication](multiphone-lexical-seed-replication-report.md) is
complete: all 600 initial fits, 600 fresh refits and 600 held-out prediction jobs,
independent saved-state and exact prediction checks, all 4,464 metric summaries,
exact offline reconstruction and the separate three-seed aggregate audit passed.
The plan is `130992603ce99158345f31ae62f427f0230b0d5503e9ac65d5b8bad55ee6cc26`.

None of the 18 same-seed primary comparisons passes the fixed screen. The child
mixture has worse Brier and below-2 AP at every seed; its NLL direction varies.
/W/ improves repeatedly, while /T/, /K/, /R/ and /NG/ worsen. Close this fixed
weighting study without adopting the rule as a general improvement. Keep the
unweighted expanded objective as the research reference and preserve the weighted
results for their documented tradeoffs.

The **unweighted expanded child mixture remains the research reference**.
Retain the recording/sound-unit-weighted checkpoints to reproduce the documented
tradeoffs. Each mixture combines a scalar head and a PCA16/scalar head with equal
probability weight. These are cross-fit experiment checkpoints and reproducible
evaluation recipes, not updated full-data inference bundles.
No seed was selected and neither model was promoted by the seed study.

The [unweighted expanded child mixture](multiphone-lexical-expanded-heads-report.md)
passes all six declared primary checks against its original-data counterpart at
seed 7: lower pooled NLL, macro NLL and Brier, better rating-0 and below-2 average
precision, and no worse child NLL in any speaker fold. Against the older
corrected-projection mixture, its secondary screen fails because fold 0 worsens.
Its /W/ loss also worsens; the all-age mixture does not pass its primary screen.

The [unit-weighted comparison](multiphone-lexical-unit-weights-report.md) shows a
tradeoff. None of its six primary comparisons passes against the corresponding
unweighted expanded model. The child weighted mixture improves /W/ but worsens
all five pooled endpoints and child NLL in folds 1/2/3. Its separate comparison
against the older corrected mixture passes all six checks, while /W/ still
worsens against that reference. This does not establish a uniformly better model.

The completed seed study tests weighting within each new seed and compares both
expanded mixtures with the fixed corrected seed-7 reference. It does **not**
retrain original-data baselines at each new seed. It therefore cannot establish
that the original expanded-versus-original-data gain is robust across seeds.

## Evidence across the improvement priorities

| Priority | Verified development evidence | Limit that remains |
| --- | --- | --- |
| All 23 consonants | Original and expanded comparisons retain every supported sound, rating-class support, speaker folds and word cells. The [response diagnosis](multiphone-lexical-phone-response-report.md) decomposes improvements and regressions. | Gains are not uniform. Rare-error support is sparse for some sounds; ZH is unsupported. |
| Rare errors | Weighting, ranking, selection, calibration and recording/sound-unit weighting studies retain their failures and mixed outcomes in the [experiment log](model-training-run-log.md). | Better rating probabilities do not establish reliable detection of actual speech errors. |
| Unfamiliar words and speakers | [Complete-utterance word exclusions](multiphone-lexical-head-report.md) and speaker-disjoint folds expose the full-feature head's weaker word-held-out behavior. PCA, fixed mixtures and expanded fitting provide separate comparisons. | These are repeatedly reused development folds from one corpus, not untouched final validation or app-prompt validation. |
| Nonspeech rejection | The explicit [occurrence-aware research filter](multiphone-position-filter-report.md) with the 100 ms speech option retains the tested speech examples and withholds several nonspeech controls. | It still admits a tested dog recording. Natural isolated-word retention and general false-acceptance rates remain unverified. |
| Uncertainty and reliability | The [expanded-fitting uncertainty analysis](multiphone-lexical-expanded-uncertainty-report.md) retains whole-child intervals, every sound and all leave-one-child-out results. Full metric artifacts include reliability summaries. | Intervals are conditional on reused development data. They neither establish calibrated pronunciation-error risk nor authorize confidence-based learner feedback. |
| Recording robustness | [Fixed noise comparisons](multiphone-lexical-noise-report.md) preserve clean replay and quantify prediction movement under cached 20 dB noise; earlier gain/noise and word-crop diagnostics remain in the [model card](multiphone-research-model-card.md). | Smaller average movement is not better accuracy. Large individual shifts remain; the newer expanded candidates have not inherited a robustness claim from older heads. |

The original eligible evaluation population has 14,837 target positions, including
5,654 child positions from 52 children aged 6–12. Expanded fitting uses 28,227
positions from the same 125 speakers, not a new independent cohort. The
[occurrence inventory](multiphone-lexical-expansion-report.md) documents the exact
original/added mapping and additional support.

## What can be used now

The four September 26 full-data bundles remain the portable research artifacts.
Start with the [artifact handoff](research-artifact-handoff.md). Their manifests,
exact feature interface and raw-WAV instructions are in the [research README](../../research/audio-head/README.md) and
[model card](multiphone-research-model-card.md). They retain their original
scope and are not silently replaced by a later cross-fit result.

Their full phonetic-feature architecture showed useful speaker-held-out results
but lost to scalar features under the later complete-utterance word exclusions.
That lexical limitation must accompany use of these older bundles. Do not apply
a newer mixture's reported development score to them.

The [occurrence-aware adapter](multiphone-position-audio-report.md) supports
explicit canonical positions, including repeated sounds. Its exact replay and
the optional filter tests establish implementation behavior on the declared
examples. They do not establish prompt correctness, produced-phone identity or
clinical pronunciation feedback.

## Limits and next work

Accessible data currently supplies subjective ratings rather than comprehensive
expert produced-phone/error labels. There is no established speech-sound-disorder
validation cohort or ages 2–5 evaluation. Timing is estimated, rare ratings are
sparse, app-word coverage is limited, and recording perturbations lack independent
correctness labels. The [access assessment](accessible-data-next-step.md) separates
usable public material from gated data; no restricted corpus access is assumed.

1. Use the reviewed [artifact handoff](research-artifact-handoff.md) to reproduce
   the existing feature/raw-audio interfaces and inspect the evaluation-only
   candidates. The seed report retains every seed, comparison and sound.
2. Any future portable candidate export needs its own specified fitting or
   checkpoint-selection rule and parity verification; it is not implied by a
   favourable pooled score.
3. For eventual learner pronunciation judgments, the [SLP handoff](slp-handoff.md)
   and [data options](child-pronunciation-data-options.md) identify the missing
   independent labels and validation. Those requirements remain outside what
   the present accessible corpus demonstrates.

Closed research leads and their numerical results remain in the
[training run log](model-training-run-log.md) and linked immutable studies.
No fresh search, model promotion, clinical claim or learner-policy change follows
merely from completing a training run.
