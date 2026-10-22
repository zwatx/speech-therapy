# /r/ confirmation — model-assisted research decisions

Decision date: 2026-10-03. The owner delegated technical research-design choices to the assistant and another model after the earlier handoff. This new record resolves the decision-policy layer; the earlier preparation documents remain preserved as historical proposals. It supersedes their requirement that a separate human statistical decision record must be supplied before these research choices can be selected. No human qualification, institutional signature, clinical/content approval or actual study execution is claimed.

GPT-6 Astra independently recommended the policy below from the published project documents. The primary assistant selected that recommendation and checked its consistency with the existing preparation tools. This is AI research-design/engineering review. [Machine-readable policy](r-confirmatory-decisions-20261003.json) records the exact settings. Research-only is true; learner, clinical and production eligibility remain false.

## Chosen decisions

| Question | Selected policy | Rationale |
| --- | --- | --- |
| What is primary? | Equally weighted mean within-child candidate-minus-retained vote-weighted AUROC on identical shared processed/rated tokens | The current question is improved ranking of corpus listener judgments; pooled ranking can mix child/study differences |
| What estimate is worth pursuing? | Mean gain at least **0.02 AUROC** | Explicit engineering target, partly for continuity with the prospectively defined DEV screen; not a validated clinical minimum |
| What uncertainty evidence is required? | Existing paired child-bootstrap 95% interval lower endpoint **strictly greater than zero** | Requires positive evidence in addition to the target-sized estimate; does not establish that the true gain exceeds 0.02 |
| How complete must the comparison be? | **80/80 child AUROCs defined**, at least **95% shared-token coverage overall**, at least **90% within every child** | Prevents a favorable subset of children from producing a decisive primary result; allows bounded token loss while preserving every denominator |
| What about probability estimates? | Candidate-versus-fixed-calibration log loss and Brier are **descriptive secondary outcomes** | Report useful probability evidence and reversals without creating another success route |
| Can we rescue a weak result with another metric? | **No** secondary, pooled, subgroup or thresholded endpoint can rescue the primary result | One predeclared primary verdict; no metric shopping |
| Who reviews the research decisions? | Primary assistant selects; independent Astra challenges; exact policy and reviewed bytes retained | Owner delegated these technical choices; AI review remains honestly labeled and does not impersonate an expert signoff |

The published development result reports a mean gain of 0.036090 and conditional 95% interval [0.021681, 0.051668], with all 119 DEV children defined. These facts motivate pursuing confirmation but are consumed development evidence, not an 80-child power calculation. The 0.02 target was fixed in the earlier development protocol before its candidate fitting; this record explicitly chooses it prospectively for the new comparison. It is not tuned from reserved outcomes, and the coverage thresholds are policy judgments rather than empirically proven feasibility. See the preserved [DEV protocol](../model/percept-r-binary-head-protocol-20261002.md) and [result](../model/percept-r-binary-head-result-20261002.md).

## Exact endpoints and coverage

Preserve all 80 reserved numeric IDs, including zero-selection and undefined children. The denominator is every token selected by the fixed per-child cap, **before** post-cap unmappable-phone exclusion or short-segment/processing/rating failure. All such selected rows remain in prediction and outcome terminal rosters. Ineligible pre-cap rows and eligible rows not chosen by the cap are reported separately; they are not invented processing failures. No replacement token is selected.

For child c, let S_c be its capped selected-token count and P_c the count with processed candidate and retained predictions and available valid listener votes. Overall coverage passes exactly when `100 * sum(P_c) >= 95 * sum(S_c)` with a positive denominator. Every child must have `S_c > 0` and `100 * P_c >= 90 * S_c`. These integer comparisons are inclusive and avoid percentage rounding. Calibration coverage is reported separately and does not change the primary intersection. Candidate-versus-retained AUROC must be defined for every child: both listener vote classes have positive mass in that child's primary shared-token set. Unknown IDs, duplicate/missing terminal rows and tampered bindings are integrity failures, not ordinary missingness.

Derhotic votes are positive (`n-k`), rhotic votes negative (`k`); retain mixed votes and self/tie half-credit. Ranking uses raw probabilities. Each of the 80 children contributes equally to the primary mean. Keep original per-child gains, including negative and tied gains, plus all failures and their reasons. Never replace an undefined AUROC with 0.5 or omit its child to obtain a decisive verdict.

Retain the implemented bootstrap: lexicographically sorted paired-defined children, fixed models, PCG64 seed 20261002, 2,000 whole-child resamples and linear 2.5%/97.5% quantiles. If fewer than 80 children are defined, its subset interval may still be reported descriptively but cannot yield primary pass/fail. Do not increase resamples, change the seed or repeat a run to move a borderline interval across a gate. Compare stored unrounded values; displayed rounding and numerical audit tolerance do not relax decision thresholds.

## Verdict order

Check integrity first, coverage second, then the numerical gates. The following table is evaluated in order; exact boundary equality follows the stated operators.

