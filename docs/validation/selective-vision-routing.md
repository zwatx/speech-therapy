# Selective vision routing and fused evaluation

Status: executable research infrastructure only. It does not authorize a model,
clinical claim, learner-facing cue, or production release.

## What the harness proves

`@speech-therapy/visual-evaluation` evaluates the selective-compute design on an
exact prospective-test split. Each run recomputes the routing decision from the
versioned audio threshold policy. The run is rejected when:

- a confident-correct or uncertain attempt invokes vision;
- an eligible, consented, high-quality mismatch does not invoke vision exactly
  once;
- a bypassed attempt contains visual latency, cost, output, or a changed fused
  decision;
- an indeterminate or unobservable visual label produces a fused decision;
- any sample, visual annotation, or blinded clinical decision is missing,
  duplicated, outside the prospective split, stale relative to current consent
  or deletion state, or not bound to its declared SHA-256 evidence;
- the independently exported run index does not bind the canonical contents of
  every attempt, route output, explicit cue action, invocation count, latency,
  cost, and subgroup record under the same item ID;
- the evaluation policy, model artifacts, fusion policy, routing thresholds, or
  evaluation-only protocol registry do not match the predeclared policy hash.

The shipped protocol registry remains unchanged: bilabial closure is still a
`candidate`. A separate hash-bound registry may mark it `validated` only inside
the evaluator, and every report records `routingSimulation: true`,
`releasePosture: research-only`, `learnerFeedbackEligible: false`, and
`productionGateEligible: false`.

## Independent reference evidence

Visual observation labels answer only whether bilabial closure was externally
observable. They are not pronunciation-correctness labels. Correctness and the
need for analysis come from a separate
`prospective-clinical-decision-index-v1`, which requires qualified-reviewer
evidence, blinded model outputs, independent adjudication, the current dataset
authorization time, exact prospective coverage, and a canonical content hash.

The evaluation reports audio-only and fused coverage, accuracy, false-pass,
false-reject, error-recall, and abstention metrics. Corrective cue safety uses
an explicit `fusedCue` action; it never treats a generic error/review decision
as proof that a cue was emitted. It also reports invocation
avoidance, visual accuracy, false cues, latency, cost, subgroup cells, harmful
regressions, paired discordance, net improvement, and an exact two-sided
McNemar p-value. All advancement thresholds are supplied in the hash-bound
policy; there are no runtime defaults that can silently relax a study. Policy
lock and approval-evidence hashes are necessary bookkeeping controls, but real
pre-registration still requires an authenticated external registry.

## Running a governed evaluation

From the repository root:

```bash
pnpm --filter @speech-therapy/visual-evaluation routing:evaluate -- \
  manifest.json lock-deletion.json lock-consent.json \
  current-deletion.json current-consent.json 2026-07-10T18:20:00.000Z \
  annotations.json clinical-decisions.json evaluation-run-index.json \
  evaluation-policy.json samples.json \
  2026-07-10T18:30:00.000Z
```

The two timestamps must be canonical UTC instants. Current consent and deletion
snapshots must share the authorization timestamp. `annotations.json` and
`samples.json` are arrays. The command writes one aggregate, privacy-safe JSON
report and exits nonzero on an invalid evidence boundary.

The run index must be sealed after current authorization and before evaluation.
Its independently exported flag and capture-system evidence hash are validated,
but the harness cannot authenticate the exporter by itself. Real studies must
use signed platform exports and verify the signer in the governed research-job
boundary.

## What remains before Gate 2 can close

The checked-in test corpus is synthetic and establishes only implementation
behavior. Gate 2 still requires an approved protocol and statistical analysis
plan, signed/authenticated platform exports, a locked real prospective cohort,
qualified SLP labeling and adjudication, sufficient subgroup cells, physical
device results, a passing report under the predeclared production thresholds,
and independent clinical, privacy, security, accessibility, and unsupported-
claim review.
