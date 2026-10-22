# Offline visible speech observations

This new macOS research tool extracts visible lip and face-contour geometry from an **already permitted, user-supplied local video**, preserving its video timestamps and mapping them to an explicitly supplied audio clock. It uses Apple's native AVFoundation decoder and Vision face landmarks. No model weights, datasets, camera access, network client, or additional package dependencies are involved.

It is a concrete foundation for later audio/vision experiments, not a trained speech model or pronunciation judge. It does not revive the closed AVA speech-presence experiment. It does not modify the iPhone app, its existing aggregate-only capture policy, shared scoring packages, or frozen model results.

## Run

Requires macOS 14+, Swift 6+, and the Apple SDK. Tested with Swift 6.4 on this Mac. Vision request revision 3 is explicitly selected; Apple's runtime implementation can still change with the OS, which the output records.

From repository root:

```sh
swift build --package-path research/visual-speech
swift test --package-path research/visual-speech
research/visual-speech/.build/debug/visual-speech --help
research/visual-speech/.build/debug/visual-speech \
  --input /absolute/permitted/local-video.mov \
  --output /absolute/new-observations.ndjson \
  --provenance /absolute/provenance.json \
  --audio-timebase /absolute/audio-timebase.json \
  --fps 10
```

The output path must not exist. A completed output is published by moving a private temporary file; a decode failure removes the incomplete temporary file. Source hashing is streamed and checked again before publication. AVFoundation external-media references are forbidden, so the hashed input is self-contained. Input must have exactly one video track. Files with multiple video tracks, nonmonotonic timestamps, corrupt video, missing permission metadata, or a missing audio clock are rejected. Decoding is sequential and observations are streamed to disk; video pixels are not saved. Extraction failures become explicitly unavailable rows and are counted in the summary, rather than represented as no face.

The tool never verifies legal permission or consent. `localProcessingPermitted` is the caller's recorded assertion, backed by `rightsReference`. Keep the rights record, consent scope if applicable, retention/deletion policy, and source lineage with the original dataset. Features and hashes are **sensitive research artifacts**, not anonymization. The initial implementation tests used no human media. The parent later ran one explicitly licensed, publisher-provided real speech sample; see the bounded smoke below.

`provenance.json`:

```json
{
  "sourceID": "your-stable-item-id",
  "rightsReference": "your-existing-license-or-permission-record",
  "localProcessingPermitted": true,
  "ageDomain": "unknown",
  "dialect": "unknown",
  "speechCorrectness": "unlabeled"
}
```

`ageDomain` is one of `unknown`, `adult`, `child-6-12`, or `other`, supplied from existing metadata, never inferred from a face. Dialect is supplied metadata or `unknown`. Correctness must remain `unlabeled`: mature/adult speech, unfamiliar dialects, synthetic fixtures, and unknown recordings never become a normal/correct target by default.

`audio-timebase.json`:

```json
{
  "referenceID": "your-existing-audio-item-id-or-hash",
  "sampleRateHz": 16000,
  "durationSeconds": 4.2,
  "videoPTSToAudioOffsetSeconds": -0.125,
  "alignmentMethod": "document-how-this-offset-was-established",
  "alignmentUncertaintySeconds": null
}
```

The equation is **audio seconds = original video presentation timestamp seconds + supplied offset**. Example: when a visual event at video PTS 1.000 s corresponds to audio 0.875 s, offset is −0.125 s. Audio seconds are relative to sample zero of the declared audio reference. In-range sample indices use floor(seconds × sample rate). Timestamps outside `[0, duration)` retain their signed time and have a null sample index; they are never clamped. The tool does not decode/verify the declared audio, estimate lip/audio synchrony, correct drift, or align a transcript. `audioAlignmentVerified` is always false. A constant offset is unsuitable when independently recorded clocks drift; use validated synchronization before fusion.

The generated fixture clock is deliberately named `synthetic-clock-not-recorded-audio`; never use it for actual recordings.

## Output and feature meaning

NDJSON contains one `header`, one `frame` per sampled video timestamp, and a final `summary`. Require `summary.complete == true` and inspect processing failures before using a result. The header records input SHA-256, sidecar hashes, supplied provenance/clock, duration, video track timing, OS, Vision request revision, feature version, orientation transform, and requested maximum sample rate.

The video track's y-down display transform is converted to Core Image's y-up coordinates before Vision. Non-square pixel aspect ratios are rejected, rather than silently skewing pixel geometry. Both eye centers define the origin (their midpoint), scale (their distance), and horizontal axis. The features therefore remove translation, uniform scale, and modest in-plane roll, but **do not** correct perspective, yaw/pitch, expression-induced eye landmark movement, or detector bias. Near-vertical eye lines (horizontal separation at most 10% of eye distance) and normalized mouths on/above the eye line yield unavailable geometry. This excludes inverted/over-rolled observations instead of flipping the feature meanings. Feature version 2 includes these geometric-domain checks and the display-orientation correction.

