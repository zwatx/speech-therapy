import { handleLearnerAssignmentFetch } from "@/lib/learner-assignment-fetch";
import { getPlatformDataService } from "@/lib/platform-runtime";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(request: Request): Promise<Response> {
  return handleLearnerAssignmentFetch(request, {
    getService: getPlatformDataService,
  });
}
