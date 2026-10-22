# TrueDepth feasibility for Cadence

Status: opt-in Debug ARKit expression lab implemented; physical-device validation pending; no depth capture

Reviewed: 2026-09-26. Sources below are Apple's documentation, retrieved on that date.

## Decision

Keep ordinary no-account practice audio-only. An optional, local-only Debug camera
lab is implemented for later testing on a physical iPhone. Its entry is hidden on
Simulator and unsupported devices. The useful capability is
front-camera face tracking or TrueDepth capture, not access to Face ID's enrolled
biometric data. Face ID APIs report authentication success; they do not expose the
enrolled face data to the app. [Apple Platform Security](https://support.apple.com/en-gb/guide/security/secc5227ff3c/web)

The camera could help us measure whether the mouth is observable and whether
visible lip/jaw movement is captured consistently. This is a research hypothesis,
not evidence that camera features improve pronunciation judgment.

## Available capabilities

| Capability | What an app can obtain | Boundary for Cadence |
| --- | --- | --- |
| Existing Vision path | Face bounds, pose, and 2D lip landmarks from RGB camera frames | Already used for local framing checks; no depth or articulation judgment |
| ARKit face tracking | Face position/orientation, a fitted face mesh, and expression coefficients | Candidate for visible lip/jaw motion and a mirror visualization |
| AVFoundation TrueDepth capture | Per-pixel depth/disparity maps; synchronized RGB/depth output | Candidate for distance and observability research on compatible hardware |
| Face ID authentication | Success/failure of authentication | No speech measurement use; no access to enrolled biometric templates |

ARKit's mesh represents the detected face's shape and current expression. Blend
shapes are normalized expression coefficients, not calibrated millimeters or
phoneme probabilities. Potential features include `jawOpen`, `mouthClose`,
`mouthFunnel`, and `mouthPucker`.
[Face geometry](https://developer.apple.com/documentation/arkit/arfacegeometry),
[blend shapes](https://developer.apple.com/documentation/arkit/arfaceanchor/blendshapes),
[feature names](https://developer.apple.com/documentation/arkit/arfaceanchor/blendshapelocation?language=objc)

AVFoundation can stream depth maps and synchronize them with color frames.
Inspect each device's available depth formats and the delivered depth quality,
accuracy, filtering, and calibration metadata; do not assume uniform metric
precision or valid measurements at every pixel.
[TrueDepth sample](https://developer.apple.com/documentation/avfoundation/streaming-depth-data-from-the-truedepth-camera),
[depth accuracy](https://developer.apple.com/documentation/avfoundation/avdepthdata/accuracy)

Face tracking and depth capture are different capability checks. Apple documents
ARKit face tracking on devices with Apple Neural Engine on iOS 14 and later, so
face-tracking support does not by itself prove TrueDepth hardware is present.
Use `ARFaceTrackingConfiguration.isSupported`; separately discover
`.builtInTrueDepthCamera` and supported depth formats when depth is required.
Apple also requires a privacy policy explaining facial-data use.
[ARFaceTrackingConfiguration](https://developer.apple.com/documentation/arkit/arfacetrackingconfiguration)

## Evidence limits

Do not infer internal tongue position, teeth contact, airflow, voicing, a causal
speech error, or correct pronunciation from these features. Apple's `tongueOut`
coefficient describes tongue extension; it is not internal tongue imaging.
Whether these observations add useful information beyond audio needs a separate
SLP-reviewed, appropriately labeled evaluation. No child or speech-sound-disorder
accuracy claim follows from Apple's API availability.
[Feature definitions](https://developer.apple.com/documentation/arkit/arfaceanchor/blendshapelocation?language=objc)

ARKit is unavailable in iOS Simulator, and Apple's TrueDepth sample requires
physical hardware. Simulator fixtures can verify an unavailable state or UI
lifecycle; they cannot demonstrate sensor fidelity, capture performance, or
speech utility. [Apple face-tracking sample](https://developer.apple.com/documentation/arkit/tracking-and-visualizing-faces),
[TrueDepth sample](https://developer.apple.com/documentation/avfoundation/streaming-depth-data-from-the-truedepth-camera)

## Implemented lab

`MouthMovementLabView()` is a separate Debug destination, not a step in practice.
Its `isAvailable` property checks real face-tracking support. The screen also
distinguishes TrueDepth hardware presence from ARKit support. **Start camera** is
the only permission/capture entry; no Face ID authentication is requested.

The ARKit delegate reads `jawOpen`, `mouthClose`, `mouthFunnel`, and `mouthPucker`
at up to 10 updates per second. Only finite scalar coefficients in the documented
0–1 range and explicit status events cross to the main actor. The app does not
collect depth maps, render or save face meshes, record audio, retain camera
frames, export readings, or upload data. The bars are labeled expression
measurements; a missing reading is displayed as unavailable, not zero accuracy.

Stopping, leaving the screen, backgrounding, interruption, or capture failure
clears the readings and stops capture. A generation token rejects permission
results and camera callbacks that arrive after a stop or from an earlier run.
The user restarts explicitly after an interruption. Permission denial leaves
ordinary practice available and provides a Settings action.

Lifecycle tests cover unsupported hardware, denial, delayed permission after
stop, stale callbacks after restart, face loss, interruption/failure, and invalid
coefficients. These use test doubles solely to verify lifecycle behavior; they
are not sensor or pronunciation evidence. The production camera path never
substitutes simulated readings. Swift 6 type-checking passed against both the
simulator and physical iPhone SDKs; the full app test result belongs in the
implementation verification log.

## Physical-device follow-up experiment

1. Use one supported physical iPhone and consenting adult, non-patient testers
   for engineering feasibility. Record hardware, OS, app build, and actual API
   capabilities. Child validation remains separate from this first experiment.
2. Keep capture behind a Debug research option and an explicit camera opt-in.
   Unsupported hardware, denied permission, or tracking failure leaves ordinary
   audio practice available. Do not add Face ID authentication or fake sensor
   output to the demo.
3. Compare the existing Vision baseline with ARKit in separate runs of the same
   short tasks: neutral pose, comfortable jaw opening, lip closure/rounding,
   head turn, mouth occlusion, dim light, and an adult over the tester's shoulder.
   Assess tracking availability, lag, repeatability, and failure behavior. Treat
   feature-to-motion correspondence as observational, not phoneme ground truth.
4. Try AVFoundation depth only if the first comparison leaves a concrete
   distance/observability question. Use a separate capture mode; do not assume
   multiple frameworks can own the front camera concurrently.
5. Process frames, meshes, depth maps, and coefficients in memory. The current
   lab has no export. If measurement logging is later added, save only explicit
   aggregate feasibility reports, with no images, video, raw geometry,
   per-frame biometric series, or uploads. Check capture stops on exit,
   backgrounding, interruption, and permission changes; inspect the app container
   and network behavior. Measure dropped frames, latency, memory, and thermal
   impact before considering audio-plus-camera capture.
6. Ask the available SLP which externally visible observations are useful before
   expanding into a labeled multimodal speech study. Advance only if the camera
   shows a measurable advantage over the existing RGB baseline worth its cost
   and usability constraints. A successful one-device experiment is not a
   production or clinical validation result.

## Existing integration points

- `MouthMovementLab.swift` contains the Debug model, hardware capability checks,
  and ARKit scalar-only delegate. `MouthMovementLabView.swift` uses the native
  practice visual style and lives under the About screen on supported phones.
  It has no relationship to pronunciation scoring or the assignment service.
- `apps/ios-learner/Sources/Visual/VisualCaptureMonitor.swift` uses
  `.builtInWideAngleCamera` and `VNDetectFaceLandmarksRequest`; it does not use
  ARKit or TrueDepth. It processes at most about ten observations per second.
- `VisualPracticeConfiguration.swift` keeps the current camera flow disabled
  unless the Debug feasibility argument is present. The tester still opts in.
- `VisualFeasibilityReport.swift` already supports aggregate-only counts,
  latency, thermal state, and provenance. Add a distinct runtime/report version
  if new feature types require it; do not label ARKit data as Vision output.
- [Visual runtime decision](visual-landmark-runtime.md) and the existing
  [physical-device protocol](../validation/visual-feasibility-protocol.md) define
  the baseline. Its full device matrix remains necessary for advancement beyond
  the small exploratory experiment described here.
