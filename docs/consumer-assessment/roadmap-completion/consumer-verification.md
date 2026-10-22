# Recording and visual-practice verification

The local app at `http://127.0.0.1:8782/` centers recording rather than practice marks. Choose a word, tap Record, stop or let the four-second cap finish, then replay or record again. The camera mirror has its own opt-in button. To process audio, select an age from 6 to 12, enable optional computer processing, and tap Process this recording for that take. Enabling processing never submits a recording automatically.

The mirror displays live video locally; no frames are saved or sent. It does not analyze faces, mouth movements or articulation. A processed response means the research pipeline finished; it provides no correctness score or corrective guidance. The prototype age restriction is not evidence of child accuracy.

## Observed browser behavior

The actual app UI and AudioWorklet ran in a browser with explicitly labelled generated media: a 48 kHz tone stream and a 640 × 480 checkerboard video stream. Hardware microphone/camera access was denied by the helper's Permissions Policy. Its processing endpoint returned a strictly bound unit refusal; it made zero model calls.

- Recording stopped automatically at four seconds. Actual browser conversion produced 64,000 mono PCM16 frames at 16 kHz, in a 128,044-byte WAV. Recording playback started; no direct playback-time measurement or acoustic quality claim is made.
- The mirror rendered a live generated video and stopped its track when switched off.
- A second recording with processing enabled waited for its own explicit processing action.
- A cancelled, delayed response released after changing words did not reappear. Late microphone and camera permission promises did not resurrect cancelled capture.
- All three generated audio tracks, both video tracks, three generator contexts and three app contexts were stopped or closed. No promises or processing responses remained pending.
- Actual widths 1280, 1024 and 375 fitted without horizontal overflow. Opus 5.5 reviewed the actual screenshots and found no blocking visual issues.

Actual hardware permission dialogs, microphone/camera capture and a real tab visibility transition were not exercised. The helper also stops generators on page exit, so page-close-only behavior is not claimed as proof of app-owned cleanup. Separate controlled source tests cover background invalidation.

## Actual processing and focused checks

The real consumer server also processed three predeclared permitted HTTP requests, without injected outcomes or sensor use. The licensed public banana recording reached `processed` in 11.203 seconds, generated nonspeech returned `speech_not_detected` in 2.410 seconds, and the unsupported ZH example returned `unsupported_target` before launching an acoustic worker. All requests, WAVs, prompts and six core pins matched their responses. No stages, cleanup intent or blocked marker remained. The retained final nonspeech-worker diagnostic confirms cleanup, normal exit and no supervision failure. The HTTP report did not retain both per-attempt diagnostics, so a two-diagnostic audit is not claimed. These functional checks are separate from the fixed 33-attempt admission benchmark and are not new child evidence.

Independent Astra reviews cleared the backend and UI. Seventeen backend checks cover actual loopback transport, origin/token/schema/capacity and failure boundaries. Twelve controlled UI lifecycle checks, four worklet checks and six media-helper checks passed. The helper and controlled tests use declared seams; their outcomes do not count as model or clinical evidence. Two initial UI failures—automatic submission after capture and stale response side effects—were corrected before the final review.

The native simulator regression separately passed 47 checks: 44 units and three actual loopback integrations. Three UI checks passed on the unchanged final UI, including large text. The mobile Python suite passed 32 checks. An earlier native run retained 49 passes and one `cleanup_unconfirmed` failure; its cause remains unknown. The original failed private stage/intent and source were preserved, exact owned-process reconciliation was documented, and only a fresh runtime was used for regression. No model policy was tuned to rescue that failure.

The desktop example-check tool retains its separate evidence: 49 backend and nine controlled UI checks, seven planned terminal attempts, two manual practice marks and one identical-byte replay. Its protected export contents were verified, but the browser's file-save event was unconfirmed. That tool's history and practice marks are not the consumer recording app or evidence of improvement.

## Privacy and remaining work

Local recordings stay in browser memory until an explicit processing action. That action sends a bounded WAV to the local computer service. Normal processing removes its private temporary audio copy; crashes or uncertain cleanup can leave a private copy and block further work pending deliberate owner reconciliation. Cancelling the browser request does not promise immediate server-worker termination or secure erasure.

Actual authorized intended recordings, factual consent/rights/reviewer records, target-sound reference evidence, finished-product professional review, physical-device verification and production release controls remain separate work. Facial/articulation analysis and evidence-supported learner feedback are not implemented. The reserved once-only study remains sealed and unexecuted.

Private verification receipts and actual screenshots are retained under `work/roadmap-completion-20261004/consumer/`; these checkout artifacts are not publicly deployed app resources.
