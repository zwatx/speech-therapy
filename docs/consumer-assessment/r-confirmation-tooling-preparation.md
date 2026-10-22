# New /r/ confirmation tooling — preparation only

This addendum describes isolated tools for the proposed new comparison. It does not revise the closed studies or the existing hash-bound seven-file review snapshot. The tools accept explicitly supplied data; they do not discover corpus files or authorize data use. Verification uses synthetic inputs only. The [confirmation draft](r-confirmatory-preparation.md) and [calibration recipe](r-calibration-preparation.md) remain **not declared**.

## Metadata-only selection

`research/audio-head/r_confirmatory/select.py` provides `prepare_selection(payload)` with exactly:

```json
{
  "children": [{"childId": "1"}],
  "tokens": [{
    "childId": "1", "tokenId": "Synthetic_1/PRE/token",
    "folder": "Synthetic_1", "session": "PRE", "recordId": "token",
    "ageYears": 6, "phones": ["R", "AE1", "T"],
    "startSeconds": 0, "endSeconds": 1
  }]
}
```

The example is synthetic. A caller must separately establish that the child roster and structural metadata are complete. Child IDs are canonical positive numeric strings, ordered lexically. The folder suffix must match the child and the token ID must equal `folder/session/recordId`. Unknown fields, including ratings/predictions, duplicate identities, malformed segments and out-of-range ages fail closed. Supplying metadata does not establish biological identity or household independence.

Eligibility requires exactly one consonantal `R` and no phone starting `ER`. Select at most 40 eligible rows per child, ordered by SHA-256 of `percept-r-external-v1|folder|session|recordId`, then token ID for a tie. This is the proposed reuse of the original Part-1 cap/order. The implementation read the historical source recipe but never imports or executes closed stage code.

Unsupported phones remain in the capped selection and are counted for the pre-audio exclusion rule. Durations rounded to six decimals below 0.1 seconds remain selected and are marked for downstream reader failure. Neither rule substitutes another token. A row can have both markers; their counts are not disjoint and must not be added as unique failures. Every supplied child, including a child with no eligible/selected tokens, appears in the result. Every input token has a disposition, including ineligible and eligible-but-not-selected rows.

The report binds canonical input, selected membership, source and the copied mapping recipe; it records full supplied/eligible/selected denominators. These are *supplied-metadata* denominators, not a verified reserved-corpus roster. No reserved metadata was opened, and no expected real TEST token count is claimed. Final source/mapping applicability, complete eligible-row extraction and actual reserved roster require review and binding in the new declaration.

Run the synthetic checks from the repository root:

```sh
PYTHONPATH=research/audio-head research/audio-head/.venv/bin/python \
  -m unittest r_confirmatory.test_select -v
```

There is no automatic metadata reader, rating join, audio decoder, model runner or real-cohort stage command in this selection helper. All learner, clinical and production eligibility flags remain false.

## Calibration and independent scalar replay

`r_confirmatory.calibrate.fit_calibration(payload)` accepts exactly `children`, `selectedTokens` and `rows`. Children contain only `childId`; selected rows contain `childId`/`tokenId`; fitting rows additionally contain `retainedProbability`, `positiveVotes` and `negativeVotes`. The retained probability is caller-supplied `p0+p1`, positive votes are derhotic (`n-k`), and negative votes rhotic (`k`). IDs are nonblank strings, matching the evaluation API; duplicate/unknown/missing rows, empty fitting children, invalid probabilities or votes, and absence of either vote class fail closed. Canonical ordering is lexical by child and token.

The fit uses the proposed recipe exactly: probability clipping at 1e-6, unweighted float64 row logit population moments, standard deviation below 1e-6 replaced by scale 1, listener weighting within equally weighted children, slope ridge 0.001 and unpenalized intercept. Damped Newton uses analytic derivatives and SciPy Cholesky, fixed Armijo/roundoff rules and budgets, with the 1e-8 stationarity gate. A negative unconstrained slope selects the zero-slope, clipped weighted-prior boundary, subject to projected stationarity. Failures raise a terminal `CalibrationFitError` carrying diagnostics; there is no altered-parameter retry.

