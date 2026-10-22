# Assessment validation workbench — 2026-10-04

A runnable research operator workbench now exercises the assessment validation workflow in a separate [research directory](../../research/assessment-workbench/README.md). It uses a Python standard-library backend and a plain JavaScript browser interface. This is synthetic workflow completion and public content preparation for ages 6–12. It adds no actual enrollment, recordings, model execution, clinical decisions or learner findings.

The workbench preserves the [assessment v1 distinctions](assessment-v1.md): capture quality, speech presence, prompt match, target evidence, research prediction, learner finding, participation and improvement are separate. Model corpus probabilities do not establish that the requested word was spoken. The [existing annotation/content handoff](annotation-data-preparation.md) remains the route for qualified task/reference/content decisions; this implementation creates no parallel clinical approval flow.

## What runs now

| Area | Implemented engineering behavior | Boundary |
| --- | --- | --- |
| Manifest | Exact schema validation and immutable task, policy, prompt and permission pins | Malformed imports fail whole; unsupported attempts stay visible |
| Journal | Private append-only sequence with previous-event hashes, locked writes and replay | Integrity checks and local order do not authenticate people or external chronology |
| Independent views | Fixed Reviewer A/B projections containing prompt context and own answers | Local demo view separation; no authenticated independence or qualification |
| Original review | One explicit immutable answer per reviewer/item, complete-batch seals | No real audio exists; invented answers exercise persistence and gates |
| Adjudication | Target-only decision citing both sealed original-answer hashes | Originals remain intact; other evidence gates cannot be bypassed |
| Prediction lock | One complete payload covering every attempt, including unavailable rows | Invented corpus-class probabilities; no model or inference |
| Report | Full terminal denominators, coverage, original agreement, repeatability and leakage diagnostics | No model accuracy, clinical validity, learner eligibility or improvement claim |
| Withdrawal | Appended current restriction blocks review availability and admission | Earlier source/events and denominators are retained |
| Content preparation | Fixed public catalog-derived pack converted into an empty pending project | Preparation projects cannot enter the browser server |
| Export | Complete private JSON history and recomputed evidence with replay verification | Plaintext; hashes are not signatures or encryption |

The synthetic browser serves an allowlist of assets on `127.0.0.1` and enforces local Host/same-origin mutation checks, strict JSON and request limits. It has no microphone, camera, upload, media playback, arbitrary-file import or participant collection path. Projects declaring preparation mode or nonsynthetic sources are refused. Any role can be selected locally; the selector is not an identity or authorization mechanism.

## Reproduce from the repository root

Use Python 3 on macOS/Linux with POSIX `fcntl`; no frontend build or third-party packages are required. The parent `work/` directory must already exist, and all creation/export destinations below must be fresh.

Start a synthetic project for manual operation:

```sh
PYTHONPATH=research/assessment-workbench python3 -m workbench create-demo work/assessment-workbench-demo
PYTHONPATH=research/assessment-workbench python3 -m workbench serve work/assessment-workbench-demo
```

Open the printed loopback URL. Coordinator content decisions are appended; Reviewer A and B each commit every original answer and seal their own batches; predictions are inspected and locked once; the Adjudicator can then append a target decision. Original agreement requires both seals. Model/reference comparison also requires a lock. Annotation can proceed with no model lock. “Recording available” indicates invented permitted metadata, not playable audio.

To reproduce the explicit prefilled exercise in another fresh project:

```sh
PYTHONPATH=research/assessment-workbench python3 -m workbench exercise-demo work/assessment-workbench-exercised
PYTHONPATH=research/assessment-workbench python3 -m workbench serve work/assessment-workbench-exercised
```

Stop the server with Control-C. The same `serve` command resumes an existing journal; creation commands do not reuse, clear or reset projects. An optional `--port` selects a different local port. An invalid or corrupt journal fails closed.

Prepare the public content snapshot separately:

```sh
PYTHONPATH=research/assessment-workbench python3 -m workbench prepare-content work/assessment-content-preparation
```

Export an existing project and replay-check the output:

```sh
PYTHONPATH=research/assessment-workbench python3 -m workbench export work/assessment-workbench-exercised work/assessment-workbench-export.json
PYTHONPATH=research/assessment-workbench python3 -m workbench verify-export work/assessment-workbench-export.json
```

The browser also requests a server attachment named `assessment-workbench-export.json`. Check the browser's Downloads list and verify the saved JSON with `verify-export`; clicking the button alone does not verify completion. Browser download permissions vary by browser/OS and are not guaranteed owner-only. The CLI refuses an existing output filename and creates owner-only files under its private creation mask.

## Observed synthetic evidence

The implementation check run recorded **61 focused standard-library tests passing with warnings as errors**, with the JavaScript syntax check also passing. Reproduce the workbench checks without running a root or mobile build:

```sh
PYTHONPATH=research/assessment-workbench python3 -W error -m unittest discover -s research/assessment-workbench/tests
```

The invented end-to-end exercise completed:

