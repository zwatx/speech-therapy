# Manual retry of a timed-out word check

An eligible word-only practice check can now be retried on the latest retained
recording after a timeout. **Try word check again** names the action; with two
takes it says **Try word check again on latest try**. Retry starts only after a
tap, uses a new operation identity, and retains the exact take, file, word and
practice visit. It does not record again or add participation history.

The action requires the existing complete request identity and confirmed worker
cleanup. An unconfirmed or mismatched receipt remains blocked. Existing duplicate,
departure, cancellation, playback and stale-result guards still apply. A settled
whole-word match, no-match or uncertain result is not a technical retry. Frozen
first-review and recheck submissions remain unchanged; selected practice can retry
without rewriting them. Completing practice still credits its exact visit once.

`LocalWordRecognizing.allowsTimedOutRetry` defaults to true for word-only providers.
The research composition overrides it to false regardless of opt-in or pause
state. Consequently native Debug guided research composition remains excluded even
when opted out; ordinary Release word-only practice and the generated word-only
guided host support the new action. This is a deliberate processing boundary.

## Observed verification

The bounded increment is retained in `work/timeout-retry-20261024`:

- 43 focused unit methods passed, including same-file/new-operation identity,
  one/two takes, exact cleanup, duplicate refusal, interrupted retry, late-result
  suppression, frozen assessment submissions and research-provider exclusion.
- Six generated Debug UI journeys passed: one take, latest of two takes, and
  selected practice through fresh recheck, each at normal and largest text sizes.
- An independent reviewer viewed all 26 distinct screenshots and checked all 24
  geometry records. All six retry controls were fully visible and at least 44
  points in both dimensions. All 18 targeted timeout, pending and matched
  paragraphs fitted wholly within their captured viewport.
- Unit and UI runs had zero failures, skips, expected failures, runtime warnings
  or test-runner restarts. Root personally observed the original test, export and
  verification processes finish. Complete generated input pins matched afterward.

The largest fresh-recheck image shows only the upper frozen context. Assertions,
not complete image coverage of that context, establish preserved first results
and a fresh empty recheck. Other content naturally scrolls outside these captures;
the target measurements do not establish every control's geometry.

Ordinary Release compilation passed in a fresh build directory. Root observed
outer process 54310 exit 0; the compiler worker closed normally in 50.164 seconds
with no signals, remaining worker processes or cleanup errors. All 25 previous
build inventories were unchanged. The resulting build contains 862 files.
`CANDIDATE.json` identifies the exact app; `POSTCHECK.json` and `DELIVERY.json`
record final preservation when present. The Release app was not launched or
installed in this increment. Earlier candidates and all previous results remain
preserved.

## Limits

Generated sources and controlled recognition receipts exercise behavior without
real microphone, camera, playback, network or model processing. They establish no
real timeout rate, recognition latency, individual-sound correctness or diagnosis.
Research-model execution, physical-device work, installed-byte comparison,
VoiceOver, historical contrast findings and whole-app release qualification are
outside this increment. The broader product goal and external review remain open.
