import { handleLearnerAttemptUpload } from "@/lib/learner-attempt-upload";
import { getEnabledBenchmarkAttemptScorer } from "@/lib/benchmark-runtime";
import { getPlatformDataService } from "@/lib/platform-runtime";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(request: Request): Promise<Response> {
  return handleLearnerAttemptUpload(request, {
    getService: getPlatformDataService,
    getBenchmarkScorer: getEnabledBenchmarkAttemptScorer,
    reportBenchmarkError: (kind) => {
      console.error(`Benchmark attempt analysis ${kind}.`);
    },
  });
}