The result retains canonical fitting rows, membership/input/source digests, coefficients, transform, weighting, initialization, unconstrained solution/step diagnostics, boundary decision, projected diagnostics and fitted predictions. Python/NumPy/SciPy versions describe the fitting environment. These private supplied-input artifacts can include vote data and must not be placed in a learner interface or published as clinical evidence. `predict_calibration(control, probabilities)` applies the saved transform to supplied probabilities without refitting. Neither API discovers data, runs an encoder or exports files automatically.

`r_confirmatory.calibration_audit.audit_calibration(payload, control)` independently uses scalar `math`/`fsum`, with no fitter, NumPy or SciPy optimizer imports. It verifies exact supplied roster/input/source/recipe bindings, equal-child weighting, logit moments, initialization, unconstrained and projected stationarity, boundary decision, objectives and probability replay. Absolute/relative numerical tolerance is 1e-10; stationarity retains the 1e-8 gate with that audit numerical allowance. Step structure and budgets are checked, but the audit does not re-execute or prove the historical optimizer trajectory, actual fit execution, original ratings or corpus membership. Dependency strings are receipt metadata, not independently reconstructed fitting environment evidence.

**Recipe edge case:** the clipped weighted-prior boundary is not the exact unconstrained intercept optimum for arbitrarily extreme vote imbalance. Synthetic retained probabilities `[0.1, 0.9]` and positive/negative vote pairs `[(1, 10^12), (0, 10^12)]` produce a negative unconstrained slope, but the clipped boundary fails the projected intercept-gradient gate. The implementation rejects it terminally. This contradiction must be resolved in a new declaration if such input support is required; the preparation does not silently change the closed recipe or imply it always converges.

Synthetic verification includes known constant priors, monotonic/nonconstant solutions, the zero-slope boundary, clipping, unequal child vote counts, canonical ordering, malformed inputs, terminal numeric failure and receipt tampering. Run the supplied-input checks:

```sh
PYTHONPATH=research/audio-head research/audio-head/.venv/bin/python \
  -m unittest r_confirmatory.test_calibrate r_confirmatory.test_calibration_audit -v
```

No full-DEV control has been fitted and no real calibration coefficients are fixed. A later authorized stage must reserve a fresh private output directory, preserve success or terminal failure, bind exact real fitting membership and environment, save outputs and perform independent replay before declaring the control fixed. Synthetic fits/audits demonstrate the implementation only.

## Required decisions before any scientific execution

The following remain explicit decisions rather than implicit defaults: minimal worthwhile ranking effect and confidence rule; minimum paired-defined child coverage; treatment of missing/undefined coverage; whether thresholded endpoints exist; proper-score success criterion; multiplicity and the role of secondary/descriptive analyses; youngest-age/context support; reviewer qualifications and independent audit responsibilities. The existing draft's numerical bootstrap settings describe implemented preparation, not approved acceptance criteria.

A new dated declaration must bind the preserved candidate/baseline, fixed calibration coefficients and audited fit receipt, exact reserved roster and structural selection, extraction/runtime contracts, complete failure denominators, metric/settings and prediction-lock/outcome-join stages. A prepared tool or automated code review does not supply qualified statistical or clinical signoff. Real fitting and reserved-data execution remain unperformed and outside this preparation.


## Observed preparation checkpoint — October 3, 2026

All 38 focused synthetic checks passed with warnings treated as errors: 14 existing evaluator, 12 calibration, seven scalar-audit and five selection tests. Genuine red/green records retain missing-function, changed-receipt and unrepresentable-number failures; overflow handling now produces validation failures without altering numeric settings. No actual full-DEV fitting or reserved metadata execution occurred.

Astra independently reviewed the exact six final source/test files and the recipe/tooling documents. It passed 18 immutable calibration/audit tests, 24 final calibration/audit/selection tests and 60 additional deterministic synthetic fit→audit cases. It did not independently rerun the 14 existing evaluator tests. Final review is CLEAR; source hashes and actual scope are in [the review receipt](../../work/assessment-calibration-20261002/final-review.json).

The parent saved one explicit synthetic fit and independently replayed the serialized control, plus one synthetic selection that preserves a zero-token child. Its fresh private output directory and exclusive files retain the examples locally. This is a real synthetic saved-artifact check, not real cohort calibration or a declared study. The [tooling snapshot](../../work/assessment-calibration-20261002/reviewed-tooling-snapshot-20261003.json) hash-binds final source, synthetic artifacts and checks. It is a frozen **preparation** snapshot; the earlier seven-file snapshot and all 13 preserved scientific bindings remain unchanged.
