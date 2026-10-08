# Broader phone-decoder development — October 25, 2026

The unchanged prefix beam16 decoder reduced **1,673 to 1,655 phone edits across
3,375 reference phones** in a separately declared 192-utterance JIBO **training**
panel. Micro-PER changed from **49.57% to 49.04%**, a 0.53-percentage-point reduction
(1.08% relative edit reduction). The effect is modest and uneven: 25 utterances
improved, 10 regressed and 157 tied. Longer letter/digit speech regressed slightly.
This result supports retaining beam decoding as a research option; it does not
support learner sound judgments, diagnosis or a model promotion.

## Fixed selection and unchanged computation

The prospective protocol selects 24 distinct children in each of eight cells:
blocks, brush, colors and letters/digits, each with short (0.025–4 seconds) and long
(>4–12 seconds) recordings. Within each cell, a declared hash order determines
selection. The earlier 32 utterance IDs are excluded. The resulting panel covers
73 children, with a maximum of six utterances per child; children can recur across
cells. These are not 192 independent children. This deliberately balanced panel
is not an estimate of the source corpus's natural task or length distribution.

Shared-manifest admission parses metadata from all splits to project only the
already acquired training partition. No held-out record is passed to the worker.
Selected pre-block20 cached tensors are bound to existing audio identity and
individual hashes; all shapes and finite values are admitted before the first
prediction. No raw recording or held-out tensor, label scoring or prediction is
used. The experiment uses the existing Stage C epoch8 weights, four final upper
blocks, norm/head, 39-phone mapping plus blank, eager attention, 64-frame padding
buckets and original trimming/masking. CPU float32, two threads, eval/inference.
No backbone construction, feature regeneration, download, fitting, calibration,
threshold change or reserved/closed-study access occurs.

Exactly one upper-model forward per input supplies identical full 40-class saved
log probabilities to greedy and the unchanged beam16. Existing greedy collapse
and the new greedy helper agree on every input. No expected word, lexicon,
language model, length reward, token pruning or selected-token renormalization
is added. Each ordinal posterior/prediction is saved incrementally; the combined
predictions are written before reference scoring. References use the existing
broad normalization of manual productions, which omits narrow distinctions.
Pruned beam mass is a lower bound, not calibrated confidence.

## Actual outcomes

| Decoder | Reference phones | Substitutions | Deletions | Insertions | Edits | Micro-PER |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Greedy | 3,375 | 856 | 769 | 48 | 1,673 | 49.57% |
| Beam16 | 3,375 | 859 | 741 | 55 | 1,655 | 49.04% |

Beam removes 28 deletions while adding three substitutions and seven insertions.
Fifty-five hypotheses changed; 25 improved, 10 regressed, and another 20 changed
without changing edit count. The other 137 hypotheses are identical. No regression
is excluded. The independently recounted edit totals use single-row Levenshtein;
individual S/D/I decompositions use the existing deterministic backtrace and are
not independently reconstructed by that recount.

Each cell contains 24 utterances. Win/loss/tie is from beam's perspective. Decode
time columns are totals across the cell, excluding the shared model forward.

| Task/duration | Utterances | Phones | Greedy edits | Beam edits | Greedy PER | Beam PER | Win/loss/tie | Greedy/beam seconds |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| blocks/short | 24 | 123 | 90 | 89 | 73.17% | 72.36% | 2/1/21 | 0.0144/0.4549 |
| blocks/long | 24 | 775 | 345 | 335 | 44.52% | 43.23% | 8/1/15 | 0.0800/2.9739 |
| brush/short | 24 | 211 | 110 | 108 | 52.13% | 51.18% | 2/0/22 | 0.0187/0.6121 |
| brush/long | 24 | 867 | 342 | 342 | 39.45% | 39.45% | 4/3/17 | 0.0851/3.2078 |
| colors/short | 24 | 183 | 142 | 142 | 77.60% | 77.60% | 1/1/22 | 0.0185/0.5943 |
| colors/long | 24 | 715 | 404 | 399 | 56.50% | 55.80% | 5/1/18 | 0.0719/2.5699 |
| letters_digits/short | 24 | 77 | 42 | 40 | 54.55% | 51.95% | 2/0/22 | 0.0140/0.4351 |
| letters_digits/long | 24 | 424 | 198 | 200 | 46.70% | 47.17% | 1/3/20 | 0.0671/2.3074 |

Task-level edits are blocks 435→424, brush 452→450, colors 546→541 and
letters/digits 240→240. The long letters/digits cell rises 198→200 edits; brush
long and colors short have unchanged total edits despite individual changes.
These mixed outcomes do not justify a universal improvement claim.

Total greedy decoding is 0.3697 seconds versus 13.1555 seconds for beam. Shared
cached upper-model forwards total 5.2836 seconds. Worker wall time is 23.7803
seconds, enclosing monitored stage 24.7370 seconds; maximum sampled process-group
RSS is 1,047,264 KiB. The stage ends normally with no signals, remaining group
members or cleanup errors. These are local cached-feature engineering timings,
not raw-audio/full-encoder, mobile or end-to-end app latency measurements.

## Evidence, interpretation and next action

