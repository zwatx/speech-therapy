# Inactive desktop reference preview

Source-only adapter for the original Hugging Face Wav2Vec2ForCTC phonetic checkpoint, revision ae45363bf3413b374fecd9dc8bc1df0e24c3b7f4. It is not connected to any application, browser route or server. Importing it does not import frameworks, read assets or start a worker.

`contract.py` admits only canonical complete mono 16000 Hz PCM16 RIFF files with 1600–64000 samples and an exact identity. `worker.py` uses the unchanged pinned NumPy extractor and CPU FP32 model, strict loading info and the original two positional weight-norm migrations. Decode uses only valid convolution frames; private logits, normalized values, IDs and symbol hypotheses are sensitive speech information. Special symbols are explicit unsupported observations. Silence/nonspeech hypotheses are not confirmed speech.

`owner.py` owns a single cold request and preserves the borrow after unknown cleanup. Root must provide a separately reviewed exact-child supervisor, independent source-buffer bootstrap, current complete runtime pins, exact five-asset snapshot-to-blob mapping and rehash, offline fixed environment and bounded private FDs. The adapter does not implement OS network isolation. `activate` is a dependency-injection boundary, not an approval or security boundary. Do not activate from a UI or pass untrusted admission objects.

Root must read and independently review the exact frozen sources before any actual run. No framework, model, waveform, compiler, simulator, archive, service or network execution was performed here. Pure tests mock acoustic admission/writing rather than generating audio. There is no prospective execution script; actual observations remain root-owned and separately admitted.

Original native 304 checks remain FAILED. The normalization prefix evidence remains 34 passed / 6 failed among 40 checks. This adapter does not repair either. OriginalNativeParityAccepted, clinical, producedPhoneTruth and learnerFeedback stay false. No phone correctness, pronunciation score, diagnosis, child admission or corrective advice follows from a successful model observation.

One pure check command is `python3 -B research/phonetic-reference-preview/test_reference_preview.py`; it imports only standard-library code and source buffers. Native/provider readiness, latency, RSS, actual model loading and acoustic results remain unverified.
