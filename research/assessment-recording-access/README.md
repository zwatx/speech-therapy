# Private recording access preparation

This isolated stdlib Python package manages a declared recording’s local copies, purpose permissions, retention, and current authenticated access. It reuses the frozen desktop review service’s actual accounts and sessions. It has no HTTP server, participant enrollment, collection, model execution, rating interface, or audio redistribution endpoint. Mobile work and reserved study files remain untouched.

The operator supplies complete PCM16 mono 16 kHz WAV bytes, at most four seconds and 132096 bytes, plus the exact declaration in [access-contract.md](../../work/assessment-real-data-20261004/access-contract.md). Rights and consent are separate for storage, review, research, inference, and redistribution. Unknown, denied, expired, restricted, withdrawn, or retention-expired inputs block the corresponding new use. Import requires current storage permission. Public reference speech requires an explicit public-reference consent declaration; its age stays null when unknown. Private-child declarations require supplied identity and authority evidence records, and none of these declarations establishes verified identity, guardian authority, licence authenticity, or professional approval.

Run from the repository root. Choose an existing private owned directory with mode 0700 as the parent of a fresh vault. The commands below use `/private/operator/vault` as a placeholder, not an existing location:

```sh
export PYTHONPATH=research/assessment-recording-access:research/assessment-review-service:research/assessment-workbench
python3 -m recording_access init /private/operator/vault project-a
python3 -m recording_access import /private/operator/vault /private/operator/reference.wav /private/operator/declaration.json
python3 -m recording_access read-check /private/operator/vault invented-reviewer-a RECORDING_ID review
python3 -m recording_access export-metadata /private/operator/vault invented-coordinator /private/operator/metadata.json
python3 -m recording_access restrict /private/operator/vault invented-coordinator RECORDING_ID review 'Operator purpose restriction'
python3 -m recording_access withdraw /private/operator/vault invented-coordinator SUBJECT_ID 'Operator withdrawal'
python3 -m recording_access purge-report /private/operator/vault /private/operator/purge-plan.json
python3 -m recording_access purge /private/operator/vault /private/operator/purge-plan.json
python3 -m recording_access reconcile /private/operator/vault
```

Initialization is exclusive and creates four invented role accounts. Passwords are generated into `fixture-credentials.json`, owned 0600 inside the owned 0700 root; values are never printed or accepted as command arguments. Protected commands prompt for the password with hidden input, log in through the actual SessionManager, verify CSRF, and derive the current account generation and project assignment. Reviewer roles read only the review purpose; coordinator access still requires the relevant permission. Expired, revoked, reset, deactivated, or restarted sessions cannot authorize access. Successful protected operations alone refresh idle time; the underlying session limits are 15 minutes idle and 30 minutes absolute. Trusted setup/import/purge commands rely on the local OS owner, not a supplied reviewer identity.

Inputs and output parents must be private: directories owned 0700; files owned regular 0600 with one link, opened without following the leaf link and without FIFO blocking. JSON outputs are exclusive and must use fresh filenames. A purge plan binds the exact journal head, eligibility time, copy IDs, and hash; intervening events require a fresh plan. There is no raw audio output command. `read-check` reads through the protected boundary and prints measured byte metadata only.

The library API is `Vault.create(root, sessions, project_id)` or `Vault.open(root, sessions)` with the same existing AuthStore root. Methods are `import_recording(bytes, declaration)`, `read_recording(token, csrf, recording_id, purpose)`, `export_metadata(token, csrf)`, `restrict(token, csrf, recording_id, purpose, reason)`, `withdraw_subject(token, csrf, subject_id, reason)`, `purge_report()`, `purge(plan)`, and `reconcile()`. The optional injected UTC clock is a testing seam. `inspect_wav(bytes)` and `validate_declaration(dict)` perform strict independent validation.

Within a fixed 4096-event/8MiB journal, ordinary receipts use at most 1536 events and 2MiB, reserving capacity for every permitted withdrawal, restriction, and deletion. Exhausted ordinary reads fail before returning bytes. A bounded private hash-linked journal records import intent/completion, access delivery attempts, denial changes, withdrawal, exports, and deletion intent/completion. Hashes check local consistency; they are not signatures, authentic provenance, or global chronology. Exported metadata uses pseudonymous subject references and omits original subject IDs, identity/authority statements, account verifiers, passwords, tokens, CSRF, and audio. All identity, rights, qualification, learner, clinical, production, and provenance claim flags remain false. Already delivered audio cannot be recalled.

Imports stage complete bytes before the durable intent. Exact known interrupted imports can recover; a pending import whose storage or retention permission has expired never promotes. Unknown, missing, tampered, linked, or malformed files quarantine protected access. A trusted `Vault.open_maintenance(...)` permits denial and explicit cleanup planning while protected reads and exports still reconcile. For a safe unknown stage, run `orphan-report ROOT PRIVATE_NEW_PLAN` followed by `purge-orphans ROOT PRIVATE_PLAN`. Unknown final files and unsafe stages remain quarantined; they are never adopted or silently deleted. Withdrawal and restrictions remain possible with quarantined media if the journal and current authorization are valid.

Deletion writes a durable tombstone before unlinking only named managed copies. Restart recovery is idempotent and records completion; import and access denominators remain. Purging makes no secure erasure, upstream deletion, backup deletion, or rollback claim. A hostile OS owner, competing uncooperative process, authentication of actual humans, remote serving, and production deployment are outside this local preparation boundary.

Focused verification uses invented PCM and actual credential hashing/session checks:

```sh
PYTHONPATH=research/assessment-recording-access:research/assessment-review-service:research/assessment-workbench python3 -W error -m unittest discover -s research/assessment-recording-access/tests
```

No root application build, mobile checks, private participant data, reserved study execution, or model fitting is required or performed by this package. Qualified reviewers, real-data onboarding, consent/permission verification, assessment validity, and deployment remain separate work.
