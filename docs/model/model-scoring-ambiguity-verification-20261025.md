# Model scoring ambiguity — October 25, 2026

Research diagnostics now expose every equally optimal edit correspondence, and
the constrained research/web scorer no longer chooses an error family by lexicon
order when top paths tie. Neither change establishes better acoustic accuracy or
enables native learner pronunciation judgments.

## Occurrence attribution

Historical `mdd_v1.evaluate.align` selects one minimum-edit path, preferring
diagonal, deletion, then insertion. Occurrence-level MDD counts and disagreement
features inherit that choice. For generated `['N', 'N']` → `['N']`, either N can
be deleted with the same cost. Stable replay does not resolve the location.

The additive standard-library module
[`alignment_ambiguity.py`](../../research/audio-head/mdd_v1/alignment_ambiguity.py)
uses forward/backward unit-cost edit distances to find every diagonal/deletion
edge on some optimal path. Each immutable reference-position result separates
possible hypothesis indices/deletion, distinct phone identities/deletion, and
agreement across all optimal paths (`match`, `mismatch`, `ambiguous`). Multiple
indices can share one identity; multiple identities can all mismatch.

These are marginal possibilities, not independently selectable steps of one
legal alignment. They do not measure acoustic confidence, phone timing,
insertion-location ambiguity or clinical correctness. Tokens are compared exactly
without normalization. Empty inputs work; invalid tokens and grids above 250,000
cells fail before distance-grid allocation. Existing alignment, GOP, Stage D
features, historical metrics, decoder outputs and model weights remain unchanged.
Changing a frozen feature would require a separate model revision.

## Complete saved TRAIN audit

Scope was written before analysis. All 192 utterances, 73 children, both saved
greedy/beam16 outputs and all eight cells of the existing
[broader TRAIN panel](ctc-prefix-broad-development-20261025.md) were retained.
References are normalized manual production transcripts, not intended-pronunciation
or clinical error labels. There was no model forward, decoding, posterior/raw
audio load, fit, tuning, held-out access or app/device operation.

| Decoder | Total edits | Index/deletion ambiguous | Identity/deletion ambiguous | Match/mismatch ambiguous |
| --- | ---: | ---: | ---: | ---: |
| Greedy | 1,673 | 1,092 | 1,078 | 133 |
| Beam16 | 1,655 | 1,051 | 1,033 | 121 |

Ambiguity columns count reference occurrences out of 3,375 per decoder. The final
column means equally optimal paths disagree about whether that occurrence matches
the decoded phone. It affects 56/192 greedy pairs and 55/192 beam pairs. The
historical selected path calls 48/133 greedy positions matches and 85 mismatches;
beam gives 44/121 matches and 77 mismatches. These are unresolved edit
correspondences, not newly identified clinical false passes or false rejects.

Greedy has 1,702 always-matching and 1,540 always-mismatching positions; beam has
1,731 and 1,523. “Always” means across minimum-edit paths only. Total error rates
remain 49.5704% and 49.0370%; this diagnostic does not improve them.

| Cell | Reference phones | Greedy identity ambiguous | Greedy match/mismatch ambiguous | Beam identity ambiguous | Beam match/mismatch ambiguous |
| --- | ---: | ---: | ---: | ---: | ---: |
| blocks/long | 775 | 232 | 38 | 201 | 28 |
| blocks/short | 123 | 61 | 4 | 56 | 4 |
| brush/long | 867 | 211 | 24 | 207 | 23 |
| brush/short | 211 | 57 | 3 | 63 | 5 |
| colors/long | 715 | 260 | 38 | 252 | 36 |
| colors/short | 183 | 97 | 4 | 97 | 4 |
| letters_digits/long | 424 | 140 | 19 | 138 | 19 |
| letters_digits/short | 77 | 20 | 3 | 19 | 2 |

No threshold, selector or learner rule follows. Per-pair details remain local in
`work/alignment-ambiguity-20261025/PAIR-DETAILS.json`; shared reporting is aggregate.

## Error-family tie repair

In [`ctc.ts`](../../packages/audio-scoring/src/ctc.ts), the first highest error
path previously won a tie. A generated two-frame example has expected `[b,l]`
mass 0.1, omission `[b]` mass 0.45 and substitution `[b,d]` mass 0.45. Reversing
the error paths changed `likelyError` from omission to substitution with identical
aggregate evidence.

The scorer now emits a family only if all exactly tied finite top error paths
share it. Conflicting ties omit `likelyError`; same-family ties and unique finite
winners retain it. Existing calibration, coverage, ambiguity and error-dominance
requirements and probability arithmetic are unchanged. There is no new tolerance
or threshold: near ties follow the strictly higher score. This fixes research/web
scoring, not a demonstrated native learner-feedback defect.

## Actual verification

- Root observed 33 passed/1 failed with the new conflicting-tie test before the
  fix, then all 34 package tests passed with no skips. Package type checking passed.
  Three new tests cover both conflicting orders, same-family ties and a strict near tie.
- A separate generated before/after reproduction observed the original family
  switch and both repaired omissions. Every other score field matched exactly
  for each order. Node emitted a module-type inference warning for this task-local
  reproduction; it did not fail.
- All 32 focused Python tests passed: ten new alignment tests, thirteen existing
  CTC tests and nine existing challenger-adapter tests. The independent new oracle
  enumerates **every legal edit path**, including nonoptimal paths, for 225 binary
  sequence pairs of lengths zero through three. Repeats, swaps, empty/invalid
  inputs, index versus identity ambiguity, immutable results and the resource
  limit are covered.
- The full audit and independent rolling-row distance/aggregate postcheck exited
  zero for all 384 pairs. Stored marginal interpretations and groups match; the
  postcheck does not independently reconstruct every actual-data marginal. The
  exhaustive generated oracle checks that algorithm separately. Historical selected
  correspondences are in the marginal sets; saved total/cell distances, reference
  counts, input hashes and unchanged historical source hashes match.
- Astra independently reviewed both implementations and tests without executing
  them; no blocking findings. Root owns execution and integration.

Evidence is in `work/alignment-ambiguity-20261025/`: `SCOPE.md`, `RESULT.json`,
`POSTCHECK.json`, `SCORER-REPRO.json`, preserved source copies and test logs.
The broader goal remains active: acoustic performance is still limited, and
intended-use sound references and independent clinical validation remain missing.
