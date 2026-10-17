# Cadence clinician web

Next.js App Router portal for learner records, consent, assignments, attempt
evidence, and privacy operations. This is a separate legacy foundation;
[Cadence's consumer iOS app](../ios-learner/README.md) does not require clinician
enrollment.

## Local interface preview

Run from the repository root with Node.js and the pinned pnpm version installed:

```sh
pnpm install
CADENCE_ACCESSIBILITY_AUDIT_MODE=1 pnpm --filter clinician-web dev --hostname 127.0.0.1 --port 3211
```

Open the [practice overview](http://127.0.0.1:3211/accessibility-preview/overview)
or the [component preview](http://127.0.0.1:3211/accessibility-preview).
The preview uses fictional records without contacting clinical providers. Explore
learner records, assignments, attempt review, safety, and privacy through its
navigation. Assignment controls create an unsaved summary in browser memory;
they do not send or store assignments.

Preview routes require the explicit audit flag and return 404 in production,
even when the flag is set. They do not bypass authentication for clinical routes
or expose real records.

## Authenticated portal

`pnpm dev` starts the clinician workspace. Persistent routes require Clerk,
managed Postgres, active organization membership, and the configuration listed
in [.env.example](.env.example). For local provider configuration, copy that
example to `apps/clinician-web/.env.local` and supply real credentials and separate
identity-hash/scorer secrets. Example values do not provision those services.

Clerk and managed Postgres are not yet provisioned for this project. Use the
fictional preview until provider setup and deployment checks are complete;
provider-backed browser verification remains open. See the
[phase gates](../../docs/implementation/phase-gates.md) for remaining requirements.

## Implemented behavior

- Learner records show current consent and append-only consent history.
  Every clinical page, API, and Server Action checks active organization
  membership and resource access.
- Clinicians can assign a bounded silent-practice dose for the single foundation
  exercise. Assignments and uploads bind the exact consent snapshot, assignment
  version, repetition, and retry slot.
- Attempt review exposes derived capture evidence only for the current consent
  snapshot with clinician review enabled. Consent changes redact older detail.
  The review and Safety views use the latest 100 authorized attempt records;
  they are not a complete history or a queue of pending clinical decisions.
- Device access lists active grants and the 25 most recent inactive records.
  Owners and clinicians can revoke or replace tokens; reviewers are read-only.
  Replacement tokens are shown once. Database-enforced capacity and hourly limits
  protect issuance, while emergency revocation stays available at the limit.
  Assignment reads and uploads have separate per-device hourly budgets.
- Consent, export, deletion, and device-access operations are tenant-scoped and
  audited. Raw media, pronunciation scores, and corrective learner feedback are
  unavailable in this foundation. Participation and attempt counts do not measure
  pronunciation progress.

Optional benchmark scoring requires `CADENCE_BENCHMARK_SCORING_ENABLED=1` and
research permission in the current consent snapshot. It is off by default and
keeps learner responses silent. See the
[audio-scoring guide](../../docs/model/audio-scoring.md) for the research boundary.
This portal is not approved for patient data or production clinical use.

## Checks

Run from the repository root:

| Command | Scope |
| --- | --- |
| `pnpm --filter clinician-web test` | Portal unit and API-handler tests |
| `pnpm --filter clinician-web typecheck` | TypeScript checks |
| `pnpm --filter clinician-web lint` | ESLint |
| `pnpm --filter clinician-web build` | Next.js production build |
| `pnpm test:a11y` | Playwright and axe accessibility suite |

The accessibility suite starts its own local fixture server on port 3210 and
uses installed Chrome. It checks the public access boundary and fictional
component states, without authenticating to clinical providers. See the
[accessibility audit](../../docs/accessibility/audit.md) for coverage and the
remaining manual assistive-technology checks.
