# Consumer assessment engineering milestone — 2026-10-02

This batch connects the existing no-account native practice app to a real internal
research pipeline, and adds local practice participation history. It does not enable
pronunciation findings, diagnosis, treatment recommendations or a speech score.
The consumer roadmap and implementation goal remain active.

## Delivered behavior

The Debug simulator lab requires reading its explanation, choosing age 6–12 and a
proposed engineering word, and opting into local processing. The actual recorder
captures temporary mono16kHz PCM16 WAV. Scope/capture failures, service failures and
unverified research outcomes produce an unavailable explanation with recovery into
manual practice. Requests bind the chosen occurrence, model, prompt, audio and exact
request bytes. The client refuses redirects and bounds streamed responses. Cancellation,
background, interruption and stale completions cannot revive a discarded attempt.
Cleanup failure prevents further recording rather than claiming deletion.

The new loopback bridge uses unchanged pinned extractor/encoder/head files, offline
loading, strict WAV/JSON bounds, one worker, process-group timeout and private temporary
cleanup. Prompt matching stays unverified and all learner/clinical/production flags
remain false. The /r/ specialist stays separate. Physical phones cannot reach this
Mac through the fixed loopback endpoint; its app entry is absent there and in Release.

Completed ordinary practice saves only a random session ID, completion date, sound
group and word count. History is capped at 100, shows the latest three, and has explicit
clear/recovery. Atomic writes request complete iOS file protection; its own directory
is excluded from backup. A save failure does not block more practice. Counts describe
participation, not improvement; research assessment attempts are not persisted.

The [assessment materials](../consumer-assessment/README.md) include the real compiled
892-word/2,398-entry audit, explicit variant/repeated-target mappings, a 15-entry pending
review worksheet, annotation preparation and an undeclared blind-/r/ preparation draft.
No qualified labels, contact, protocol declaration or child evidence were created.

The continuation adds a memory-only Debug attempt ledger. Accounting starts before
microphone permission, includes explicit complete/opted-in unsupported preflight
rejections, and retains exactly one terminal outcome per started attempt. Fixed
reasons cover unusable capture, permission/lifecycle/processing/cleanup failures and
processed-but-unverified output. Request IDs are caller-owned and forwarded to the
bound HTTP request. Same-setup retries retain parent/index; changing setup, opting
out, reset and end break the chain. The latest 100 rows retain elapsed monotonic
durations; separate session-lifetime totals retain evicted attempts. No prompt, age,
identity, audio or probability is stored, and closing the lab discards the ledger.

The new isolated [confirmation evaluator](../../research/audio-head/r_confirmatory/README.md)
preserves complete terminal rosters, mixed listener votes, undefined-child coverage
and identical-token paired comparisons. Its conditional whole-child bootstrap is
explicitly limited to defined paired children. The [reviewed preparation snapshot](../../work/assessment-continuation-20261002/reviewed-preparation-snapshot.json)
binds its code/documents after synthetic verification and independent Astra review;
it is not a study declaration. A read-only receipt verified 68 source/dependency/model
bindings, including the actual candidate checkpoint. The full-DEV calibration recipe
is proposed only; no fitting, scientific evaluation or TEST access occurred.

## Verification and limits

Engineering receipts are in `work/assessment-milestone-20261002/`. The bridge's 16
focused tests passed. One permitted fitting fixture processed in 9.106 seconds with
exact feature/CTC/direct-loader parity and saved-batch predictions within existing
numerical tolerance. All 13 preserved scientific source/document hashes match.
The catalog's nine oracle groups and seven verification groups passed.

137 native unit checks passed, including the unskipped live iOS loopback check.
Five distinct UI checks passed across recorded runs: consent/default scope,
unsupported-sound recovery, full XXXL accessibility, ordinary home/prompt audit and
actual recorder/replay/completion/history/relaunch/clear. UI coverage reporting was
disabled after simulator launch/report-transfer stalls; all assertions ran. A full
final UI suite is not claimed. Strict formatting and unsigned generic physical-iPhone
Release build passed. Separate Astra code and verified Opus 5.5 final screenshot
reviews cleared the change. Detailed receipts are consolidated in the final checkpoint. The loopback transport input is
synthetic silence; model parity is one fitting fixture. Neither establishes child,
isolated-word or microphone generalization. Actual iOS data protection needs hardware
verification because simulator metadata is unavailable. Full cold/warm runtime/memory,
physical assessment capture and prospective product
qualification remain. TEST is sealed; closed studies and eligibility are unchanged.

Continuation verification: all 139 native unit tests passed in one final run,
including the unskipped real iOS loopback synthetic-WAV check. All 14 synthetic
evaluator tests and strict formatting of all six changed Swift files passed.
The final unsigned generic physical-iPhone Release build passed, and a separate
Astra read-only review cleared the final attempt-accounting source and tests.
The earlier UI checks remain the UI evidence; no new UI run or physical execution
is claimed for this accounting-only change. Detailed continuation receipts are in
`work/assessment-continuation-20261002/`. Calibration coefficients, exact new TEST
selection, acceptance/coverage criteria, qualified review and a new scientific
declaration remain absent.
