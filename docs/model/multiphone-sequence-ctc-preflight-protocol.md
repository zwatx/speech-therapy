# Single-slot sequence likelihood preflight

Declared September 27, 2026 before calculating new real-recording sequence
features. This checks numerical correctness and feasibility, not model quality.
The [research notes](multiphone-sequence-ctc-notes.md) state its basis and limits.

## Inputs and fixed selection

Use only the existing author-training full-vocabulary CTC cache. Preserve all
392 output probabilities, blank ID 0, and original canonical mappings. Alternative
slots take every token ID 4–391, including the original token, or delete the
slot. IDs 1–3 remain excluded special tokens; their probability mass is not
renormalized. No insertion, confusion-map restriction, learned prior or
post-hoc token subset is introduced.

Derive fold-0 child fitting rows from the pinned cohort/splits and verify they
match the original child-only warm configuration. Sort their unique recordings
by `(sampleCount, id)` and select shortest, middle (`n//2`) and longest. This
fixed geometry rule selects:

| Recording | Frames | Canonical tokens | Eligible fitting target rows |
| --- | ---: | ---: | --- |
| 000050175 | 79 | 6 | 199–202 |
| 000540123 | 159 | 20 | 819–824 |
| 000560117 | 535 | 25 | 917–924 |

Process every eligible target slot in those recordings: 18 positions total.
Ratings do not enter selection, computation, comparisons or outputs. No
validation/outer/test feature calculation, label correlation or performance
evaluation is permitted by this preflight.

## Verification and bounds

Before real feature calculation, pin this protocol, new source/tests, relevant
original sources, Python executable/runtime, upstream cohort/splits, manifest,
cache configuration/index, provisional mapping recipe, vocabulary and original
warm config. Hash the three selected posterior files and source WAVs; verify
their audio/frame/sequence/row bindings. No new audio inference occurs.

First pass computes each recording's canonical forward/backward tables and all
18 slot likelihood sets using float64 log arithmetic. An independent PyTorch
`ctc_loss` call enumerates every single-token replacement and deletion over the
same full-utterance log probabilities, in batches of at most 32 hypotheses,
without exponentiating, renormalizing or masking invalid paths to zero.
Compare all 7,002 slot hypotheses and the three canonical likelihoods with
absolute tolerance 1e-8; matching negative infinities remain explicit.

Repeat the optimized calculation exactly once and require byte-equivalent
numerical results. Record both observed durations and the reference duration;
these are one-machine observations, not a general speed guarantee. Exhaustive
toy-path enumeration tests additionally cover repeated neighbors, first/last
slots, deleting the sole token, impossible paths, exact zero probabilities and
excluded vocabulary mass. Reject zero-frame inputs and undefined normalized
scores. Preserve failures and partial artifacts rather than silently retrying
with changed mathematics or omitting failing slots.

Budget: these three recordings only, two optimized passes, one independent
reference pass per fixed hypothesis, CPU two threads, no Colab. No fitting or
new feature pass over the rest of the corpus. If verification succeeds, retain
raw likelihoods, derived restricted-set log ratios, all input/source hashes,
maximum deviations and timings. Recheck pinned bytes before completion.

## Decision boundary

A pass permits proposing a separate, predeclared feature/model comparison.
It does not establish a useful quality signal, produced-phone identification,
timing accuracy or clinical validity. A failure blocks that comparison until
the discrepancy is understood. Historical sources and research bundles remain
unchanged. Learner pronunciation judgments stay disabled.
