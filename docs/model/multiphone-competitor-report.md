# Canonical-competitor posterior exploratory results

All ten fixed fits and separate-process exact checkpoint replays completed. The added posterior columns do not yield a consistent gain; no winner is selected. These are five overlapping inner-development folds, not an independent replication or clinical evaluation.

The fixed study uses all-age fitting, 23 supported targets, and 24 competitor columns including ZH. Both arms have 37 input columns and the same 4,163 parameters; the control zero-pads its additional columns, so effective capacity is not identical. Full 392-token posterior normalization and existing forced intervals are preserved.

## Descriptive five-fold means

| Slice | Age | Arm | Macro NLL | Per-rater Brier | Rating-0 AUROC | Rating-0 AP | Below-2 AUROC | Below-2 AP |
|---|---|---|---:|---:|---:|---:|---:|---:|
| allRows | allAges | control | 0.238754 | 0.119148 | 0.880939 | 0.496839 | 0.839055 | 0.478430 |
| allRows | allAges | competitor | 0.239846 | 0.118732 | 0.879235 | 0.501864 | 0.838434 | 0.481417 |
| allRows | ages6to12 | control | 0.203063 | 0.089601 | 0.760173 | 0.177884 | 0.747441 | 0.206158 |
| allRows | ages6to12 | competitor | 0.203077 | 0.090298 | 0.752836 | 0.180658 | 0.738988 | 0.206580 |
| targetWordSeen | allAges | control | 0.223249 | 0.112350 | 0.883716 | 0.503253 | 0.834423 | 0.477444 |
| targetWordSeen | allAges | competitor | 0.225085 | 0.112169 | 0.877819 | 0.500032 | 0.829646 | 0.472512 |
| targetWordSeen | ages6to12 | control | 0.189818 | 0.083198 | 0.756289 | 0.165096 | 0.738879 | 0.188453 |
| targetWordSeen | ages6to12 | competitor | 0.190224 | 0.084301 | 0.747122 | 0.164978 | 0.727966 | 0.183864 |
| targetWordUnseen | allAges | control | 0.351680 | 0.159548 | 0.864311 | 0.515688 | 0.806806 | 0.492958 |
| targetWordUnseen | allAges | competitor | 0.350134 | 0.157767 | 0.860428 | 0.521363 | 0.804933 | 0.494439 |
| targetWordUnseen | ages6to12 | control | 0.254252 | 0.136074 | 0.756381 | 0.247089 | 0.684304 | 0.268297 |
| targetWordUnseen | ages6to12 | competitor | 0.252312 | 0.133796 | 0.759241 | 0.251627 | 0.713136 | 0.277656 |

Ranking is macro across phones with both positive and negative votes; defined phone sets vary by fold and slice. The full per-phone tables include undefined entries and denominators. No intervals are calculated from overlapping fold means.

## Each fold

| Fold | Arm | Selected epoch | All-age NLL | Child NLL | Child rows | Unseen child rows |
|---|---|---:|---:|---:|---:|---:|
| 0 | control | 9 | 0.255067 | 0.218027 | 545 | 77 |
| 0 | competitor | 18 | 0.255017 | 0.228941 | 545 | 77 |
| 1 | control | 20 | 0.255518 | 0.164230 | 967 | 87 |
| 1 | competitor | 20 | 0.259462 | 0.165953 | 967 | 87 |
| 2 | control | 15 | 0.233828 | 0.173802 | 784 | 104 |
| 2 | competitor | 15 | 0.240844 | 0.176423 | 784 | 104 |
| 3 | control | 10 | 0.216001 | 0.259564 | 753 | 93 |
| 3 | competitor | 10 | 0.211494 | 0.247615 | 753 | 93 |
| 4 | control | 14 | 0.233356 | 0.199692 | 1196 | 129 |
| 4 | competitor | 20 | 0.232412 | 0.196454 | 1196 | 129 |

The child tables contain 4245 row memberships, 2954 distinct rows, 39 speaker-fold memberships and 27 distinct children. Repeated memberships are not independent observations.

The target-word-unseen slice uses exactly the same validation rows for both arms and each fold’s fitting target-row vocabulary. It is not word-disjoint: fitting utterances can contain these words elsewhere. All-age fitting can favor proper probability scores while lower-rating ranking trades off. This run is a short exploratory recipe, not a replacement for earlier tuned scalar controls.

## Verification and retained artifacts

- Four focused tests passed: full-vocabulary mass, exact interval, invalid interval/token rejection, fit-only normalization, and matching input width (four test methods).
- Five additional certificate tests pass: missing/stale evidence, changed checkpoint/cohort, and incorrect or incomplete run/check identities are rejected before verified reporting.
- The replay certificate binds the current study report, configuration, competitor array and all ten run artifact sets. Historical generated reports remain in `historical-report-v1`.
- Loader preflight audited 14,837 eligible rows and 2,495 CTC matrices; each target posterior reproduces its existing scalar within 1e-6.
- All ten saved checkpoints replay exactly in a separate process, including fit-only moments, probabilities and all reported metrics.
- Each arm ran 20 epochs; best/last checkpoints, optimizer state, every epoch NLL and row-order hash, predictions and input/source hashes are retained. No failures occurred.
- [complete report.json](../../research/audio-head/outputs/multiphone-20260927/competitor-v1/report.json) retains every age/slice/phone metric; [per-phone.csv](../../research/audio-head/outputs/multiphone-20260927/competitor-v1/per-phone.csv) exposes positive/negative vote, row and speaker denominators. `independent-replay.json` records the separate verification.

Run from repository root:

```sh
research/audio-head/.venv/bin/python -m unittest discover -s research/audio-head -p "test_multiphone_competitor_*.py"
research/audio-head/.venv/bin/python research/audio-head/multiphone_competitor_study.py --run
research/audio-head/.venv/bin/python research/audio-head/multiphone_competitor_replay.py
research/audio-head/.venv/bin/python research/audio-head/multiphone_competitor_report.py
```

The run command refuses to overwrite any completed or failed run. No outer predictions, author-test recording access, external data, encoder extraction, corpus relabeling or model promotion occurred. Forced windows and canonical mappings remain unverified, produced-phone/error-type labels are absent, and ZH has no supervised model.
