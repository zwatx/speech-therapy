import {
  getPlatformDataService,
  requireActorContext,
} from "@/lib/platform-runtime";
import { handleConsentPost } from "@/lib/platform-api-handlers";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(
  request: Request,
  context: { params: Promise<{ learnerId: string }> },
): Promise<Response> {
  const { learnerId } = await context.params;
  return handleConsentPost(request, learnerId, {
    requireActor: requireActorContext,
    getService: getPlatformDataService,
  });
}
