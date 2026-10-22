# Local phrase practice

A small local interface for choosing a phrase, uploading one WAV, listening back, and explicitly checking it. It runs the existing frozen short-phrase research pipeline. Recordings are not sent to a cloud speech service. No model is downloaded at startup.

The check requires a genuinely known age of 6–12 and explicit permission to process the uploaded recording. Leaving the age blank still permits listening. Supported audio is mono 16 kHz PCM16 WAV, 0.1–4 seconds, at most 132,096 bytes. This version does not record, resample or crop audio and does not access a camera.

A recognized phrase means the independently recognized words matched the requested phrase. Research sound estimates remain uncertain: their forced sound locations have not been verified, and corpus-rating probabilities do not identify the sounds actually produced. The interface does not show those probabilities, diagnose a condition, grade pronunciation or claim a detected phone error. Practice cues describe the intended phrase only.

## Run locally

From the repository root, check the complete frozen source inventory:

```sh
research/audio-head/.venv/bin/python -B research/assessment-consumer-phrase-app/phrase_app/server.py --check
```

Launch with a fresh private runtime directory (replace the example suffix for every new server):

```sh
research/audio-head/.venv/bin/python -B research/assessment-consumer-phrase-app/phrase_app/server.py --port 8821 --runtime-root "$PWD/work/phrase-practice-runtime-new"
```

Open `http://127.0.0.1:8821/`. The server binds only to this loopback address and port. An existing runtime directory is refused. The source inventory and the original phrase prototype SOURCE-v4 must match. The check reads local cached models only when a user explicitly submits a recording.

## Privacy and cancellation

The page keeps one uploaded recording in memory for manual playback; changing or clearing it revokes its local playback URL. It does not save recordings to browser storage. Explicit checking creates private local temporary files and starts one owned research process. Uploaded audio, request details, sound vectors and features are removed only after both the outer process and its inner workers report confirmed cleanup. A small private aggregate job summary remains.

Cancel asks the running check to stop; a browser request ending does not prove that processing stopped. If worker cleanup cannot be confirmed, the server retains the borrowed files and blocks further checks. The page reports this state. Do not treat a page reload or server termination as proof that retained files are safe to remove.

## Verification and limits

The local engineering handoff is in `work/r-inference-checkpoint-20261012/phrase-practice-ui-v1/`. Generated checks cover admission, state transitions and failure handling; a separately declared real fitting-audio case checks the browser/HTTP/research-process path. These checks do not establish child pronunciation accuracy, reliable corrections, improvement, physical recording/playback, or clinical validity.

The catalog contains explicit expected phrases and intended sound cues. Its reference phrase comes from an already-permitted SpeechOcean762 training prompt; no dataset recording is bundled or served by this app. Existing research source terms and permissions do not establish product release eligibility. The once-only PERCEPT-R study remains preserved as a failed attempt and is not retried here.

Recording/mirror integration, independent pronunciation-error evidence, calibrated abstention, useful corrective feedback and professional final review remain on the wider app roadmap.
