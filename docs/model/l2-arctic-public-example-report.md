# Public manual-annotation ingestion verified

The actual public L2-ARCTIC example now passes the new importer and its offline
replay check. This establishes a usable annotation schema path, not a new
training corpus or a model-quality result.

The [fixed protocol](l2-arctic-public-example-protocol.md) bound the reader,
acquisition script and tests before retrieval. Five public resources—the
annotation, corpus page, annotation documentation, license and Praat format
documentation—totaled **212,502 bytes**. Exact downloaded bytes, retrieval
metadata, attribution and hashes are retained locally. No audio or archive was
downloaded, and no registration or contact occurred.

## Actual sample findings

The [official example](https://psi.engr.tamu.edu/wp-content/uploads/2018/03/lxc_arctic_a0018.txt)
contains 7 word intervals, 16 phone intervals and 7 auxiliary IPA intervals.
Only the phone tier contributes events: ten unchanged speech labels, three
substitutions and the standalone `sil`, `sp` and empty labels. Its three
substitutions are R→AH (0.20–0.28 s), Z→S (0.44–0.53 s), and JH→CH
(0.94–1.01 s). The parser retains the `0` stress suffix on perceived AH.

There are eight canonical positions across seven of Cadence's 23 consonants:
CH, DH, JH, N, R, W and Z. Only JH, R and Z have an observed substitution.
The other 16 consonants have no positions in this sample. There are no observed
insertions, deletions, unresolved identities or marked deviations; synthetic
tests cover those formats separately and do not expand corpus support.

The [official conventions](https://psi.engr.tamu.edu/l2-arctic-corpus-docs/)
distinguish expected and perceived phones, unknown perceived identity (`err`),
and deviation (`*`). The importer preserves all of these plus raw labels,
stress, exact source time strings, tier identity and all word overlaps.
Deletions have no perceived phone; insertions have no canonical phone. IPA is
retained without double-counting errors. The meaning of standalone `sp` remains
unresolved. Unchanged labels imply annotator acceptance only with established
manual provenance, never merely because an automatic alignment has no error tag.

## Verified scope and limits

Twelve focused tests pass. Separate source/code review cleared the strict
long-text IntervalTier reader, bounds, label handling and provenance checks.
The actual offline verifier re-parses the retained source and reconstructs every
record, summary and hash without network access. Independent saved-output
review also passed: all source bindings, 30 tier intervals, 16 typed phone
records, word overlaps, counts and exclusion flags matched the original bytes.

All resulting rows remain excluded from fitting, evaluation and learner
feedback. The sample's release version and speaker age remain unknown; its
URL date does not establish membership in v5. TextGrid bounds were checked,
but waveform duration and perceptual correctness were not verified. The
[official access page](https://psi.engr.tamu.edu/l2-arctic-corpus/)
requires registration for the full corpus and states CC BY-NC 4.0; this check
does not establish commercial model rights. No model weights changed.

The subsequent [MRPL2 access check](mrpl2-access-assessment.md) found restricted
files for version 1.0 and unverified access to version 1.1. Its public description
is relevant, but no audio or labels were acquired. The next bounded check is
the actual produced-phone notes already present in permitted SpeechOcean
author-training data, with missing notes kept distinct from correct productions.

## Saved evidence

- [Plan](../../research/audio-head/outputs/multiphone-20260927/l2-public-example-v1/plan.json): `f0884a3551824b27849bc2909f708fae2e12ff80a04d8006702b9b6a8df5015b`.
- [Acquisition and summary](../../research/audio-head/outputs/multiphone-20260927/l2-public-example-v1/report.json): `620ba895606ed563721611a5237f0dca184593cace9b5fd20d2b9a6675b4b753`.
- Original TextGrid SHA-256: `bb2e198e06fb6646f7f60f6548e5ed7d6d558987bad52c4d0e9a278190d88573`.
- Parsed annotations SHA-256: `cd61bf4e532f97735c2e461c2c2b3601168087e8e4a0d85766af919d61dde375`.

Mac CPU only; no GPU or Colab units. Broader application checks did not run
because this change adds isolated research ingestion and documentation only.
