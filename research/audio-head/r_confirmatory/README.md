# Confirmation evaluation preparation

This new module evaluates explicitly supplied terminal predictions and listener
votes. It loads no model, performs no inference or fitting, and discovers no corpus
files. It is preparation for a new study; it is not a study declaration, outcome
rating join, independent numerical audit or prediction lock. No reserved data was
used in its verification. See the [preparation draft](../../../docs/consumer-assessment/r-confirmatory-preparation.md).

From the repository root:

```sh
PYTHONPATH=research/audio-head research/audio-head/.venv/bin/python \
  -m unittest r_confirmatory.test_evaluate -v
PYTHONPATH=research/audio-head research/audio-head/.venv/bin/python \
  -m r_confirmatory.evaluate /absolute/synthetic-terminal-roster.json \
  --output /absolute/fresh-synthetic-evaluation.json
```

The public `evaluate(payload)` boundary requires exactly `children`,
`selectedTokens`, `arms` and `ratings`. Child and token IDs are nonblank strings.
Children contain `childId` and optional finite JSON `descriptors`; absent age or
study may remain null. Each selected row is a unique `{childId, tokenId}` pair.
The three arms are exactly `candidate`, `retained` and `calibration`, each with one
terminal row for every pair: `processed` with finite `[0,1]` `probability`, or
`unavailable`/`failed` with a nonblank `reason`. Ratings also require a complete
terminal roster: `available` with separate integer `positiveVotes` (derhotic) and
`negativeVotes` (rhotic), nonnegative with positive total; or `unavailable` with
`reason`. Unknown/duplicate/missing rows and invalid numbers fail closed.

The report retains every terminal row, own-arm coverage and empty/undefined
children. Vote-weighted AUROC preserves mixed votes and half-credit self/tied
pairs. Log loss and expected per-vote Brier clip probabilities at `1e-6` and weight
votes within child. The paired comparisons use the exact shared processed/rated
token intersection. AUROC gains are candidate-minus-retained; proper-score gains
are calibration-minus-candidate, so positive means improvement.

The child bootstrap is conditional on the explicitly defined paired subset,
sorted lexicographically: PCG64/seed 20261002, 2,000 whole-child draws and linear
95% quantiles. The full roster and excluded children remain separate. Empty
subsets produce null intervals without rescue; singleton intervals are marked
degenerate. This does not estimate performance for missing children or refitted
models. These are preparation settings, not declared acceptance criteria.

Output is schema version 1, research-only, with all learner/clinical/production
eligibility false and no pass/fail decision. CLI duplicate JSON keys are rejected;
input and existing exports are never overwritten. It makes no authenticity or
study-lineage claim about supplied data. Any scientific execution requires the
separate declaration, frozen artifact/selection bindings and execution authority
described in the preparation draft. Test fixtures are made-up engineering data.
