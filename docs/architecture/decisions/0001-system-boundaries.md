# ADR 0001: Separate clinical policy from sensor and model implementations

Status: accepted for foundation implementation

## Decision

The product is split into four explicit boundaries:

1. A native iOS learner app owns permissions, short synchronized capture,
   on-device quality/landmark work, offline practice, and child-facing feedback.
2. A clinician web app owns assignments, trends, review, overrides, consent
   visibility, and safety operations.
3. A shared clinical domain owns target eligibility, pass/analyze/abstain
   routing, consent gates, and safe feedback policy. It cannot depend on a
   particular model vendor or UI framework.
4. Versioned inference services own acoustic/visual evidence production. They
   return evidence and uncertainty; they do not invent clinical copy.

## Rationale

The most safety-sensitive rule is not a neural-network architecture. It is the
decision about when evidence is adequate, whether video is permitted and useful,
and which claim is allowed for a target. Keeping that policy pure and tested
makes model changes auditable and allows the native and web clients to agree on
the same outcome vocabulary.

## Consequences

- A model cannot directly return user-facing clinical advice.
- Research targets cannot become production-eligible through configuration drift.
- Audio/video consent is enforced by routing. Clinician-review and research-use
  consent are copied explicitly onto every decision for enforcement by those
  future boundaries; neither choice changes pronunciation evaluation.
- Every persisted result must record target, protocol-registry, threshold,
  model, and feedback versions. The current in-memory routing decision records
  only the target, protocol-registry, and threshold versions; persistence and
  inference-version fields arrive at the corresponding boundaries.
- TypeScript is the first executable domain implementation. A language-neutral
  JSON Schema and generated Swift types are required before the iOS app consumes
  the API; hand-maintained duplicate contracts are not accepted.
- Authentication, persistence, and inference clients must initialize lazily at
  runtime so builds never depend on production secrets.
- Native visual feature extractors conform to a swappable boundary. Camera
  sample buffers remain ephemeral, and only observable derived geometry may
  cross into app state. Runtime choice cannot broaden consent, persistence, or
  clinical claims.
