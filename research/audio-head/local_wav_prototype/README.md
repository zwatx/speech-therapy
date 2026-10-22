# Local WAV research preview

This isolated CLI accepts an existing WAV and an expected practice prompt. It runs the existing local Whisper/Silero word-admission policy. A matched word and an explicitly known child age of 6–12 permit the unchanged shared 23-consonant research model. Its three outputs per occurrence are **subjective corpus-rating probabilities**, not calibrated chances of correctness or clinical findings.

An additional `phrase_cli.py` entry point accepts an explicit canonical phrase of 2–8 words and a genuinely known child age of 6–12. This research mode compares the entire prompt-blind recognized sequence, preserving the existing waveform, VAD, decoder, confidence, no-speech and completion rules. It records the original word-policy refusal separately; the original single-word entry point remains the default.

No server, microphone, playback, training, model acquisition or application integration is included. The initial implementation was Astra-authored; actual Opus 5.5 API/copy reviews and Fable 5.1 source review informed the subsequent fixes. Existing services and frozen research sources are unchanged.

WAV/prompt paths beneath the PERCEPT-R source root or consumed confirmatory run root are explicitly refused without opening them. This is a path guard, not provenance detection for renamed copies. Use only permitted non-holdout recordings.

From the repository root:

```sh
research/audio-head/.venv/bin/python research/audio-head/local_wav_prototype/cli.py list

research/audio-head/.venv/bin/python research/audio-head/local_wav_prototype/cli.py run \
  --wav /absolute/path/to/permitted.wav \
  --prompt-choice r-middle-bread --recognition-only \
  --output "$PWD/research/audio-head/outputs/local-wav-prototype/new-attempt"
```

For a genuinely known child age, replace `--recognition-only` with `--age-years 6` (completed ages 6–12 only). Invalid ages refuse; there is no default or imputed age. Unknown/adult age uses recognition-only mode and never invokes the shared head. The CLI never determines a recording's speaker age from its contents or pathname.

`--prompt-json /absolute/path/prompt.json` accepts the existing schema-2 canonical-prompt format in place of a catalog choice. It must describe exactly one English word, with explicit canonical ARPAbet and distinct target IDs/positions. Repeated consonants are supported and caller order is preserved. There is no text-to-phone dictionary or `--word` shortcut. The catalog has 15 entries, including the deliberately unsupported ZH entry; `list` marks support, and selecting ZH refuses. Vowels are allowed in the canonical sequence but are never scored targets.

Input must be mono PCM16 RIFF/WAV, 16 kHz, 0.1–4 seconds, at most 132,096 bytes. Nothing is resampled, normalized, cropped or overwritten. This single-word boundary belongs to the existing word-admission policy. Earlier sentence extraction/parity evidence remains separate; this CLI does not reinterpret it as single-word admission evidence.

Input and prompt paths may be relative or absolute, but must resolve without symlinked components. On macOS use `/private/tmp`, rather than the `/tmp` symlink. Hardlinked files and files owned by another user also refuse. Use the command as shown; Python's `-I` isolated-import option is not supported by this script entry point.

The output must be a fresh direct child of `research/audio-head/outputs/local-wav-prototype`. Each attempt has a private request and terminal receipt, measured elapsed time, source/model bindings and worker facts. Accepted shared extraction additionally retains `features.npy` and `shared-result.json`. Outputs are exclusive; there is no retry/resume switch. A new attempt is a separate observation, not a replacement of a failed one.

The terminal shows the state, fixed reason, failure phase, number of scored occurrences, receipt path and a short explanation. Exit `0` means abstain, recognition-only or research scores; it does not imply a pronunciation pass. Exit `1` means execution or cleanup failed, and exit `2` means refusal before execution. No argmax rating, praise, phoneme correction, raw ASR transcript or numerical score is displayed. Private JSON retains the conditional three-class corpus-rating vectors only when the fixed word-admission and necessary phone-evidence rules pass. Prompt-blind CTC token IDs and expected mapped IDs are separate diagnostics. Their equality does not gate scores and does not establish produced-phone identity. Retained ASR and CTC token IDs can be decoded into speech information. Removing the literal transcript field does not anonymize these private receipts; do not share them as anonymous data.

Failures preserve private diagnostics with exception type, processing phase, code locations and operating-system error number when applicable. Exception messages, source-line text, stack locals and worker stderr are excluded because they can contain recognition text. Parent failures use `failure.json`; shared-worker failures use `worker-error.json`. A launch failure is recorded separately and permits temporary cleanup when no worker started. A receipt-write failure is reported as execution failure, never as refusal before execution.

Temporary WAV copies, private ASR transcript, CTC posteriors/jobs and private model staging are removed only after the exact owned child has been collected and its process group is observed absent. Original input bytes are rehashed after cleanup. A surviving group after a collected leader is **unknown**; the controller does not signal a potentially reused group or delete its borrowed files. Permission failures are never credited as absence. `cleanup_unknown` requires inspection, not blind deletion while a worker may remain alive. Uncatchable termination, power loss and filesystem stalls cannot guarantee cleanup.

