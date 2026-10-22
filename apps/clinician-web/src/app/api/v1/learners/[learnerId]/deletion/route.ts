import {
  getPlatformDataService,
  requireActorContext,
} from "@/lib/platform-runtime";
import { handleDeletionPost } from "@/lib/platform-api-handlers";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(
  request: Request,
  context: { params: Promise<{ learnerId: string }> },
): Promise<Response> {
  const { learnerId } = await context.params;
  return handleDeletionPost(request, learnerId, {
    requireActor: requireActorContext,
    getService: getPlatformDataService,
  });
}
