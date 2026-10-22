# Research improvement handoff — September 27, 2026

The research reference is the **unweighted expanded child scalar/PCA mixture**.
Its seed-7 development comparison improves all five pooled endpoints and child
NLL in every speaker fold against the matching original-data mixture. This is
a measured development gain, not evidence of reliable child error detection.
The newer three-seed study rejects recording/sound-unit weighting as a general
improvement: none of its 18 primary comparisons passes the fixed screen.

Use the [current decision](current-multiphone-decision.md) for model selection
and the [artifact handoff](research-artifact-handoff.md) for exact input contracts
and runnable research entry points. Four older portable bundles remain available;
newer cross-fit results do not replace them or transfer their scores to them.
Learner pronunciation judgments remain disabled.

## Full objective coverage

“Documented limit” below means an investigated research priority with retained
evidence and a concrete next step. It does not mean that the model has solved
that problem. These are development findings on accessible data; there is no
claim of clinical readiness or an untouched final evaluation.

| Requirement | Delivered evidence and its scope | Limit and concrete next step |
| --- | --- | --- |
| Improve across all 23 supported consonants | [Expanded fitting](multiphone-lexical-expanded-heads-report.md) adds 13,390 permitted occurrences, preserves all 23 sounds and the original comparison population, and yields the child-mixture development gain. [Seed replication](multiphone-lexical-seed-replication-report.md) retains every sound, seed, support count and regression. | Gains are not uniform; ZH remains unsupported. The next replication of the data-expansion gain should fit matching original-data baselines at seeds 17/29/43, with the same fixed screen and exclusions. The completed weighting study does not answer that question. |
| Rare-error detection | Rating-class weighting, ranking, calibration and later unit-weighting failures remain in the [run log](model-training-run-log.md). The [direct-note diagnostic](multiphone-note-likelihood-report.md) retains 182 selectively annotated events and every excluded category. | Only 12 selected events concern children, across 12 sounds; missing notes are not correct labels. Use the prepared [blinded listening pack](slp-handoff.md) to distinguish actual errors, acceptable variation and unscorable recordings before defining a new error-detection target. No expert labels are fabricated while review is unavailable. |
| Unfamiliar-word and speaker generalization | [Complete-utterance word exclusions](multiphone-lexical-head-report.md), speaker-disjoint roles and independently checked inner/refit/outer membership expose the full-feature architecture's weakness. Expanded fitting preserves those exclusions and original checkpoint-selection examples. | Reused folds from one corpus are development evidence. A subsequent evaluation needs a prospectively fixed, independently permissioned speaker/prompt cohort; the public author-test partition must not be relabeled untouched after historical exposure. |
| Non-speech rejection | The [position filter](multiphone-position-filter-report.md) retains 66 positions in seven tested speech recordings and withholds vectors for silence, noise, tone and helicopter controls. Exact raw/filter replay and null-output behavior are verified. | A tested dog recording still passes. The next filter study should fix a disjoint collection of permitted natural non-speech and isolated-word speech examples before threshold selection, then report both false admissions and lost speech. Current known cases must remain regression tests, not a new validation set. |
| Uncertainty | [Whole-child analysis](multiphone-lexical-expanded-uncertainty-report.md) retains eight comparisons, every sound, 2,000 child-resampling draws per comparison, and leave-one-child-out sensitivity. | Intervals are conditional on the reused data and fixed fitted models; three seeds are not independent participants. Preserve this distinction and separately evaluate calibration on independent target-specific labels before any confidence-based feedback. |
| Recording robustness | [Fixed 20 dB noise comparisons](multiphone-lexical-noise-report.md) independently reproduce 300 head outputs, 200 mixtures and the complete movement report. No transformed recording receives invented human labels. | Movement is not accuracy; newer expanded candidates do not inherit older heads' robustness result. A subsequent study should preregister clean/perturbed replay for the exact retained candidate, then obtain paired recording-quality/correctness review for accuracy claims. |
| Honest baselines and reproducible bounded experiments | The completed seed study contains 600 initial fits, 600 fresh refits, 600 held-out prediction jobs, 4,464 metric summaries, exact offline reconstruction, and independent state/prediction/metric/aggregate checks. All 18 failed primary screens remain visible; no best seed was selected. | Audit assertions are not independent observations. Saved-state checks do not reconstruct every optimizer trajectory. Use the exact bound environments, protocols and artifacts when reproducing results. |
| Accessible permitted data and compute | Training uses retained public corpus author-training data and cached features; additional occurrences come from the same 125 speakers. The [access assessment](accessible-data-next-step.md) records gated sources separately. The actual public annotation sample is an ingestion check excluded from fitting/evaluation. | Access observations are not a blanket rights grant. No registration, restricted-data bypass or patient-audio acquisition is part of this work. Current cached-feature studies ran on the Mac; Colab remains available for a justified GPU benchmark within the existing 100-unit monthly authorization. |
| Preserve the learner boundary | Current benchmark manifest/scorer, practice receipt service and native decoder retain disabled-feedback restrictions; study plans/results explicitly deny promotion and learner eligibility. | This handoff inspects current source and research artifacts, not a deployed service. Appropriate expert labels, independent validation and a separately reviewed release decision remain necessary before changing learner behavior. |
| Usable model handoff | Four pinned seven-file bundles, feature loader, repeated-position raw-WAV adapter, optional final filter, exact examples and separate experimental replay recipes are documented in the [artifact handoff](research-artifact-handoff.md). | Raw extraction requires repository encoders/caches; copying a head is insufficient. New portable mixture export needs an explicit fitting/selection rule and parity checks. No evaluation-only checkpoint is presented as a new deployed model. |

## Verification record

The [final seed publication review](../../work/lexical-seed-replication-audit-20260927/final-review.json)
checks the report, current decision, shared numerical receipt chain and rendered
figure. Its scope is separate from the broad requirement assessment here.
The [current integrity check](../../work/campaign-integrity-20260927.json)
rehashes 195 files spanning the bound publication, positive expanded-data result,
uncertainty/noise evidence, raw/filter implementations, all four bundles, direct
note evidence and unchanged learner-gate sources. It also checks 89 local links.
It does not rerun fitting, model inference, full metric reconstruction or app tests.

The research sources and numerical results were preserved. The only model-card
edit at handoff changes a stale “running” seed-study reference to “completed.”
No app source, release policy, deployment or model bundle changed at handoff.
No commit or publishing action was requested or performed.
