# Research audio inference for repeated consonants

The research WAV interface can now address repeated consonants by their exact
word and phone position. It keeps each requested occurrence separate, preserves
caller order, and produces the same feature values as the completed position
export. The original schema-1 interface and all four bundled models are unchanged.

## Behavior

Use `position_inference.audio` with a schema-2 prompt. Each target supplies a
unique caller ID, zero-based `wordIndex` and `phoneIndex`, and the canonical
`targetPhone`. Two targets may have the same phone, but cannot share an ID or
position. The interface accepts up to 512 occurrences from a canonical sequence
of at most 512 phones. Existing constraints on audio format, word structure,
supported sounds and explicit canonical transcription still apply.

For example, both /B/ occurrences in the supplied canonical word BOB can be
requested separately:

```json
{
  "schemaVersion": 2,
  "language": "en",
  "transcript": "BOB",
  "words": [{"text": "BOB", "phones": ["B", "AA1", "B"]}],
  "targets": [
    {"id": "initial-b", "wordIndex": 0, "phoneIndex": 0, "targetPhone": "B"},
    {"id": "final-b", "wordIndex": 0, "phoneIndex": 2, "targetPhone": "B"}
  ]
}
```

The caller supplies the intended canonical sequence; this is not a verified
transcription of the produced sounds. Equal adjacent canonical tokens must
retain a separating CTC blank. Their contextual pooling windows may overlap,
because the unchanged extractor includes two surrounding frames.

## Actual verification

The [fixed protocol](multiphone-position-audio-protocol.md) chose recordings
from metadata before inference. Seven child recordings cover **66 positions,
all 23 supported consonants and all four existing bundles**. The cases include
repeats within a word, across words, adjacent equal consonants, one new clip
with only added positions, and an original-only clip. Three prompts request
targets in reverse order. There are 38 original positions and 28 added positions.

| Recording | Positions | Original / added | Existing bundle |
| --- | --- | --- | --- |
| 000010115 | 11 | 4 / 7 | Unweighted all-age |
| 000010035 | 8 | 6 / 2 | Unweighted child-only |
| 000010113 | 12 | 8 / 4 | Weighted all-age |
| 000530027 | 6 | 0 / 6 | Weighted child-only |
| 000010011 | 6 | 6 / 0 | Unweighted all-age |
| 000260096 | 10 | 5 / 5 | Unweighted child-only |
| 014390134 | 13 | 9 / 4 | Weighted all-age |

Each actual run recomputed the q8 CTC posteriors and full-precision phonetic
hidden representation from its WAV. All CTC bytes, all 1,037 feature values per
position, occurrence identities, target ordering, occupancy/pooling windows,
estimated frame centers, scalar diagnostics and mapping ambiguities match the
saved position reference exactly. Bundle probabilities replay exactly from
those reference features. Input/source
hashes were checked again before publishing. No network fetch occurred in the
CTC worker. Observed per-case adapter time was 5.41–7.06 seconds on this Mac,
including startup and provenance checks; this is not a mobile latency estimate.

Thirteen new adapter tests and nine unchanged legacy tests pass. They cover
repeat identity, reversed order, adjacent blanks, more than 23 targets, bounds,
unsupported/malformed inputs, contract/source changes, and failure publication
when the source audio changes. The legacy duplicate-phone rejection still passes.
An initial test invocation used the wrong working directory; a subsequent
mocked pipeline test caught a missing import. Both were corrected before the
declaration and real inference. No actual inference case failed.

Independent source, artifact and narrative review passed. Offline replay also
passed without rerunning either encoder. The independent audit reconstructed
all 68,442 feature values, seven CTC chains, caller order, recording measurements
and direct saved-head predictions. It checked 93 declared input bindings and
97 unique file bindings, including 13 repeated-token groups and two adjacent
equal-token pairs. The [verification record](../../work/position-audio-audit-20260927/verification.json)
has SHA-256 `ca3d7518e57e4f521580ffacb0d9d1281f8f153ab99c8018961757097fd7a99b`.
No app behavior changed, so app builds and UI tests
were not run. No model was trained, no author-test recording was used, and no
Colab compute was allocated.

## Reproduce a verified repeated-position case

From `research/audio-head`, use a fresh output directory:

```sh
.venv/bin/python -m position_inference.audio \
  --wav outputs/speechocean762-audio-v1/speechocean762/WAVE/SPEAKER0001/000010115.WAV \
  --wav-sha256 7703a9d8510c8773061be4c4ac88937b6694b7a027d0f69134d79e4d3c22fe0c \
  --prompt outputs/multiphone-20260927/position-audio-v2/000010115-prompt.json \
  --prompt-sha256 6e414ffa04dd166dab781b159b6eef90b38f451c355aae679c2b4c588e330c9b \
  --bundle outputs/multiphone-20260926/phonetic-final/unweighted-all-age \
  --manifest-sha256 d3c95f8d42fddb692708f7431ef4cf48a5abc4ab1be6a5e1afc4f5f705bb0be6 \
  --phonetic-snapshot outputs/model-cache/models--facebook--wav2vec2-lv-60-espeak-cv-ft/snapshots/ae45363bf3413b374fecd9dc8bc1df0e24c3b7f4 \
  --contract-sha256 f089324f893253f7dafb0b8920ed04eaf9d2e182e969645ccc7bcb1618d4d9ce \
  --output outputs/multiphone-20260927/position-audio-example
```

Verify the saved seven-case artifacts without rerunning encoders:

```sh
.venv/bin/python -m position_inference.verify verify \
  --plan outputs/multiphone-20260927/position-audio-v2/plan.json \
  --plan-sha256 1f80191c05ba51385d927cbf44b202f8a7aaed5ca8b3010dc042fb6bc6054a59
```

The [declaration](../../research/audio-head/outputs/multiphone-20260927/position-audio-v2/plan.json)
binds the cases, source code, protocol, contract, original audio, reference
features and all four bundles. The [completed report](../../research/audio-head/outputs/multiphone-20260927/position-audio-v2/report.json)
has SHA-256 `8883aa10bb76701d968a2fee03d61800f14d5470831c0a6bdb0486e98d2cf6c2`.

This is an extraction and inference capability improvement. Existing heads
were trained on original unique-phone rows; this interface does not promote
the mixed-result expanded models. Exact parity does not establish pronunciation
accuracy, produced-phone identity, verified articulation timing, nonspeech
rejection or independent child generalization. Outputs remain research corpus
rating distributions, and learner judgments remain disabled.