- 11 terminal attempts and four invented participants, retaining unavailable and unsupported examples.
- 22 committed originals, two complete reviewer seals, one complete prediction lock and one explicit target adjudication.
- Three engineering-ready attempts. An appended withdrawal for `person-a` reduced that count to one while preserving the 11-attempt denominator and the complete historical review/lock/adjudication record.
- Full CLI export/replay verification at revision 30, with authenticity still false.
- A real native browser attachment download saved and replay-verified at revision 30 with 11 attempts. Its OS file mode was `0644`; the retained private evidence copy was `0600`.
- A real browser withdrawal appended revision 31, reduced engineering-ready attempts from three to one, retained the 11 attempts/22 originals/two seals, and was independently export/replay-verified through the CLI.

These observations verify implementation behavior. They establish no actual reviewer qualification, speech correctness, model accuracy, learner finding, meaningful speech improvement, clinical validity or production readiness. The demo contains recording metadata and fabricated answers but no audio file or model output generated from speech.

## Public pack preparation and provenance

`prepare-content` reads the fixed [proposed engineering pack JSON](proposed-engineering-pack.json), using `workbench.content.prepare_content_manifest(pack_bytes: bytes) -> dict`. The current snapshot produces **15 prompts, 17 pronunciation variants and 23 target occurrences**, with zero participants and zero attempts. Every content status and the controlled task definition remain pending; the server rejects the resulting preparation project.

All declared pronunciation variants and all `targetIndexesByVariant` become workbench variants/occurrence indexes, including repeated-target words. Lexical groups explicitly normalize `sourceWord` with whitespace stripping and Unicode case folding, so separate prompt positions for the same declared source word remain connected in leakage diagnostics. Unsupported targets are retained.

Task and prompt versions bind the SHA-256 of the exact supplied pack bytes. The source kind is `dictionary_snapshot`, and its hash denotes this **catalog-derived public snapshot**, not a raw dictionary digest. The three upstream `catalogSourceHashes` declarations are retained historical metadata, with current-source verification and qualified review explicitly false. The adapter does not follow the declared mobile/source paths, rebuild the catalog or remeasure those historical hashes.

The adapter rejects nonpending headers/reviews, learner eligibility claims, extra rating fields, invalid byte/JSON encoding, duplicate keys, nonfinite values, inconsistent variant counts, incomplete target indexes and contradictory selected-position metadata. Conversion does not upgrade a proposed pack into accepted content, grant recording rights or fabricate reference qualification.

## Evidence and interpretation rules

**Admission.** Engineering readiness requires a declared in-scope age/variety, known identity linkage and household, supported target/selected occurrence, permitted content/reference rights, permitted recording/research context, suitable terminal/prediction availability and two sealed originals confirming speech, prompt match, resolved occurrence and usable quality. An adjudication may resolve a target alone. Confidence cannot substitute for these independent gates. Learner, clinical and production eligibility flags remain false for every attempt.

**History and current restrictions.** Task, policy, prompt and permission snapshots are pinned at initial manifest preparation. Original prompts/reviews are never overwritten. Later content decisions and participant withdrawal are append-only records; they can block current admission without changing the historical context or removing attempts. A later adjudication cites the exact sealed originals rather than replacing them.

**Denominators.** Report counts include every attempt, including failed, skipped, rejected, cancelled, permission-blocked, unknown-linkage, unsupported and withdrawn attempts. Coverage exposes numerator/denominator pairs, and age/target/split strata reconcile the complete attempt roster. Multiple abstention reasons can apply to one attempt, so reason counts are not a partition of the attempt denominator.

**Agreement.** Exact target agreement uses all paired original Reviewer A/B answers across five categories. Conditional kappa uses only pairs where both targets are expected, altered or omitted, with indeterminate/unscorable exclusions reported separately. Undefined/degenerate kappa is null. Adjudication never increases original agreement retrospectively, and agreement does not establish truth or qualified review.

**Repeatability.** Only declared planned-repeat links enter the pair roster. Retry endpoints are excluded from comparability, including successful retries selected as a later baseline. Condition mismatch and abstention leave the declared pair visible while suppressing probability differences. Eligible differences describe repeat-minus-original subjective corpus classes. Meaningful improvement remains false.

**Isolation.** Participant, known-household and lexical-group constraints are considered together through connected components. Unknown identity linkage or households leave isolation unestablished. Fewer than three components makes three nonempty isolated splits infeasible; more components does not validate allocation, quotas or scientific independence. The workbench creates no randomized split or favorable subset.

## Storage boundary and remaining prerequisites

New projects use directory mode `0700` and journal mode `0600`; ownership, access modes, regular-file/no-symlink requirements and complete hash/sequence replay are checked on open. Writers hold an exclusive journal lock and persist appended events. The CLI's export path is exclusive and owner-only. Preserve corrupt or failed-creation evidence; this tooling has no silent reset or automatic journal repair.

Exported JSON includes the entire private history. Owner-only permissions are not encryption, and access to a local demo role is not authenticated authorization. Local hashes identify content and detect inconsistent replay; they cannot prove a global timeline, independent prediction generation, signatures or authenticity against complete consistent rewriting. `verify-export` explicitly returns `authenticityEstablished: false` even on success.

Further research work follows the existing controlled task/content/reference handoff. Actual qualified review, documented permissions and identity/household linkage, authenticated independent reviewer access, and prospective validation in the declared app-domain population remain distinct prerequisites for actual-data use. Research technical preparation can continue with public metadata and invented fixtures. Mobile work remains paused; the sealed study is unchanged and unexecuted. No TEST access, fitting, model execution, real participant collection or reviewer outreach occurred in this workbench task.
