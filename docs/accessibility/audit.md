# Accessibility audit and verification

Status: automated foundation verified on 2026-07-10. Manual assistive-technology
and disabled-user validation remains required before any pilot or production
accessibility gate can close.

September 23 interface revision: ten web checks pass, including the connected
fictional preview, local-only assignment summary, desktop current-page links,
mobile menu closure, practice selection/search/empty states, and axe checks on
each preview screen. Unknown preview paths return 404 before response streaming.
Production preview requests return 404 even with the development flag set.
Current consent stays visible while earlier choices expand using native
keyboard-operable disclosure controls. Every historical choice and timestamp
remains available; desktop and narrow-screen interaction checks pass.
The signed-in overview now uses the same layout with authorized records; its
projection tests and source review pass. The ten browser checks exercise
fictional preview data, not a provisioned clinician identity and database.
Read-only learner-record previews exercise the actual shared record layout,
consent history, back navigation, empty captures, unavailable mutations, and
invalid-record handling. This exposed and fixed a mobile grid sizing issue:
the capture table now scrolls inside its container without widening the page.
The mobile learner list now keeps each record action on screen, and the mobile
practice list uses page scrolling so no learner is concealed in a nested scroll
area. The preview's activity labels no longer imply clinical progress. The
responsive learner action, full list height, and read-only record navigation
were checked at narrow width; desktop table navigation still works.
Mobile attempt review now places capture status and reason directly in a flat
row instead of hiding them behind horizontal scrolling. Review links from the
selected learner keep that filter through preview navigation, with a visible
way back to all attempts. The scoped mobile review and a11y scan pass.
The later compact, line-based pass keeps all five fictional learners visible in
the first 1280×720 desktop overview and directory views. An independent
read-only check found no document-level horizontal overflow or axe A/AA
violations on learner directory/detail, Safety, or Privacy at 320 pixels; the
keyboard-expanded consent history and preview-only disabled data controls
remained usable. The assignment preview action is visible in the first desktop
viewport and still produces only a local, unsaved summary. The ten web browser
checks and optimized build were rerun after the final CSS changes.
Swift syntax parsing and formatting pass for the native redesign and recording
state fixes; current simulator/build verification is blocked by an unaccepted
Xcode license. The native palette and typography pass also passed independent
source review, but rendered contrast and accessibility still need a simulator
rerun after the license is accepted by the user. The earlier native audit
result is not a rerun of these changes.

## Scope and standard

The clinician web boundary was reviewed against WCAG 2.2 A/AA across desktop,
keyboard-only, 390-pixel mobile, reduced-motion, and forced-colors states. The
iOS enrollment, assignment loading, no-assignment, assignment-error, and
ready-practice screens were reviewed with XCTest's native accessibility audit
on an iPhone 17 Pro simulator. Source review also covered
forms, tables, status messages, capture controls, Dynamic Type, target sizes,
color-independent meaning, and state transitions.

Automation is deliberately split:

- `pnpm test:a11y` runs axe-core against the public access boundary and an
  explicit development-only fixture containing representative dashboard,
  attempt-review table, device-access history/revocation/rotation controls,
  safety, and form states. The fixture is a 404 in production and
  contains no clinical data.
- `pnpm test:ios` runs native unit tests plus XCTest accessibility audits for
  enrollment, assignment loading/no-assignment/error, and ready practice. The
  fixtures are compiled only in Debug builds.
- `pnpm lint` checks JSX semantics and Swift formatting; `pnpm build` verifies
  both production surfaces.

## Resolved findings

### A11Y-01 — iOS text could clip under larger Dynamic Type

- Location: enrollment URL field and practice assignment progress.
- Criteria: WCAG 1.4.4 Resize Text; Apple Dynamic Type guidance.
- Severity: Major.
- Impact: larger-text users could lose the server example or current-word
  position.
- Remediation: replaced placeholder-only field labels with persistent visible
  labels and empty, explicitly named inputs; allowed assignment progress to
  retain its intrinsic width. XCTest now audits both screens without findings.

### A11Y-02 — asynchronous recording states were not explicitly announced

- Location: iOS practice phase transitions.
- Criteria: WCAG 4.1.3 Status Messages.
- Severity: Major.
- Impact: VoiceOver users could miss recording, saving, retry, permission, or
  failure transitions after activating a control.
- Remediation: every practice phase now posts a concise platform accessibility
  announcement while leaving visible copy and control labels unchanged.

### A11Y-03 — form errors were not programmatically tied to their inputs

- Location: learner creation and owner deletion confirmation.
- Criteria: WCAG 3.3.1 Error Identification and 3.3.3 Error Suggestion.
- Severity: Major.
- Impact: screen-reader users could hear an alert without knowing which field
  needed attention.
- Remediation: inputs now expose `aria-invalid` and conditionally include the
  exact error element in `aria-describedby`.

### A11Y-04 — repeated navigation and current location needed stronger cues

- Location: clinician portal shell and mobile menu.
- Criteria: WCAG 2.4.1 Bypass Blocks; 2.4.4 Link Purpose; 2.4.8 Location (AAA
  enhancement).
- Severity: Minor.
- Impact: keyboard and screen-reader users had weaker location context, and the
  skip target was not explicitly focusable across browsers.
- Remediation: the main landmark is a programmatic focus target; navigation now
  emits `aria-current="page"`; compact branding has an explicit destination
  name; mobile menu controls meet a 44-point target.

### A11Y-05 — Windows high-contrast affordances were implicit

- Location: portal status chips, routes, buttons, and selected navigation.
- Criteria: WCAG 1.4.11 Non-text Contrast and 1.4.1 Use of Color.
- Severity: Minor.
- Impact: system color replacement could remove borders or selected-state
  differentiation.
- Remediation: a forced-colors stylesheet restores system-color borders and
  outlines. Axe scans authored colors before forced-colors emulation because
  automated contrast calculations do not model system palette replacement
  reliably; operability is then checked with forced colors active.

## Verified evidence

- Three axe-core WCAG 2/2.1/2.2 A/AA scans passed with zero detectable
  violations; a fourth Playwright test verifies keyboard focus transfer.
- Keyboard skip-link focus transfer: passed.
- Mobile menu, reduced motion, forced colors, and horizontal overflow: passed.
- XCTest native accessibility audit: enrollment, assignment loading,
  no-assignment, assignment-error, and ready-practice screens passed after the
  audit exposed and drove two clipping fixes.
- Authenticated clinical pages remain authorization-protected; the audit fixture
  exercises their shared components—including long learner names, dense capture
  reasons, review-table scrolling, device-status labels, confirmation, and
  uniquely named 44-point revoke/replace controls—without weakening that
  boundary.

## Required manual and participant validation

Automation cannot close the product accessibility gate. Before pilot use:

1. Test every authenticated route and every learner phase with VoiceOver on a
   physical iPhone and Safari on macOS.
2. Test clinician workflows with NVDA + Firefox/Chrome and JAWS + Chrome on
   Windows, including tables, immutable consent, token display, export, and
   deletion errors.
3. Exercise Voice Control, Switch Control, keyboard-only use, 200–400% browser
   zoom, all Dynamic Type accessibility sizes, Bold Text, Increase Contrast,
   Reduce Motion, and landscape/iPad layouts.
4. Conduct task-based sessions with disabled clinicians, caregivers, and
   children; resolve observed barriers and rerun the complete regression suite.
5. Record device/browser/assistive-technology versions, tasks, severity,
   evidence, owner, and retest status. No automated zero-finding result may be
   presented as conformance certification.
