# Provisional /R/ reviewer-export intake

The [reviewer-facing protocol draft](../../docs/model/r-reviewer-protocol-draft.md)
describes the proposed listening flow; it also requires qualified SLP signoff.

This is a **draft local validator**, not an annotation request or an approved
label format. A qualified SLP and study owner must first approve the listening
task, categorical definitions, timing tolerance, agreement criteria, and any
later training use. No labels have been collected or distributed here.

The [locked draft contract](experiments/speechocean-r-annotation-intake-draft-v1.json)
pins the existing 40 public, author-training clips, blinded queue, local pack
queues, and source mapping by SHA-256. The validator hashes both copies of each
selected WAV against the trusted internal manifest, reads the actual PCM frame
count, and accepts only a complete local export with one independent record for
each opaque clip ID and each of `reviewer-a` and `reviewer-b`. It does not save,
merge, or adjudicate records. A separate draft merge command below can combine
two future independent reviewer exports before this validation.
The local sample and pack generators create owner-only directories (`0700`)
and JSON/WAV artifacts (`0600`) and tighten verified existing artifacts on
rerun. Preserve those permissions if an approved reviewer workspace receives
copies later.

The export top level has exactly `schemaVersion: 1` and a `records` array. Each
record has exactly `clipId`, `reviewer`, `targetPresence`, `wordInterval`,
`rInterval`, and `qualityReason`. `targetPresence` is one of `expected`,
`altered`, `omitted`, or `indeterminate`. `qualityReason` is one of `none`,
`targetWordOmitted`, `targetSoundOmitted`, `captureNoise`, `overlap`, or
`timingIndeterminate`. Either interval may be `null`; otherwise it has only
finite numeric `startSeconds` and `endSeconds` within the verified WAV duration.
An absent interval needs a closed reason, while complete intervals require
`none`. An omitted target needs an omission reason; an omitted word has no word
interval. An omitted or indeterminate /ɹ/ cannot have a forced `rInterval`; if
both intervals exist, /ɹ/ must lie within the word. These are provisional
capture rules, not clinical scoring criteria.

Future local validation, after SLP signoff and an authorized export, would use:

```sh
research/audio-head/.venv/bin/python research/audio-head/speechocean_r_annotation_intake.py /absolute/path/to/local-export.json
```

The command prints only structural counts and research-only flags. The export
must not contain source or speaker IDs, ages, original ratings, model outputs,
names, free text, raw audio, or adjudication. The pinned internal source mapping
and WAV digests stay outside the reviewer export. Passing this validator would
establish structural and timing-range validity only, not reviewer agreement,
label quality, or eligibility for training, product feedback, or clinical use.

For a future authorized **single-reviewer** export, the
[reviewer validator](speechocean_r_annotation_reviewer_export.py) checks one
complete 40-record file before merge. It requires the selected reviewer on
every record and the exact order of that reviewer's pinned blinded pack. It
uses the same six-field and interval rules as the combined intake validator:

```sh
research/audio-head/.venv/bin/python research/audio-head/speechocean_r_annotation_reviewer_export.py reviewer-a /absolute/path/to/reviewer-a.json
```

Use `reviewer-b` for the second pack. The command reads the private local file,
verifies both pinned audio copies and pack queues, and prints only aggregate
provisional counts. It does not save, display, or approve any labels. No real
reviewer exports exist yet.

## Provisional local reviewer page

The [draft reviewer page](speechocean_r_annotation_reviewer_ui.py) is disabled
by default. It must not be used to collect real judgments until a qualified
SLP and study owner have documented the task definitions and listening rules
in the [signoff worksheet](../../docs/model/r-annotation-signoff-draft.md).
After that signoff, the **study owner** can start one assigned pack with an
explicit flag. The owner must keep the repository and private sample outside
the reviewer's filesystem access. The reviewer uses only a browser session
under a separate local OS account without access to the repository, rating
manifest, or other pack; do not give the reviewer the launcher terminal or
the owner's account. Startup rejects a sample directory that another account
can traverse. If that account separation is unavailable, this page is not
ready for real blinded review.