| Field under `features` | Observation | Units |
| --- | --- | --- |
| `outerLipWidth`, `outerLipHeight` | Extents of the outer lip landmark polygon in the eye-aligned plane | Inter-eye distances |
| `innerLipWidth`, `innerLipHeight` | Extents of the inner lip polygon | Inter-eye distances |
| `innerLipPolygonArea` | Shoelace area using Vision's ordered inner contour | Squared inter-eye distances |
| `outerLipCenterX`, `outerLipCenterY` | Mean outer contour point, relative to eye midpoint | Inter-eye distances |
| `eyeLineToLowestContourProxy` | Downward extent of the lowest face-contour point | Inter-eye distances |

The last field is a **jaw-region contour proxy**, not measured jaw opening, bone position, muscle activation, or millimeters. Ratios and polygon geometry are observable feature candidates, not a validated closure, rounding, phoneme, or speech-error classifier. The CLI emits no thresholds or learner feedback.

Rows retain exact PTS value/timescale, frame duration when available, mapped audio time, observed image dimensions, face count, face bounds, pose where available, and Apple's face confidence. That confidence is neither calibrated geometry quality nor pronunciation confidence. No/multiple faces yield no geometry; the tool does not choose a speaker or track identity. It cannot establish whether the one visible face is the audible speaker.

`mouthOcclusion`, `lightingQuality`, `motionBlur`, `depth`, `teeth`, `tongue`, and `speechCorrectness` are explicitly null. Missing landmark groups also yield null geometry. A detected face can still have inaccurate, occluded, or unsuitable landmarks; no-face frequency and extraction counts alone are not performance evidence. Sampling preserves gaps and actual PTS rather than inventing a fixed-frame-rate timeline; the requested rate is an upper bound, not a promise of exact cadence.

Vision's 2D lip landmarks are not tooth/tongue segmentation. Ordinary external RGB may show exposed teeth/tongue in some frames, but this extractor supplies no such labels. Internal tongue position, contact, airflow, and voicing are unobserved, and many sounds are visually ambiguous. Separate labeled observations and an audio-conditioned evaluation would be required before speech feedback.

## Verification

`swift test` tests known geometry, translation/scale/roll invariance, a contour change independent of lips, missing/invalid/degenerate and inverted geometry, signed audio offsets and duration boundaries, variable-rate/gapped timestamps, permission/domain/correctness rejection, nonfinite video timing/transforms, and pixel aspect ratios. A native test writes eight real non-human H.264/MOV clips with one bright corner and different rotation/mirror metadata. It compares decoded-and-transformed corner pixels with independent `AVAssetImageGenerator` rendering, including 90°/270° mirrored cases; it also verifies that the former direct Core Image transform disagrees on the four quarter-turn variants.

The native integration smoke requires an **already installed** FFmpeg solely to generate solid black pixels (the converter itself does not need FFmpeg):

```sh
python3 research/visual-speech/smoke_test.py /absolute/new-smoke-directory
```

It exercises actual decoding and Vision, source hashes, 30-to-10 FPS thinning, null modalities, timebase mapping, output preservation, anamorphic-video rejection, and failure cleanup. Expected result: 30 decoded frames, 10 no-face rows, **zero face geometry**, zero extraction failures. These synthetic clips are not speech, face detection sensitivity, audio alignment, child, or depth evidence.

See [DATASETS.md](DATASETS.md) for permitted-data candidates and [TRUEDEPTH.md](TRUEDEPTH.md) for the real iPhone capture boundary and next test. There is no depth-sidecar import yet: actual synchronized AVDepthData and calibration must exist before a depth feature format is implemented. RGB never becomes guessed depth.

## First permitted real-face extraction

On 2026-10-02 a separate parent check processed one [official Lombard GRID public frontal sample](https://spandh.dcs.shef.ac.uk/avlombard/) and its matching audio, published under CC BY 4.0. The full corpus citation, license links, exact URLs, input hashes and processing-purpose record are retained locally in work/consumer-app-20261002/vision/lombard-sample/acquisition.json. No raw media or per-frame features were published.

Actual native decoding yielded 52 frames and 18 sampled observations, all with finite single-face geometry and zero processing failures. The effective sampled rate is 8 fps from 24 fps input (every third frame), below the requested 10 fps upper bound; this sample has an identity track transform. Depth, teeth, tongue and speech correctness remained null. A declared zero audio offset follows the publisher's paired synchronization description, but alignment remains explicitly unverified; the tool did not establish it. Age and dialect remained unknown. This is one real-face implementation smoke with no landmark ground truth, child validation, error labels, model training or measured depth evidence.
