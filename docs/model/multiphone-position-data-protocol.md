# Complete consonant-position cohort protocol

September 27, 2026. Build a new research cohort from the already permitted,
SHA-pinned SpeechOcean author-training partition. The previous metadata audit
established expected support before this implementation: 28,227 supported
positions, 2,500 recordings and 125 speakers; ages 6–12 contribute 9,891
positions from 52 children. This step builds and verifies data, not a model.

Include every canonical position belonging to the existing 23 supported
consonants. Do not choose examples by rating, error note, alignment confidence
or model outcome. ZH remains outside the supported inventory. Decode only
author-training score objects from the shared metadata containers. Missing
production notes remain unknown, and approximate, unknown, deletion-marker
and multi-phone descriptions retain their literal values.

Each row must have a unique utterance/word/phone occurrence ID, the zero-based
word and within-word phone indices, and the independently checked flattened
canonical index. Reconstruct the five rating votes from the detailed rater
strings and verify the published aggregate. Keep repeated words and repeated
phones distinct, including when their ratings differ. These are canonical
positions with ratings, not verified produced-phone identities or time spans.

Bind the old cohort and split artifacts. Reconcile every one of its 14,837
eligible rows exactly by position, phone, speaker, age, word and five-rater
counts, preserving a legacy row index and ID. The 13,390 additional positions
must be explicitly distinguishable from the retained original rows. Preserve
old files and all existing source/checkpoint hashes.

Keep the same 125 speaker assignments and each fold's original inner-fit,
inner-validation, outer-fit and outer-holdout speaker sets. Generate row/clip
membership from those sets without reseeding or rebalancing. Check speaker
disjointness and waveform-hash separation, full row coverage, and one outer
holdout assignment per position. The expanded set is still previously used
development data; it does not become an independent final evaluation cohort.

Verify all 2,500 selected train WAVs against their members in the original
pinned archive. Validate mono 16 kHz PCM16, 0.1–30-second bounds, complete
sample payloads and finite measurements. Reconcile the old 2,495 clips'
identity, byte hashes and measurements; verify the remaining five by the same
rules. Do not decode author-test score objects or load author-test WAV payloads.

Declare exact input/source/test/protocol/runtime bindings before creating
the cohort and splits in a fresh ignored output directory. Retain failures;
never overwrite a locked output or silently omit a bad row. Preserve all
23 phone support tables and the child 6–12 slice. Offline verification must
reconstruct the data and splits exactly and recheck waveform provenance.

Focused tests cover repeated occurrences with different labels, repeated
words, position IDs, five-rater disagreement, invalid/misaligned metadata,
legacy reconciliation, speaker membership, duplicate audio across splits,
and unsupported targets. An independent review must clear the implementation
and actual saved artifacts before they become inputs to feature extraction.

This step performs no recognizer inference, fitting, checkpoint selection,
deployment or learner feedback. Production, clinical and learner eligibility
stay false. Additional positions and votes come from the same participants;
they do not establish new population coverage or clinical validation.
