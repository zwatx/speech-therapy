# Cadence (speech-therapy)

Consumer speech app for children ages6–12 first, an expanded local native practice library, a preserved legacy clinician foundation, and research-only audio/visual model work. Built so far mostly in Codex (GPT-6 Sol/Astra); this file carries that context into Claude Code. Global preferences in `~/.claude/CLAUDE.md` still apply.

## Read first
- `README.md`: product scope and implementation status.
- `work/WORKLOG.md`: live steering, constraints, and next steps for the model work. Gitignored (`work/WORKLOG*.md`). Older phases are archived in `work/WORKLOG-through-*.md`. Read it when resuming and keep it current.
- `docs/model/child-acoustic-heads-result-20260929.md`: latest model result (M6/M10 comparison executed, failed screen, closed). Earlier state: `docs/model/child-acoustic-transfer-status-20260928.md`.
- `docs/implementation/native-demo-checkpoint.md`: iOS demo delivery record.
- `research/audio-head/README.md`: recipes, checkpoints, verification commands.
- `.plans/2026-10-02_consumer_speech_app_direction.html`: current consumer product/vision/model plan; July plan is historical. `.plans/high-effort-continuation.md`: Codex checkpoint log.

## Layout
- `apps/ios-learner` SwiftUI learner (XcodeGen; project is generated, ignored by git); `apps/clinician-web` Next.js portal.
- `packages/*` shared contracts (JSON Schema, generated TS/Swift), scorer, etc.; `docs/*` architecture, data, security, accessibility, validation, model reports.
- `research/audio-head` Python model pipeline; `work/` experiment outputs, receipts, hashes.
- pnpm workspace. Commands: `pnpm install`, `pnpm dev`, `pnpm test:js`, `pnpm test:a11y`, `pnpm typecheck`, `pnpm lint`, `pnpm build:js`. Full `pnpm test`/`build` also need Xcode, XcodeGen, and an iPhone 17 Pro simulator.
- Git: branch `master` is unborn; the whole repo is untracked. No commits, pushes, or publication unless asked.

## Current owner direction · 2026-10-02
- Consumer app: download, optional account, immediate assessment followed by targeted practice. No required clinician setup, assignment, organizational tenant, or device enrollment in the consumer flow.
- Children ages6–12 FIRST. Speech score, condition assessment, movement guidance, exercises, and validated progress are requested goals, not existing capabilities. Do not fabricate them or enable old clinical/learner flags.
- Major RGB/TrueDepth/audio research alongside audio improvement. New runnable offline visible-motion tool is research/visual-speech; no depth or child/clinical validation yet. Primary-source dataset rights audit and actual phone capture design are there.
- Cadence name rejected. Brainstorm names with wordplay/a story; no placeholder and no rename until chosen.
- Current consumer implementation/verification: work/consumer-app-20261002/ and work/assessment-milestone-20261002/. Active product plan .plans/2026-10-02_consumer_speech_app_direction.html supersedes July clinician-first direction. Lab plan publication only is covered by thelab-plans standing permission; no issue side effects.
- New binary/r/head is CLOSED, development screen/audit passed, saved result docs/model/percept-r-binary-head-result-20261002.md. 80reservedchildren remain sealed; no scientific changes or TEST access in this product tranche.

## Product state
- iOS app is a no-account demo: 24 sound groups, 892 distinct words / 2,398 verified sound-position entries, search/position browsing/forward short sessions (vocabulary review pending), record/replay/retry/finish, temp local audio only, no pronunciation judgments. Black/white low-card design direction (The Lab rows, serif display type); the user prefers compact, neutral, no cards, no purple, no eyebrows or all-caps labels.
- Debug simulator research check: Sources/Assessment uses an explicit opt-in loopback bridge (research/audio-head/consumer_assessment), ages6–12 and occurrence-bound prompts. Prompt match unverified, all eligibility flags false; never render probabilities as findings. Local practice history stores only session/date/sound/count, up to100 entries. Docs/consumer-assessment includes current full-catalog audit and DRAFT/NOTDECLARED /r/ confirmation preparation.
- Clinician foundation (consent, enrollment, device grants, assignments, research quarantine) is extensive and research-only. Not a diagnostic device. No clinical feedback, learner judgments, or patient recordings without explicit authorization.

## Broader model goal (not achieved)
Substantially better usable pronunciation research model for ages 6–12 and all 23 consonants: unfamiliar speakers/words, rare errors, recording robustness, nonspeech rejection. Packaging and documentation alone do not meet it. Do not invent labels, claim clinical correctness, or enable learner judgments.

Standing constraints (from the worklog):
- Accessible, permitted data only; strictly noncommercial research. Compute: Mac, Dell over SSH (`zwatx`), and at most 300 existing monthly Colab compute units (ceiling, not a spend target). No unrelated uploads, purchases, signatures, or messages. LDC/MyST paperwork is a separate chat; do not touch it.
- Preserve frozen scientific sources, plans, declarations, and results. No outcome-driven exclusions, thresholds, seeds, recipes, or checkpoint rescue. Closed and consumed routes stay closed; see the worklog and `docs/model/multiphone-*` before proposing "new" ideas.
- Retained research model: `work/ages-6-12-bundle-20260927/cadence-ages-6-12-research.zip` (SHA `9a178efe…9cb9258`). Votes are observed ratings, not produced-phone truth.
- Latest state (2026-09-29): the fixed M6 (adult) vs M10 (child) encoder comparison ran (100 fits + exact control reproduction, `work/child-acoustic-heads-20260929/`). Child did not beat adult or retained (primary NLL .17900 / .17861 / .17746); screen failed; this exact comparison is CLOSED. Retained bundle unchanged. Later 2026-09-29/30: fresh nonspeech Part A done (combined admissions 3/60 at 250 ms, 8/60 at 100 ms; `docs/model/nonspeech-robustness-result-20260929.md`); retained-bundle cached 20 dB noise replay done (descriptive; noise shifts toward lower ratings; `docs/model/retained-noise-replay-result-20260929.md`). Ordinal (proportional-odds) head tested 2026-09-30: clearly worse (NLL +.015, rating-0 AP −.026), CLOSED (`docs/model/ordinal-head-result-20260930.md`). Historical note superseded by the completed Oct1 result: speech-retention Part B is complete (357words;31lost at250ms,15at100ms). Older access note: CORRECTION 2026-09-30, no form to sign (the PDF is the contributors' distribution permission); access is free TalkBank/PhonBank registration + login, and use must cite a corpus paper. Downloads need a logged-in browser, so the user downloads into `research/audio-head/outputs/percept-r-source/`. See `work/WORKLOG.md` for next steps.

## Working rules carried over
- Independent review for substantive work. Record model identity truthfully. Never use Haiku.
- Use `work/` for receipts and scratch. Do not print secrets or credentials.

## Codex history
Codex threads for this project live in `~/.codex/state_5.sqlite` (`threads`, cwd = this folder; 172 threads) with rollouts under `~/.codex/sessions`; goals in `~/.codex/goals_1.sqlite`. Main threads:
- `01a0e175-0a7f-7c30-ab8a-d35b88c123b6` Improve the speech therapy model (model goal above).
- `01a0dc94-f9ff-7471-981b-f8eed91a96a9` Build Cadence practice demo.
- `01a0c764-c290-7542-b1f7-e07f3b5a01cf` Redesign app UI and model plan (UI/usability goal, paused).
Treat them as read-only history.
