# Full-DEV calibration control — preparation recipe

**PROPOSAL / NOT DECLARED / NOT FITTED.** This is preparation for the new blind comparison. It does not authorize a scientific stage, reuse an outer-fold control, change the preserved candidate or access TEST. Review with the [confirmation draft](r-confirmatory-preparation.md).

The control converts the unchanged retained `p0+p1` score to the PERCEPT-R binary listener-vote target. It is needed because the original retained distribution has different semantics; a proper-score comparison against that raw score alone would be inadequate. A monotonic calibration may leave ranking unchanged, and a boundary solution may collapse it. This is a research comparator, not clinical calibration.

Use exactly the closed full DEV cohort of 119 numeric children and 4,534 complete selected tokens, with no new exclusion, encoder run, feature fitting, candidate refit, hyperparameter search or TEST information. The immutable DEV selection, saved retained predictions and listener-count join require independent byte/roster/target verification in the new preparation declaration. Historical input digests are listed in the preserved [development protocol](../model/percept-r-binary-head-protocol-20261002.md); this document has not reopened those inputs.

The proposed fit follows that protocol's existing monotonic calibration family:

1. Validate every finite retained probability in `[0,1]`, exact selected child/token membership, integer `n>0`, and `0<=k<=n`. Derhotic target is `(n-k)/n`. Require both vote classes across the fitting set.
2. Clip retained probability to `[1e-6,1-1e-6]` for the logit input. Calculate its full-DEV row mean and population standard deviation in float64; replace standard deviation below `1e-6` with 1. Fit this transform only on DEV.
3. Give token `i` weight `n_i / sum(n_j for the same child) / 119`. Fit an unpenalized intercept and a nonnegative standardized-logit slope, with fixed slope ridge `0.001`; do not penalize the intercept.
4. Use the unchanged damped-Newton objective, Armijo/roundoff rules, 100-iteration/50-backtracking limits and `1e-8` gradient gate documented in the closed protocol. If the unconstrained slope is negative, use the exact boundary solution: slope zero, intercept the clipped weighted target-mean logit. Verify projected stationarity; retain both the unconstrained solution and boundary decision. Failure is terminal, with no silent retry or parameter change.
5. Save coefficients, transform, fixed target/probability order, optimizer diagnostics, complete fitting-membership digest and source/dependency/environment bindings under a fresh exclusive output directory. Independently recompute objective, stationarity and predictions from the saved control before declaring it fixed. Use isolated new stage code; do not run or edit closed study stages.

No full-DEV control bytes, fitted probability result, independent numerical audit or execution declaration exists for this proposal. Its eventual output must stay research-only with learner, clinical and production eligibility false. The eventual evaluation uses the separately declared proper-score clipping and cannot select a calibration family or threshold from TEST outcomes.
