import { handleLearnerGet } from "@/lib/platform-api-handlers";
import {
  getPlatformDataService,
  requireActorContext,
} from "@/lib/platform-runtime";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(
  _request: Request,
  context: { params: Promise<{ learnerId: string }> },
): Promise<Response> {
  const { learnerId } = await context.params;
  return handleLearnerGet(learnerId, {
    requireActor: requireActorContext,
    getService: getPlatformDataService,
  });
}
