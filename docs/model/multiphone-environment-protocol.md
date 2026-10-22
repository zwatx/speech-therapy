# Fixed ESC-10 environmental input challenge

Declared September 27, 2026, before inference. This is an exploratory challenge
of the fixed input-evidence gate, not an accuracy estimate or VAD gold benchmark.
Environmental category labels do not prove the absence of incidental speech.

## Selection and source

Use only `esc10=true`, fold 1 rows at ESC-50 commit
`33c8ce9eb2cf0b1c2f8bcf322eb349b6be34dbb6`. For each of `dog`, `rain`,
`sea_waves`, `crackling_fire`, `helicopter`, and `chainsaw`, select the first two
lexicographically sorted filenames with distinct `src_file`. Fail if any
category has insufficient eligible sources; do not replace clips based on
recognition results. Save the exact 12-row selection before audio download.
There is no author-test evaluation or model fitting in this challenge; fold 1
is the sole metadata selection boundary.

[Official pinned README](https://github.com/karolpiczak/ESC-50/blob/33c8ce9eb2cf0b1c2f8bcf322eb349b6be34dbb6/README.md)
and [LICENSE](https://github.com/karolpiczak/ESC-50/blob/33c8ce9eb2cf0b1c2f8bcf322eb349b6be34dbb6/LICENSE)
state the ESC-10 subset is CC BY 3.0; the full ESC-50 dataset is CC BY-NC 3.0.
Retain the complete license and each selected recording's original attribution.
Credit Karol J. Piczak, *ESC: Dataset for Environmental Sound Classification*,
ACM Multimedia 2015, and the Freesound contributors named in the saved license.

## Fixed processing and evaluation

Download only pinned metadata, README, LICENSE and the selected 12 WAVs.
Keep whole five-second mono 44.1-kHz PCM16 originals. Resample with installed
ffmpeg to mono 16-kHz PCM16, no trimming or amplitude normalization. Record
exact commands, ffmpeg version, original and converted SHA-256 hashes.

Run each clip once through the unchanged pinned raw adapter on local CPU,
two threads, the replayed `unweighted-all-age` head and the fixed BALL prompt
`B AO1 L` with target B. Apply the hardened
`multiphone_evidence_gate.filter_report` to each completed bound report.
Pin the gate source, raw runtime inputs, bundle, protocol and plan before
inference. No fitting, threshold adjustment, additional heads, feedback,
promotion, cloud use, or results-based reselection.

Report accepted and abstained counts by category, recognized-phone token
counts, and every pipeline failure separately. Runtime exceptions are never
counted as successful rejection. Acceptance only means the fixed necessary
input check passed; it does not establish speech, BALL, or correct B.

## Reproduction

From `research/audio-head`, use the existing `.venv/bin/python` to run
`multiphone_environment_tests.py`, then
`multiphone_environment_challenge.py declare`. Inspect the saved selection and
plan before `multiphone_environment_challenge.py run --sha256 <plan-sha256>`.
The output is fixed to ignored `outputs/multiphone-20260927/environment-v1`;
existing output prevents implicit overwrite or repeated inference.