Word/shared worker budgets are 60/120 seconds, with a 190-second processing budget checked between phases and a five-second child-exit grace after a group kill. Hashing and final filesystem cleanup are synchronous; this is not an OS-enforced end-to-end hard deadline. Model loaders are local-only, Python feature-worker socket calls are denied, and the existing CTC worker denies fetches. These are application guards, not OS network isolation.

Generated-only checks:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 research/audio-head/local_wav_prototype/test_prototype.py
```

Those checks exercise malformed/generated inputs, actual Python helper ownership and cancellation, cleanup, and routing with in-memory model doubles. They establish neither model readiness nor recognition/scoring accuracy. Root owns review and subsequent permitted non-holdout model executions.

Use one fresh CLI invocation per attempt. The policy-compatible RSS field is the OS's cumulative child-process peak for that invocation, not a separately sampled per-worker RSS trace. Calling `run()` repeatedly in one interpreter is only a test seam and would inherit that process's earlier child peak.

## Observed checks and remaining gap

Run this from the speech-therapy repo root. Each run needs a new output folder name.

```sh
research/audio-head/.venv/bin/python -B research/audio-head/local_wav_prototype/cli.py run --wav work/assessment-real-data-20261004/references/wav/bread.wav --prompt-choice r-middle-bread --recognition-only --output research/audio-head/outputs/local-wav-prototype/new-private-preview
```

The terminal prints `status`, `reason`, `scoredOccurrences`, `cleanupConfirmed`, and the private receipt path.

What we observed:

- All 24 generated tests passed (0.350s).
- The matching public "bread" recording was recognized (4.48s). The speaker's age is unknown.
- A "door" recording with the "bread" prompt was declined with `requested_word_not_matched` (2.72s).
- Generated silence was declined before any model ran (0.014s).
- A malformed file and the `zh-middle-treasure` choice were refused before running, with exit code 2 and no output created.
- A recording of a child with a known age of 6 was declined with `single_word_required` (2.78s). A second, pre-declared word crop was declined with `recognition_uncertain` (4.08s).
- No single-word run produced shared scores. The model and policy stayed fixed, every attempt was kept, cleanup was confirmed, and the original files were unchanged.

Remaining gap: this interface has not yet produced shared sound scores after genuine child-word admission. It needs a permitted isolated-word recording with a genuinely known child age (6–12) and explicit canonical prompt. The separate earlier whole-sentence proof of 11 shared occurrences does not establish this interface's complete path. The model supports 23 consonants; the 15 catalog choices are a smaller prompt set, including the unsupported ZH choice. Vowels are not scored. Recognition-only mode can be used when age is unknown or outside 6–12. Research probabilities estimate subjective corpus ratings; they do not establish pronunciation correctness or produced-phone identity. Accuracy validation and application integration remain open.

## Separate short-phrase research mode

```sh
research/audio-head/.venv/bin/python -B research/audio-head/local_wav_prototype/phrase_cli.py \
  --wav /absolute/path/to/permitted-phrase.wav \
  --prompt-json /absolute/path/to/canonical-phrase.json \
  --age-years 6 \
  --output research/audio-head/outputs/local-phrase-prototype/new-private-preview
```

The supplied schema-2 prompt must contain the exact phrase transcript, an explicit canonical phone sequence for every word, and distinct consonant targets identified by word and phone position. Target order and repeated sounds are preserved. The same mono 16 kHz PCM16, 0.1–4-second audio bound applies; nothing is cropped or converted. Unknown/adult age is refused in this phrase interface.

Phrase normalization folds ASCII case, separates whitespace and trims punctuation at word edges. Internal ASCII apostrophes and hyphens are preserved. Punctuation-only tokens, non-ASCII lexical forms, changed word order, missing/extra words, contraction expansion and approximate matches refuse. These strict rules can decline otherwise usable speech; recognition mismatch is not a pronunciation-error finding.

The separately hashed phrase policy opens its sequence comparison only after the frozen word policy returns `single_word_required` with all preceding evidence checks passed. It preserves that original decision as **not admitted**. A matched phrase can then reach the unchanged child research head if necessary phone evidence is available. Forced alignment follows the supplied canonical sequence; it does not identify produced-phone errors. Ordinary ASR and CTC token IDs are omitted from retained phrase receipts; canonical prompts and private research vectors still contain sensitive speech information.

The phrase terminal shows status, reason, scored occurrence count, cleanup and elapsed time. Exit zero can also mean abstention. Runtime setup, exclusive outputs, local model bindings, supervision, timeout limitations and cleanup ownership follow the word interface. This is an isolated research preview; consumer integration and independent validation remain open.

Generated phrase checks use invented evidence and explicit worker doubles:

```sh
research/audio-head/.venv/bin/python -B research/audio-head/local_wav_prototype/test_phrase_admission.py
research/audio-head/.venv/bin/python -B research/audio-head/local_wav_prototype/test_phrase_runtime.py
```
