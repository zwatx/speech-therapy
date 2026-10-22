# Assessment validation workbench

A local research operator workbench for exercising assessment evidence, review, prediction locking, reporting and withdrawal with invented metadata. The browser uses a Python standard-library server and plain JavaScript. It contains no audio files, playback, recording capture, model or inference.

The intended preparation population is ages 6–12. The demo deliberately retains unsupported and unavailable attempts to exercise abstention. `engineering_ready` means the declared engineering gates passed; it does not establish pronunciation correctness, reviewer qualification, scientific validity or a learner finding. Authentication, qualified review, model accuracy, meaningful improvement, clinical use, learner feedback and production use remain unestablished.

## Start from the repository root

Use Python 3 on a POSIX system such as macOS or Linux; the private journal uses `fcntl` file locks. No dependency installation or frontend build is required. The examples assume the parent `work/` directory exists. Each creation command requires a fresh project directory; choose a new name if one already exists.

```sh
PYTHONPATH=research/assessment-workbench python3 -m workbench create-demo work/assessment-workbench-demo
PYTHONPATH=research/assessment-workbench python3 -m workbench serve work/assessment-workbench-demo
```

Open the address printed by the server, normally [http://127.0.0.1:8770](http://127.0.0.1:8770). An optional `--port 8771` changes the port. Stop with Control-C. To resume, run the same `serve` command against the existing project; do not run a creation command again.

The server binds only to `127.0.0.1`, checks local Host headers and requires same-origin JSON POSTs. It serves an allowlist of static files and synthetic records. It refuses preparation projects and any project declaring nonsynthetic prompt or recording sources. There are no uploads, media endpoints, camera/microphone controls or arbitrary filesystem import routes.

## Exercise the browser workflow

1. In **Coordinator**, append engineering content decisions. The initial prompt manifest stays pending and unchanged; the latest appended decision is current. For invented content, a null reference is sufficient only for this synthetic engineering exercise.
2. Select **Reviewer A**, then **Reviewer B**, to commit one explicit original answer for every item. These local views show prompt context and the reviewer's own answer, with participant identifiers, sources, splits, predictions and the other reviewer's work omitted. Even an “available” recording is metadata only; no audio exists to judge.
3. Seal each complete reviewer batch from that reviewer's view. A committed original cannot be overwritten, and a seal is final. Unavailable items remain in each batch and the attempt roster.
4. In Coordinator, load the explicitly invented complete prediction payload and inspect it before locking. The lock can be written once. Manual annotation does not require a model lock; original agreement waits for both seals, and model/reference comparison additionally waits for the prediction lock.
5. In **Adjudicator**, compare sealed originals and append a target decision citing both original hashes. Adjudication resolves only the target; it cannot repair uncertain speech, prompt mismatch, unresolved occurrence, unusable quality or permissions.
6. Inspect the complete report, then request **Download export (JSON)**. Check the browser's Downloads folder; the interface reports that a download was requested. File permissions depend on the browser and OS. The CLI below supplies an exclusive owner-only export and replay verification.
7. Optionally append an invented participant withdrawal. Current review availability and engineering admission change, while original source metadata, prior events and all attempt denominators stay intact.

The role selector demonstrates view separation on one local computer. It does not authenticate independent reviewers or provide access control for sensitive data. The coordinator and export contain the full local project history.

## Reproduce the completed invented exercise

`exercise-demo` creates a different fresh project and explicitly appends invented content decisions, two complete original-review batches, two seals, one prediction lock and one adjudication. It does not assess actual speech.

```sh
PYTHONPATH=research/assessment-workbench python3 -m workbench exercise-demo work/assessment-workbench-exercised
PYTHONPATH=research/assessment-workbench python3 -m workbench serve work/assessment-workbench-exercised
```

The observed exercise contains 11 attempts, four invented participants, 22 original answers, two seals and one adjudication. Three attempts become engineering ready. Appending a withdrawal for `person-a` reduces that count to one while preserving the denominator of 11, all 22 originals, both seals and the prior lock/adjudication. These counts verify workflow behavior, not accuracy or speech improvement.

## Prepare the existing public content pack

```sh
PYTHONPATH=research/assessment-workbench python3 -m workbench prepare-content work/assessment-content-preparation
```

This command reads only the fixed public [proposed engineering pack](../../docs/consumer-assessment/proposed-engineering-pack.json). Its preparation manifest preserves all 15 prompts, 17 pronunciation variants and 23 target occurrences, including repeated targets and unsupported targets. It creates zero participants and zero attempts. All engineering content statuses and the task definition remain pending.

Lexical groups use `sourceWord.strip().casefold()`, grouping display variants by their declared source word. Prompt and task versions bind the SHA-256 of the supplied pack bytes. The `dictionary_snapshot` source hash identifies this catalog-derived public pack, not a raw dictionary file. Historical `catalogSourceHashes` are retained upstream declarations; the adapter does not open those paths or verify current mobile sources. Approval or actual-rating fields, nonpending review claims, malformed variants/indexes, duplicate JSON keys and nonfinite values are rejected.

`serve` refuses this preparation project with `browser_synthetic_only`. Content preparation enables reviewable metadata; it does not enroll participants or authorize collection.

## Export and verify

Choose a fresh output filename:

```sh
PYTHONPATH=research/assessment-workbench python3 -m workbench export work/assessment-workbench-exercised work/assessment-workbench-export.json
PYTHONPATH=research/assessment-workbench python3 -m workbench verify-export work/assessment-workbench-export.json
```

Exports contain the immutable manifest, complete append-only event history, reconstructed aggregate, recomputed report and split diagnostics. Export creation refuses an existing filename. Verification checks the bundle hash, replays every event in a temporary private journal and compares reconstructed contents. A successful result explicitly keeps `authenticityEstablished: false`.

Projects are created with owner-only directory mode `0700` and journal mode `0600`; the CLI uses an owner-only creation mask for export files. Opening a project checks ownership, permissions, symlinks, journal structure, sequential/hash links and valid event transitions. Truncated, malformed or inconsistent history fails closed. Preserve a failed project for investigation; there is no automatic reset, repair or history editing command.

These are private plaintext JSON records, not encrypted storage. A hash chain detects inconsistent local content and replay ordering. It is not a signature, authenticated provenance, independent prediction chronology or a guarantee against someone rewriting an entire consistent history.

## Interpret the report

- Every imported attempt contributes to the full denominator, including failed, skipped, permission-blocked, unsupported and withdrawn attempts. Coverage pairs each numerator with its denominator; age, target and split breakdowns reconcile the same roster.
- Admission requires supported declared scope/linkage, permitted content/recording context, a processed locked prediction, two sealed original reviews confirming speech/prompt/occurrence/usable quality, and a scorable agreed or explicitly adjudicated target. Research model confidence never establishes speech presence or prompt match.
- Agreement compares original Reviewer A/B targets only. Exact agreement uses all paired originals. Kappa uses the explicit conditional subset where both targets are expected, altered or omitted; indeterminate/unscorable exclusions are separate, and undefined kappa is null. Adjudication does not retrospectively improve original agreement.
- Repeatability uses declared planned-repeat pairs. Retries are excluded from comparable endpoints, including a successful retry selected as a baseline. Condition mismatches and abstaining endpoints remain visible; corpus probability differences are descriptive and never establish meaningful improvement.
- Split diagnostics expose participant, known-household and lexical-group leakage jointly through connected components. Unknown identities/households keep isolation unestablished. Fewer than three joint components cannot supply three nonempty isolated splits; having more components does not prove a valid allocation. The workbench assigns no quotas or random slices.

## Scoped checks and remaining research work

Run only this workbench's checks from the repository root:

```sh
PYTHONPATH=research/assessment-workbench python3 -W error -m unittest discover -s research/assessment-workbench/tests
```

The implementation verification recorded 61 focused checks passing with warnings treated as errors and a passing JavaScript syntax check, plus the invented workflow and export/replay exercise described above. A native browser download was saved and replay-verified at revision 30 with 11 attempts; the browser withdrawal then appended revision 31 and preserved the full roster. The downloaded file had mode `0644`, while its private evidence copy had mode `0600`; browser exports have no owner-only permission guarantee. Checks use invented fixtures and the public pending content snapshot. No root/mobile build, model execution, fitting, actual learner/audio data, reserved study access, study execution, collection or outreach is part of this workbench.

The next research work follows the existing controlled content/reference handoff: qualified review of task and content, documented recording permissions and participant/household linkage, authenticated independent reviewer access, and prospective validation in the declared app-domain population. Those capabilities and authorizations remain separate prerequisites for actual-data use. The mobile effort stays paused and the sealed study stays untouched.

See the [dated engineering record](../../docs/consumer-assessment/assessment-validation-workbench-20261004.md) and [existing annotation/content handoff](../../docs/consumer-assessment/annotation-data-preparation.md) for the relationship to prior preparation work.
