# Native research-head normalization correction

October 23, 2026. `NativeFeatureHeadMath.mixture` now keeps the maximum shift
through log-softmax subtraction. Previously, adding the log normalization term
to a large common score could round that term away. Valid equal finite scores
then produced incorrect probabilities and a `logits` rejection.

The correction computes `(value - maximum) - logSum`. Model parameters, equal
head weighting, validation, callback behavior and the probability-sum tolerance
of `1e-12` are unchanged. This follows the stable shifted calculation used by
[SciPy's log-softmax implementation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.special.log_softmax.html).
SciPy is a reference only; no dependency was added.

Four permanent XCTest methods ran against the original source: the two offset
methods failed with `logits`, while the analytical unequal-mixture and invalid
input/cancellation methods passed. The same unchanged methods all passed after
the correction, covering 81 independent uniform-offset pairs and 16 exactly
representable unequal-offset pairs. The failed run is retained. A thrown error
ended each failing method early, so the original run did not cover every pair.

All 20 existing generated math controls also passed against the corrected
canonical helper, covering transforms, constants, mixture and cancellation.
The app-only unsigned Release simulator build passed. These checks used no
trained-head inference, recordings, participant data or reserved study inputs.

The helper has no current app call site. No learner-visible failure or actual
trained-score range was established. Historical model-output comparisons were
not rerun, and their original snapshots remain preserved. The separate q8
acoustic mismatch remains unresolved; no sound finding, diagnosis or eligibility
flag is enabled by this correction.

Actual source, red/green results, build bindings and independent reviews are in
`work/native-assessment-source-audit-20261023/`. The previously installed guided
practice build is preserved; this internal arithmetic change required no UI or
media action.
