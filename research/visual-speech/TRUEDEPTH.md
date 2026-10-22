# RGB/audio now; measured depth later

Checked against current Apple documentation on 2026-10-02. The offline CLI currently reads RGB only. It does not ingest, estimate, or fabricate depth. Every depth field remains null.

## Three different capabilities

- **RGB Vision landmarks:** estimated 2D points from visible image content. `pointsInImage(imageSize:)` converts facial landmark points into image coordinates; this CLI applies the video's display transform before extraction. [Apple landmark API](https://developer.apple.com/documentation/vision/vnfacelandmarkregion2d).
- **ARKit:** a generic face mesh fitted to the observed shape/expression and expression coefficients. These are not equivalent to a measured per-pixel TrueDepth map. Face tracking support on newer Neural Engine devices alone does not establish TrueDepth hardware. [Face geometry](https://developer.apple.com/documentation/arkit/arfaceanchor/geometry), [face tracking support](https://developer.apple.com/documentation/arkit/arfacetrackingconfiguration), [expression modeling explanation](https://developer.apple.com/videos/play/tech-talks/601/).
- **AVFoundation TrueDepth:** compatible hardware can deliver actual sensor-derived `AVDepthData`, containing per-pixel depth/disparity and metadata. Apple's sample separately configures video/depth outputs and selects an available depth format. This needs a physical device. [Apple TrueDepth sample](https://developer.apple.com/documentation/avfoundation/streaming-depth-data-from-the-truedepth-camera).

Face ID enrollment data is inaccessible to apps. Authentication returns a result, not a stored biometric template to use for speech. Apple's October 1, 2026 support document states this explicitly. [About Face ID](https://support.apple.com/en-ie/102381).

The existing `MouthMovementLab.swift` reads four ARKit coefficients, and `VisualCaptureMonitor.swift` uses ordinary RGB/Vision. Neither captures AVDepthData. This new offline extractor does not change those app paths.

## Concrete next capture design

Use a separate opt-in research mode and a single AVFoundation session owning the front camera, rather than assuming ARKit and AVFoundation can simultaneously own it. Discover `.builtInTrueDepthCamera`, choose an actually supported RGB/depth format pair, and record the delivered format and hardware/OS. Configure `AVCaptureVideoDataOutput` and `AVCaptureDepthDataOutput`, retaining the original depth/disparity type, calibration when present, quality/accuracy flags, filtering setting, and invalid-pixel mask. Apple's example disables filtering for its stream. Filtered values must not be silently treated as unprocessed measurements. [TrueDepth setup](https://developer.apple.com/documentation/avfoundation/streaming-depth-data-from-the-truedepth-camera), [depth output](https://developer.apple.com/documentation/avfoundation/avcapturedepthdataoutput), [depth accuracy](https://developer.apple.com/documentation/avfoundation/avdepthdata/depthdataaccuracy).

Synchronize RGB and depth with `AVCaptureDataOutputSynchronizer(dataOutputs: [videoOutput, depthOutput])`. The first output drives delivery. The synchronizer collects matching samples or reports their absence; it does not guarantee a valid depth sample for each video frame. Inspect both `sampleBufferWasDropped` and `depthDataWasDropped`, preserving timestamped missingness and the drop reason. Do not forward-fill a dropped depth observation. [Synchronizer initialization](https://developer.apple.com/documentation/avfoundation/avcapturedataoutputsynchronizer/init(dataoutputs:)), [synchronized depth](https://developer.apple.com/documentation/avfoundation/avcapturesynchronizeddepthdata).

For audio, capture sample buffers with their presentation timestamps and sample rate in the same session, then establish their clock relationship to the synchronized video/depth stream. Preserve audio chunk ranges and interruptions; do not pair one arbitrary audio chunk with one RGB frame or use callback wall-clock arrival as the timestamp. Confirm the actual offset and drift with a recorded audiovisual timing event before claiming synchronization. This is a proposed implementation/test requirement, not verified capture behavior on this Mac. The current CLI accepts a declared constant offset and marks alignment unverified.

A future depth artifact needs actual depth frame timing, RGB alignment transform, pixel dimensions/type, calibration reference, hardware/format, filtering/accuracy/quality, drop reason, valid-pixel fraction, and source lineage. Derive only features supported by valid calibrated samples. Ordinary video files, fitted ARKit meshes, monocular depth estimates, and missing camera-calibration values must never be labeled measured TrueDepth. No speculative importer is included before a real capture is available.

## First real capture test (not performed)

With an explicitly consenting adult engineering tester and a supported physical iPhone, after implementing that separate capture mode:

1. Capture short neutral, lip opening/closure, comfortable rounding, small head turns, and controlled partial occlusion examples. Include a visible/audible synchronization event. Record permission scope, hardware, OS, format, clock relation, and source hashes; establish retention/deletion before retaining per-frame data.
2. Verify audio/RGB/depth timestamps, orientation/mirroring, mapped pixel coordinates, dropped samples, and calibration against the actual artifacts. Compare filtered/unfiltered missingness if both are recorded; label the setting explicitly.
3. Check tracking loss, an extra face, dim light, interruptions, stopping/backgrounding, memory, frame rate, latency, and thermal behavior. Keep failure cases; never substitute zero geometry or guessed depth.
4. Compare repeated visible movement observations between RGB and actual depth. Do not judge pronunciation or internal tongue posture. Even success on one adult/device demonstrates only engineering feasibility.
5. Only then define a separately permitted and labeled child ages 6–12 study with audio-only and multimodal comparisons. Leave developmental/dialect variation and unadjudicated speech correctness unlabeled.

No child footage, microphone capture, physical-device test, sensor-fidelity measurement or depth comparison was performed. The generated black-video smoke tests decoding and no-face behavior. A later separate parent smoke processes one explicitly licensed publisher-provided real speech sample, with no geometry ground truth or validated audio alignment; see README.md. It does not establish any depth or child evidence.
