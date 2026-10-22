# Feedback template and claim-release governance

Status: candidate research infrastructure only. No checked-in template is
learner-feedback eligible, and no shipped target protocol is validated for deep
vision. The iOS learner and attempt API remain silent.

## Safety boundary

Models return structured evidence; they never return learner-facing prose.
Aggregate accuracy, schedule pressure, or partner demand cannot waive a failed
consent, subgroup, unsupported-claim, security, or accessibility gate. A failed
gate stops release of that target.
`@speech-therapy/clinical-domain` now owns four versioned template roles:

- calm positive reinforcement after a confident correct route;
- a neutral retry for poor capture or ambiguous audio;
- one bilabial practice instruction after an eligible deep route reports
  `closure-not-observed`; and
- a move-on message that queues clinician review after a retry limit, distress,
  or a stop request.

Every template binds its exact static title and body, locale, target protocol,
allowed evidence types, structured claim types, SLP license evidence, SLP
content-approval evidence, approval time, version, and canonical SHA-256 digest.
The catalog itself is `candidate-only` and hardcodes
`learnerFeedbackEligible: false`.

## Research evaluation authorization

An opaque research-simulation evaluation can be created only when all of these
agree:

1. an exact candidate catalog and four role-to-template bindings;
2. one narrow age/language/dialect/clinical population scope;
3. a validated bilabial target in the exact content-hashed protocol registry;
4. a locked two-retry/two-cue policy with one cue per attempt, move-on and
   clinician-review escalation, and immediate stop on distress or request;
5. a complete bounded policy audit, rerun from the exact content-hashed sample
   cohort during authorization, with zero detected violations, all four
   templates, and all nine required scenarios exercised;
6. hashes for clinical governance, usability, accessibility, fused utility,
   and authenticated-export evidence; and
7. valid lock, audit, approval, authorization, selection, and expiry chronology,
   including a 15-minute research authorization lease.

The resulting object remains `research-simulation-only`,
`learnerFeedbackEligible: false`, and `productionGateEligible: false`. Its
selector is named `simulateFeedbackSelection`; no function in this package can
mint learner-feedback eligibility from hash-shaped evidence.

The current shipped registry marks bilabial closure `candidate`, so it fails the
authorization boundary. Unit tests use a clearly synthetic evaluation-only
registry to prove positive and negative behavior; that registry is not exported
as product configuration.

## Unsupported-claim audit

The audit checks both declared template content and rendered evaluation samples.
It reparses each original attempt and recomputes its route with the candidate's
content-hashed threshold policy and registry instead of trusting a caller's
declared decision.
It rejects:

- diagnostic or causal language;
- hidden-articulator and unsupported anatomy claims;
- absolute or shaming language;
- dynamic prose that differs from the approved template;
- a cue without an eligible bilabial non-closure model result;
- a route that does not satisfy the template evidence allow-list;
- an unbound template or content hash;
- retries or corrections beyond the locked budget;
- ignored stop/distress signals; and
- a missing or spurious clinician-review escalation.

The candidate policy also fixes the exact four English titles/bodies and exact
claim-kind matrix. Samples must cover confident correct, capture retry and
exhaustion, uncertain retry and exhaustion, corrective cue and exhaustion,
distress, and stop request. A canonical sample-evidence hash prevents a report
from being reused for a different cohort. A hash-bound per-attempt state and
deterministic selection receipt make replays idempotent; after that receipt is
recorded, the next state prevents a second cue for the attempt. Durable receipt
storage is still required before any runtime connection.

The report deliberately says `zeroDetectedPolicyViolations` and identifies its
scope as `bounded-static-policy-and-lexical-v1`; it does not claim that a regex
proves clinical safety. The lexical rules are defense in depth, not a substitute for qualified SLP,
privacy, accessibility, regulatory, and usability review. Authenticated evidence
hashes must be produced and verified by the governed platform before a real
release; arbitrary strings are not proof of an approval ceremony.

Run an audit from the repository root:

```bash
pnpm --filter @speech-therapy/clinical-domain feedback:audit -- \
  catalog.json release-candidate.json protocol-registry.json release-samples.json \
  2026-07-10T18:10:00.000Z
```

Exit status `0` means the supplied candidate samples produced zero detected
policy violations; `3` means the JSON report contains findings; `1` means the evidence
was malformed or failed validation; and `2` means command usage was invalid.
A zero-finding synthetic report cannot authorize learner feedback, production,
or Gate 2 closure.

## Remaining release work

Before learner-facing feedback is connected, the program still requires real
SLP authorship and license verification, approved clinical content, a locked
population and target protocol, authenticated prospective samples, passing
fused-utility and subgroup evidence, physical-device and accessibility studies,
learner/caregiver/SLP usability findings, regulatory and privacy approval,
runtime persistence of the exact release/template versions, clinician review
queue integration, rollback and complaint handling, and a final zero-finding
audit of the actual release sample set.
