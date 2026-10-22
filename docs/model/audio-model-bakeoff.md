# Open-source audio bake-off and owned adaptation

Status: executable research infrastructure with synthetic fixtures only. No
open checkpoint, owned adaptation, target, calibration, or score is approved
for learner feedback or production.

## Why this exists

General ASR accuracy cannot select a pronunciation model. The bake-off in
`@speech-therapy/audio-scoring` forces every candidate through one predeclared,
speaker/household-independent test cohort, the same constrained phone lexicon,
the same scoring policy, the same thresholds, and—in the frozen-encoder stage—
the same owned lightweight head recipe.

The charter locks the exact candidate-manifest hashes and roles, at least three
primary candidates and two references, reference labels and subgroup cells,
numeric thresholds, subgroup dimensions, metric and deployment gates, legal
and label policies, the executed head recipe, a signed scorecard rubric and
authority, a signed full-run authority, calibration/deployment recipes, and the
seven model-selection weights from the Lab plan. The lock hashes the complete
evaluation-manifest envelope (version, lock time, item digest, and items), not
only its attempt rows. A
convenient public WER, relabeled attempt, different test split, new head,
candidate-specific threshold, or post-lock candidate cannot silently enter the
comparison.

## Candidate provenance

Each candidate manifest content-hashes:

- exact code repository, revision, digest, and license identifier;
- exact weight artifact, revision, digest, and license identifier;
- upstream training-data lineage and legal-review evidence;
- separate dispositions for benchmark use, commercial health inference,
  derivative training, redistribution, and mobile bundling;
- whether the interface emits phone posteriors, aligned embeddings, engineered
  features, graphemes, or transcripts;
- whether a prompt-aware decoder can guess the intended word; and
- whether the candidate can feed the constrained owned phone head.

Hash-shaped legal evidence is bookkeeping, not legal approval. Real runs must
obtain authenticated counsel/platform evidence before using any checkpoint or
dataset. All manifests remain `research-candidate-only`.

## Ranking

The CLI rebuilds every result locally from the exact samples. Ranking refuses
serialized or caller-forged result objects and requires all primary candidates
and reference baselines named in the charter. Hard gates run before the
weighted score:

- false-pass, false-reject, abstention, and conditional calibration error;
- minimum total, subgroup, subgroup-correct, and subgroup-error cells, plus the
  maximum pairwise rate gap within each subgroup dimension;
- p95 latency, average cost, peak memory, and model size;
- benchmark, commercial-health, and derivative-training rights;
- no prompt-aware decoder; and
- a phone-posterior, aligned-embedding, or engineered-feature interface that
  supports the constrained head.

Only candidates clearing every hard gate receive an adaptation rank. Whisper-
style transcript references remain useful comparisons but cannot win the
clinical path. The result and selection reports hardcode research-only authority,
`learnerFeedbackEligible: false`, and `productionEligible: false`.

The qualitative score cannot be supplied as an unsigned JSON opinion. Its
rubric, scorer key, scores, and per-dimension evidence hashes are covered by an
Ed25519 signature from the authority locked in the charter. This authenticates
the scorer and evidence claim; it does not make the evidence clinically valid.
Separately, an Ed25519 full-run attestation binds the exact charter, candidate,
evaluation/reference/sample/threshold hashes, probability outputs, latency and
cost observations, deployment measurements, artifact versions, content-hashed
calibration artifact and cohort, calibration recipe, executed head, inference
container, device protocol, and evaluation time. Local rebuilding verifies the
math; the run signature authenticates which governed runner supplied the
evidence.

## Owned adaptation

The adaptation manifest does not train a foundation model from scratch. It
supports an owned head, parameter-efficient tuning, partial fine-tuning, or a
distilled student descended from the selected teacher. Verification requires:

- the exact selected parent manifest, rebuilt result, and selection report;
- approved derivative-training disposition;
- content-verified training and calibration manifests whose speaker and
  household identities are disjoint from each other and the locked evaluation
  manifest;
- consent and deletion-lineage hashes that match both dataset manifests;
- an Ed25519-signed, time-bounded platform authorization binding those dataset,
  consent, deletion, label-policy, parent-result, and selection hashes;
- label, recipe, code, and container hashes;
- at least three distinct random seeds; and
- a new output checkpoint digest that cannot equal the parent weights.

Dataset locks must predate the signed authorization and training event;
authorization must follow the selected parent evaluation, and training must
occur within the authorization window before lineage verification.

Verification reports only structurally valid research lineage and remains
`research-adaptation-only`; it never sets adaptation, learner-feedback, or
production release authority. The signing authority is expected to issue an
authorization only after the research artifact registry has authenticated the
current consent and deletion evidence.

## CLI

Rebuild and rank a bake-off:

```bash
pnpm --filter @speech-therapy/audio-scoring bakeoff -- select \
  charter.json evaluation-manifest.json candidates.json runs.json
```

Verify a research adaptation against a rebuilt selection:

```bash
pnpm --filter @speech-therapy/audio-scoring bakeoff -- adaptation \
  charter.json evaluation-manifest.json candidates.json runs.json \
  adaptation.json training-dataset.json calibration-dataset.json \
  authorization.json 2026-07-10T20:10:00.000Z
```

Each run entry contains its candidate ID, exact evaluation samples, numeric
thresholds, artifact versions, deployment measurements, signed seven-dimension
scorecard, content-hashed calibration artifact/cohort/recipe, executed-head
digest, inference-container digest, device protocol, canonical evaluation time,
and signed full-run attestation. CLI records and their nested threshold/artifact
objects reject unknown fields. The checked-in tests use synthetic keys, hashes,
and measurements solely to prove invariants.

## What remains

Gate 1 still requires real SLP-approved targets and labels, authenticated legal
and dataset lineage, consented representative child/SSD data, an independently
locked evaluation cohort, actual frozen-encoder and engineered-feature runs,
candidate-specific calibration, device profiling, subgroup confidence
intervals, blinded clinical review, and then a separately authorized owned
adaptation job. No synthetic winner is a model recommendation.
