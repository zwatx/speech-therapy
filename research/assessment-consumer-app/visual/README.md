# Optional local visual runtime preparation

The new `../ui/visual-runtime.js` and `../ui/visual-worker.js` implement an explicitly started engineering visual aid. They do not start camera or microphone capture. The caller owns the mirror stream, distinct analysis opt-in, camera permission, overlay drawing and all camera-track stopping. Ordinary recording and mirror use remain independent.

```js
import { LocalVisualRuntime } from '/visual-runtime.js';
const visual = new LocalVisualRuntime();
await visual.start(videoElement, (observation) => {
  // Draw only current ephemeral observation; no saving, uploading or scoring.
});
const cleanup = await visual.stop();
```

`start(video, callback)` resolves after bounded initialization, or rejects after cancellation/unavailability. Each callback has `status`, `outline`, `bounds`, `aperture`, `networkBlockedCount`, `researchOnly:true`, `coordinateSpace:'unmirrored_image'`, and `pronunciationFeedbackEligible:false`. Status is `initializing`, `ready`, `tracking`, `no_face`, `multiple_faces`, `unavailable` (stale observation), or `failed` (fixed reason). `outline` is an ephemeral array of `{x1,y1,x2,y2}` normalized lip line segments; `bounds` is normalized image geometry. `aperture` is a descriptive pixel-space ratio between selected inner-lip and mouth-corner distances, without normative ranges or target-word comparison. Empty/unavailable observations have no geometry. These estimates do not identify a person, diagnose a problem, establish physical dimensions, or determine speech correctness. Mirror transforms must apply equally to the video and outline.

`stop()` returns `{cleanupConfirmed,networkBlockedCount}` after SDK shutdown acknowledgement or a 500 ms deadline, then always terminates the owned worker. Repeated stop and subsequent start await detached cleanup. Cleanup confirmation is conservative across this runtime instance: an earlier unacknowledged shutdown remains false, and blocked-attempt counts are cumulative at stop. A stale frame-construction promise can only close its bitmap, never restart processing. No camera track is stopped by this module because those tracks belong to the caller.

The caller receives each failed state after the old generation is invalidated, so a restart from its callback cannot be cancelled by the old continuation. Backgrounding stops analysis. The main thread captures at most one transferred bitmap (maximum 640×480) at a time and at most 5 Hz, with 15 s initialization, 1 s bitmap construction, 1.5 s inference and 500 ms stale-observation budgets. The worker separately refuses video timestamps less than 200 ms apart, and closes every received frame in `finally`. No recording file, landmark history or visual endpoint is created.

## Frozen acquisition and routing

`asset-manifest.json` byte SHA-256 is `ac02f689b9ec4a105f4d0e6aa4093698d3ffbf430acc4d1849426c7f0bb3ecf1`. The worker pins this exact byte manifest. Each fixed asset record includes route, relative file, MIME, byte length, SHA-256, official source/version, license and purpose. The backend owner implements owned-descriptor reading and verifies each served byte hash against this closed manifest; it must never accept caller-supplied filesystem paths.

Fixed asset routes are `/visual/asset-manifest.json`, `/visual/vision_bundle.mjs`, `/visual/wasm/vision_wasm_internal.js`, `/visual/wasm/vision_wasm_internal.wasm`, `/visual/wasm/vision_wasm_nosimd_internal.js`, `/visual/wasm/vision_wasm_nosimd_internal.wasm`, `/visual/face_landmarker.task`, `/visual/public-portrait.jpg`, and `/visual/LICENSE.mediapipe.txt`. The portrait is an operator test fixture, not user content. All evidence JSON/HTML and test files in this directory are outside the served inventory. Two additional fixed UI routes are `/visual-worker.js` and `/visual-runtime.js`.

The npm archive was fetched from the official registry and its published SHA-512 integrity verified before extracting five allowlisted regular members. No installer or upstream script executed. `acquisition-npm-metadata.json` records the archive's SHA-256, exact version 1.0.1, exported paths and integrity. The upstream assets are unmodified. The model is the official float16/version1 `.task` with a byte SHA-256 in `model-acquisition.json`. Static ZIP inspection finds face detector, landmark detector, geometry metadata and blendshape components; no model was run during acquisition. The three official model cards state Apache-2.0, and the official repository license is preserved. The npm archive contains no standalone LICENSE/NOTICE; its registry states Apache-2.0. Full binary/source/third-party notice correspondence remains a provenance limitation, not an invented legal clearance for a future product release.

`public-portrait.jpg` is the original public White House portrait by Pete Souza, acquired from Commons only after verifying pinned public-domain US-government metadata. Source SHA-1 and exact byte length were checked; SHA-256, revision 1241943590, API response and permanent rights-page HTML are preserved in `portrait-rights.json`, `portrait-rights-api.json`, and `portrait-rights-page.html`. No derivative transform or identity inference was performed. Capture age is unknown. This is a public engineering fixture, not consented child validation. It has not yet been processed by the actual model.

## Network boundary and telemetry facts

The downloaded 1.0.1 ESM contains a real metrics logger and `https://odml.pa.googleapis.com/v1/log`, with flush on close and a 60-second interval. It therefore does not match the official public source default DummyTaskLogger path. Do not claim this SDK contains no telemetry. `source-audit.json` records static observations, never private metrics payloads or an API key.

Before importing upstream code, the owned classic worker replaces fetch with exact local-inventory GET-only requests, strips credentials, refuses redirects/payloads/query/fragment/alternate origins and verifies bounded returned hashes. Its XHR fallback also permits only inventory GETs without credentials or request body. Other available worker network APIs are denied. Script loading permits only the two local WASM loader names. Denials increment a bounded counter (maximum 1000); URLs, payloads and model/private fields are not logged. SDK close is allowed to complete so its metrics attempt is denied before I/O and reflected in the shutdown count.

The backend must send enforcing CSP on **the worker response itself**, as well as the document: default-src none; script-src self plus wasm-unsafe-eval; worker-src self; connect-src self; no JavaScript unsafe-eval, external reporting endpoint or remote CDN. Frame processing should still work with external requests denied. No successful-external-request claim is established until actual cold/warm/init/infer/error/close browser checks inspect both successful requests and blocked attempts. This preparation enforces a proposed boundary; it does not erase SDK telemetry code or establish absence of attempts.

The classic worker dynamically imports the upstream ESM bundle, then the SDK uses classic importScripts to load its UMD WASM loader and publish ModuleFactory. Pure module-worker loading of that UMD file would not publish its global factory. CPU inference still uses OffscreenCanvas/WebGL for image texture handling; CPU is not a promise of no WebGL or universal Safari support. Exact browser compatibility and WASM CSP behavior remain actual runtime checks.

## Focused verification

```sh
node --check research/assessment-consumer-app/ui/visual-worker.js
node --check research/assessment-consumer-app/ui/visual-runtime.js
node research/assessment-consumer-app/visual/lifecycle-tests.cjs
```

Seventeen actual-source unit-seam tests pass: guarded bootstrap, remote/POST/query refusal, no/multiple/finite-invalid geometry, frame-rate refusal, frame closing, SDK-unit close metrics denial, bounded capture/one-frame ownership, late bitmap/result discard, background cleanup, termination deadline, stale geometry, init cancellation, detached cleanup and callback restart. The fake SDK/worker seams are explicitly labelled and do not execute upstream inference, browser APIs or physical sensors. Actual model checks on the pinned portrait, blank/checkerboard and declared multiple-face derivative belong to the root's later independent browser run. Source review and real network/runtime evidence are required before treating this as verified visual feedback.
