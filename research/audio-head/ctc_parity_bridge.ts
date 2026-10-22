// This local research bridge calls the application's scorer without changing it.
import { readFileSync } from "node:fs";
import { ctcSequenceLogProbability } from "../../packages/audio-scoring/src/ctc.ts";

const cases = JSON.parse(readFileSync(0, "utf8"));
const results = cases.map((item: {
  id: string; frames: Record<string, number>[]; phones: string[]; blankToken: string;
}) => {
  try {
    const score = ctcSequenceLogProbability(item.frames, item.phones, item.blankToken);
    if (!Number.isFinite(score) && score !== Number.NEGATIVE_INFINITY) {
      throw new Error("Unexpected nonfinite score");
    }
    return { id: item.id, logProbability: score === Number.NEGATIVE_INFINITY ? "-Infinity" : score };
  } catch (error) {
    return { id: item.id, rejected: true, error: error instanceof Error ? error.message : String(error) };
  }
});
process.stdout.write(JSON.stringify(results));
