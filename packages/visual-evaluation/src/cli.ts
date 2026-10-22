import { readFile } from "node:fs/promises";

import { evaluateVisualFeasibility } from "./evaluate.ts";
import { parseVisualFeasibilityReport } from "./parse.ts";

const paths = process.argv.slice(2);
if (paths.length === 0) {
  process.stderr.write(
    "Usage: pnpm --filter @speech-therapy/visual-evaluation evaluate <report.json> [...]\n",
  );
  process.exitCode = 2;
} else {
  const reports = await Promise.all(paths.map(async (path) =>
    parseVisualFeasibilityReport(
      JSON.parse(await readFile(path, "utf8")) as unknown,
    )));
  const evaluation = evaluateVisualFeasibility(reports);
  process.stdout.write(`${JSON.stringify(evaluation, null, 2)}\n`);
  if (evaluation.status !== "pass") process.exitCode = 1;
}
