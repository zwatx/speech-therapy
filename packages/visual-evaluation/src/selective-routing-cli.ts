import { readFile } from "node:fs/promises";

import type { VisualCueAnnotationBundle } from "./annotation-types.ts";
import {
  authorizeVisualDatasetUse,
  verifyLockedVisualDatasetManifest,
} from "./dataset-manifest.ts";
import {
  evaluateSelectiveVisionRouting,
  type ProspectiveEvaluationRunIndex,
  type ProspectiveClinicalDecisionIndex,
  type SelectiveVisionEvaluationPolicy,
  type SelectiveVisionEvaluationSample,
} from "./selective-routing.ts";

const args = process.argv.slice(2);

try {
  if (args.length !== 12) {
    process.stderr.write(
      "Usage: selective-routing-cli <manifest.json> <lock-deletion.json> "
      + "<lock-consent.json> <current-deletion.json> <current-consent.json> "
      + "<authorization-at> <annotations.json> <clinical-decisions.json> "
      + "<evaluation-run-index.json> <evaluation-policy.json> <samples.json> "
      + "<evaluated-at>\n",
    );
    process.exitCode = 2;
  } else {
    const [
      manifestPath,
      lockDeletionPath,
      lockConsentPath,
      currentDeletionPath,
      currentConsentPath,
      authorizationAt,
      annotationsPath,
      clinicalDecisionsPath,
      runIndexPath,
      policyPath,
      samplesPath,
      evaluatedAt,
    ] = args;
    const [
      manifest,
      lockDeletion,
      lockConsent,
      currentDeletion,
      currentConsent,
      annotations,
      clinicalDecisions,
      runIndex,
      policy,
      samples,
    ] = await readJSONFiles([
      manifestPath!, lockDeletionPath!, lockConsentPath!, currentDeletionPath!,
      currentConsentPath!, annotationsPath!, clinicalDecisionsPath!, runIndexPath!,
      policyPath!, samplesPath!,
    ]);
    if (!Array.isArray(annotations) || !Array.isArray(samples)) {
      throw new TypeError("Annotations and evaluation samples must be JSON arrays.");
    }
    const verified = verifyLockedVisualDatasetManifest(
      manifest,
      lockDeletion,
      lockConsent,
    );
    const authorized = authorizeVisualDatasetUse(
      verified,
      currentDeletion,
      currentConsent,
      authorizationAt,
    );
    const report = evaluateSelectiveVisionRouting(
      samples as SelectiveVisionEvaluationSample[],
      authorized,
      annotations as VisualCueAnnotationBundle[],
      clinicalDecisions as ProspectiveClinicalDecisionIndex,
      runIndex as ProspectiveEvaluationRunIndex,
      policy as SelectiveVisionEvaluationPolicy,
      evaluatedAt!,
    );
    process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
  }
} catch (error) {
  const message = error instanceof Error
    ? error.message
    : "Unexpected selective routing evaluation failure.";
  process.stderr.write(`Selective routing evaluation failed: ${message}\n`);
  process.exitCode = 1;
}

async function readJSONFiles(paths: readonly string[]): Promise<unknown[]> {
  return Promise.all(paths.map(async (path) =>
    JSON.parse(await readFile(path, "utf8")) as unknown));
}
