# Recording-condition sensitivity

This September 26, 2026 diagnostic tests whether research predictions change
when a waveform's recording conditions change. It does not measure whether a
child pronounced a sound correctly. The fixed protocol uses five available
children ages 6, 8, 10, 11 and 12 from fold zero's inner validation partition,
one metadata-selected clip per speaker, and every eligible target in those
clips: 23 target positions. These speakers were already used for head selection.

The [machine-readable result](../../research/audio-head/outputs/multiphone-20260926/capture-sensitivity-v2/diagnostic/report.json)
has SHA-256 `162827b916ca1ab167c131a05d148b2acb12c9351befe9d2872e97e02fd815df`.
The v2 plan has SHA-256
`1ccb263465c987cd0185013db09942092e1d60f55f2ab7c977519fec5e3d0781`.
The earlier v1 plan is preserved but superseded; no inference ran against it.

## Controlled changes

Each source waveform is retained byte-for-byte and paired with three PCM16
variants: gain 0.25, additive white noise at 20 dB whole-waveform SNR, and
additive white noise at 10 dB. A source-hash-seeded Gaussian noise draw is
shared between the two noise levels. If necessary, the protocol attenuates
signal and noise together to prevent clipping; that was not needed for these
five clips. Measured SNR after quantization is within 0.00019 dB of its target.
No trimming, time shifting, resampling or relabeling occurs.

For each variant the offline CPU pipeline recomputes all 392 phoneme posterior
columns, canonical forced occupancy, 13 scalar features, and the official
phonetic encoder's 1,024-dimensional target-window vector. It uses the original
fold-zero all-age and child-only target-plus-scalar heads, each selected at
learning rate 0.0003 and epoch five. These are not the full-data final exports.
All 20 waveform computations finished, with zero network fetch attempts.

On unmodified audio, posterior arrays, scalar features, windows and pooled
phonetic features match the original cache exactly. Saved head probabilities
differ by at most 1.863e-9, within the predeclared 2e-6 tolerance. The reported
mean/max probability movements and argmax-change counts were independently
recomputed from all saved predictions, and every bound artifact hash matched.

## Observed prediction changes

Total variation is half the sum of absolute changes in the three rating
probabilities. It ranges from zero for identical distributions to one for
disjoint distributions. These means weight each target position equally.

| Condition | All-age mean / maximum total variation | Child-only mean / maximum total variation | Estimated target windows that moved |
| --- | --- | --- | --- |
| Quarter volume | 0.00364 / 0.01875 | 0.00108 / 0.00439 | 0/23 |
| 20 dB white noise | 0.03106 / 0.17268 | 0.01376 / 0.06205 | 4/23 |
| 10 dB white noise | 0.09217 / 0.70831 | 0.05955 / 0.17181 | 13/23 |

At 10 dB, the largest absolute shift in the all-age expected rating is 1.410
on a 0–2 scale; one of its 23 maximum-probability classes changes. No other
condition/head combination changes its maximum-probability class. That does
not establish robustness: substantial distribution changes can occur without
changing the largest component. The largest estimated pooling-window endpoint
movement is one frame at 20 dB and 27 frames at 10 dB. These are unverified
canonical alignment changes, not observed movement of a true phone boundary.

The noise result supports investigating recording sensitivity further. It
does not establish that the child-only head is clinically safer, nor that
noise should always leave a rating distribution unchanged: masking can remove
audible evidence. No transformed audio receives the original human ratings.
There is no transformed NLL, Brier, accuracy or calibration measurement.

This five-speaker check supplies no independent-sample uncertainty interval.
Synthetic white noise does not reproduce rooms, reverberation, microphone
hardware, clipping or mobile signal processing. Encoder input normalization
can suppress gain differences. Real device recordings and independently
reviewed child/SSD examples remain necessary before learner judgments.
