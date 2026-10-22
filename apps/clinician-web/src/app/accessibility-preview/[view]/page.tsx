import { notFound } from "next/navigation";
import { PreviewWorkspace } from "@/components/preview-workspace";
import { isPreviewView } from "@/lib/preview-navigation";
import { previewLearnerRecords } from "@/lib/preview-learner-records";
import { LearnerRecord } from "@/components/learner-record";

export const metadata = {
  title: "Workspace preview",
  robots: { index: false, follow: false },
};
export const dynamic = "force-dynamic";

export default async function WorkspacePreviewPage({ params, searchParams }: {
  params: Promise<{ view: string }>;
  searchParams: Promise<{ learner?: string | string[] }>;
}) {
  if (process.env.NODE_ENV === "production"
    || process.env.CADENCE_ACCESSIBILITY_AUDIT_MODE !== "1") notFound();
  const { view } = await params;
  if (!isPreviewView(view)) notFound();
  const { learner: learnerId } = await searchParams;
  if (learnerId !== undefined) {
    if ((view !== "learners" && view !== "review" && view !== "assignments") || typeof learnerId !== "string") notFound();
    const learner = previewLearnerRecords.find((record) => record.id === learnerId);
    if (!learner) notFound();
    if (view === "review" || view === "assignments") return <PreviewWorkspace view={view} learnerId={learnerId} />;
    return <div className="learner-record-preview">
      <p className="preview-disclosure"><strong>Read-only demo record</strong> Fictional data. Changes are unavailable in this preview.</p>
      <LearnerRecord learner={learner} deviceSessions={[]} canManage={false} canDelete={false} preview />
    </div>;
  }
  return <PreviewWorkspace view={view} />;
}
