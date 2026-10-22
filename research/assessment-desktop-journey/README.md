# Local desktop engineering journey

Anonymous visitors can browse 15 neutral word prompts, 17 retained dictionary variants, the original project illustrations, and 13 licensed public audio examples. Manual practice is available without an account through the browser. Sign-in protects engineering assessments, persisted participation and private history. Public reference speaker ages and dictionary-variant coverage remain unknown; examples are not child recordings, phonetic truth or clinical reference approval.

The private journey connects assessment, neutral manual practice and a linked repeat. Whole-word admission, capture quality, speech evidence and the frozen research stage have separate meanings. The UI never receives transcripts, recognition probabilities or research ratings. An unavailable assessment still supports manual practice. Identical audio is explicitly a reproducibility replay, never an independent reassessment or improvement score. All learner-feedback, clinical-use and production-use eligibility flags remain false.

## Run locally

Use the system Python and the existing offline audio-head model environment. From the repository root:

```sh
export PYTHONPATH=research/assessment-desktop-journey:research/assessment-reference-assets:research/assessment-recording-access:research/assessment-review-service:research/assessment-workbench:research/assessment-admission:research/audio-head
python3 -m journey init /absolute/private/parent/new-journey --account operator
python3 -m journey serve /absolute/private/parent/new-journey --port 8780
```

The parent directory must already exist. The root must be new. Account passwords are read through a hidden prompt; there are no default passwords or HTTP account-enrollment/upload routes. The owner initializes actual AuthStore and SessionManager accounts and copies only the fixed registered public examples plus one generated nonspeech fixture into a fresh managed Vault. Managed permissions expire after 24 hours. Unsupported source-bound targets remain unavailable without invoking an acoustic worker. The recording source age stays unknown; the research harness age of 9 is an explicit engineering request input.

For private operational browser verification, `python3 -m journey fixture /absolute/private/parent/new-fixture` creates random coordinator and reviewer credentials in `fixture-credentials.json` with mode 0600. They are never printed. `python3 -m journey cleanup ROOT` reconciles retained derived data. The source public audio catalog is separately licensed and cached after byte/evidence checks; managed private-copy withdrawal does not revoke that public source license.

## HTTP contract

The service binds only `127.0.0.1`. POST requests require exact same Origin, JSON, the current cookie and `X-Journey-CSRF`. The session cookie is HttpOnly and SameSite Strict; transport is local HTTP. Unknown fields, duplicate JSON fields, malformed UTF-8, foreign Host/Origin, arbitrary paths, Range and unsupported framing are rejected.

Public routes are `GET /api/catalog`, `/api/public-references/{registeredWord}` and `/illustrations/{registeredWord}.svg`. The catalog exposes safe attribution, licenses, declared variety, retained variants and the selected occurrence. Anonymous practice is ephemeral browser participation. `GET /api/session` supplies the anonymous sign-in CSRF bootstrap; POST `/api/login` takes `{accountId,password}` and `/api/logout` takes `{}`.

Protected routes are `GET /api/state`, `/api/history`, `/api/export`, `/api/attempts/{attemptId}` and `/api/references/{opaqueItemId}`. The last route also requires the CSRF header and reads only a permitted managed review copy. No original path or recording ID appears in the browser inventory.

POST `/api/assessments` takes `{idempotencyKey,promptId,itemId,repeatOf}`; `repeatOf` is null or the caller's terminal attempt ID. The reply is `{attemptId,status}`. POST `/api/cancel` takes `{idempotencyKey,attemptId}`. POST `/api/practice` takes `{idempotencyKey,promptId,attemptId}`, with null allowed. POST `/api/history/clear` takes `{idempotencyKey}`. Exact duplicate actions retain their original identity; changed payloads conflict. Private starts require the coordinator role. Private history is restricted to the signed-in account's own attempts.

Assessment states are pending, available, unavailable, cancelled, interrupted, suppressed and forgotten. Rows retain prompt/item identities, source/content/pipeline/request hashes, repeat bindings and safe stage explanations. Export and participation counts include all planned attempts, started attempts, every terminal state and manual practice. They do not select only favorable outcomes.

## Durability and bounds

The owned mode-0700 root contains single-link mode-0600 journal/result files, opened through the frozen descriptor-based Files API. Hash-linked journal events validate before append and fsync. A maximum of 128 attempts and 65,536 bytes per result bounds retained data. Ordinary starts, participation and empty history-clear actions use at most 384 events and 1 MiB, leaving 640 control slots within the 1,024-event/8-MiB total for terminal outcomes, cancellation and forgetting. Capacity failures preserve existing history.

A worker reads permitted current bytes and records its started intent while holding the AuthStore lock, then releases the lock during offline computation. Both inference and research permissions are required before any source read or model call. Immediately before a private result write, completion refreshes the clock and rechecks the actual session, account generation, project role, both permission scopes, source bytes, retention deadline, durable cancel/clear intents and exact pipeline declaration before persisting a bound result. The full adapter runs in the existing virtual environment with offline flags and a 110-second computation deadline plus bounded cleanup. The owned supervisor continuously tracks PID/start-stamp/ancestry metadata (no process arguments), keeps its direct child unreaped, stops the discovered tree, kills deepest descendants first and verifies recorded identities are gone or zombies before reaping. It includes frozen children that start separate process groups. This is scoped to fixed trusted local workers: macOS process snapshots cannot provide atomic PID identity or adversarial process containment. A small private process-cleanup-required.json intent is fsynced before launch and removed only after confirmed worker-tree and private-stage cleanup. A leftover intent or an unconfirmed scan/cleanup writes or retains a private durable latch and blocks subsequent model starts in that root, including after reopening. It requires owner reconciliation; the CLI never silently resets that latch. Model startup stays outside the HTTP/request lock. There is no rescue model or network fallback.

Every private read, reopening and explicit cleanup reconciles source withdrawals, current authorization, permission/retention expiry and result retention. Denied results are suppressed and scrubbed; forgetting records a durable deletion intent before unlink and finishes on recovery. Reopening a pending attempt records interrupted rather than adopting unpublished output. Cancellation is a durable intent replayed before worker publication and signals the owned supervisor to stop and clean the active worker tree. A clear intent binds the exact attempt IDs present at that action, including empty clear actions; replay/retry cannot clear later attempts. History clearing keeps the denominator and minimal replay bindings while deleting derived outputs. This does not claim secure physical erasure or recall of already delivered output.

The service assumes one owner-launched process for a private root. Authentication and project operations share the frozen AuthStore lock; there is one in-process assessment worker at a time. Public cached references do not enter the managed Vault when played. All original source evidence and frozen workbench, admission, AuthStore and Vault implementations remain unchanged.

## Verification

```sh
python3 -W error -m unittest discover -s research/assessment-desktop-journey/tests
```

Unit results are injected only through the explicit adapter seam in tests and marked unit-only; the CLI always selects the actual offline adapter. Tests use real temporary private roots, actual password/session machinery, durable files and real loopback HTTP. Actual offline positive/negative receipts are stored separately under the private task fixture directory. No mobile build, participant enrollment, sensors, outreach or clinical validation is included.
