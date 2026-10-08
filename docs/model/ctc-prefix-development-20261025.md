# Phone-sequence decoder development — October 25, 2026

A new research-only prefix-beam decoder reduces errors from **184 to178 across307 reference phones** on one fixed32-utterance JIBO **training** subset. The model weights are unchanged. This is a small in-training-set development gain, not independent accuracy, intended-child validation or a clinical finding. The current app's word recognizer and feedback are not replaced.

## Implemented and verified

[`prefix_decode.py`](../../research/audio-head/mdd_v1/prefix_decode.py) preserves full native vocabulary IDs and expands every token. It keeps separate blank/nonblank alignment mass in log space, handles repeated phones correctly and orders ties deterministically. There is no expected word, lexicon, language model, token pruning, length reward or posterior renormalization over selected phones. Blank ID is explicit. Finite-beam scores describe retained alignment mass, a lower bound on the exact full sequence likelihood; they are not calibrated confidence.

The recurrence follows [Hannun's CTC explanation](https://distill.pub/2017/ctc/). Nine actual standard-library unit tests pass under Python3.13.14 with warnings treated as errors. Independent exhaustive path enumeration covers vocabulary sizes2/3, lengths0–4 and every blank position, along with repeated labels, empty/allblank outputs, ties, invalid normalization and a case where greedy differs from the most likely collapsed sequence. Beam width1 is not assumed equivalent to greedy.

## Fixed development measurement

The pre-prediction declaration selects32 different training children, eight clips each from blocks, brush, colors and letters/digits. Within each task, selection follows a fixed hash order, globally at most one utterance per child, with declared duration0.025–4.0seconds. Existing Stage C membership and feature/audio identity mappings are checked. The shared manifest contains all splits: admission parses its metadata to project training records only; no dev/test records are passed to the worker. No held-out features, audio, predictions or references are used.

Inputs are the selected existing pre-block20 cached tensors, each float32[T,1024],1≤T≤199. The loader constructs only the unchanged Stage C model's final four stable-layer-norm blocks, final norm and40-output head; it strictly loads the selected epoch8 weights. It reuses the original eager-attention bucket/mask/trimming forward method. No backbone is constructed, no raw recording is opened and no feature extraction, new fit, calibration, threshold tuning or download occurs.

One CPU float32 forward per selected tensor supplies the identical saved log probabilities to greedy decoding and beam16. Two CPU threads are used. All predictions are saved before reference scoring. The original greedy collapse is checked against the new greedy helper for every input. Reference sequences are the existing broad-phone normalization of manual child production transcriptions; that normalization omits narrow phonetic distinctions. The source corpus covers younger children, with substantial letter/digit material; it is not the intended6–12 SSD population or a clinical error-reference set.

| Decoder | Reference phones | Substitutions | Deletions | Insertions | Total edits | Phone error rate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Existing greedy |307|86|94|4|184|59.93%|
| Prefix beam16 |307|88|85|5|178|57.98%|

The1.95-percentage-point decrease comes from nine fewer deletions, offset by two additional substitutions and one insertion. Six utterances have fewer edits, none more, and26 tie. Nine hypotheses changed, so three changed sequences tie on edit count. This is not a claim that every emitted phone or task improved.

| Task | Utterances | Reference phones | Greedy edits | Beam edits |
| --- | ---: | ---: | ---: | ---: |
| Blocks |8|66|35|35|
| Brush |8|133|75|71|
| Colors |8|81|56|55|
| Letters/digits |8|27|19|18|

Total measured decoder times are0.0302seconds greedy and1.0063seconds beam across32 inputs. These implementations have different search work; beam is slower. The cached upper-model forwards total0.5412seconds. Worker wall time is5.315seconds, enclosing monitored stage5.931seconds, and maximum sampled process-group RSS765,744KiB. These are local cached-feature engineering timings, excluding raw-audio/full-encoder work—not mobile or complete-check latency. The600second/8GiB caps were not approached; the worker closed normally without signals, remnants or cleanup errors.

## Evidence and limits

The declaration/protocol, source/runtime pins, saved local tensors' hashes, predictions, aggregate results and owner receipts are retained in `work/ctc-prefix-development-20261025/`. A separate single-row edit-distance implementation independently reconstructs184/178 edits and the307-phone denominator from saved outputs. Source and selected-tensor bindings remain unchanged. The postcheck makes no model call.

Raw child audio, identities, reference transcriptions, features and participant-level outputs are not published with this report. Only aggregate findings are described here. Existing Stage C/D checkpoints, selections, calibration and reporting evidence are unchanged. PERCEPT, reserved data and closed native-model screens remain untouched.

Source attribution: Shankar et al.(2024), [doi10.1121/10.0034195](https://doi.org/10.1121/10.0034195); JIBO Kids Corpus release [doi10.5281/zenodo.19604408](https://doi.org/10.5281/zenodo.19604408); DrivenData JIBO Kids Corpus Transcripts dataset13/version12. The acquired CC BY4.0 source/license and transcript-description records remain in the existing ignored JIBO source folder. The existing [Stage C report](../../work/mdd-v1/stage-c-result.md) describes mapping exclusions, training and source limitations.

Retain beam16 as a research option. The next useful accuracy-development step is a separately declared broader training-only comparison with unchanged weights, mapping and beam width, including longer utterances and per-task deletion/cost accounting. Do not tune beam width on these32 examples or present them as independent validation. No decoder or model is automatically promoted to learner sound feedback. Better expected-word transcription alone still cannot establish which sound a child produced.
