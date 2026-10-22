# Cross-platform contract boundary

Status: implemented for attempt evaluation v1

`packages/contracts/schema/attempt-evaluation.schema.json` is the canonical
wire contract. The generator emits:

- `packages/contracts/src/generated/attempt-evaluation.ts` for the API and
  shared clinical domain.
- `packages/contracts/swift/Sources/CadenceContracts/AttemptEvaluationModels.swift`
  for the native learner.

Generated files are never edited by hand. `pnpm contracts:generate` updates
both clients; package tests run the generator in check mode and fail when a
checked-in client is stale. The Swift package independently compiles and
round-trips Codable request values.

JSON Schema expresses structure, enums, ranges, unique capture reasons, and the
video-unavailable conditional. The probability-sum invariant is documented as
`x-cadence-invariants` and enforced in both the TypeScript request parser and
the Swift request factory. Runtime API validation also rejects undeclared
fields so the implementation cannot accept a wider, PHI-prone payload than the
published contract.

Adding a protocol, reason, decision, or consent field starts with a schema
change, regeneration, domain-policy updates, fixtures, and tests in both
languages. A client-only enum edit is a contract violation.
