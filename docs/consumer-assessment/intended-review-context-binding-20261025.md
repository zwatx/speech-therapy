# Intended-review target context binding — October 25, 2026

New intended-recording preparations use schema2 and bind each original review to
the selected sound occurrence. This fixes an actual generated counterexample in
v1: a valid banana attempt could change its selected N from index2 to index4 while
both unchanged recording-bound original reviews remained accepted. The references
are whole observation vectors, so selected target context must remain attached
even though phone-decision evaluation is currently excluded.

## Implemented behavior

`make_protocol_v2` declares the review-context binding policy. The pure
`review_context_digest(protocol, attempt)` binds protocol SHA, attempt ID,
recording SHA, prompt ID, word, variant ID and occurrence index. Each v2 original
requires that digest as `reviewContextSha256`, included in its `originalSha256`.
Report validation compares it after validating the attempt's prompt/variant/index
and before accepting observations. Missing or stale context fails; it is never
filled from a currently edited attempt. Existing adjudications pin the original
hashes, so changing context and rehashing originals invalidates an earlier decision.

New private CLI preparation creates v2 protocol, bundle and report files. Strict
version dispatch rejects mismatched/unsupported versions and booleans. The legacy
`make_protocol` constructor and v1 reporting path remain replay-compatible.
Historical protocols, reviews and reports are not rewritten. V1 still lacks this
selected-target guarantee and is for historical replay; new programmatic studies
must use `make_protocol_v2`. No automatic migration creates missing review evidence.

The change shares the existing report implementation and private-file helpers;
it introduces no new service, account system, judgment fields, clinical rule or
quality/adjudication redesign. The older fixture service was also inspected:
its blinded allowlists, append-only originals, sealing, conservative non-target
admission and replay exports supplied no justified production change.

## Actual verification

- Root first reproduced v1 acceptance with generated records: changing only the
  selected occurrence2→4 left original hashes unchanged and `positiveConfirmed`
  true. No people, recordings or model calls were involved.
- All **34 intended-validation tests pass** under trusted Python3.13.14 with
  warnings treated as errors:26 preexisting tests plus8 new v2 tests. Root observed
  the actual command exit0; its stdout is retained in the task-local test log.
- Every preexisting test file is byte-identical to its before snapshot. The full
  generated legacy protocol, bundle and report semantic digests match the values
  captured before implementation, rather than merely checking a few counters.
- New tests cover valid v2 records, the valid banana occurrence swap, missing/
  stale/unhashed context, stale adjudication after original rehashing, context
  field inclusions/exclusions, strict versions and actual private/exclusive CLI
  preparation of v2 files.
- A separate direct generated v2 check rejects the swap with
  `review_context_binding_mismatch` while preserving original review records.
- Native Astra independently reviewed the design and final four-module change
  plus new tests with no blocking findings. Root reviewed the final diff and
  whitespace checks passed.

The retained evidence is in `work/reviewer-context-binding-20261025/`: exact before
sources/tests, `BEFORE.json`, `REPRO-v1.json`, `LEGACY-BASELINE.json`,
`UNIT-TESTS.log` and `VERIFICATION.json`. No historical study was rerun or refitted,
and no app/device, recording upload, outreach or publication occurred.

## Limits

This establishes context correspondence. Hashes do not independently establish
reviewer identity, blinding, chronology, consent, permissions or clinical truth.
The generated records are engineering examples, never synthetic human gold.
Phone-decision evaluation remains `not_evaluable`; learner, clinical, production,
qualified-review and meaningful-improvement flags remain false. Professional
review and intended-recording observations remain factual external dependencies.
