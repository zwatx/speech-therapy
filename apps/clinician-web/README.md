# Clinician web

## Interface preview

The workspace uses a neutral, compact, line-based layout with restrained boxed
surfaces. The practice overview is a searchable worklist showing assigned
targets, recent activity, review availability, and the next action; consent
and device details live in learner records. The same visual language continues through
learner records,
assignments, attempt review, safety, privacy, and the access boundary.
Phone layouts keep record actions and evidence readable. To inspect it without
clinical providers:

```sh
CADENCE_ACCESSIBILITY_AUDIT_MODE=1 pnpm --filter clinician-web dev --hostname 127.0.0.1 --port 3211
```

Open `http://127.0.0.1:3211/accessibility-preview/overview` for the practice overview, or
`/accessibility-preview` for representative forms and evidence states. The
workspace navigation stays within `/accessibility-preview/<view>` so learners,
assignments, attempt review, safety, and privacy can be explored without clinic
providers. Assignment controls generate an unsaved summary in browser memory;
no assignment is sent or stored. Preview routes require the explicit local audit
flag and return 404 in production. Clinical routes retain normal authentication.
The preview does not provide access to clinical records.

The preview learner list opens read-only example records using the same
`LearnerRecord` layout as signed-in pages. Consent history, capture details,
device-link empty states, and return navigation can be inspected on desktop
and mobile. On narrow screens, the learner table becomes a compact list with
each record action visible without horizontal scrolling. The practice overview
uses the page scroll for all learner rows. Preview status labels describe
recorded activity or available review rather than judging pronunciation.
Example records never query clinic services, and record mutations
are unavailable. Unknown or repeated learner IDs return 404; production still
rejects the entire preview even when the audit flag is set.

The matching native redesign covers caregiver enrollment and learner practice.
The [model development roadmap](../../docs/model/model-development-roadmap.md)
sets out the next research milestones; no model feedback is enabled by the UI.

## Current behavior

Next.js App Router workspace for assignments, attempt evidence review, consent
visibility, and clinical safety operations.

Run commands from the repository root. Authenticated, tenant-scoped
consent/export/deletion and assignment handlers plus a Postgres persistence
package back the dynamic learner workspace. Clinicians can append a bounded
silent-practice dose for the one assignable foundation exercise. The assignment
is consent-bound and every device upload must match its exact version,
repetition, and retry slot. Every clinical page, API, and Server Action
rechecks active organization membership. Clerk and managed Postgres are not yet
provisioned, so local screens must use fictional data only; see the root README and
`docs/implementation/phase-gates.md` for the authoritative status.

The attempt-review page is backed by an audited tenant query rather than demo
scores. It exposes derived capture evidence only when the attempt is bound to
the learner's exact current consent snapshot and clinician review is enabled.
Consent renewal or withdrawal immediately redacts older-snapshot detail;
operational counts remain visible. Raw media, pronunciation scores, and learner
feedback are not available in this foundation.

The Safety desk shows capture retries from the same authorized query, limited
to its latest 100 attempts. It is a recent evidence view, not a complete issue
history or a pronunciation assessment. The local preview labels its single
capture example as fictional.

The signed-in home screen reads learners, latest assignments, and reviewable
attempts through three existing tenant-authorized bulk queries. Its assigned
target must match the learner's current consent; its review filter means that
evidence is available in the clinic's latest 100 authorized review records,
not that an attempt is pending review. Attempt totals do not indicate dose
completion or pronunciation progress. Empty clinics stay empty, and the
fictional overview fixtures are imported only by the gated preview routes.
Opening review from a learner keeps that learner selected within the already
authorized latest-100 list; an All attempts link clears the filter. On mobile,
capture status and reason appear directly in each review row without sideways
scrolling, while desktop retains the detailed table.
Provider-backed browser verification remains open until Clerk and Postgres
are provisioned; projection tests cover consent changes and missing data.

Learner records show the current consent choice first. Earlier choices remain
available in an expandable history, so a long audit trail does not push the
consent controls down the page. This changes presentation only; saving still
appends a consent snapshot and invalidates earlier device access.

The learner workspace also lists every active device grant plus the 25 most
recent inactive records. Owners and clinicians can revoke an active grant after
confirming that the device must be enrolled again; reviewers have read-only
visibility. Listing and revocation are tenant/resource authorized and audited,
and neither API nor UI returns stored token hashes. A database slot invariant
allows at most five current grants per learner. Owners/clinicians can atomically
replace an active token; the old token is revoked and the replacement is shown
once. Issuance and replacement share durable database-clock limits of 10
generations per learner and 30 per clinician actor per UTC hour; capacity
conflicts count, internal slot retries count once, and responses include a
private `429` plus `Retry-After` when blocked. Emergency revocation is never
subject to this generation limit. The UI explicitly explains interrupted-
response recovery. Learner-device invalid-token/IP throttling, provider-edge
controls, deployed role verification, migration rehearsal, and managed Neon
concurrency testing remain open. Valid enrolled devices are separately limited
to 120 assignment reads and 120 attempt uploads per device session per UTC hour;
the budgets are operation-specific, database-backed, and returned as private
`429` responses with `Retry-After`.

The learner route can optionally run the benchmark-only phoneme model when
`CADENCE_BENCHMARK_SCORING_ENABLED=1` and the current consent snapshot allows
research use. The flag is off by default, the learner response stays silent,
and this mode is not approved for patient data or production deployment. See
`.env.example` and `docs/model/audio-scoring.md`.

Run `pnpm test:a11y` from the repository root for the Playwright + axe WCAG
regression suite. It audits the public access boundary and a development-only,
fictional component fixture; the fixture returns 404 in production and never
bypasses clinician authorization. See `docs/accessibility/audit.md` for scope,
resolved findings, and the required manual assistive-technology matrix.
