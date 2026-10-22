import {
  getPlatformDataService,
  requireActorContext,
} from "@/lib/platform-runtime";
import {
  handleDeviceSessionDelete,
  handleDeviceSessionRotate,
} from "@/lib/platform-api-handlers";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function DELETE(
  request: Request,
  context: {
    params: Promise<{ learnerId: string; sessionId: string }>;
  },
): Promise<Response> {
  const { learnerId, sessionId } = await context.params;
  return handleDeviceSessionDelete(request, learnerId, sessionId, {
    requireActor: requireActorContext,
    getService: getPlatformDataService,
  });
}

export async function POST(
  request: Request,
  context: {
    params: Promise<{ learnerId: string; sessionId: string }>;
  },
): Promise<Response> {
  const { learnerId, sessionId } = await context.params;
  return handleDeviceSessionRotate(request, learnerId, sessionId, {
    requireActor: requireActorContext,
    getService: getPlatformDataService,
  });
}
