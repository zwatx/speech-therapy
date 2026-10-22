# Authenticated desktop review service

This local research service exercises account-based access, blind review, media delivery, prediction locking and recoverable audit attribution. It uses invented accounts, one generated nonspeech waveform and the existing public pending-content pack. It imports the [frozen assessment workbench](../assessment-workbench/README.md) without changing it. No real recordings, enrollment, model execution or scientific validation are included. Learner, clinical and production claims remain false.

## Start a fresh fixture

Run from the repository root on a POSIX system with Python 3. The service uses the Python standard library and plain browser JavaScript/CSS; no package installation or root build is needed.

```sh
export PYTHONPATH=research/assessment-review-service:research/assessment-workbench
python3 -m review_service create-fixture work/review-service-fixture-01
python3 -m review_service serve work/review-service-fixture-01 --port 8772
```

The creation destination must be new. Open the printed `http://127.0.0.1:8772` address. Creation stores four random invented passwords in the private `fixture-credentials.json` inside the new root; it never prints them. Use that file locally as the operator, and keep its values out of screenshots, logs, exports and shared documents. The account names are `fixture-coordinator`, `fixture-reviewer-a`, `fixture-reviewer-b` and `fixture-adjudicator`. Sign out before changing accounts in the same browser.

The root and private directories are owned `0700`; private journal, credential and waveform files are `0600`. Stop the server with Ctrl-C and run `serve` again to resume the same journals. Restart invalidates every browser session. Authenticated sessions expire after 15 minutes without a successful protected operation or 30 minutes from login; failed requests and passive session reads do not extend them. Login starts are limited to five per minute across the service.

## Use the fixture

The coordinator sees the two fixed projects. `demo-review` contains four invented participants and eleven attempts. Nine present recordings share the exact same quiet 220 Hz, 1.2-second PCM waveform. Its transport bytes are real; all speech labels, example answers and predictions are fabricated workflow metadata. Tone playback cannot establish pronunciation, accuracy or clinical findings. There is no real-media import.

Reviewers receive their own blind items through current server-resolved account assignments. Source participant/split/model information and the other reviewer's notes are withheld. Submit every original item, then seal each reviewer roster. Missing or currently restricted recordings accept only the canonical unavailable marker, allowing the complete roster to be sealed. The adjudicator requires both seals and changes only the target decision while preserving original reviews. Current recording/playback restrictions block all new adjudications.

The coordinator can preview and lock the exact invented payload in the private `fixture-predictions.json` created with the fixture. The preview checks the complete prepared JSON and its digest before locking. Content decisions are engineering records, without qualified approval. The second project, `content-preparation-a957a9e3291f0d90`, retains the fixed public pack's 15 prompts, 17 pronunciation variants and 23 target occurrences. Its manifest content and task definitions start pending, with zero participants and attempts; it supports no enrollment or collection.

Withdrawal retains original reviews and the full attempt denominator, while blocking new media, substantive original answers, new adjudications and engineering admission for affected attempts. Canonical unavailable original markers remain permitted. Previously delivered or in-flight audio cannot be recalled. Media receipts mean an authorization/delivery attempt, not that someone heard the recording.

## Check and export privately

These commands are trusted directory-owner operations. Project export resolves the current active fixed fixture coordinator assignment; it does not claim a browser password login. Output files must be new and their existing parent directory must be owned `0700`. The fixture root satisfies that requirement.

```sh
python3 -m review_service verify-service work/review-service-fixture-01
python3 -m review_service export work/review-service-fixture-01 demo-review work/review-service-fixture-01/demo-export-01.json
python3 -m review_service export work/review-service-fixture-01 content-preparation-a957a9e3291f0d90 work/review-service-fixture-01/content-export-01.json
python3 -m review_service audit-export work/review-service-fixture-01 work/review-service-fixture-01/access-export-01.json
```

Project exports are replay-verified before exclusive `0600` writes. The separate audit export contains validated attribution records, without the credential registry. These are private JSON files, not encryption. Browser downloads use the browser/OS destination and may have different permissions. Journal hashes check integrity, source correspondence and replay; they do not establish authentic provenance, signatures or global chronology.

A mutation writes its audit intent before the source event and its completion receipt afterward. Those files are not one atomic transaction. If `operation_outcome_unavailable` appears, refresh or run `verify-service` before making a manual next-step decision. Recovery checks whether the operation was applied and never repeats it blindly or claims rollback. Unexpected/corrupt or unaccounted history quarantines the project. Failed creation/output can leave incomplete new files; existing files are never cleared or overwritten.

## Administer invented accounts

Run password reset in an interactive private terminal. It prompts twice without echo and refuses input if hidden entry is unavailable. Passwords must contain 16–1024 UTF-8 bytes; there is no password command argument.

```sh
python3 -m review_service reset-password work/review-service-fixture-01 fixture-reviewer-a
python3 -m review_service deactivate-assignment work/review-service-fixture-01 fixture-reviewer-a demo-review
python3 -m review_service revoke-account work/review-service-fixture-01 fixture-reviewer-a
```

Reset invalidates existing sessions. Revocation and assignment deactivation are irreversible. Each project role retains its historical holder, and each account retains its historical project role; neither a replacement holder nor reactivation is allowed. A reset cannot recover a revoked account. Create a fresh fixture root to repeat a workflow after irreversible administration. There is no HTTP account/assignment administration, reviewer-selected role parameter or HTTP audit export.

## Verification and limits

Observed checks: the first service suite passed 81 tests, the final expanded suite passed 84 with warnings treated as errors, and the unchanged workbench regression suite passed 61. Reproduce only these scoped checks from the repository root:

```sh
PYTHONPATH=research/assessment-review-service:research/assessment-workbench python3 -W error -m unittest discover -s research/assessment-review-service/tests -p 'test_*.py'
PYTHONPATH=research/assessment-workbench python3 -W error -m unittest discover -s research/assessment-workbench/tests -p 'test_*.py'
```

The real browser run exercised login/logout, one original answer, one unavailable original marker, both seals, one adjudication, prepared-file preview/lock, a public pending-content engineering record, export download, withdrawal and revocation. The remaining twenty originals and four content decisions were prepared through real authenticated HTTP, not browser interactions. Audio duration metadata reached 1.2 seconds; audible playback was not verified. See the [dated validation record](../../docs/consumer-assessment/authenticated-desktop-review-service-20261004.md) for evidence scope.

The single-threaded server binds loopback and checks exact Host/Origin, CSRF, cookies, framing and closed routes. It does not provide TLS or port isolation, and excludes a hostile OS owner or other localhost servers from its threat model. Account separation does not prove independent humans or qualified reviewers. This is a closed engineering fixture, not production security or application-domain validation. Real-data onboarding, permissions/reference licensing, qualified review and deployment require a separate authorized goal. Mobile work remains paused; the reserved sealed study is not executed.