| Verdict | Rule |
| --- | --- |
| Invalid | Material source/anchor/membership mismatch, unauthorized outcome-informed changes, leakage or unresolved independent numerical-audit disagreement prevents interpretation |
| Inconclusive — coverage | Integrity holds, but any full-child or token-coverage requirement fails |
| Pass — ranking | Integrity and coverage hold; mean gain >=0.02 and lower 95% endpoint >0 |
| Fail — below target | Integrity and coverage hold; pass conditions do not hold and upper 95% endpoint <0.02 |
| Inconclusive — precision | Every remaining valid, adequately covered result |

A below-target failure can still contain a small positive gain. Inconclusive does not mean no effect, and pass does not mean the true gain is known to exceed 0.02. A failed/inconclusive/invalid once-only run does not authorize TEST-informed tuning, checkpoint substitution or a rescue attempt. A structural preflight that proves the gates infeasible stops before outcome execution and reports a readiness issue, not a scientific outcome.

Boundary examples, with integrity and all coverage gates satisfied: mean .02/lower .001 passes; mean .03/lower 0 does not pass; upper .019 fails; upper .02 remains inconclusive if pass conditions fail. Exactly 38/40 paired tokens meets the overall 95% gate when every child's counts are the same; 36/40 meets the per-child 90% floor but not that overall gate. Any undefined child makes the primary verdict inconclusive regardless of a favorable defined-subset mean.

## Probability outcomes, immutable recipes and claim limits

Keep all three declared arms. Fit exactly one full-DEV retained-score monotonic calibration control using the existing [recipe](r-calibration-preparation.md) in its separately prepared/authorized stage; no fold-control reuse, alternate optimizer, new ridge selection or candidate refit. An unsuccessful fixed calibration stage remains terminal for the declared stage. Its actual coefficients/audited receipt still need preparation; this record invents no fitted bytes and launches no fitting.

Report child-balanced log loss and expected per-vote Brier on candidate-versus-fixed-calibration shared tokens with the existing 1e-6 clipping, all coverage and conditional intervals. They are descriptive, not independent confirmatory success claims; no simultaneous interval coverage is asserted. If they worsen, the result must say so, even when ranking passes. Ranking success cannot be described as probability improvement. No thresholded endpoint, composite score, pooled gate or subgroup rescue is selected for this first comparison. Future product scores need a separate task and evidence.

Preserve candidate/baseline bytes, selection salt and 40-token cap, pre-cap eligibility, post-cap exclusions with no substitution, calibrated target semantics, and reviewed lock/join/evaluation/audit tools. Do not modify closed study sources/protocols/results/checkpoints or inspect reserved data to refine these rules.

The allowed positive claim is bounded: the preserved candidate met a fixed corpus-listener ranking criterion on the reserved numeric-ID cohort. Numeric IDs are not independently established biological/household identities; studies and words were not held out. Child bootstrap uncertainty is conditional and does not capture study-level dependence, refitting or population-wide uncertainty. No power, formal calibrated Type-I-error rate, clinical validity, acoustic-only mechanism, age-6/7-specific effect, other-sound/ER generalization, native-microphone transfer, therapy benefit or learner eligibility follows. The strict 80-child gate prevents missing-child selection but does not remove token-missingness bias or these independence limits.

## Method sources and their role

- [FDA, Multiple Endpoints in Clinical Trials, October 2022](https://www.fda.gov/regulatory-information/search-fda-guidance-documents/multiple-endpoints-clinical-trials): multiple endpoints increase the risk of misleading positive conclusions without an appropriate analysis strategy. We apply the general multiplicity principle by choosing one primary verdict and descriptive secondary reporting. This is a drug-trial guidance source, not a determination that this project meets a regulatory standard.
- [TRIPOD-Cluster explanation and elaboration, BMJ 2023](https://pmc.ncbi.nlm.nih.gov/articles/PMC9903176/): reporting should address missingness, heterogeneity and performance across clustered sources. Its authors describe it as reporting guidance, not a prescribed study-design algorithm. It does not validate our thresholds or child-independence assumptions.
- [Riley et al., External validation, BMJ 2024](https://pmc.ncbi.nlm.nih.gov/articles/PMC10788734/): predictive performance and clinical utility are distinct evaluation questions. Corpus ranking evidence alone cannot establish clinical benefit.

Source-access note: the FDA page was directly read. BMJ canonical pages returned 403 and PMC article opens presented a browser check; the stated limited methodological summaries were obtained from search-indexed extracts of the original papers. No inaccessible full text is represented as read. These sources support general rationale; **0.02/80/95%/90% are explicit project policy choices, not numbers prescribed by these sources**.

## Readiness after this decision record

The research-policy decision gap is resolved under the owner's new delegation. The scientific execution declaration is still unassembled: actual permitted DEV calibration input/coefficients/audit, verified reserved metadata/membership/denominators, complete runtime/dependency/source bindings and stage authority must be attached. AI-selected criteria do not manufacture those bytes or authorize sealed TEST access. The first milestone needs a frozen executable protocol, not execution of the reserved comparison now. Qualified content-review materials are already delivered; human SLP approval is a later content/product requirement. Physical checks remain deferred under simulator-only steering; no contacts, participant data, commit/push or deployment occur.
