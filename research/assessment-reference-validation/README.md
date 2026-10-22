# Public reference assessment validation

This separate runner declares the complete engineering matrix before invoking the frozen assessment bridge. It does not train, tune, reopen reserved study data or estimate intended-child accuracy. Public source word labels are not verified produced-phone labels. `ageYears: 9` is an engineering request parameter; the actual recorded speaker ages remain unknown.

The fixed matrix has 23 attempts: all 17 dictionary variants across 15 prompts, two deliberately mismatched source words, silence, a generated tone, clipping and malformed WAV. Both selected banana positions are exercised; the engineering display independently chooses the first one. Unsupported ZH remains in the denominator. No failed attempt is silently filtered or retried.

Use the existing audio runtime and explicit module paths, with absolute private paths:

```sh
export PYTHONPATH=research/assessment-reference-validation:research/assessment-reference-assets:research/content-review-preparation:research/assessment-workbench:research/audio-head
research/audio-head/.venv/bin/python -m reference_validation prepare ABSOLUTE_REGISTRY ABSOLUTE_NEW_PLAN
research/audio-head/.venv/bin/python -m reference_validation run ABSOLUTE_REGISTRY ABSOLUTE_PLAN PRINTED_PLAN_SHA256 ABSOLUTE_NEW_RUN_DIRECTORY
```

The asset validator requires all 13 fixed source licenses, permission declarations and source/original/converted-byte receipts before inference. The frozen source pack, bridge and runner bytes are bound into the plan. All inputs are checked before the first call. Every call durably writes a started receipt first, then the complete response and elapsed time. A malformed response or interruption leaves an incomplete run with started receipts, rather than a false completed denominator. A new run directory is required; there is no automatic retry or resumption.

Unit tests isolate the model boundary with an explicitly named test-only response. Those checks establish runner behavior only. Actual inference is reported separately in the private delivery report. Runtime responses preserve research-only, unverified prompt matching and false learner/clinical/production eligibility.

```sh
PYTHONPATH=research/assessment-reference-validation:research/assessment-reference-assets:research/content-review-preparation:research/assessment-workbench:research/audio-head python3 -W error -m unittest discover -s research/assessment-reference-validation/tests
```
