# Exposed-pilot development measurement

The declared development profile resolved 31 of the same 48 already-exposed adult items. On those 31 complete references, the unchanged strict scorer found 191 edits over 853 reference tokens: a 22.39% token error rate. This is conditional development evidence, not held-out accuracy, child-speech validation or permission to offer sound-specific corrections.

The [original strict result](l2-strict-scoring-result-20261013.md) remains unchanged: 48 unscorable references, zero pairs and null rates. The 20-speaker reserve was not opened. No model, predictions, thresholds, cohort membership or token mapping changed.

## Declared reference profile

The [convention audit](l2-reference-convention-audit-20261013.md) identified an exactly empty trailing phone interval in every item. The new profile treats that interval as a structural boundary gap only when every positive-duration word-tier overlap has an empty label. It also treats standalone `sp` as an optional pause under the declared historical MFA convention. Neither rule establishes acoustic silence. The corpus's exact MFA version remains unestablished.

Other labels retain the original interpreter, including intended/perceived substitution, addition and deletion. Any unresolved interval excludes the whole reference; valid pieces are not stitched together. Coverage was persisted and checked before accessing hypothesis fields. Complete authenticated row bytes already contain hypotheses, so this is field-independent coverage rather than a claim that those bytes were never read.

## Actual results

| Measure | Observed |
| --- | ---: |
| Planned / completed predictions | 48 / 48 |
| Scorable complete references / paired items | 31 / 31 |
| Unscorable references | 17 |
| Reference tokens in paired items | 853 |
| Substitutions / deletions / insertions | 149 / 24 / 18 |
| Total edits | 191 |
| Micro strict mapped-token error rate | 0.223915592028136 |
| Speaker macro rate | 0.22843112496780776 |
| Defined / undefined speaker rates | 4 / 0 |
| Completed hypothesis tokens across all 48 | 1,363 |
| Unsupported hypothesis tokens across all 48 | 90 |

The 17 unresolved references have nonexclusive reason counts: 15 `deviationUnsupported`, two `malformedAnnotation` and one `unresolvedNonlexical`. These overlap; they are not a denominator to add together. Unsupported hypothesis totals include unpaired items and must not be described as 90 independently established pronunciation errors.

Coverage retained 48 structural boundary gaps, 83 optional-pause intervals, 58 existing silence intervals, 29 canonical-deletion intervals, 1,326 mapped-phone intervals and 38 unresolved intervals. The last group occurs in 17 items. No raw labels, hypotheses, speaker identifiers or confusion entries are published here.

## Execution and limits

The actual measurement ended with exit zero (`d19e13`, immediate completion without a session). Independent current-source/evidence/output and saved-projection checks ended with exit zero (`70e494`). The original monotonic start was 274704.436965333; collection completed within 7.761 seconds of the unchanged 180-second limit. No child process, waveform, archive, model, new prediction or numerical runtime was used.

The aggregate is 3,589 bytes, SHA-256 `6c5cfe2285284aa07ef6075af660ebd81e198178fd52f1657816bdff2c05fbc5`. The root qualification is 721 bytes, SHA-256 `67fe419d27de124eb136d6024c91490aaf1f2e0c6a20d1a770ee81d66533e9a2`. Original identities were checked during the worker; the independent collector authenticated current pinned bytes and retained its own identities. Private coverage, scoring and reference records stay local.

A selected subset of previously exposed adult recordings cannot establish representative performance, specific error detection, uncertainty calibration or clinical diagnosis. The next product step is to retain the verified word observations while developing independently supported sound feedback; this measurement does not enable learner phone judgments.
