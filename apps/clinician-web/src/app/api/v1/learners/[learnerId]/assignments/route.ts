import {
  handlePracticeAssignmentPost,
  type PlatformApiDependencies,
} from "@/lib/platform-api-handlers";
import {
  getPlatformDataService,
  requireActorContext,
} from "@/lib/platform-runtime";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const dependencies: PlatformApiDependencies = {
  requireActor: requireActorContext,
  getService: getPlatformDataService,
};

export async function POST(
  request: Request,
  { params }: { params: Promise<{ learnerId: string }> },
): Promise<Response> {
  const { learnerId } = await params;
  return handlePracticeAssignmentPost(request, learnerId, dependencies);
}
