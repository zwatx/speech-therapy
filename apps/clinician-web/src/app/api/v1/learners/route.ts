import {
  handleLearnerCreate,
  handleLearnerList,
} from "@/lib/platform-api-handlers";
import {
  getPlatformDataService,
  requireActorContext,
} from "@/lib/platform-runtime";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const dependencies = {
  requireActor: requireActorContext,
  getService: getPlatformDataService,
};

export async function GET(): Promise<Response> {
  return handleLearnerList(dependencies);
}

export async function POST(request: Request): Promise<Response> {
  return handleLearnerCreate(request, dependencies);
}
