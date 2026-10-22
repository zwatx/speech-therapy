# UltraSuite: first frozen-model comparison with clinician ratings

The retained learned model showed **no consistent advantage over the simple CTC acoustic control in this fixed check**. Equal-child mean ranking concordance was **64.4062% for the model** and **64.4085% for the control**, a difference of **−0.0023 percentage points**. The model improved on the control for two children and fell below it for five. The prespecified research-candidate pattern failed; the result category is `mixed-or-unsupported-comparison`.

This is evidence from new individual paired outcomes, not a training improvement. Near-identical mean estimates do not establish equivalence, absence of pronunciation signal, or an upper limit on achievable performance. Neither percentage is clinical classification accuracy.

## What was tested

The unchanged ages-6–12 portable research mixture generated 690 grade-free predictions: 666 prepared UXSSD items from seven nominally age-eligible children and 24 UPX items from one separate child. All 792 original items remain inventoried, including 96 under-six items without head predictions and six structurally unresolved items. Age is the documented first-assessment nominal age, not a verified age for each recording session. The primary cohort contains nominal ages 6–10; ages 11–12 are absent.

The model score is the native ranking statistic `p1 + 2*p2`. The control is the original `targetMeanLogPosterior` feature. Both rank the original clinician primary 1–5 grades without label conversion, calibration or thresholds. Pairs include only distinct grades within the same child and consonant (/g/, /k/ or /r/), using the prospectively fixed first presentation. Credits and counts pool across consonants within each child, and each child receives equal weight in the primary mean.

