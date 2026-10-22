import {
  getPlatformDataService,
  requireActorContext,
} from "@/lib/platform-runtime";
import {
  handleDeviceSessionList,
  handleDeviceSessionPost,
} from "@/lib/platform-api-handlers";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(
  _request: Request,
  context: { params: Promise<{ learnerId: string }> },
): Promise<Response> {
  const { learnerId } = await context.params;
  return handleDeviceSessionList(learnerId, {
    requireActor: requireActorContext,
    getService: getPlatformDataService,
  });
}

export async function POST(
  request: Request,
  context: { params: Promise<{ learnerId: string }> },
): Promise<Response> {
  const { learnerId } = await context.params;
  return handleDeviceSessionPost(request, learnerId, {
    requireActor: requireActorContext,
    getService: getPlatformDataService,
  });
}
