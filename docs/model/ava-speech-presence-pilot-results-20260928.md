# Fixed AVA speech-presence experiment — 28 September 2026

The learned candidate failed the predefined comparison against both existing speech detectors. It is **not adopted**. This experiment measures speech presence in movie excerpts; it does not measure child pronunciation accuracy or clinical correctness. The existing pronunciation research bundle is unchanged.

## Actual result

| Method | Balanced accuracy, mean over 16 evaluation films |
|---|---:|
| Learned candidate | 84.83% |
| YAMNet Speech score ≥0.5 | 85.85% |
| Standalone Silero, minimum 100 ms | 87.89% |
| Energy-only control | 72.32% |
| Shuffled-label control | 43.07% |

Candidate minus YAMNet was **−1.02 percentage points**, with positive differences on **5/16** films. Candidate minus Silero was **−3.06 points**, positive on **3/16**. The predefined screen required at least 12 positive films, a positive mean and every leave-one-film-out mean positive against each control. Both comparisons failed; every leave-one-film-out mean was negative. All 16 evaluation films had defined balanced accuracy, including at 0.5 seconds.

These are results conditional on this fixed sample. They are not population accuracy, equivalence, a natural-prevalence false-positive rate, or proof that future speech-presence models cannot improve. The lower energy-control point estimate does not rule out loudness effects. The shuffled-label result is descriptive and does not establish genuine speech learning or exclude every confound.

## Fixed method and execution

Before any audio extraction or model outcome, 32 provider-listed films were selected by a fixed hash order and split 16 training/16 evaluation. All original objects were acquired and fully decoded; no failed recordings were replaced. Fixed interior windows of 0.25/0.5/1/2 seconds produced **960 training and 983 evaluation clips** (1,943 total), with original human speech/no-speech annotations. The exact source-clock/window manifest was independently reconstructed. Interval-level labels can contain short pauses; annotation-to-waveform alignment has not independently been proven.

The candidate uses the mean of original YAMNet frame embeddings and one fixed train-only standardized logistic fit (L2, C1, threshold 0.5). Energy and within-film shuffled-label heads use the same frozen fitting recipe. No parameter search, threshold rescue, new padding, subset selection, refitting or implicit restart occurred. All three heads converged. Model inference took 35.97 seconds for YAMNet and 7.52 seconds for Silero on the Mac; fitting took 0.058 seconds. No new Colab runtime was allocated.

Original frame outputs and control probabilities are saved. First-window model replay was byte exact for both detectors. A separate checker importing no experiment code or models independently reconstructed original PCM energy, frame summaries, training membership/weights/permutation/scaler, checkpoint probabilities, evaluation membership, integer counts, rational balanced accuracies, fixed comparison screen and conditional diagnostics. Its closing input/output hash checks passed. This does not claim an independent model forward pass.

## Child development check

The unchanged candidate was run on every previously declared input: **1,037 utterances and 17 known word crops**, with zero unresolved inputs. It retained **985/1,037 utterances** and **15/17 crops**, dropping **52 utterances and 2 crops** that the historical baseline retained. The lost crops were AFTER (0.545 seconds) and BY (0.285 seconds), both from the age 12 recording panel. These estimated crops are not manual phone-boundary truth.

First-scored-clip replay was byte exact. A separate checker importing no experiment code independently reconstructed all 1,054 original identities/audio geometry and hashes, scored coverage, original saved-frame means, unchanged checkpoint logits/probabilities (tolerance 1e−9), saved replay bytes, decisions and retention counts, then rechecked all bound input/output hashes. Verification passed. No model forward or refit was performed by that checker.

This is a consumed development panel, not fresh speech-audibility, pronunciation or clinical validation. Its retention prerequisite failed independently of the movie-screen failure. The candidate is **rejected**, with no threshold/padding/subset/refit rescue and no replacement of the existing model. See [actual child result](/Users/zacharywilson/Documents/speech-therapy/work/ava-speech-presence-pilot-20260928/runs/child-development-v1/result.json) and [independent child verification](/Users/zacharywilson/Documents/speech-therapy/work/ava-speech-presence-pilot-20260928/root-child-development-verification.json).

## Authorship, review and reproducibility

Actual verified Opus 5.5 calls 36/37/38 supplied the design, original extraction/fitting implementation and child-development implementation. Root owns integration and documented corrections; native Astra independently reviewed source and the actual inference setup. Opus 39 found a result-checker run-lineage bug, fixed before actual inference with a regression test. Opus 40 reviewed the actual negative outcome, finding no blocking conclusion error; root retained qualifications to its broader learning/loudness/bottleneck interpretations. All original source and review evidence are preserved. No claim is made that this chat changed models.

- Fixed plan: `d54d8c18d66c3ef9a3fc8648bb5c15c8f13b2cf3a7b82270985f857e2716b0e6`.
- Actual window manifest: `c0408a79d2b7a19355ab9377fc48aa04d9be83942336313e02fd23b7c316f35f`.
- Actual inference declaration: `7d2cef35f85bab4f5113b4b8c4a83b5fad0830de9337b5e2739ab8da10c2e52b`.
- Actual fit report: `29a2c468cfd4ed4cd9e5015b6652b2d9c69c41704d1171b8eb3a292b6a5bee90`.
- Actual child result: `a328e0695111aa65fa409d839c04fac39af4bb39c2730e5f7469eba13db4724e`.

Evidence: [fixed plan](/Users/zacharywilson/Documents/speech-therapy/work/ava-speech-presence-pilot-20260928/plan.json), [actual fit report](/Users/zacharywilson/Documents/speech-therapy/work/ava-speech-presence-pilot-20260928/runs/fit-v1/report.json), [independent result verification](/Users/zacharywilson/Documents/speech-therapy/work/ava-speech-presence-pilot-20260928/root-fixed-result-verification.json), [Opus outcome review](/Users/zacharywilson/Documents/speech-therapy/work/ava-speech-presence-pilot-20260928/opus-outcome-review.json), [root qualifications](/Users/zacharywilson/Documents/speech-therapy/work/ava-speech-presence-pilot-20260928/root-opus-outcome-assessment.json).

Source references: [official AVA downloads](https://sites.research.google/gr/ava/download/), [provider repository](https://github.com/cvdfoundation/ava-dataset). See [source audit](/Users/zacharywilson/Documents/speech-therapy/docs/model/ava-speech-source-access-20260928.md) for label/domain/access limits. The research goal remains active; this experiment has not demonstrated a pronunciation-model improvement.
