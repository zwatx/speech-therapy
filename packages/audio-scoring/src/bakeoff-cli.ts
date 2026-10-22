import { readFile } from "node:fs/promises";

import {
  buildAudioBakeoffCandidateResult,
  selectAudioBakeoffCandidates,
  verifyOwnedAudioAdaptation,
  type AudioBakeoffCandidateManifest,
  type AudioBakeoffCharter,
  type AudioBakeoffMeasurements,
  type AudioBakeoffRunAttestation,
  type AudioAdaptationAuthorization,
  type AudioAdaptationDatasetManifest,
  type OwnedAudioAdaptationManifest,
} from "./bakeoff.ts";
import { validateLockedEvaluationManifest } from "./evaluation.ts";
import type {
  EvaluationArtifactVersions,
  EvaluationSample,
  EvaluationThresholds,
  LockedEvaluationManifest,
} from "./types.ts";

interface BakeoffRunInput {
  readonly candidateId: string;
  readonly samples: readonly EvaluationSample[];
  readonly thresholds: EvaluationThresholds;
  readonly artifacts: EvaluationArtifactVersions;
  readonly measurements: AudioBakeoffMeasurements;
  readonly headRecipeSha256: string;
  readonly inferenceContainerSha256: string;
  readonly runAttestation: AudioBakeoffRunAttestation;
  readonly evaluatedAt: string;
}

const [command, ...args] = process.argv.slice(2);

try {
  if (command === "select" && args.length === 4) {
    const evidence = await rebuildSelection(...asFour(args));
    process.stdout.write(`${JSON.stringify(evidence, null, 2)}\n`);
  } else if (command === "adaptation" && args.length === 9) {
    const [charterPath, manifestPath, candidatesPath, runsPath, adaptationPath,
      trainingDatasetPath, calibrationDatasetPath, authorizationPath, verifiedAt] = args;
    const evidence = await rebuildSelection(
      charterPath!, manifestPath!, candidatesPath!, runsPath!,
    );
    const adaptation = await readJSON(adaptationPath!) as OwnedAudioAdaptationManifest;
    const trainingDataset = await readJSON(trainingDatasetPath!) as AudioAdaptationDatasetManifest;
    const calibrationDataset = await readJSON(calibrationDatasetPath!) as AudioAdaptationDatasetManifest;
    const authorization = await readJSON(authorizationPath!) as AudioAdaptationAuthorization;
    const parentId = evidence.selection.recommendedTeacherCandidateId;
    const parent = evidence.candidates.find((item) => item.candidateId === parentId);
    const parentResult = evidence.results.find((item) => item.candidateId === parentId);
    if (!parent || !parentResult) throw new TypeError("The selected adaptation parent is missing.");
    const verified = verifyOwnedAudioAdaptation(
      adaptation,
      parent,
      parentResult,
      evidence.selection,
      evidence.charter,
      evidence.verifiedManifest,
      trainingDataset,
      calibrationDataset,
      authorization,
      verifiedAt!,
    );
    process.stdout.write(`${JSON.stringify({
      status: "verified-research-adaptation-lineage",
      manifest: verified.manifest,
      verifiedAt: verified.verifiedAt,
      learnerFeedbackEligible: verified.learnerFeedbackEligible,
      productionEligible: verified.productionEligible,
    }, null, 2)}\n`);
  } else {
    process.stderr.write(
      "Usage:\n"
      + "  bakeoff-cli select <charter.json> <evaluation-manifest.json> "
      + "<candidates.json> <runs.json>\n"
      + "  bakeoff-cli adaptation <charter.json> <evaluation-manifest.json> "
      + "<candidates.json> <runs.json> <adaptation.json> <training-dataset.json> "
      + "<calibration-dataset.json> <authorization.json> <verified-at>\n",
    );
    process.exitCode = 2;
  }
} catch (error) {
  const message = error instanceof Error ? error.message : "Unexpected bake-off failure.";
  process.stderr.write(`Audio bake-off failed: ${message}\n`);
  process.exitCode = 1;
}

async function rebuildSelection(
  charterPath: string,
  manifestPath: string,
  candidatesPath: string,
  runsPath: string,
) {
  const [charterValue, manifestValue, candidatesValue, runsValue] = await Promise.all([
    readJSON(charterPath),
    readJSON(manifestPath),
    readJSON(candidatesPath),
    readJSON(runsPath),
  ]);
  if (!Array.isArray(candidatesValue) || !Array.isArray(runsValue)) {
    throw new TypeError("Candidates and runs must be JSON arrays.");
  }
  const charter = charterValue as AudioBakeoffCharter;
  const candidates = candidatesValue as AudioBakeoffCandidateManifest[];
  const runs = runsValue as BakeoffRunInput[];
  const verifiedManifest = validateLockedEvaluationManifest(
    manifestValue as LockedEvaluationManifest,
  );
  const runByID = new Map(runs.map((run) => [run.candidateId, run]));
  if (runByID.size !== runs.length || runs.length !== candidates.length) {
    throw new TypeError("Every candidate requires one unique run input.");
  }
  const results = candidates.map((candidate) => {
    const run = runByID.get(candidate.candidateId);
    if (!run) throw new TypeError("A candidate run input is missing.");
    if (!hasExactKeys(run, ["candidateId", "samples", "thresholds", "artifacts",
      "measurements", "headRecipeSha256", "inferenceContainerSha256", "runAttestation",
      "evaluatedAt"])) {
      throw new TypeError("A candidate run input contains unsupported fields.");
    }
    return buildAudioBakeoffCandidateResult(
      candidate,
      charter,
      run.samples,
      run.thresholds,
      verifiedManifest,
      run.artifacts,
      run.measurements,
      run.headRecipeSha256,
      run.inferenceContainerSha256,
      run.runAttestation,
      run.evaluatedAt,
    );
  });
  const selection = selectAudioBakeoffCandidates(charter, candidates, results);
  return { charter, verifiedManifest, candidates, results, selection };
}

function hasExactKeys(value: unknown, expected: readonly string[]): boolean {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return false;
  const actual = Object.keys(value).sort();
  const wanted = [...expected].sort();
  return actual.length === wanted.length
    && actual.every((key, index) => key === wanted[index]);
}

async function readJSON(path: string): Promise<unknown> {
  return JSON.parse(await readFile(path, "utf8")) as unknown;
}

function asFour(values: readonly string[]): [string, string, string, string] {
  return [values[0]!, values[1]!, values[2]!, values[3]!];
}
