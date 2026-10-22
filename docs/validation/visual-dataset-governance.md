# Prospective visual dataset governance

Status: research infrastructure only. The checked-in fixtures are synthetic and
do not represent collected participants, clinical evidence, or permission to
train or release a model.

## Purpose

`@speech-therapy/visual-evaluation` now defines a locked
`visual-dataset-manifest-v1` for the bilabial-closure research protocol. The
contract makes the following properties machine-verifiable before annotation,
agreement analysis, training, or evaluation:

- the cue family, collection protocol, label policy, and manifest contents are
  versioned and canonically SHA-256 hashed;
- every item is bound to purpose-separated speaker, household, site, consent,
  and deletion-lineage hashes rather than direct identity;
- every item has affirmative video-processing, clinician-review, and research
  eligibility plus affirmed or not-applicable assent;
- train, calibration, test, and prospective-test splits are all present;
- speakers and households cannot cross splits, and prospective-test sites are
  held out from development splits;
- only physical iPhone/iPad hardware identifiers are accepted;
- raw media and raw landmarks cannot appear in the manifest;
- annotations must cover exactly the authorized manifest and retain their
  original blinded ratings and adjudication provenance; and
- all resulting indexes and agreement evidence remain `research-only` with
  `learnerFeedbackEligible: false`.

These checks prevent bookkeeping errors and some classes of leakage. They do
not establish that the underlying media, identities, consent ledger, or
workforce records are authentic. Those records must come from authenticated,
audited platform exports. The fixtures use deterministic fake hashes only.

## Lock transaction

The manifest lock is valid only when all three artifacts share the exact lock
time:

1. the immutable dataset manifest;
2. a deletion-lineage snapshot listing every withdrawn/deleted subject hash;
3. a consent-eligibility snapshot containing the current eligible consent
   snapshot for each included subject.

The manifest stores the hashes of both snapshots. Verification rejects a
revoked subject, missing or superseded consent snapshot, mismatched notice or
assent state, consent captured after the item, hash tampering, or a snapshot
created before/after the declared lock transaction.

Upstream identifiers must be keyed, purpose-separated pseudonyms created by an
approved identity service. Plain hashes of names, email addresses, medical
record numbers, or other enumerable identifiers are prohibited.

## Authorization before every use

A verified lock is not permanent authorization. Immediately before each
annotation export, training run, calibration run, or evaluation run, the
orchestrator must obtain new consent and deletion snapshots captured at the
same declared authorization time. `authorizeVisualDatasetUse` rejects stale
snapshots, later deletion, consent withdrawal/supersession, or a missing
subject. Annotation indexes and agreement evidence record both current snapshot
hashes and that authorization time.

No downstream training or evaluation API should accept a bare manifest or
annotation index. It must require the opaque `AuthorizedVisualDataset` boundary
created from current snapshots. This prevents a stale checked-in manifest from
silently bypassing a later privacy choice.

## Required production controls still missing

Before real participant data or any model training, the program still needs:

- counsel- and SLP-approved notices, protocol, retention schedule, and label
  policy;
- authenticated and signed platform exports rather than unsigned JSON files;
- connection of signed visual dataset exports and every real training job to
  the implemented research artifact registry;
- production adapters, scheduling, alerts, and signed-provider receipts for the
  implemented quarantine action outbox, proving cache purge, deployment
  disablement, and retraining/re-evaluation;
- encrypted media review with short-lived access, audit logs, reviewer
  authorization, and verified purge jobs;
- subgroup definitions and minimum-cell rules approved before dataset lock;
- prospective collection, double labeling, adjudication, dataset card, and
  independent privacy/security review.

Until those controls and the phase-gate evidence exist, this package is only a
fail-closed research harness. It cannot close Gate 2, start a clinical pilot, or
authorize learner-facing visual feedback.

## Executable checks

From the repository root, verify the synthetic contract fixtures with:

```bash
pnpm --filter @speech-therapy/visual-evaluation dataset verify \
  fixtures/visual-dataset-manifest.valid.json \
  fixtures/deletion-lineage-snapshot.valid.json \
  fixtures/consent-eligibility-snapshot.valid.json
```

To produce bound agreement evidence, use `dataset evidence` with the manifest,
lock-time snapshots, newly captured current snapshots, their exact canonical
UTC authorization time, and one adjudication bundle per manifest item. The
command fails if any item, consent, deletion state, split, hash, or reviewer-pair
invariant is invalid.
