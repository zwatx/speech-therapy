# Ages 6–12 research model: fitted and portable

The current model target is **ages 6–12**. Younger ages are outside this milestone and are not a blocker. A new full-fit version of the retained unweighted expanded child scalar/PCA16 mixture is now trained, exported and runnable. This closes the earlier gap between evaluation-only mixture checkpoints and a usable feature-input candidate.

**This is a capability and packaging improvement, not a newly measured accuracy gain.** The new full-fit weights have no independent performance score. Historical cross-fit results describe the recipe, not these exact weights. Outputs remain subjective corpus-rating distributions; learner feedback, clinical eligibility and promotion remain disabled.

## What was built

Two fresh heads were fitted on all **9,891 eligible sound positions from 52 children in 1,040 recordings**, using the existing permitted author-training corpus and all 23 supported consonants. Adults and the author-test partition were excluded. No new audio, labels or Colab runtime was needed.

The [fixed protocol](ages-6-12-bundle-protocol.md) retained seed 7, the established training cores and equal probability weights. Median historical inner-selected epochs fixed the scalar head at 16 epochs and the PCA16/scalar head at 18. Both completed: 2,480 and 2,790 optimizer updates respectively. PCA and normalization use only the 9,891 fitting rows. No outer score selected a seed, epoch or mixture weight.

The loader requires an explicit age in years, accepts 6 <= age < 13 (completed ages 6–12), and rejects ages outside that range. Age is a scope guard, not an inferred property or acoustic feature. Canonical target IDs cover `B P M T D N K G F V S Z SH CH JH L R W Y HH TH DH NG`; ZH is unsupported. Repeated consonants retain separate rows.

## Fitting support by age

| Age | Children | Recordings | Sound positions |
| --- | ---: | ---: | ---: |
| 10 | 2 | 40 | 411 |
| 11 | 7 | 140 | 1479 |
| 12 | 7 | 140 | 1510 |
| 6 | 13 | 260 | 2309 |
| 7 | 10 | 200 | 1814 |
| 8 | 2 | 40 | 394 |
| 9 | 11 | 220 | 1974 |

Ages 8 and 10 each have only two fitting children. All seven ages are represented, but these counts do not establish equal performance. The declaration retains all 161 age/phone support cells, including sparse or empty cells. Across the full fitting population there are 918 rating-0, 1,086 rating-1 and 47,451 rating-2 votes; these are subjective votes, not independently verified speech errors.

## Use the candidate

The [portable ZIP](../../work/ages-6-12-bundle-20260927/cadence-ages-6-12-research.zip) contains the five-file bundle, loader, required model class and instructions (472,809 bytes). It requires NumPy and PyTorch; the verified environment is Python 3.13.14, NumPy 2.2.6 and PyTorch 2.8.0. Original training archives and training modules are not needed for inference. The source implementation lives in [ages_6_12_bundle](../../research/audio-head/ages_6_12_bundle/).

The archive SHA-256 is `9a178efed3f412fef655cfc8a7b97188722828330d91aa0effcd45ddb1cb9258`. The caller-pinned bundle manifest SHA-256 is `bc62f1e4f1727379161d0f3f7d8e6074e645e7578b5c25661fd9da53e4fde1bf`.

After extracting the ZIP, run from its directory:

```python
from pathlib import Path
from ages_6_12_bundle.inference import load_bundle

model = load_bundle(
    Path("bundle"),
    "bc62f1e4f1727379161d0f3f7d8e6074e645e7578b5c25661fd9da53e4fde1bf",
)
result = model.predict(features, target_ids, age_years=9)
```

`features` must be finite NumPy `float32[N,1037]`: 1,024 raw target-window features from the pinned encoder, followed by the 13 ordered CTC scalars. `target_ids` must be a same-length integer array with IDs 0–22. The outputs are `probabilities` and `logProbabilities`, one three-class distribution per input occurrence, with disabled eligibility flags. Shape alone does not verify extraction provenance or the intended prompt.

Audio encoders and a nonspeech filter are not included in this feature-only package. The existing [occurrence-aware audio extractor](multiphone-position-audio-report.md) saves `features.npy` and per-target `modelTargetId` values. Its `--bundle` argument still expects an older head interface; feed its saved features to the new loader rather than substituting this bundle there. Use serial calls: this research loader temporarily configures PyTorch thread count.

## Verification and limits

- All 10 loader tests passed, including age boundaries, malformed inputs, repeated-row order, independent mixture arithmetic, PCA/normalization, corrupted state and manifests, relocation and RNG preservation.
- Exported predictions matched the established training-core predictions **exactly across all 9,891 fitting positions**, for both probabilities and log-probabilities. This is implementation parity, not held-out accuracy.
- Copying the bundle to a new directory gave exact predictions for the same 65-row input. A separate isolated Python process loaded the ZIP contents with original output-file reads forbidden and without importing training modules. Its 65-row result stayed within the predeclared 1e-6 log-probability tolerance when compared with the first 65 rows of the larger replay; the final batch size differs.
- A real recorded-speech example used the previously verified features for child recording `000010115`, age 6. All 11 canonical positions, including repetitions, produced research outputs. No encoder was rerun and this author-training recording is not an independent validation example.

Evidence: [fixed declaration and all support cells](../../research/audio-head/outputs/multiphone-20260927/ages-6-12-mixture-v1/plan.json), [completed export/parity report](../../research/audio-head/outputs/multiphone-20260927/ages-6-12-mixture-v1/export-report.json), [source review](../../work/ages-6-12-bundle-20260927/source-review.json), [isolated package check](../../work/ages-6-12-bundle-20260927/portable-check.json), and [recorded-speech example](../../work/ages-6-12-bundle-20260927/recording-example.json).

The previous [Colab final-layer pilot](colab-expanded-pilot-results.md) still failed its improvement screen and was not adopted. This candidate follows the retained scalar/PCA approach instead. Better child error labels, independent speakers/prompts and recording robustness remain research priorities within ages 6–12. Lack of results below age 6 is no longer a requirement for this target. No app behavior or release policy changed. App build and UI checks were not run because application code was unchanged.
