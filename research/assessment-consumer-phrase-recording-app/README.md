# Local speech practice

Choose a sound and word, record up to four seconds, listen back, and explicitly check the recording. The app uses the existing local cached models and the project's hand-selected 892-word library (2,398 sound/position entries, 24 groups). No audio is sent to an external speech service. The responsive interface also provides a guided recognition review, user-chosen practice and a separate recheck round.

Recognition mode is the default. It accepts adult or unknown-age word recordings without inventing a child age, and does not run the child sound model. A matched word means the independent recognizer matched the requested word under the unchanged recognition gate; it is not a pronunciation grade. Recognition failures are not diagnosed speech errors. The 23 ZH entries are available for recording/listening practice, without model checks.

An explicit child-research mode accepts genuinely known completed ages 6–12. Its sound estimates remain uncertain: forced canonical sound locations are unverified, and corpus-rating vectors do not identify the phones actually produced. The four short phrases use this research path only. The interface does not show those vectors or infer a diagnosis, detected phone substitution, treatment need or improvement. Guided results count observations and let the user choose practice words.

## Record and listen

Only an explicit Record action requests microphone permission. The page never requests a camera. Recorded audio uses actual captured frame counts, is limited to four seconds, and is converted to mono 16 kHz PCM16 WAV with a low-pass filter before downsampling. Microphone audio is not played through speakers during capture. Playback requires a separate user action. Existing compatible WAV uploads remain available (0.1–4 seconds, at most 132,096 bytes).

Permission may remain pending until the user responds to the browser. Discard invalidates the attempt but does not report it stopped until the late stream, audio graph and context are settled. Cleanup uncertainty blocks further capture/checks. Reloading does not prove retained processing stopped.

## Run locally

From the repository root:

```sh
research/audio-head/.venv/bin/python -B research/assessment-consumer-phrase-recording-app/phrase_app/server.py --check
research/audio-head/.venv/bin/python -B research/assessment-consumer-phrase-recording-app/phrase_app/server.py --port 8823 --runtime-root "$PWD/work/speech-practice-runtime-new"
```

Use a new private runtime directory name for each server. Open `http://127.0.0.1:8823/` on this Mac. This service binds exclusively to loopback; it is not reachable from a separate phone. It is a local web interface, not an installed mobile app. The native iOS app under `apps/ios-learner` remains a separate mobile implementation. Exposing this research listener or transferring phone audio to this Mac requires a separately reviewed connectivity/privacy decision.

Complete candidate source pins and the original prototype SOURCE-v4 must match. The verified prior upload version on port 8821 and the frozen word/phrase prototype are unchanged. No model downloads, refits, holdout retries or external hosting are part of this app.

## Privacy and sources

The page keeps one current recording in memory with manual playback. It does not persist recordings in browser storage. Explicit checking creates private local temporary files; audio, prompts, numeric recognition tokens, features and vectors are removed only after the exact outer process and its workers confirm cleanup. A small private aggregate job audit remains. Unconfirmed cleanup retains borrowed files and blocks further checks.

Vocabulary pronunciations derive from the project's pinned CMUdict source. All listed pronunciation variants and selected-position metadata remain in the generated catalog; checking uses its first canonical variant. US-English dictionary metadata does not establish suitability for every accent, dialect or learner. Original CMUdict terms are served at `/credits`. No research dataset audio is bundled.

## Verification limits

Task evidence is in `work/r-inference-checkpoint-20261012/phrase-recording-v1/`. Generated unit and browser checks exercise capture, resampling, ownership, selection, consent and failure states. A generated-silence check exercises the real HTTP/CLI path without acoustic model execution. Previous fitting-audio execution established integration, not accuracy. Physical microphone usefulness, independent pronunciation-error calibration, clinical diagnosis, treatment outcomes and qualified final review remain open. The consumed once-only PERCEPT-R failure is preserved and is not retried.