```sh
research/audio-head/.venv/bin/python research/audio-head/speechocean_r_annotation_reviewer_ui.py reviewer-a --enable-provisional-review
```

The reviewer opens the printed `http://127.0.0.1:<port>/` address on that same
computer. Use `reviewer-b`
only for the separately assigned second pack. Startup verifies the pinned
sample, both pack queues, all 80 pack WAV copies, and the 40-clip order before
opening the page. The server binds only to IPv4 loopback, serves the selected
pack's blinded queue fields and a hash-checked in-memory snapshot of its WAVs,
and has no endpoint for labels or other
files. The page uses native audio controls and keeps draft answers only in
browser memory. Its six-field closed responses follow the provisional
single-reviewer validator's interval and category constraints. Progress counts
valid records; export becomes available only when all 40 are valid. Export is
a browser download in pack order. Refreshing or closing the page loses draft
answers, so keep the downloaded file in the study's approved private location.
Stop the server with Ctrl-C.

Run the single-reviewer validator on the downloaded file before any later
intake. The page and structural validator cannot establish clinical judgment,
agreement, approved training use, or compliance with the listening procedure.
No real labels were collected while preparing this UI.

## Draft local merge of separate reviewer exports

If qualified SLPs and the study owner approve the protocol and two future
reviewers produce separate exports, each input should have exactly
`schemaVersion: 1` and a `records` array with all 40 opaque IDs once. The first
input contains only `reviewer-a` records and the second only `reviewer-b`
records. Each record uses the six fields and closed values above. The local
[merge command](speechocean_r_annotation_merge_draft.py) combines them without
changing either reviewer's judgments:

```sh
research/audio-head/.venv/bin/python research/audio-head/speechocean_r_annotation_merge_draft.py /absolute/path/to/reviewer-a.json /absolute/path/to/reviewer-b.json /absolute/path/to/new-combined.json
```

The output path must be new and absolute, in an existing local directory with
no symlink in its path. The command verifies the pinned schema, pack queues,
both copies of every WAV, and actual durations, checks each reviewer export
against its own pack order, then runs the complete 80-record intake validator
before writing. It publishes the combined JSON
atomically without replacing an existing file; the file is private to the
current user by default. Standard output gives only aggregate counts and
research-only flags, with no clip IDs or raw labels. A failed validation
creates no combined export. Keep the two original exports separately. This
merge does not adjudicate disagreements or approve any training or clinical
use. No real reviewer labels have been collected or processed by this draft.

## Draft descriptive agreement report

After qualified SLP signoff and a future authorized export, the local
[agreement command](speechocean_r_annotation_agreement_draft.py) can describe
the two independent records without changing them:

```sh
research/audio-head/.venv/bin/python research/audio-head/speechocean_r_annotation_agreement_draft.py /absolute/path/to/local-export.json
```

Before calculating anything, the command runs the same locked intake schema,
queue, pack-WAV hash and duration, and complete-export checks above. It prints
one JSON object to standard output and saves no labels. For both
`targetPresence` and `qualityReason`, it gives exact agreement counts and
fractions plus confusion counts with reviewer A as rows and reviewer B as
columns. For target-word and /ɹ/ intervals separately, it counts pairs with
both, one, or neither interval present. Only pairs with both intervals enter
the mean and median intersection-over-union and absolute start/end boundary
differences in seconds. Disjoint intervals have overlap zero; when none are
paired, the timing metrics are `null`. The report contains no clip IDs,
source IDs, raw audio, original corpus ratings, free text, or per-clip results.

These numbers are **descriptive pilot diagnostics**, with no acceptance
threshold. They do not adjudicate disagreements, approve labels for training,
or establish clinical or product use. Reviewer records and any later
adjudication remain separate. No real reviewer labels have been collected or
processed by this draft command.
