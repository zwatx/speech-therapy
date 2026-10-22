# Offline speech and word admission

This isolated engineering adapter separates capture validity, Silero speech evidence, independent Whisper recognition, whole-word matching, and the frozen research prediction. Recognition failures are unavailable attempts; they never become articulation errors. The underlying bridge’s `promptMatch` remains `unverified`, and learner, clinical, production, child-accuracy, qualified-review, and authentic-provenance claims remain false.

`recognize(wav_bytes)` runs the prompt-blind worker with bytes alone. It receives no expected word, phones, source filename, hint, history, or context. It returns private transcript/posterior evidence with byte/model/policy hashes. `decide(evidence, expected_word)` applies the fixed policy without another acoustic call. `assess(wav_bytes, prompt, age_years=9)` calls the frozen bridge only after admission and verifies exact audio, schema2 prompt, and request hashes. The optional `recognition_evidence` reuses same-byte private evidence. The injected acoustic/research execution seams exist for unit checks; actual challenge results use real models and the real bridge.

The schema2 prompt is `{schemaVersion:2,language:'en',transcript:word,words:[{text:word,phones:[...]}],targets:[{id,wordIndex:0,phoneIndex,targetPhone}]}`. Harness ages must be integers6–12; this parameter never establishes a public recording’s actual speaker age. The JSON result contains `schemaVersion`, `status` (`processed` or `unavailable`), `reason`, `capture`, `speechEvidence`, `wordMatch`, `research`, `runtime`, `binding`, and `claimLimits`. Rejection/failure has `research:null`. Public admission projections contain no recognized transcript or selected-token probabilities. Research probabilities remain private engineering data, not requested-word proof or learner scores.

`readiness()` and `declaration()` expose model IDs/revisions, model/policy/source hashes, readiness, and false claim flags without local paths/transcripts. They establish local correspondence, not signatures or authentic provenance. The installed runtime is `research/audio-head/.venv` with torch2.8.0, transformers4.57.6, and safetensors0.8.0. No dependency installation, remote model code, downloaded Python helper, tuning, or fitting is required.

The fixed policy is declared in [contract.md](../../work/roadmap-completion-20261004/admission/contract.md) before acoustic inference. Complete PCM16 mono16kHz WAV must be0.1–4seconds and<=132096bytes; rail clipping and RMS silence reject. Silero uses512sample windows at0.5, requiring160ms total positive samples and96ms consecutive positive samples. Whisper base.en uses greedy single-beam decoding without word prompts, context, sampling, or fallback, at most24newtokens with an EOS requirement. Mean selected ordinary-token processed-posterior log probability must be>=−0.8 and raw no-speech posterior<=0.6. Only case/ordinary edge punctuation normalization and the explicit yo-yo/yoyo alias are allowed. Extra/repeated words, uncertainty, truncation, malformed output, crash, and timeout abstain. These thresholds are engineering admission rules, not calibrated child accuracy or verified speech.

Pinned official artifacts are retained privately under `work/roadmap-completion-20261004/admission/models`, owned0700/0600. [Whisper base.en](https://huggingface.co/openai/whisper-base.en) revision`911407f4214e0e1d82085af863093ec0b66f9cd6` uses safetensors; its HF distribution declares Apache2.0, distinct from [OpenAI’s upstream MIT licence](https://github.com/openai/whisper/blob/v20250625/LICENSE). [Silero](https://github.com/snakers4/silero-vad) revision`1e261b036686cd0017d500ee96acd1c4ba572a9d` supplies the MIT TorchScript VAD. Exact hashes, source URLs, original card/licences, and dependency versions are in the bound manifest. Acquisition and inference are separate; inference is offline.

Run from the repository root with the retained private model files and frozen permitted source assets:

```sh
export PYTHONPATH=research/assessment-admission:research/audio-head:research/assessment-reference-assets
research/audio-head/.venv/bin/python -m admission plan PRIVATE_FRESH_PLAN.json
research/audio-head/.venv/bin/python -m admission run PRIVATE_PLAN.json PRIVATE_FRESH_RUN_DIRECTORY --expected-sha DECLARED_PLAN_SHA
```

Plans and run directories are exclusive. Output parents must be private owned0700, with600files. The runner binds every source clip, attribution, prompt, policy, model and source before the first call. It performs33 declared attempts:13 unique known public originals,13 paired concatenations,5 generated negatives, and2 exact-byte replicates. All169 cross-word comparisons reuse the13 original recognition results. Any concatenation exceeding four seconds is unavailable; it is never cropped. Every recognition and actual admitted research call has started/terminal evidence. Runtime records actual elapsed time, worker exit/timeout and peak RSS including import/model loading. There are no hidden rescue retries. A started-only interruption remains incomplete; a new run must disclose that history.

These clips and earlier wrong-word probes were already inspected. They are known engineering challenges, not untouched population validation. Source labels are not independently heard phonetic truth; public speakers’ ages are unknown. Exact-byte replicates measure deterministic pipeline behavior, not children’s capture/repeatability. First-policy failures remain failures; no result-based threshold rescue is permitted.

Focused unit checks use invented audio and explicit unit-only worker/bridge responses:

```sh
PYTHONPATH=research/assessment-admission:research/audio-head:research/assessment-workbench python3 -W error -m unittest discover -s research/assessment-admission/tests
```

Actual model results are recorded separately in the sealed private run report. No mobile files/builds/sensors, participants, sealed-study inputs, model fitting, outreach, publication, or deployment are part of this module. Intended-recording permission/qualification and independent validation remain separate work.
