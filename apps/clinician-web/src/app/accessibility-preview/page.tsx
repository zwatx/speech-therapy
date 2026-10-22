import { overviewPreviewData } from "@/lib/overview-preview-data";
import { OverviewWorkspace } from "@/components/overview-workspace";
import { notFound } from "next/navigation";

import { ConsentLedgerForm } from "@/components/consent-ledger-form";
import { ConsentHistory } from "@/components/consent-history";
import { AttemptReviewTable } from "@/components/attempt-review-table";
import { CreateLearnerForm } from "@/components/create-learner-form";
import { DeviceSessionForm } from "@/components/device-session-form";
import { DeviceSessionList } from "@/components/device-session-list";
import { LearnerDataControls } from "@/components/learner-data-controls";
import { LearnerTable } from "@/components/learner-table";
import { MetricStrip } from "@/components/metric-strip";
import { PortalHeader } from "@/components/portal-header";
import { PracticeAssignmentForm } from "@/components/practice-assignment-form";
import { SafetyQueue } from "@/components/safety-queue";
import { SignalRoute } from "@/components/signal-route";
import { dashboardMetrics, learnerRows, safetyItems } from "@/lib/demo-data";

export const metadata = {
  title: "Accessibility audit fixture",
  robots: { index: false, follow: false },
};
export const dynamic = "force-dynamic";

const auditConsent = {
  id: "audit-consent-current", version: 2, noticeVersion: "cadence-practice-notice-v1",
  capturedAt: "2026-09-22T00:00:00.000Z", audioProcessing: true,
  videoProcessing: false, clinicianReview: true, researchUse: false,
  assentStatus: "affirmed" as const,
};

export default async function AccessibilityPreviewPage({ searchParams }: { searchParams: Promise<{ view?: string }> }) {
  if (process.env.NODE_ENV === "production"
    || process.env.CADENCE_ACCESSIBILITY_AUDIT_MODE !== "1") notFound();

  const { view } = await searchParams;
  if (view === "overview") return <OverviewWorkspace data={overviewPreviewData} />;
  if (view !== undefined) notFound();

  return (
    <>
      <PortalHeader
        eyebrow="Automated audit fixture"
        title="Representative clinical workspace states."
        description="Fictional content only. This route exists only in an explicit local accessibility-audit process."
      />
      <section aria-labelledby="audit-dashboard-heading" className="content-section">
        <h2 id="audit-dashboard-heading">Dashboard components</h2>
        <MetricStrip metrics={dashboardMetrics} />
        <SignalRoute />
        <LearnerTable learners={learnerRows.slice(0, 2)} />
        <SafetyQueue items={safetyItems.slice(0, 1)} />
      </section>
      <section aria-labelledby="audit-form-heading" className="content-section">
        <h2 id="audit-form-heading">Form and status components</h2>
        <ConsentHistory current={auditConsent} snapshots={[
          auditConsent,
          { ...auditConsent, id: "audit-consent-earlier", version: 1,
            capturedAt: "2026-09-20T00:00:00.000Z", clinicianReview: false },
        ]} />
        <div className="workspace-grid">
          <CreateLearnerForm />
          <DeviceSessionForm
            activeCount={1}
            eligible={false}
            learnerId="audit-learner"
          />
          <DeviceSessionList
            canManage
            learnerId="audit-learner"
            sessions={[
              {
                id: "audit-device-session-active",
                learnerId: "audit-learner",
                consentSnapshotId: "audit-consent",
                consentVersion: 2,
                createdAt: "2026-07-10T00:00:00.000Z",
                expiresAt: "2026-07-11T00:00:00.000Z",
                status: "active",
              },
              {
                id: "audit-device-session-old",
                learnerId: "audit-learner",
                consentSnapshotId: "audit-consent-old",
                consentVersion: 1,
                createdAt: "2026-07-09T00:00:00.000Z",
                expiresAt: "2026-07-10T08:00:00.000Z",
                status: "consent-invalidated",
              },
            ]}
          />
          <ConsentLedgerForm learnerId="audit-learner" current={undefined} />
          <PracticeAssignmentForm
            learners={[
              {
                id: "audit-learner",
                displayLabel: "Fictional learner",
                createdAt: "2026-07-10T00:00:00.000Z",
                attemptCount: 0,
                activeDeviceSessionCount: 0,
                latestConsent: {
                  id: "audit-consent",
                  version: 1,
                  noticeVersion: "cadence-practice-notice-v1",
                  audioProcessing: true,
                  videoProcessing: false,
                  clinicianReview: false,
                  researchUse: false,
                  assentStatus: "affirmed",
                  capturedAt: "2026-07-10T00:00:00.000Z",
                },
              },
            ]}
          />
          <LearnerDataControls
            learnerId="audit-learner"
            canExport={false}
            canDelete={false}
          />
        </div>
      </section>
      <section aria-labelledby="audit-review-heading" className="content-section">
        <h2 id="audit-review-heading">Authorized review evidence</h2>
        <AttemptReviewTable
          attempts={[
            {
              attemptId: "audit-attempt",
              learnerId: "audit-learner",
              learnerDisplayLabel: "Fictional learner with a deliberately long name",
              consentSnapshotId: "audit-consent",
              consentVersion: 2,
              assignmentId: "audit-assignment",
              exerciseId: "foundation-ball-initial-b-v1",
              protocolId: "bilabial-closure-v1",
              prompt: "ball",
              targetLabel: "Beginning /b/",
              repetitionIndex: 2,
              retryIndex: 1,
              status: "retry-capture",
              durationMilliseconds: 1250,
              reasonCodes: ["background-noise", "multiple-speakers"],
              receivedAt: "2026-07-10T00:00:00.000Z",
              benchmarkStatus: "scored-ambiguous",
            },
          ]}
        />
      </section>
    </>
  );
}
