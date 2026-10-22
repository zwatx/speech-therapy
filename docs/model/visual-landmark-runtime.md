# Visual landmark runtime decision

Status: local feasibility implementation; not a validated clinical model

## Decision

The first on-device face/mouth quality slice uses Apple's Vision framework
behind the `FaceLandmarkExtracting` boundary. It detects face bounds, pose, and
outer/inner lip landmarks from front-camera sample buffers. The app immediately
reduces those observations to framing and mouth-geometry measurements. It does
not write frames, mouth crops, or raw landmark arrays to disk, include them in
attempt uploads, or use them to generate articulation feedback.

Production visual processing remains off. In Debug builds, a developer can add
the `-CadenceVisualFeasibility` launch argument to make the camera-quality flow
available on a physical test device with non-patient data. The tester still sees
the local-processing explanation and must tap **Turn on camera framing** before
the app requests permission. This flag does not change server consent, upload,
routing, or feedback behavior.

The feasibility UI is portrait-only. Rotation-aware capture and camera-session
interruption handling remain part of the physical-device feasibility gate.

The Debug flow can export a versioned aggregate JSON report. It stores counts,
latency buckets, thermal state, and provenance only; report parsing fails closed
if any raw-retention or upload flag is enabled. The collection and advancement
procedure is defined in
[`../validation/visual-feasibility-protocol.md`](../validation/visual-feasibility-protocol.md).

Runtime identifier:

```text
apple-vision-landmarks-feasibility-v1
```

## Why MediaPipe is not embedded yet

The Lab plan selected MediaPipe Face Landmarker as the preferred open-source
feature-extraction candidate. It remains the principal bake-off candidate, but
the current official iOS integration has two unresolved release concerns:

- Google's current iOS guide requires the `MediaPipeTasksVision` CocoaPod and a
  separately downloaded model bundle. Both the binary and exact model artifact
  need immutable provenance and license review.
- The current MediaPipe repository privacy notice says Tasks APIs send
  performance and utilization metrics to Google and places consent obligations
  on the app developer. That conflicts with Cadence's current prohibition on
  third-party tracking and with the decision not to introduce another child
  data processor before privacy review.

Primary references reviewed on 2026-07-10:

- [Official Face Landmarker iOS guide](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker/ios)
- [Official MediaPipe repository and privacy notice](https://github.com/google-ai-edge/mediapipe)
- [MediaPipe release history](https://github.com/google-ai-edge/mediapipe/releases)

This is not a claim that Apple Vision is clinically superior. It is a
lower-dependency feasibility runtime that keeps the privacy boundary honest
while the model bake-off and vendor review remain open.

## Evidence boundary

Allowed derived outputs are limited to:

- capture-quality score;
- face count and normalized face coverage;
- face-center offset;
- yaw and roll estimates;
- normalized mouth width and aperture;
- explicit framing/observability issue codes.

These are capture and observability features, not proof of tongue placement,
teeth contact, voicing, phoneme correctness, or a causal speech error. The
learner UI may coach framing, distance, head direction, lighting, and mouth
visibility only.

## MediaPipe re-evaluation gate

Do not add the MediaPipe binary or model bundle until all of the following are
recorded:

1. A documented way to disable or contractually govern SDK metrics for the
   intended child/clinical deployment.
2. Exact CocoaPod, source revision, model-bundle URL, SHA-256, license, model
   card, and data-lineage review.
3. Physical-device latency, thermal, memory, framing-failure, and network-capture
   results across the pilot device matrix.
4. A replay comparison against the same consented, speaker-held-out landmark
   fixtures used for the Apple Vision baseline.
5. Privacy, security, clinical-safety, and accessibility approval.

Any replacement must preserve the extractor boundary and the rule that raw
frames are ephemeral by default.
