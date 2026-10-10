# Fixed pretrained phoneme-challenger comparison — October 25, 2026

The separately trained XLS-R/TIMIT challenger is **not a clear replacement** for
the current research model. On32 fixed JIBO TRAIN recordings/596 reference phones,
it produces281 edits, versus283 for saved Stage C greedy and279 for saved Stage C
beam16. Its lower deletion count comes with more substitutions and insertions.
The runtime works locally; this result does not establish useful child-sound
judgment or justify changing learner feedback.

## Fixed design and data admission

Before downloading weights or making challenger predictions, the declaration
selects the first four entries in each of the eight existing task/duration cells
of the [broader TRAIN panel](ctc-prefix-broad-development-20261025.md). Selection
uses original declaration order, without outcome-based replacements. There are
26 children, at most three contributions each. Stage C greedy and beam16 outputs
are reused exactly from that completed run; there is no baseline inference.

Shared-manifest metadata supplies selected TRAIN intervals and verifies every row
referencing a selected session belongs to the same TRAIN child. The worker
receives only these32 rows. Each resolved session path is admitted inside the
fixed existing JIBO audio root with its frozen child split. The loader memory-maps
the containing TRAIN session/header and converts only the rounded/clamped slice
to float32; it does not open isolated utterance files. All32 crops' endpoints,
mono16kHz encoding, duration, finite samples and original float32 SHA256 match
before the first data forward. No waveform is saved or uploaded.

The transcript release README describes phonetic transcriptions written by
transcribers and subsequent formatting normalization, supporting the use of
production references. It does not establish perfect annotations, clinical error
labels or speech-disorder diagnoses. Existing broad mapping/exclusions remain
unchanged. The corpus's younger children and task mix do not establish intended
6–12 SSD performance. Stage C was fitted on JIBO TRAIN, while the challenger is
reportedly TIMIT-trained: this is asymmetric, exploratory cross-model development,
not an independent accuracy test or a controlled architecture comparison.

## Verified weights and runtime

The [qualified challenger](xlsr-timit-challenger-qualification-20261025.md) stays
at revision `efb7ae9b88f13db0d42eac8cedbba19739e2a278`. Root acquired only its
published `model.safetensors`, exactly1,261,987,832 bytes, SHA256
`0e3bde20ed7b252a48e69eddf7bd6d7eadc7dbacb06924148514e500ebad4b35`.
Verified TLS streaming used no account credentials; no pickle, custom model code,
TIMIT corpus or extra checkpoint was acquired. Pinned metadata copies match.
Publisher-declared weight licensing and TIMIT/Kaggle upstream provenance remain
separate; this does not grant commercial distribution clearance.

Built-in Transformers loading is local-only/safetensors-only, remote code disabled,
with no missing, unexpected, mismatched or errored keys. Parameter count is exactly
315,483,820; CPUfloat32, eager attention, two threads, eval/inference and no gradients
are checked. The official feature extractor applies the pinned16kHz normalization
and returns an all-ones attention mask for each single unpadded clip.

One synthetic1-second signal first passes the independent runtime probe, producing
49 finite44-channel frames. The subsequent comparison makes one full-backbone
forward per admitted crop (32 data forwards). Native greedy decoding uses all44
classes with blank41; vowels1/2 stay vowels, separators remain counted and emitted
unsupported tokens remain errors. There is no beam search for the challenger,
lexicon, prompt, language model, subset renormalization, fit, calibration or tuning.
All ordinal posteriors/predictions are saved before reference scoring.

## Actual comparison

| Decoder/model | Reference phones | Substitutions | Deletions | Insertions | Edits | Micro-PER |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Saved Stage C greedy | 596 | 135 | 138 | 10 | 283 | 47.48% |
| Saved Stage C beam16 | 596 | 132 | 135 | 12 | 279 | 46.81% |
| XLS-R/TIMIT greedy | 596 | 168 | 66 | 47 | 281 | 47.15% |

Against Stage C greedy, challenger yields72 fewer deletions,33 more substitutions
and37 more insertions: two fewer net edits (0.34 percentage points). It improves15
utterances, regresses13 and ties4. It has two more edits than saved Stage C beam.
These numbers do not establish robust superiority or equivalence.

| Task/duration | Utterances | Phones | Stage C greedy edits | Stage C beam edits | Challenger edits | Challenger win/loss/tie vs C greedy |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| blocks:short | 4 | 32 | 18 | 18 | 17 | 2/2/0 |
| blocks:long | 4 | 126 | 61 | 57 | 55 | 3/1/0 |
| brush:short | 4 | 18 | 13 | 13 | 13 | 1/1/2 |
| brush:long | 4 | 122 | 45 | 45 | 45 | 2/1/1 |
| colors:short | 4 | 25 | 18 | 19 | 25 | 1/3/0 |
| colors:long | 4 | 120 | 77 | 76 | 71 | 3/1/0 |
| letters_digits:short | 4 | 11 | 5 | 4 | 10 | 0/3/1 |
| letters_digits:long | 4 | 142 | 46 | 47 | 45 | 3/1/0 |

