# Bilabial closure prospective label policy

Status: engineering-ready research draft; SLP approval and prospective labels
are still required. Policy version: `bilabial-closure-observation-v1`.

## Scope and non-claim

This policy labels one externally observable event for `/p, b, m/`: whether the
reviewer can see both lips close during the pre-specified target interval. It
does not label diagnosis, phoneme correctness, oral pressure, voicing, nasal
airflow, hidden contact, cause, treatment response, or whether the learner has
a speech sound disorder. Audio and visual judgments remain separate.

The implementation is a research contract and agreement harness. It cannot
enable production vision, route an attempt, or generate learner feedback. The
Gate 2 item remains open until an approved protocol is used to collect
prospective labels and the resulting agreement and subgroup evidence pass
predeclared thresholds.

## Prospective review procedure

1. The study owner locks the collection protocol, target interval definition,
   inclusion criteria, subgroup plan, label policy, and evaluation thresholds
   before the first held-out item is reviewed.
2. A consent-authorized media service presents the target interval to two
   qualified SLP reviewers. The annotation JSON contains only opaque item and
   reviewer identifiers; it contains no media, name, learner identifier, free
   text, model output, or derived geometry.
3. Each reviewer is blinded to model output and the other reviewer's rating.
   Presentation order is randomized outside this record and documented in the
   dataset card.
4. The two original ratings are immutable. A third, independent qualified SLP
   adjudicates every disagreement after both original ratings are complete.
5. Agreement is calculated from the original ratings, never the adjudicated
   label. Adjudication supplies a governed reference label without erasing
   disagreement.

## Label definitions

- `closure-observed`: both external lip borders visibly meet during the locked
  target interval. Do not infer completeness inside the mouth or sound accuracy.
- `closure-not-observed`: the interval is observable and the external lip
  borders do not visibly meet. This is an observation, not a causal statement.
- `indeterminate`: the interval is visible enough to review, but timing or the
  event cannot be decided reliably. A quality reason is mandatory.
- `unobservable`: capture conditions prevent a defensible judgment. A quality
  reason is mandatory and this label must not be treated as a production error.

Allowed quality reasons are intentionally closed: `low-light`,
`face-off-center`, `head-turned`, `mouth-occluded`, `motion-blur`,
`multiple-faces`, and `target-window-unclear`. Free text is excluded to reduce
identity leakage and post-hoc taxonomy drift.

## Adjudication rules

- Agreeing ratings require no adjudication. If an agreement confirmation is
  recorded, it must retain the agreed label.
- A disagreement cannot enter an analysis set without an independent
  adjudication record.
- `unresolvable` must produce the final label `indeterminate`; uncertainty may
  not be converted into a binary label.
- Reviewer and adjudicator identities are opaque workforce identifiers. Their
  qualification and authorization records live in the controlled study system,
  not in the model dataset.
- The upstream study system must mint non-identifying opaque IDs. The bounded ID
  syntax is not a substitute for preventing names, emails, medical-record
  numbers, or other human-readable identifiers at issuance.
- Annotation and adjudication times use canonical UTC timestamps with
  milliseconds (`YYYY-MM-DDTHH:mm:ss.sssZ`) so ordering is deterministic across
  runtimes.

## Machine-enforced safeguards

`@speech-therapy/visual-evaluation` strictly parses annotations and bundles. It
rejects undeclared identity/media fields, unblinded ratings, duplicate
reviewers, missing uncertainty reasons, unadjudicated disagreements,
self-adjudication, retroactive timestamps, and incompatible resolutions. Its
agreement report includes raw agreement, Cohen's kappa (or `null` when
degenerate), unobservable/indeterminate prevalence, disagreements, resolutions,
and unresolved items.

Each Cohen's kappa report is restricted to one consistently ordered reviewer
pair. Separate reports must be produced for each reviewer pair and each
predeclared subgroup stratum; aggregating unlike pairs into one kappa value is
not permitted.

Required evidence before closing the Gate 2 label item includes SLP sign-off,
the locked prospective protocol and manifest, double labels, adjudication,
inter-rater reliability by target and predeclared subgroup, deletion lineage,
and an unsupported-claim audit. This document and green tests are not that
evidence.

Dataset locking, current-consent reauthorization, split isolation, and deletion
lineage are specified separately in `visual-dataset-governance.md`.
