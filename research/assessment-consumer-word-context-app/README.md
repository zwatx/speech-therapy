# Staged declared-context word practice successor

This sibling represents whole-word practice context truthfully: adult is a self-declared category, with no fabricated child age or adult calibration. Child ages6–12 remain explicit. The original8782 word service,8788/8789 sound services and their native bindings remain unchanged. This candidate needs separate source/runtime verification before promotion; prior actual-model outcomes have not been relabelled.

Only `/api/feedback` accepts the closed schema2 request: `schemaVersion`, `attemptId`, `practiceContext`, `prompt`, `audioBase64`. Context is exactly `{"kind":"adult"}` or `{"kind":"child","ageYears":6}` through12. Missing/extra/unknown context, adult with ageYears, boolean or out-of-range child ages, and schema1 feedback are refused. `/api/assessment` retains its original schema1 ages6–12 decoder. All eleven feedback claim flags remain false; target assessment is not performed, with ZH unsupported. Context is bound by the exact request hash and source-pinned feedback policy v2. Private worker metadata repeats requestSha256 so results from a different context cannot settle.

The unchanged recognition worker receives audio only, then the policy compares its whole-word recognition. Adult/child context does not select an ages6–12 head, change model thresholds, supply an expected-word decoding prompt or assert age/recognition validity. The public response/declaration field shapes remain schema1; `consumer-recording-feedback-v2` and the new feedback/wrapper/policy hashes identify this successor. `--runtime` selects a fresh separate owned runtime; reserved live ports8782/8788/8789 are refused by the explicit launcher. `--check` verifies package/source/content metadata without reading model weights, opening Catalog media, creating runtime or listening.

From the repository root:

```sh
python3 scripts/consumer-word-context-app.py --check
python3 scripts/consumer-word-context-app.py
```

Open `http://127.0.0.1:8791/`. The app uses the installed pinned offline speech models, listens only on this computer, and starts with microphone, camera and word checking off. Use `--port` for a different port and `--runtime` for a fresh separate runtime; only one process can own it. Control-C stops the server. No account is required.

Choose a word, play its attributed example, then choose Record and say it once. Capture stops after four seconds. You can replay a try without checking it. For optional word checking, choose Adult (18+) or the person's child age (6–12), opt in, then choose Check this try. Each recording requires its own explicit check. Results distinguish recognized-word match, mismatch, uncertain recognition, no detected speech, recording problems and processing failures. These are recording properties and whole-word model observations, not pronunciation correctness, a diagnosis or measured improvement. ZH words can receive whole-word recognition while their target-sound assessment remains unsupported.

Free practice of canonical **bread** adds a listening focus for b followed by r at the beginning of the whole-word example. After recording, Play example, Play this try and Record again are beside the word-check controls, including when word checking is off. This is a cue from the selected word, not a detected error or a treatment recommendation. Playback and recording remain explicit. The shortcut follows the existing recording/cleanup guard, keeps the ordinary two-try limit, and is hidden in guided sessions or when no example is available.

Up to two tries for the selected word stay in tab memory for listening and comparison. A third replaces the oldest after successful capture. Changing word or check settings, clearing tries, hiding or closing the page clears clips/results and cancels display of pending replies. Hiding/closing also stops sensors. Each check creates a temporary private computer copy; normal completion removes staging before a result is returned. Failed or uncertain cleanup preserves evidence and blocks new checks, including after restart. Stopping waiting does not stop a server worker immediately. Secure erasure and zero retention across crashes are not promised.

Guided word check adds a 13-word first round, all-word summary, manual practice and one explicit fresh recheck. Select Guided word check, choose a declared practice context, enable checking, then start. Every Record and Check is explicit. Skipped, unsuccessful and unreached words stay in the summary; practice never changes first-round rows. Recheck requires new recording attempts and shows observations side by side, including incomplete comparisons and identical-byte disclosure. Technical counts are under How this round was checked. No score or improvement claim is added. Session metadata and rendered results clear on end, switching to free practice, setup/context changes or leaving; clips clear across words/views. See [guided verification and limitations](../../docs/consumer-assessment/guided-word-check-verification-20261004.md).

The camera is a separate optional mirror. After turning it on, Show a mouth outline runs a pinned local face model in a worker. It estimates visible mouth position only; no speech, tongue, depth, identity or clinical finding is inferred. Zero or multiple detected faces suppress the outline. Camera frames and landmarks are not saved or uploaded. The worker blocks external connections, including SDK telemetry attempts. Word/settings changes, clear, camera off and leaving the page stop analysis. Unconfirmed model cleanup blocks a restart until reload. Mirror use remains independent of word checking.

The catalog is the exact fifteen reviewed engineering prompts, thirteen licensed public recordings and original illustrations. Attribution, source labels, conversion changes and unknown speaker ages remain visible. Professional suitability and intended-child recognition accuracy remain unestablished.

## Service and verification

The new `/api/feedback-declaration` and `/api/feedback` are separate from the preserved `/api/declaration` and `/api/assessment` research schemas. Exact current-origin/Host/process-token checks, closed catalog/media routes, source/content/model/policy bindings, finite metrics, four-second/200,000-byte JSON/132,096-byte WAV limits and single-worker cleanup ownership remain enforced. No camera upload or durable recording-history endpoint exists. Fresh private runtime: `work/consumer-feedback-20261007/adult-word-context/runtime`.

[Historical predecessor API contract](../../work/consumer-feedback-20261004/feedback-api.md) · [Predecessor verification and limitations](../../docs/consumer-assessment/recording-feedback-verification-20261004.md) · [Visual assets, source and rights](visual/README.md).

```sh
PYTHONPATH=research/assessment-consumer-word-context-app:research/assessment-mobile-admission:research/assessment-admission:research/assessment-desktop-journey:research/assessment-reference-assets:research/assessment-recording-access:research/assessment-review-service:research/assessment-workbench:research/audio-head python3 -W error -m unittest discover -s research/assessment-consumer-word-context-app/tests -p 'test_*.py'
```

The predecessor focused suite had 35 checks; its historical source-bound evidence remains unchanged. Two additional actual HTTP invalid-prompt regressions, 19 independent response rejection checks, 52 independent actual-UI-source checks and separate visual lifecycle/network checks passed. Actual eight-request model verification and actual face-SDK browser behavior are reported separately from injected unit outcomes. No hardware microphone/camera or intended-child study was used. The original failed mobile runtime, frozen research sources, policy and benchmark evidence remain preserved.

Focused bread practice behavior checks: `node --test research/assessment-consumer-word-context-app/tests/bread-practice.test.cjs`. These use generated state, not sensors, speech inference or correctness labels.

Example playback explicitly downloads at most 132,096 bytes from the local public-reference route into a short-lived browser object URL. Stop, changing words, recording or leaving cancels a pending download and releases the player URL. The 10-second limit bounds downloading. This fixes browser media range requests being refused by the closed reference route; server guards and recognition/model bindings are unchanged. Focused async failure/race checks: `node --test research/assessment-consumer-word-context-app/tests/example-playback.test.cjs`.

[Current bread practice/playback verification](../../docs/consumer-assessment/bread-practice-verification-20261006.md) records the latest source, generated browser checks and remaining limits; earlier UI evidence applies to its preserved versions.