Short colors and short letters/digits regress materially in this small panel;
longer blocks/colors improve. All cells remain included. Four reference AO phones
remain scored although the challenger lacks AO output; there are zero ZH
references, so this panel cannot test its missing ZH capability. Four emitted
flaps stay unsupported `<unk>` errors. Twenty-six native delimiters and185 literal
spaces are omitted only in the declared phone projection, with separate counts.
No unsupported mass is removed from decoding or renormalized.

## Observed execution and independent recount

Root personally observed each outer terminal before its dependent step:

- Declaration exited0; frozen declaration SHA256 `b77325df6f91d16f45542b7ff2f6995bba16089b603eae8132782c66a0f234ef`.
- Download outer33138 exited0:59.1055s monitored stage,35,712KiB sampled RSS.
- Synthetic probe outer49706 exited0:4.9183s,1,188,848KiB sampled RSS; signal processing0.1570s.
- Comparison outer23916 exited0:10.8618s,2,357,440KiB sampled RSS. All real clip processing totals6.7893s, including official preprocessing, full model execution and greedy decoding. Prediction-loop wall time6.8113s also includes ordinal writes.
- Independent postcheck exited0: saved-output single-row Levenshtein recount agrees with every total/task/cell edit count, reference denominator and paired result, verifies projections, source pins and exact safe weights, and makes no model call or audio read.

All monitored stages close normally with no signals, remaining group members or
cleanup errors. Caps are600s download/180s probe/600s data, sampled8GiB RSS and
12GiB free-disk reserve. Synchronous hash admission is not a strict whole-parent
deadline or proof of every implicit runtime allocation. Mapped load timings
(0.0694s probe/0.0560s data process) are not cold physical loading measurements.
Full-waveform challenger timing is not comparable to cached-upper-layer Stage C
timing, nor native/mobile or complete app latency. The independent recount checks
summed edits, not a second independent S/D/I alignment decomposition.

## Evidence and next direction

Protocol, source/runtime/metadata bindings, declaration, safe weights, stage owner
receipts, private ordinal outputs, aggregate results and `POSTCHECK.json` are
retained under `work/xlsr-timit-train-comparison-20261025/`. Only aggregate results
are reported here. Existing source attribution is linked in the preceding JIBO
report and qualification. No reserved/held-out input, baseline refit/rerun,
threshold adjustment, recording upload, simulator or app modification occurred.

Retain this mixed result. The next useful saved-output diagnostic is whether the
two models make sufficiently complementary errors to justify a separately
specified reference-blind agreement/abstention mechanism. Shared exact successes,
failures, disagreement and a reference-informed per-utterance minimum edit count
can describe that headroom. The minimum is an unattainable oracle selection
bound, not a deployable model, score, improvement claim or learner decision.

## Exploratory saved-output complementarity

A separate, source/input-bound arithmetic audit now checks Stage C greedy versus
challenger greedy using only these saved32 outputs and references. It reconciles
all/task/cell edit denominators and paired outcomes with the independent postcheck;
there is no new inference, audio read, posterior decoding, fit or rule selection.

The models produce identical complete phone sequences on only2/32 utterances;
both agreed sequences differ from the manual reference. They differ on30. Stage C
alone has three exact-reference sequences, challenger alone zero, both exact zero,
and neither exact29. Two other utterances have different sequences but equal edit
counts. Agreement here is whole-sequence identity, not aligned-phone agreement,
clinical correctness or an independently validated confidence measure.

An oracle allowed to read each reference and choose the lower-error *complete
utterance output* achieves247 edits/596 phones (41.44%), versus283/281 individually.
That is36 fewer than C greedy or34 fewer than the challenger. It is an unattainable
reference-informed selection bound for these two saved utterance hypotheses,
**not achieved model performance**. It does not bound arbitrary phone-level fusion
or other models and cannot become a learner score or reference-blind selector.

| Task | Reference phones | C greedy edits | Challenger edits | Oracle minimum edits, not deployable |
| --- | ---: | ---: | ---: | ---: |
| Blocks | 158 | 79 | 72 | 67 |
| Brush | 140 | 58 | 58 | 49 |
| Colors | 145 | 95 | 96 | 86 |
| Letters/digits | 153 | 51 | 55 | 45 |

`COMPLEMENTARITY-SCOPE.md`, `complementarity.py` and `COMPLEMENTARITY.json` retain
all original strata and exact source/input bindings. Root observed exit0. These
results supply counterexamples to treating whole-sequence agreement as proof of
correctness and show limited whole-utterance selection headroom on this panel.
They do not qualify a fusion rule or establish an error rate for new children.
No model or learner behavior is promoted from this audit.
