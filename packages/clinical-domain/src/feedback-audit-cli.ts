import { readFile } from "node:fs/promises";

import {
  auditUnsupportedFeedbackClaims,
  type FeedbackAuditSample,
  type FeedbackReleaseCandidate,
  type FeedbackTemplateCatalog,
} from "./feedback.ts";
import type { TargetProtocolRegistry } from "./types.ts";

const [catalogPath, candidatePath, registryPath, samplesPath, auditedAt] = process.argv.slice(2);

try {
  if (!catalogPath || !candidatePath || !registryPath || !samplesPath || !auditedAt
    || process.argv.slice(2).length !== 5) {
    process.stderr.write(
      "Usage: feedback-audit-cli <catalog.json> <release-candidate.json> "
      + "<protocol-registry.json> <release-samples.json> <audited-at>\n",
    );
    process.exitCode = 2;
  } else {
    const [catalog, candidate, registry, samples] = await Promise.all([
      readJSON(catalogPath),
      readJSON(candidatePath),
      readJSON(registryPath),
      readJSON(samplesPath),
    ]);
    if (!Array.isArray(samples)) {
      throw new TypeError("Feedback release samples must be a JSON array.");
    }
    const report = auditUnsupportedFeedbackClaims(
      catalog as FeedbackTemplateCatalog,
      candidate as FeedbackReleaseCandidate,
      registry as TargetProtocolRegistry,
      samples as FeedbackAuditSample[],
      auditedAt,
    );
    process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
    if (!report.zeroDetectedPolicyViolations) process.exitCode = 3;
  }
} catch (error) {
  const message = error instanceof Error
    ? error.message
    : "Unexpected feedback audit failure.";
  process.stderr.write(`Feedback audit failed: ${message}\n`);
  process.exitCode = 1;
}

async function readJSON(path: string): Promise<unknown> {
  return JSON.parse(await readFile(path, "utf8")) as unknown;
}
