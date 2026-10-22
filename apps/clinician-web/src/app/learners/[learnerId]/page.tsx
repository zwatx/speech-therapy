import { notFound } from "next/navigation";
import { PlatformDataError, type LearnerDetail, type LearnerDeviceSessionSummary } from "@speech-therapy/platform-data";
import { LearnerRecord } from "@/components/learner-record";
import { requirePortalActor } from "@/lib/portal-page-access";
import { getPlatformDataService } from "@/lib/platform-runtime";

export const dynamic = "force-dynamic";

export default async function LearnerDetailPage({
  params,
}: {
  params: Promise<{ learnerId: string }>;
}) {
  const { learnerId } = await params;
  const actor = await requirePortalActor();
  const service = getPlatformDataService();
  let learner: LearnerDetail;
  let deviceSessions: readonly LearnerDeviceSessionSummary[];
  try {
    [learner, deviceSessions] = await Promise.all([
      service.getLearner(actor, learnerId),
      service.listLearnerDeviceSessions(actor, learnerId),
    ]);
  } catch (error) {
    if (error instanceof PlatformDataError && error.code === "access-denied") {
      notFound();
    }
    throw error;
  }
  const canManage = actor.role === "owner" || actor.role === "clinician";
  return <LearnerRecord learner={learner} deviceSessions={deviceSessions}
    canManage={canManage} canDelete={actor.role === "owner"} />;
}
