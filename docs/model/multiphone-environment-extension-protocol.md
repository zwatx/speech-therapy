# Fixed environmental extension acquisition

Declare before audio download or inference. Use ESC-50 commit
`33c8ce9eb2cf0b1c2f8bcf322eb349b6be34dbb6` and existing metadata, LICENSE and
README bound by prior environment-v1 plan SHA-256
`1016d94bb15fab78929319da24f3706980c742505d50e805ea8bbbe60f45d9e9`.

The initial fold-2 proposal failed a metadata-only feasibility check: helicopter
has only two distinct sources there, and only three in fold 3. Fold 4 is the
first single fresh fold with at least four sources in every fixed category.
This revision happened before any audio download, declaration or inference.
No failed output was created and no audio was inspected for selection.

In this fixed order, use dog, rain, sea_waves, crackling_fire, helicopter,
chainsaw. For each, select the first four lexicographic filenames with
esc10=true and fold=4, skipping every prior twelve src_file values and every
source already selected across all categories. Fail unless exactly 24 distinct
sources are available. No results-based substitution or reselection is allowed.

Before downloading audio, write selection.json with all selected rows,
exclusions and per-file attributions. Bind acquisition code, tests, this
protocol, the original conversion helper, binding helper, ffmpeg binary,
metadata, LICENSE, README and prior plan. Write exclusively and mark the
selection read-only. Acquisition requires its SHA and refuses existing audio
output directories; failures remain failures, without automatic replacement.

Download only the selected 24 audio files from the official pinned raw
GitHub URLs. Validate complete five-second mono 44.1-kHz PCM16 originals.
Use the existing inspected ffmpeg conversion helper to produce complete
five-second mono 16-kHz PCM16 files without trimming or normalization. Preserve
originals, original and converted SHA-256 hashes, exact conversion commands,
ffmpeg version and the exact attribution from LICENSE for each file. Preserve
references to the complete bound LICENSE and README. The ESC-10 subset is
CC BY 3.0; credit Karol J. Piczak, *ESC: Dataset for Environmental Sound
Classification*, ACM Multimedia 2015, and each named Freesound contributor.

These clips are fresh to this experiment and source-disjoint from the prior
12 environmental clips. They are not guaranteed disjoint from pretrained
model training data. Environmental category labels do not establish the
absence of incidental speech and are not speech-detection ground truth.
This script performs no model, CTC or VAD inference, fitting, uploads or
clinical judgments. A separate fixed comparison protocol governs inference.

From research/audio-head, run `.venv/bin/python -m unittest
 test_multiphone_environment_extension multiphone_environment_tests`, then
`multiphone_environment_extension.py declare` using the same interpreter.
Record the returned selection SHA before running
`multiphone_environment_extension.py acquire --sha256 <selection-sha>`.
Output is fixed to ignored
`outputs/multiphone-20260927/environment-extension-v1`; plan.json is written
only after every clip passes validation. Existing declarations and acquisition
outputs are never implicitly overwritten or resumed.
