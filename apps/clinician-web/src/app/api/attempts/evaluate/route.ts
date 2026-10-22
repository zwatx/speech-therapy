import { handleTrustedEvaluation } from "@/lib/trusted-evaluation";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(request: Request): Promise<Response> {
  return handleTrustedEvaluation(request, process.env.CADENCE_SCORER_SERVICE_TOKEN);
}
