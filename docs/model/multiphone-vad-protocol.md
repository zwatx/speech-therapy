# Fixed pretrained speech-detector comparison

Declared September 27, 2026 before candidate acoustic inference. The preceding
phone-evidence gate retained all corpus speech but admitted two dog recordings
and one fire recording in the twelve-clip environmental challenge. This study
asks whether a separate pretrained speech detector provides a useful additional
input check, including the cost of rejecting corpus recordings.

## Candidate and fixed settings

Use the official MIT-licensed Silero VAD TorchScript model and its unchanged
segmentation utility from commit
`5cd7945676eb32225748052e2e6a0580e4686a08`. Download only pinned official
artifacts; preserve LICENSE and record their SHA-256 digests before execution.
The model is 2,272,526 bytes; its Git blob identity is independently checked
against the upstream contents metadata. No package installation, model fitting,
fine-tuning, threshold search or model promotion belongs to this experiment.

Use CPU, two threads, existing PyTorch 2.8, evaluation/inference mode, existing
PCM16-to-float conversion and unmodified 16 kHz mono waveforms. The official
utility resets recurrent state at each recording, retains state between its
512-sample frames and zero-pads the final frame. Preserve the true audio length.
Record every frame probability and all sample-index speech intervals.

Fix the official default segmentation settings: speech threshold 0.5, negative
threshold 0.35, minimum speech 250 ms, minimum silence 100 ms, padding 30 ms,
unlimited maximum speech duration, no visualization and sample-index output.
The upstream duration comparison is strictly greater than the minimum. A clip
passes the candidate if it has at least one resulting speech interval. Do not
change these settings after viewing any outcome. Short isolated productions
may be rejected by this duration rule; corpus retention cannot resolve that
product-use limitation.

## Full declared inputs

Use every clip in the existing complete author-training manifest: 2,495
recordings, 125 speakers, 14,837 eligible consonant positions across 23 sounds.
Preserve the 1,037 recordings, 52 speakers and 5,654 positions from children
ages 6–12 as a separately reported subset. Include every eligible row regardless
of its ratings, phone or acoustic outcome. No author-test data is accessed.
Bind the feature-manifest/cohort chain already used by the evidence-gate
evaluation. Original waveforms, ratings, features and model bundles remain
unchanged.

Use the twelve already observed ESC-10 environmental clips from the pinned
environment-v1 plan, plus the original zero, Gaussian-noise and 440 Hz tone
examples. These are known development challenges; they are not a fresh test
set. Environmental category labels do not prove absence of incidental speech.
No environmental accuracy or population false-acceptance rate is claimed.
The choice of candidate follows those observations and is exploratory.

Compare three fixed decisions: previous phone-evidence gate alone, candidate
speech detector alone, and their conjunction. The prior gate report is bound
by SHA-256
`82c16b2a01b552b5f1382a44a6b939a011d1d44d131b076a149741ad7bba18d9`;
the environmental plan is bound by SHA-256
`1016d94bb15fab78929319da24f3706980c742505d50e805ea8bbbe60f45d9e9`.
Combining decisions does not recompute or improve pronunciation predictions.

## Execution and verification

Write and hash the declaration before inference. Bind protocol, evaluator,
tests, upstream source/model/license, runtime versions, input manifests, prior
gate outcomes and all waveform identities. Require fresh output; preserve
partial evidence after a failure and never silently rerun it. Read each audio
through the existing hash-checked loader. Validate frame count, finite bounded
probabilities, finite in-range intervals and exact input coverage. Runtime or
integrity failures abort and are not counted as successful abstentions.

Save each completed recording before proceeding. A separate verification pass
must reconstruct intervals and decisions from saved probabilities with the
same pinned utility, verify source and artifact hashes, and regenerate every
table. A repeated first recording after intervening recordings must reproduce
its probabilities exactly, checking state reset. Tests should exercise invalid
probabilities, frame padding, state isolation, short-input handling, missing
coverage and result tampering. No second acoustic inference over the whole
corpus is required merely to reconstruct report tables.

## Reporting and limits

For all ages and children separately, report total/retained/withheld clips,
speakers, positions, rating-0 and below-2 positions/votes, and all 23 individual
phones for each decision rule. List every withheld corpus clip and its support.
Report all environmental and synthetic outcomes, with explicit denominators.
Do not calculate pronunciation accuracy or score discarded recordings as
correctly detected pronunciation errors. Whole-recording retention does not establish speech at each target position.
Corpus retention only describes these recordings; it does not validate all child speech, short isolated speech, SSD,
ages 2–5, prompt matching, speaker identity or physical recording conditions.

This default candidate can provide evidence for a research-only input policy,
but learner judgments remain disabled. Any retained candidate needs a separate
evaluation on fresh permitted environmental sources and representative child
recordings before broad claims. Do not tune to this report and describe the
same recordings as independent validation.

## Primary sources

- [Pinned official utilities](https://github.com/snakers4/silero-vad/blob/5cd7945676eb32225748052e2e6a0580e4686a08/src/silero_vad/utils_vad.py): inference, state reset, frame size and segmentation defaults.
- [Pinned model](https://github.com/snakers4/silero-vad/blob/5cd7945676eb32225748052e2e6a0580e4686a08/src/silero_vad/data/silero_vad.jit) and [MIT license](https://github.com/snakers4/silero-vad/blob/5cd7945676eb32225748052e2e6a0580e4686a08/LICENSE).
- [Official quality metrics](https://github.com/snakers4/silero-vad/wiki/Quality-Metrics): domain-specific evaluation; the reviewed source does not establish pediatric/SSD validation.
