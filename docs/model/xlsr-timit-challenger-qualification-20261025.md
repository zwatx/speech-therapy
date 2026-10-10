# XLS-R/TIMIT phoneme challenger qualification — October 25, 2026

Select `vitouphy/wav2vec2-xls-r-300m-timit-phoneme` as one **research challenger**,
not an app replacement or an established child-speech improvement. Public
metadata identifies independent XLS-R/TIMIT fine-tuning, distinct from the
existing LV-60/eSpeak-based Stage C model. The preceding
[saved-TRAIN audit](ctc-prefix-broad-development-20261025.md) motivates investigating
model alternatives rather than another beam-width sweep.

## Pinned public evidence

Revision: `efb7ae9b88f13db0d42eac8cedbba19739e2a278`. Root fetched only seven
small public metadata/source files; local hashes and URLs are recorded in
`work/phoneme-challenger-qualification-20261025/SOURCE-MANIFEST.json`. No weights,
corpus recordings or datasets were downloaded, and no challenger inference ran.
The browser could not open Hugging Face pages; direct public HTTPS metadata
retrieval succeeded and the revision API's returned commit was checked exactly.

- [Revision API](https://huggingface.co/api/models/vitouphy/wav2vec2-xls-r-300m-timit-phoneme/revision/efb7ae9b88f13db0d42eac8cedbba19739e2a278?blobs=true): publisher license tag Apache-2.0; 315,483,820 float32 parameters. Its published `model.safetensors` size is1,261,987,832 bytes, artifact SHA256 `0e3bde20ed7b252a48e69eddf7bd6d7eadc7dbacb06924148514e500ebad4b35`. These are remote artifact metadata, not a local weights verification.
- [Pinned config](https://huggingface.co/vitouphy/wav2vec2-xls-r-300m-timit-phoneme/blob/efb7ae9b88f13db0d42eac8cedbba19739e2a278/config.json): built-in `Wav2Vec2ForCTC`, 24 layers, hidden size1024, 16 attention heads, output width44, CTC blank/pad ID41. A future loader should use the pinned safe-tensor artifact and built-in architecture, with remote-code execution disabled.
- [Pinned preprocessor](https://huggingface.co/vitouphy/wav2vec2-xls-r-300m-timit-phoneme/blob/efb7ae9b88f13db0d42eac8cedbba19739e2a278/preprocessor_config.json): 16kHz scalar waveform features, normalization enabled, zero-valued right padding and attention masks enabled. Preprocessing must use the official feature-extractor contract; no custom waveform normalization is implemented here.
- [Pinned model card](https://huggingface.co/vitouphy/wav2vec2-xls-r-300m-timit-phoneme/blob/efb7ae9b88f13db0d42eac8cedbba19739e2a278/README.md): reports TIMIT fine-tuning of `facebook/wav2vec2-xls-r-300m`, an80/10/10 split and7.996% Test CER. These are publisher-reported results, not verified child PER or evidence of standard speaker-disjoint TIMIT evaluation. The linked training notebook was not inspected.

## Token and scoring contract

The [vocabulary](https://huggingface.co/vitouphy/wav2vec2-xls-r-300m-timit-phoneme/blob/efb7ae9b88f13db0d42eac8cedbba19739e2a278/vocab.json)
and [added tokens](https://huggingface.co/vitouphy/wav2vec2-xls-r-300m-timit-phoneme/blob/efb7ae9b88f13db0d42eac8cedbba19739e2a278/added_tokens.json)
together supply44 IDs. Collapse native frame IDs with **blank41**, before phone
projection. Preserve native IDs and token strings; never concatenate them and
retokenize. A separately projected already-collapsed beam sequence must preserve
repeated phones that were separated by blank in its alignments.

- `|` ID0 and literal space ID16 are distinct native separators. Omit only these
  from the declared phone-scoring projection and count each separately.
- Preserve diphthongs as whole tokens. Explicit spelling aliases are `g→G`,
  `ʧ→CH` and `ʤ→JH`, alongside direct matches to the existing broad IPA inventory.
- Flap `ɾ` ID10 stays unsupported in the primary projection. Do not silently
  reuse the existing eSpeak `ɾ→T` collapse. `[UNK]`40, `<s>`42 and `</s>`43 also
  remain visible as unknown phone errors with their original native token.
- Standalone AO/`ɔ` and ZH/`ʒ` have no output token. Do not invent these outputs or
  treat the first character of diphthong `ɔɪ` as AO. This limits comparison with
  the existing39-phone target inventory and must be reported with reference counts.
- **Metadata inconsistency:** config bos/eos IDs1/2 name actual vowel tokens
  `ɑ`/`æ`, whereas tokenizer added tokens put `<s>`/`</s>` at42/43. Do not filter
  IDs1/2 as special tokens. CTC uses blank41; tokenizer identity is explicit.
- Decode all44 probability channels before projection. Unsupported-token mass
  remains present; no subset renormalization, expected-word constraint, lexicon,
  calibration or threshold is introduced.

## Rights, runtime and next gate

The publisher's Apache-2.0 model tag and the training corpus's terms are separate
facts. The [official TIMIT catalog](https://catalog.ldc.upenn.edu/LDC93S1) lists
an LDC user agreement and copyright. The model card points to a Kaggle copy;
its upstream corpus access/provenance has not been independently established.
This work does not acquire or redistribute TIMIT, certify upstream compliance,
or establish rights for commercial model redistribution. No legal signoff or
professional model review is fabricated.

The1.26GB float32 checkpoint is an offline research candidate. Local load/runtime,
full-waveform memory/latency, native conversion, child-phone performance and
clinical usefulness remain unmeasured. Existing Stage C pre-block20 caches cannot
be reused as XLS-R input: they come from a different frozen backbone. Any later
comparison must prospectively declare permitted TRAIN recordings, identical
manual references and scoring gaps, sample/budget limits, exact safe weights and
preprocessing, with no refitting, held-out access or app promotion.

## Implemented adapter and actual verification

`research/audio-head/mdd_v1/xlsr_timit.py` now supplies a separate research-only
contract and immutable projection result. `collapse_frames` collapses native frame
IDs with blank41; `project_sequence` preserves already-collapsed repeats. Results
retain native IDs/tokens, projected phones, original unsupported tokens and both
separator counts. `decode_greedy` admits normalized full44-column log probabilities
through the existing shared CTC helper, then projects; it does not load weights,
preprocess waveform audio, run inference or enter any learner flow. Metadata
validation checks interpretation fields; revision and source hashes remain a
separate required check.

Nine generated adapter tests cover all44 IDs, the nonzero blank/vowel metadata
mismatch, repeat separation, diphthongs/aliases, flap/missing-phone limitations,
separators and special outputs, shape/normalization and malformed IDs/metadata.
Root's combined trusted Python3.13.14 run passes **22 tests** (13 shared
CTC decoder/exact-score tests plus9 adapter tests), warnings treated as errors.
Root separately verified every fetched source hash, the returned revision, exact
44-token identity and actual metadata against the adapter contract. Evidence is
`UNIT-TESTS.log` and `VERIFICATION.json` in the qualification task. Independent
Astra source/metadata review found no blockers; that review did not run weights.

No runtime readiness or child-performance claim follows from these model-free
checks. Next is a separately declared safe-weight acquisition/load qualification
and bounded permitted-TRAIN comparison, preserving fixed references and explicit
representational gaps; no refitting, reserved-data access or app promotion.

## Subsequent fixed runtime comparison

A separate [32-TRAIN-input comparison](xlsr-timit-train-comparison-20261025.md)
now verifies the exact downloaded safe weights, strict local runtime and all32
admitted crops. Its281 edits/596 phones compare with283 for saved C greedy and279
for saved C beam. This mixed result does not qualify an app replacement. The
metadata-only receipts above remain historical; no TIMIT corpus, refit, held-out
evaluation or learner-policy change is involved. The later report includes
short-utterance regressions and exploratory complementarity limits.
