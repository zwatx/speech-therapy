# Public content review preparation

This isolated desktop tool turns the existing pending pack into a readable review
packet and a strict declaration worksheet. It preserves 15 prompts, 13 normalized
source words, 17 pronunciation variants, 23 total target occurrences and 18
selected-position occurrences. The two middle N occurrences in banana remain
unresolved. Dictionary indexes are zero-based metadata, not observations of speech.

The fixed input is `docs/consumer-assessment/proposed-engineering-pack.json`, with
SHA-256 `a957a9e3291f0d90b275d40cd914890836ee7e6fc4fd361f7589cd1444587ef3`.
Any byte change fails before interpretation. Declared upstream source paths are
never opened. No mobile files, recordings, participants or models are used.

Run from the repository root with Python 3 and the existing workbench on the import
path. There are no new dependencies. Substitute absolute paths belonging to you:

```sh
PYTHONPATH=research/content-review-preparation:research/assessment-workbench \
  python3 -m content_review build /absolute/private-parent/new-packet
PYTHONPATH=research/content-review-preparation:research/assessment-workbench \
  python3 -m content_review check /absolute/private-parent/new-packet/packet.json \
  /absolute/private-parent/new-packet/declarations.json
PYTHONPATH=research/content-review-preparation:research/assessment-workbench \
  python3 -m content_review inspect-export /absolute/private-parent/preparation-export.json \
  /absolute/private-parent/prepared-history.json
```

`build` exclusively creates a new directory (0700) and five files (0600):
`packet.json`, `declarations.json`, `readiness.json`, `validation-draft.json` and
`review-packet.html`. Open the HTML locally in a desktop browser. Existing outputs
are never overwritten. An interrupted write can leave a partial directory; use a
new directory for another build and inspect any partial output locally.

`check` and `inspect-export` require absolute paths, a current-user-owned 0700
parent, and current-user-owned 0600 regular files with one hard link. Symlinks
anywhere in the path, pipes, directories and files over 8 MiB are refused. Input
JSON rejects duplicate keys, nonfinite or oversized numbers and invalid Unicode.
Command errors contain fixed codes; console summaries omit supplied notes and
reference declarations. There is no media-file operation or external URL fetching.

In `declarations.json`, pending values are `null`. Fill each required field with a
nonempty description (at most 1,000 characters), and each variant's occurrence rule
for **every** target index. Notes allow 2,000 characters. Decisions are `pending`,
`needs_revision` or `engineering_prepared`; `mode` is `preparation` or
`invented_exercise`. Identities, hashes, index-selection flags, requirements and
false claim limits must remain exact. Duplicate, missing, contradictory or foreign
records fail; partially filled valid records report what remains missing.

All fields and rules plus `engineering_prepared` establish declaration completeness
only. The statuses are `pending_declarations`,
`complete_unverified_preparation_declarations` and
`complete_invented_declaration_exercise`. Even a complete worksheet does not verify
reference bytes, rights, identity, qualifications, cue safety or clinical validity.
A description of denied rights or unavailable scope can be structurally complete;
it provides no permission to use the reference. All approval, reference verification,
rights verification and learner/clinical/production eligibility flags stay false.
The static HTML always shows the original pending pack, not the mutable worksheet.
Rerun `check` after editing; the initially generated readiness file is a snapshot.

`inspect-export` accepts only the exact preparation manifest, zero people and
attempts, and content-review history. It checks both initial and aggregate manifests,
then replays the frozen workbench export and recomputes reports. It saves engineering
decisions, account labels and declared references separately; it never promotes
them to worksheet completion or qualified approval. Replay proves consistency,
not authentication or the existence of distinct qualified people. The live service's
sign-in controls are a separate mechanism, and account labels remain invented.

This packet is an addendum to the existing controlled workflow:

- `docs/model/slp-handoff.md`
- `docs/consumer-assessment/proposed-engineering-pack.md`
- `docs/consumer-assessment/annotation-data-preparation.md`

`validation-draft.json` lists prospective evidence requirements: independent task
and reference decisions, every attempt and terminal outcome, joint participant /
household / word linkage, possible split infeasibility, repeat versus retry ancestry,
conditions, clustered precision, rare strata, abstention and false corrections.
Sample size, thresholds, actual permissions, identity, references and retention are
pending. It is not a finalized collection protocol and borrows no frozen /r/ criteria.

Focused verification:

```sh
PYTHONPATH=research/content-review-preparation:research/assessment-workbench \
  python3 -W error -m unittest discover -s research/content-review-preparation/tests
```

No real media, collection, clinical cues, professional signoff, mobile execution or
product deployment is provided by this tool. The prior workbench and authenticated
fixture service remain unchanged.

The October 4 delivery passes 34 focused checks with warnings treated as errors,
plus the unchanged 61 workbench and 84 review-service regression checks. An actual
signed-in coordinator preparation export replays at revision 1 with one pending
record, zero people and zero attempts. Complete/incomplete invented declaration
exercises keep all claim limits false. Actual desktop views at 1024 and 1440 pixels
retain all occurrence markers without page overflow; keyboard focus is visible.
Independent Astra source review and Opus 5.5 screenshot review clear the delivery.
No screen-reader, print, mobile, real-reference or clinical verification is claimed.
