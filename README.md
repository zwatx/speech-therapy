# Speech Therapy

A consumer speech-practice app for children ages 6–12, built with SwiftUI.
The product goal is to let families start an assessment, practice the sounds
identified, and recheck without requiring an account or clinician enrollment.
See the [consumer product plan](.plans/2026-10-02_consumer_speech_app_direction.html)
for the intended scope.

This repository contains the iOS app, a separate clinician web portal, shared
packages, and speech-model research. The app still uses the name Cadence in its
bundle and project files; a replacement name is pending.

## Current app

Ordinary iPhone launch opens the Congressional App Challenge presentation
prototype with **Today**, **Sounds**, and **Progress** tabs. A three-word sound
check leads to selected practice and a fresh recheck. Recording, replay, and
temporary-file cleanup are real and local. On supported TrueDepth devices, an
optional live face preview shows facial movement during practice; it does not
score pronunciation. Prototype results stay in memory.

**The presentation prototype uses authored pronunciation outcomes.** Its feedback
is not inferred from the recording or a model. It demonstrates the intended
experience without establishing speech accuracy, improvement, or a diagnosis.
See the [presentation routine and evidence](docs/consumer-assessment/cac-presentation-routine-20261025.md)
for the scenario, media behavior, and verification limits.

The retained practice and research routes are available through explicit Debug
launch flags. They include:

- A library of 24 consonant groups, 892 distinct words, and 2,398 sound-position
  entries, with search and beginning/middle/end browsing.
- Short recording sessions with replay, retry, skip, and device-local
  participation history. Practice audio stays temporary and local.
- On-device whole-word recognition using a bundled English Whisper model.
  A word match does not assess individual sounds.
- Opt-in simulator research checks, separate from consumer feedback.

The [iOS guide](apps/ios-learner/README.md) describes these routes, launch flags,
recording ownership, and native verification. The
[practice-library provenance](docs/content/practice-library-provenance.md)
records the licensed CMUdict source and sound-position checks. Vocabulary and
exercises are not a validated treatment plan.

## Research and clinical status

Sound-level models remain research candidates. Training results, numerical
parity checks, and software tests do not establish validated child pronunciation
judgments. Full learner-model qualification and prospective clinical validation
remain open. The [audio research guide](research/audio-head/README.md) contains
recipes and reports; the [model roadmap](docs/model/model-development-roadmap.md)
and [current multi-sound decision](docs/model/current-multiphone-decision.md)
describe the evidence and remaining work.

The clinician portal preserves consent, enrollment, assignments, attempt-evidence
review, export, and deletion infrastructure. Its optional research scoring is off
by default and returns no corrective learner feedback. Clerk and managed Postgres
are not provisioned; local previews use fictional records. Clinician enrollment
is separate from the consumer workflow.

The project is not a diagnostic device, a production clinical system, or a
substitute for a speech-language pathologist. Provider setup, deployment controls,
models qualified for their intended use, and clinical validation remain required
before a clinical pilot. See the [phase gates](docs/implementation/phase-gates.md).

## Development

Run commands from the repository root. JavaScript development uses Node.js and
pnpm; the package manager is pinned to `pnpm@11.10.0` in `package.json`.
iOS development also requires macOS, Xcode, Swift, and XcodeGen. The native test
script targets an **iPhone 17 Pro** simulator.

```sh
pnpm install
```

### iOS app

Generate the Xcode project:

```sh
pnpm ios:generate
open apps/ios-learner/CadenceLearner.xcodeproj
```

Run the `CadenceLearner` scheme on an installed iPhone simulator. The deployment
target is iOS 17.0; simulator builds need no signing team. A physical device is
needed to exercise the TrueDepth preview.

Compiled Whisper model directories are excluded from Git. Native word checks
need the exact resources listed in the
[bundled-resource manifest](apps/ios-learner/WhisperResources/RESOURCE-MANIFEST-v1.json);
a fresh clone does not include those model weights. The authored presentation
journey needs no model server, download, account, or network.

### Clinician web

`pnpm dev` starts the clinician portal. To explore the interface with fictional
records and without clinical providers, use the local preview:

```sh
CADENCE_ACCESSIBILITY_AUDIT_MODE=1 pnpm --filter clinician-web dev --hostname 127.0.0.1 --port 3211
```

Open [the practice overview](http://127.0.0.1:3211/accessibility-preview/overview).
Preview routes are unavailable in production. See the
[clinician web guide](apps/clinician-web/README.md) for setup and access boundaries.

### Checks

| Command | Scope |
| --- | --- |
| `pnpm test:js` | JavaScript workspace tests |
| `pnpm typecheck` | TypeScript workspace checks |
| `pnpm lint:js` | JavaScript workspace linting |
| `pnpm build:js` | JavaScript workspace builds |
| `pnpm test:a11y` | Clinician Playwright and axe accessibility suite |
| `pnpm test:swift-contracts` | Shared Swift contract tests |
| `pnpm test:ios` | Native unit and UI tests on the configured simulator |
| `pnpm lint` | JavaScript linting and Swift formatting checks |
| `pnpm test` | JavaScript, Swift contract, and native tests |
| `pnpm build` | JavaScript builds and iOS simulator build |

Full tests and builds require the Apple toolchain. Provider-backed routes and
some research checks also need their separately documented setup. Check the
linked verification reports for what actually ran and what remains unverified.

## Repository map

| Path | Contents |
| --- | --- |
| [apps/ios-learner](apps/ios-learner/README.md) | SwiftUI consumer prototype and retained native routes |
| [apps/clinician-web](apps/clinician-web/README.md) | Next.js clinician portal and fictional-data preview |
| [packages](packages) | Clinical domain, contracts, persistence, audio adapters, scoring, and visual evaluation |
| [docs/consumer-assessment](docs/consumer-assessment/README.md) | Assessment preparation, catalog coverage, and native verification reports |
| [docs/model](docs/model) | Model protocols, results, and integration diagnostics |
| [research/audio-head](research/audio-head/README.md) | Audio training and evaluation tools |
| [research/visual-speech](research/visual-speech/README.md) | Offline lip-geometry tooling and dataset/TrueDepth research |

The [July foundation plan](.plans/2026-07-10_ai_speech_therapy_app_plan.html)
remains historical context. The consumer plan supersedes its clinician-first
entry flow. Detailed dated results belong in the linked reports rather than in
this overview.