Clinician ratings combine ultrasound, audio and spectrogram judgments. They do not establish a transcript of produced phones or manual phone localization. Each UXSSD child has one assigned clinician, so child and rater remain confounded. The [provider paper, Section 4](https://arxiv.org/html/2103.00324v1#S4) supplies the rating direction. Published aggregate outcomes were already visible; this check does not claim full blinding.

## Primary results

All seven children and all 21 child–consonant blocks had informative pairs. There were 7060 pair comparisons, which are dependent comparisons among 666 items, not 7060 independent children. Neither scorer had exact score ties in the primary comparisons.

| Child | Nominal age | Informative pairs | Model concordance | Control concordance | Difference (pp) |
|---|---|---:|---:|---:|---:|
| uxssd/01M | 6y 0m | 1236 | 56.31% | 57.20% | -0.89 |
| uxssd/02M | 10y 1m | 1006 | 79.82% | 77.83% | +1.99 |
| uxssd/03F | 8y 7m | 1041 | 59.37% | 59.56% | -0.19 |
| uxssd/04M | 8y 11m | 1208 | 63.00% | 67.14% | -4.14 |
| uxssd/05M | 6y 5m | 719 | 63.98% | 66.06% | -2.09 |
| uxssd/07F | 7y 6m | 683 | 82.87% | 76.28% | +6.59 |
| uxssd/08M | 7y 7m | 1167 | 45.50% | 46.79% | -1.29 |

Leaving one defined child out produced mean differences from **−1.1008 to +0.6872 percentage points**, with mixed signs. The exact sign enumeration counted all 128 sign patterns as at least as extreme as the observed near-zero mean. This is only the prespecified conditional symmetry/sign-exchangeability diagnostic; it is not a population-valid p-value, confidence interval or equivalence test.

## Prespecified descriptives and sensitivity

| Consonant | Equal-child model concordance | Equal-child control concordance | Difference (pp) |
|---|---:|---:|---:|
| /g/ | 70.69% | 68.11% | +2.59 |
| /k/ | 69.79% | 67.24% | +2.55 |
| /r/ | 61.63% | 63.05% | -1.42 |

These consonant comparisons were planned descriptives. They do not justify dropping /r/, changing weights, selecting a subset, or claiming an overall gain. Their equal-child consonant means are not the primary across-consonant pooling calculation.

The fixed unresolved-item sensitivity retained all 672 primary-cohort items. Each distinct-grade pair containing an unresolved score received half credit for both scorers; no scalar prediction was fabricated. This added 137 pairs, giving 7197 pairs in total. Mean concordance was 64.2660% for the model and 64.2640% for the control; the difference was **+0.0020 percentage points**. Its change from the primary difference was +0.0043 percentage points, and child signs remained two positive and five negative. This sensitivity supplies no rescue or validation gain.

For the 96 extra UXSSD repeated ratings, 69 matched their first rating exactly. The same 69-of-96 agreement count occurred among UPX repeats; their absolute-change distributions differ. Repeated ratings reuse the same audio and one frozen prediction, so they are not new independent items or prediction-stability observations.

UPX is reported separately: 24 items from one child, eight clinicians and 192 first ratings. The learned model was below the control for five clinicians and above it for three. These are clinician descriptives on shared audio, not eight independent children or a healthy baseline; UPX 04M is not merged with UXSSD 04M.

## Verification and disposition

Opus 5.5 authored the implementation, synthetic tests and protocol. Originals are preserved. Before any real prediction, root integrated two independently identified audit-guard fixes and corrected an erroneous synthetic test expectation by independent pair counting; the metric implementation and frozen plan were unchanged. All 32 synthetic tests passed.

GPT-6 Astra independently cleared the final source and actual prediction declaration, all 2156 bindings and exact age inventory. Predictions were executed, independently checked, and fixed before grades were parsed. Astra then cleared a distinct actual evaluation declaration. The completed evaluation preserved source, plan, runtime, model and all four prior prediction artifact pins.

The root verifier imports no study code and executes no model. It independently reconstructed all 1152 original primary grades and their ten metadata fields, all 960 first-presentation selections, all primary and sensitivity child–consonant pair counts and concordances, equal-child means, leave-one-out means, conditional sign enumeration, repeated grades and UPX blocks. All checks passed. It rechecked output lineage and all input bindings. Native head logits were not independently replayed; the source-reviewed runner executed the retained portable model.

**This fixed external route is now consumed and closed.** Preserve its results without rescoring modified weights, fitting on its ratings, calibration, threshold or subset selection, or outcome-driven repair. The retained bundle remains unchanged and research-only. Clinical use, learner feedback, promotion and training remain false. The broader ages-6–12/all-23 goal remains active, including rare errors, unfamiliar words/speakers, recording robustness and nonspeech rejection. Further candidate claims need independent evidence beyond this consumed check.

No Colab runtime was allocated for this feature/prediction/evaluation sequence. Its compute allowance remains available for substantive matched experiments; compute alone does not provide missing labels or independent evaluation evidence.

## Frozen artifacts

- `work/ultrasuite-frozen-model-check-20260928/plan.json`: SHA-256 `958f448e2730a13c89334d6a993e6780033d6227b73f9279d3c696d36b40b870`.
- `prediction-declaration.json`: `6f5f045255fdb7864e114c7ca103b1fdc5e903a6c746d83c752562bf8b0423ab`.
- `predictions/result.json`: `a37f859c2a3bea087f07c4c54fcdfa48f24f14e6c6023381a57de88b2dee617a`.
- `evaluation-declaration.json`: `6d00a13b997702e41f811fc3615c3c7e84f3146a826ba60543652a2a615b8061`.
- `evaluation/result.json`: `60223e175c0852711a9954232e5ff11e829530d09e9b85d9b325efcd4267bd49`.
- `astra-prediction-review.json`, `astra-evaluation-review.json`, `root-prediction-verification.json`, `root-evaluation-verification.json`, `verify_results.py`, `tests-final.txt`: review and verification evidence.
- `opus-authorship-receipt.json`, `opus-source-as-written/`, `opus-result.json`: verified Opus 5.5 implementation provenance.
- `opus-result-interpretation-*`: actual Opus 5.5 tool-free result review completed successfully in 37.24 seconds, with verified canonical model identity and no errors or permission denials. It cleared the headline interpretation. Root preserved two qualifications: repeated-rating variability is observed but supplies no concordance ceiling, and positive consonant descriptive estimates remain reportable without establishing general gains. The separate raw/parsed review, receipt and root assessment are preserved.
