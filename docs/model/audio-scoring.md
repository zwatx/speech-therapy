# Constrained audio-scoring foundation

Status: connected benchmark scoring path; no child-speech model or clinical
target is approved for production.

For the next implementation sequence, candidate shortlist, owned-head training
design, and data/compute assumptions, see the
[model development roadmap](model-development-roadmap.md).

`packages/audio-scoring` implements the clinical layer that an acoustic encoder
must feed. It deliberately does not accept a decoded word as pronunciation
truth. Instead, it scores only versioned phone paths supplied by a clinical
lexicon: expected productions, acceptable variants, and explicitly enumerated
error hypotheses.

## Current boundary

- The pinned phoneme-CTC adapter supplies frame-level posterior probabilities
  from server-inspected mono 16 kHz PCM for one candidate exercise.
- The scorer computes the exact CTC probability of each allowed phone path,
  without a broad word language model.
- Probability mass outside the enumerated paths remains uncertainty. Low path
  coverage forces an ambiguous result instead of manufacturing confidence.
- Temperature/bias calibration is considered valid only when its artifact hash
  matches a canonically hashed, leakage-checked manifest and records speaker-
  and household-independent fitting on the calibration split.
- The reporting harness measures false passes, false rejects, abstention,
  expected calibration error, p95 latency, average cost, and declared subgroup
  slices. A report accepts exactly the test attempts in its verified manifest;
  manifest validation rejects speaker or household split leakage and item/hash
  mismatches.

The `ball` phone paths used in unit tests are synthetic algorithm fixtures, not
an SLP-approved target, pronunciation dictionary, threshold, or clinical cue.

## Connected benchmark path

The learner upload can run the pinned checkpoint only when all of these are
true:

- `CADENCE_BENCHMARK_SCORING_ENABLED=1` is explicitly configured on the server;
- the exact current immutable consent snapshot enables both audio processing
  and research use and the learner has not declined or withdrawn assent;
- the capture passes server-side duration, level, and clipping checks;
- the exercise has a checked-in benchmark-only profile; and
- no append-only analysis already exists for that attempt.

Inference is synchronous because raw audio is deliberately never retained for
an asynchronous worker. The learner receipt remains silent and contains no
probabilities or error claim. The database stores only aggregate `pCorrect`,
`pError`, modeled-path coverage, forced ambiguous/uncalibrated flags, latency,
and immutable checkpoint/lexicon/policy provenance. Frame posteriors,
hypothesis scores, and raw audio are discarded. Inference or persistence
failure cannot manufacture feedback or turn an otherwise stored attempt into a
learner-visible error.

The 318 MB model and ephemeral runtime cache are not approved as a production
serverless architecture. The flag is off by default until provider sizing,
cold-start behavior, rate limits, legal review, research operations, and an
independent security review are complete.

Run the real synthetic-audio integration smoke test with:

```sh
pnpm --filter clinician-web smoke:benchmark
```

## Open-source versus owned model layer

The checked-in candidate registry reflects the Lab decision: begin with frozen
wav2vec 2.0/XLSR features, challenge them with WavLM Base/Base+ and a compact
Conformer-CTC path, and use Whisper/GOPT only as reference baselines. Montreal
Forced Aligner is offline corpus tooling, not learner runtime. The registry is a
candidate inventory—not a release registry—and therefore does not approve any
checkpoint, weights, training dataset, or downstream license.

Training a foundation model from scratch remains rejected for the first
product. The owned layer is the target lexicon, error hypotheses, task-specific
head, calibration artifact, thresholds, evaluation manifest, and eventually a
distilled mobile student. Those artifacts require consented child/SSD data,
expert labels, legal clearance, and prospective clinical validation.

The research bake-off and owned-adaptation lineage are now executable rather
than prose-only. They rebuild exact charter-locked candidates on one immutable
label/subgroup cohort with locked numeric thresholds and executed-head evidence,
authenticate rubric-bound scorecards, enforce hard clinical/equity/deployment/
legal gates before weighted ranking, authenticate complete run and calibration
evidence, keep transcript references from winning,
and require signed, time-bounded, speaker/household-disjoint adaptation lineage.
See [`audio-model-bakeoff.md`](audio-model-bakeoff.md). All checked-in results
are synthetic invariant tests and retain hard-false learner/production flags.

## Required before the Gate 1 scorer item closes

- A paid SLP group approves one or two target protocols, acceptable variants,
  error taxonomy, and claim boundaries.
- Exact encoder code, checkpoint, dictionary, and training-data provenance are
  recorded with hashes and commercial-use review.
- Repeat the connected adapter evaluation on consented, representative,
  independently labeled child speech; the public API already rejects
  client-supplied `pCorrect`/`pError` values.
- A locked, representative dataset provides disjoint train, calibration, and
  test speakers and households.
- Frozen-encoder and engineered-feature baselines run on the same manifest.
- Thresholds clear predeclared false-pass, false-reject, calibration,
  abstention, subgroup, latency, device, and cost gates.