The task-local prospective protocol, declaration, source/runtime/tensor pins,
ordinal outputs, aggregate results, owner receipts and `POSTCHECK.json` remain in
`work/ctc-prefix-broad-development-20261025/`. Root personally observed outer
session4980 exit0 before postchecking. The postcheck reconstructs total and each
cell's edit counts, denominators and win/loss/tie counts, verifies incremental
prediction equality and unchanged source/tensor pins, without model reexecution.
The preceding [32-input result](ctc-prefix-development-20261025.md) remains separate;
its outputs are not pooled here. The canonical decoder remains unchanged.

These inputs belong to the same population used to fit the model. Neither the
smaller PER than the previous panel nor the beam gain establishes generalization:
selection and reference denominators differ. JIBO's corpus-level ages4–7 and broad
productions do not establish intended6–12 SSD performance or clinical error truth.
The existing source attribution and CC BY4.0 records linked in the preceding
report apply. Identities, transcriptions, cached features and participant-level
outputs remain local and ignored; this report contains aggregates only.

This beam16 comparison removes only a small part of the observed edit burden;
it does not establish how much is due to search versus model probabilities or
reference structure. Do not tune widths,
thresholds, mappings or weights using this panel or repeatedly enlarge it to seek
a better gain. The next useful bounded work is an explicitly exploratory audit of
saved TRAIN posteriors: compute full CTC likelihoods for reference, greedy and
beam sequences, with deletion/blank behavior as descriptive context. This can
expose higher-probability missed sequences or reference under-ranking, without
proving label defects or an exclusively acoustic cause. No new acoustic inference
or app decision change is involved.
Any resulting training proposal must preserve the no-refit/no-reserved-data
constraints. The prepared app and primary simulator remain untouched.

## Exploratory exact-likelihood audit of the saved TRAIN outputs

After the fixed comparison, an additive, research-only
`sequence_log_probability` helper now computes the full CTC alignment sum for an
exact token sequence. It does not use a beam, expected word, language model or
length reward. All **13 canonical standard-library tests pass** under
Python3.13.14 with warnings treated as errors. Independent tiny-path enumeration
checks vocabulary sizes2/3, lengths0–4, every blank position and every target
through frame length, plus empty/impossible/repeated targets, validation and
retained-beam lower bounds. The original decoder and greedy implementations are
unchanged. Exact before-helper sources are preserved with hashes matching both
completed comparison declarations; those historical postchecks are not rerun
against the intentionally extended module.

The separate exploratory audit consumes only the 192 saved TRAIN posteriors and
predictions. It recomputes all three whole-sequence likelihoods (manual reference,
greedy, beam), checks normalization/greedy parity and retained beam mass as a lower
bound, and uses a fixed1e-6 natural-log comparison tolerance for numerical ties.
This tolerance does not alter any prediction or learner decision. The audit is
not a preregistered endpoint or independent model evaluation.

All 192 references are CTC-feasible. Fourteen match each decoder's complete output
exactly. The remaining **178 references rank below both decoded sequences**;
none ranks above either. Beam has higher exact likelihood than greedy in54 cases,
ties in137 and lower likelihood in one. That last case, in long letters/digits,
is one concrete witness of a beam16 search miss, not a global-optimum certificate.
Perfect maximum-likelihood search would still not choose those178 references over
these already known higher-probability sequences under the frozen posteriors.
This does not establish erroneous references, an exclusively acoustic cause, or
that another decoding objective cannot improve edit error.

| Task/duration | Reference below beam | Beam matches reference | Greedy above beam | Beam above greedy | Greedy/beam likelihood ties |
| --- | ---: | ---: | ---: | ---: | ---: |
| blocks/short | 22 | 2 | 0 | 3 | 21 |
| blocks/long | 24 | 0 | 0 | 10 | 14 |
| brush/short | 20 | 4 | 0 | 6 | 18 |
| brush/long | 24 | 0 | 0 | 10 | 14 |
| colors/short | 24 | 0 | 0 | 3 | 21 |
| colors/long | 24 | 0 | 0 | 11 | 13 |
| letters_digits/short | 17 | 7 | 0 | 4 | 20 |
| letters_digits/long | 23 | 1 | 1 | 7 | 16 |

Descriptive context: greedy emits2,654 phones and beam2,689 against3,375 reference
phones. Greedy has three empty outputs and beam two, all among short recordings.
Blank is the frame argmax in92.19% of36,656 frames; mean blank posterior is90.72%.
CTC normally uses blank between phone emissions, so these values alone do not
establish blank bias or erroneous deletions. Aggregate aligned per-reference-phone
counts are retained locally, under the same deterministic edit-tie convention;
they are not calibrated sound correctness or diagnoses.

Root observed saved-audit outer94505 exit0 (2.6060seconds monitored stage,
35,760KiB sampled RSS) before inspecting outputs. The audit makes no model call,
reads no audio and performs no fitting/tuning. Source and input hashes remain
unchanged within that audit; all outputs/owner receipts are retained under
`saved-audit-v1` and `saved-audit-owner-v1`. Astra independently reviewed the exact
scorer, tests, audit protocol, runner and actual aggregate outcomes with no
blocking issue.

Next: qualify one independently trained phoneme-CTC challenger from authoritative
lineage, vocabulary, preprocessing/runtime and rights evidence, then add a
research-only adapter with model-free mapping/shape tests. A model-card license
tag alone does not establish rights to its training corpus or commercial
redistribution. Any later TRAIN-only comparison needs its own fixed declaration.
No current model, thresholds, references or app policy are replaced here.
