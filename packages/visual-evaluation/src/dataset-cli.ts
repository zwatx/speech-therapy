import { readFile } from "node:fs/promises";

import type { VisualCueAnnotationBundle } from "./annotation-types.ts";
import {
  authorizeVisualDatasetUse,
  buildVisualDatasetAgreementEvidence,
  verifyLockedVisualDatasetManifest,
} from "./dataset-manifest.ts";

const [command, ...args] = process.argv.slice(2);

try {
  if (command === "verify" && args.length === 3) {
    const [manifest, deletionLedger, consentLedger] = await readJSONFiles(args);
    const verified = verifyLockedVisualDatasetManifest(
      manifest,
      deletionLedger,
      consentLedger,
    );
    process.stdout.write(`${JSON.stringify({
      status: "verified",
      manifestSha256: verified.sha256,
      itemCount: verified.manifest.items.length,
      lockedAt: verified.manifest.lockedAt,
      releasePosture: verified.manifest.releasePosture,
      learnerFeedbackEligible: verified.manifest.learnerFeedbackEligible,
    }, null, 2)}\n`);
  } else if (command === "evidence" && args.length >= 7) {
    const [
      manifestPath,
      lockDeletionPath,
      lockConsentPath,
      currentDeletionPath,
      currentConsentPath,
      authorizationAt,
      ...bundlePaths
    ] = args;
    const [
      manifest,
      lockDeletion,
      lockConsent,
      currentDeletion,
      currentConsent,
      ...bundles
    ] = await readJSONFiles([
      manifestPath!,
      lockDeletionPath!,
      lockConsentPath!,
      currentDeletionPath!,
      currentConsentPath!,
      ...bundlePaths,
    ]);
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
    const bundleValues = bundles.flatMap((value) =>
      Array.isArray(value) ? value : [value]);
    const evidence = buildVisualDatasetAgreementEvidence(
      authorized,
      bundleValues as VisualCueAnnotationBundle[],
    );
    process.stdout.write(`${JSON.stringify(evidence, null, 2)}\n`);
  } else {
    process.stderr.write(
      "Usage:\n"
      + "  dataset-cli verify <manifest.json> <lock-deletion.json> <lock-consent.json>\n"
      + "  dataset-cli evidence <manifest.json> <lock-deletion.json> <lock-consent.json> "
      + "<current-deletion.json> <current-consent.json> <authorization-at> <bundle.json> [...]\n",
    );
    process.exitCode = 2;
  }
} catch (error) {
  const message = error instanceof Error
    ? error.message
    : "Unexpected dataset validation failure.";
  process.stderr.write(`Dataset validation failed: ${message}\n`);
  process.exitCode = 1;
}

async function readJSONFiles(paths: readonly string[]): Promise<unknown[]> {
  return Promise.all(paths.map(async (path) =>
    JSON.parse(await readFile(path, "utf8")) as unknown));
}
