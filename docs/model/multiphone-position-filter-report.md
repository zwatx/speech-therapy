# Filtering research scores for repeated consonants

The existing 100 ms speech-evidence filter works with the new occurrence-aware
audio interface. It preserves requested IDs, word/phone positions and order;
when the recording fails either input-evidence check, it withholds every score
vector. No filter implementation, threshold or model bundle changed.

The fixed integration check retained all 66 positions in seven child speech
recordings and withheld all three requested positions on each of four known
challenges: silence, Gaussian noise, a 440 Hz tone and a helicopter recording.
The known dog recording still passed and exposed all three requested vectors.
This remains an exploratory whole-recording filter, not validated speech
recognition, prompt matching or per-position evidence of articulation.

## What actually ran

The [protocol](multiphone-position-filter-protocol.md) fixed thirteen cases.
Seven reused the completed schema-2 position-audio reports, covering all 23
consonants and all four bundles. One reused the schema-1 BE word crop. Five
fresh schema-2 raw runs used the exact previously retained challenge WAVs with
the canonical prompt BOB B, requesting three B occurrences in deliberately
non-chronological order. The prompt tests identity handling; it does not imply
that BOB B was spoken in these recordings.

All five new CTC outputs match their previous same-WAV runs byte-for-byte.
Changing the canonical prompt does not affect this recognizer input. Each of
the thirteen cases then ran the actual existing filter: one Silero pass at the
unchanged baseline settings, with both 250 ms and 100 ms segmentations derived
from identical saved probabilities. Every case completed without failure.

| Case | Requested positions | 250 ms combined | 100 ms combined |
| --- | ---: | --- | --- |
| Seven child speech recordings | 66 | All retained | All retained |
| BE crop, schema-1 control | 1 | Withheld | Retained |
| Silence | 3 | All withheld | All withheld |
| Gaussian noise | 3 | All withheld | All withheld |
| 440 Hz tone | 3 | All withheld | All withheld |
| Dog `4-182395-A-0.wav` | 3 | All retained | All retained |
| Helicopter `4-161579-A-40.wav` | 3 | All withheld | All withheld |

The helicopter has a positive 100 ms VAD segment but no recognized phone
tokens, so the conjunction withholds all three vectors. The dog has two
recognized phone tokens and a positive segment under either policy. Its
admission demonstrates why this filter cannot establish that the requested
phones were produced. Environmental category labels do not establish absence
of incidental speech, and these previously observed cases do not estimate a
population false-acceptance rate.

The short policy preserves 70 of the 82 requested vectors across this mixed
regression set; the baseline preserves 69. These totals include the known dog
admission and are software-behavior counts, not an accuracy measure. The BE
control verifies short-speech recovery through the legacy raw schema. It does
not validate short repeated-position crops. Passing a whole-recording check
does not prove speech exists within every target's estimated window.

## Use the existing filter after occurrence-aware inference

From `research/audio-head`, this command filters one verified repeated-position
report into a fresh directory:

```sh
.venv/bin/python multiphone_short_vad_filter.py \
  --report outputs/multiphone-20260927/position-audio-v2/cases/000010115/report.json \
  --sha256 2ba3c6add16cef058ff0e6ecb65c8271dac93a46b0d4543752bd02fd16a05838 \
  --output outputs/multiphone-20260927/position-filter-example
```

Read the resulting `finalreport.json`. When `decision.ratingAvailable` is
false, each target's `subjectiveCorpusRatingProbabilities` is `null`. Otherwise
the vectors are preserved exactly, without converting them into correctness
judgments. The output's schema version is 1 for the **filter envelope**; its
source report may use occurrence-aware raw schema 2. Source hashes establish
that link. Raw and intermediate diagnostic files still contain unfiltered
vectors and should not substitute for the final filtered report.

## Verification and limits

Seventeen distinct tests passed: seven existing filter tests and ten tests
using repeated-position fixtures. They check all-target masking, exact score
restoration, target count/order, malformed source/parameter handling and the
unchanged absence of prompt/local-speech validation. The actual runs verify
raw CTC job/audio/posterior chains, canonical geometry, feature scalar columns,
saved-head replay, VAD segmentations and all 82 target identities/vectors under
both policies. The first test-file write used the wrong working directory and
failed before creation; this was corrected before declaration or inference.

Offline reconstruction and independent artifact/narrative review passed.
The independent audit directly replayed the frozen speech detector with a
state reset for every recording: all 1,269 probabilities match exactly. It
reconstructed 26 segmentations, checked all 164 target outputs across both
policies, independently replayed thirteen saved pronunciation heads, and
confirmed all five same-WAV CTC comparisons. All 826 declared input bindings
were checked, covering 310 unique bound files. The
[verification record](../../work/position-filter-audit-20260927/verification.json)
has SHA-256 `8e8f1528a6fa8543e7daec521469dabe001416fcd5af0cbb4169d5aab8a8e36b`.
App builds and UI tests were not run because app behavior did not change.
No model training, threshold tuning, new audio acquisition, author-test access
or Colab compute occurred. Learner judgments remain disabled.

The completed [target-local overlap diagnostic](multiphone-position-overlap-report.md)
measures estimated target-window overlap across the expanded corpus. Many
zero-overlap positions have all five ratings equal to 2, so these checks do not
justify adding a per-position withholding rule.

- [Declaration](../../research/audio-head/outputs/multiphone-20260927/position-filter-v1/plan.json): `5e67bd7a2c7e6b52fae7b80dba6cd7ec29b73b59f2a4ae8719239cb4bee4aafc`.
- [Complete results](../../research/audio-head/outputs/multiphone-20260927/position-filter-v1/report.json): `4e34bc966f147c8d754c400c6de177f80353da42a36b3a8bc65f69baf745ae72`.

Reconstruct the saved checks without acoustic inference:

```sh
.venv/bin/python -m position_filter.study verify \
  --plan outputs/multiphone-20260927/position-filter-v1/plan.json \
  --plan-sha256 5e67bd7a2c7e6b52fae7b80dba6cd7ec29b73b59f2a4ae8719239cb4bee4aafc
```
