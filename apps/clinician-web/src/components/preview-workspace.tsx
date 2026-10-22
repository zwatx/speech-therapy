import { overviewPreviewData } from "@/lib/overview-preview-data";
import type { ReviewAttemptSummary } from "@speech-therapy/platform-data";
import { previewLearnerRecords } from "@/lib/preview-learner-records";
import type { PreviewView } from "@/lib/preview-navigation";
import { AttemptReviewTable } from "./attempt-review-table";
import { ClinicalLearnerTable } from "./clinical-learner-table";
import { OverviewWorkspace } from "./overview-workspace";
import { PortalHeader } from "./portal-header";
import { PortalLink } from "./portal-link";
import { PreviewAssignmentForm } from "./preview-assignment-form";
import "./safety-privacy-workspace.css";

const headings = {
  learners: ["Learners", "A place for consent, device access, and practice history."],
  assignments: ["Assignments", "Confirm that beginning /b/ fits the learner’s plan, then set a bounded practice dose."],
  review: ["Attempt review", "Capture details for clinician review. Recordings are not retained."],
  safety: ["Safety desk", "Capture retries are recording-quality checks, not pronunciation judgments."],
  privacy: ["Privacy and consent", "Separate choices for practice, clinician review, and research."],
} as const;

function currentReviewIdentity(learnerId: string) {
  const learner = previewLearnerRecords.find((record) => record.id === learnerId);
  const consent = learner?.latestConsent;
  if (!learner || !consent?.audioProcessing || !consent.clinicianReview) {
    throw new Error("Preview review evidence requires current clinician-review consent");
  }
  return { learnerId, learnerDisplayLabel: learner.displayLabel,
    consentSnapshotId: consent.id, consentVersion: consent.version };
}

const previewAttempts: readonly ReviewAttemptSummary[] = [
  { attemptId: "demo-learner-01-example-attempt", ...currentReviewIdentity("demo-learner-01"), assignmentId: "demo-learner-01-example-assignment", exerciseId: "foundation-ball-initial-b-v1", protocolId: "bilabial-closure-v1", prompt: "ball", targetLabel: "Beginning /b/", repetitionIndex: 1, retryIndex: 0, status: "accepted-silent", durationMilliseconds: 1420, reasonCodes: [], receivedAt: "2026-09-21T14:30:00.000Z" },
  { attemptId: "demo-learner-02-example-attempt", ...currentReviewIdentity("demo-learner-02"), assignmentId: "demo-learner-02-example-assignment", exerciseId: "foundation-ball-initial-b-v1", protocolId: "bilabial-closure-v1", prompt: "ball", targetLabel: "Beginning /b/", repetitionIndex: 2, retryIndex: 1, status: "retry-capture", durationMilliseconds: 1250, reasonCodes: ["background-noise"], receivedAt: "2026-09-21T14:18:00.000Z" },
];

export function PreviewWorkspace({ view, learnerId }: { view: PreviewView; learnerId?: string }) {
  if (view === "overview") return <OverviewWorkspace data={overviewPreviewData} />;
  const [title, description] = headings[view];
  const selectedLearner = learnerId ? previewLearnerRecords.find((record) => record.id === learnerId) : undefined;
  const shownAttempts = learnerId ? previewAttempts.filter((attempt) => attempt.learnerId === learnerId) : previewAttempts;
  return (
    <div className={`preview-workspace${view === "assignments" ? " assignment-page" : view === "learners" ? " learner-directory-page" : view === "review" ? " review-page" : view === "safety" ? " safety-page" : view === "privacy" ? " privacy-page" : ""}`}>
      <PortalHeader eyebrow={view === "assignments" ? "Practice planning" : view === "learners" ? "Caseload" : view === "review" ? "Evidence review" : "Workspace"} title={title} description={description} />
      <p className="preview-disclosure"><strong>Demo workspace</strong> Fictional records. Changes are not saved.</p>
      {view === "learners" ? (
        <section className="content-section" aria-labelledby="preview-learners">
          <div className="section-heading-row"><h2 id="preview-learners">{previewLearnerRecords.length} learners</h2><PortalLink href="/">Open practice workspace →</PortalLink></div>
          <ClinicalLearnerTable learners={previewLearnerRecords}
            recordHref={(id) => `/accessibility-preview/learners?learner=${encodeURIComponent(id)}`} />
          <p className="preview-footnote">These target examples illustrate the interface. The current assignable exercise is “ball,” beginning /b/.</p>
        </section>
      ) : null}
      {view === "assignments" ? (
        <div id="assignment-form" className="preview-assignment-layout">
          <PreviewAssignmentForm key={learnerId ?? "all"} selectedLearnerId={learnerId} />
        </div>
      ) : null}
      {view === "review" ? (
        <section className="content-section" aria-labelledby="preview-review">
          <div className="section-heading-row"><h2 id="preview-review">{selectedLearner ? `${selectedLearner.displayLabel}’s capture evidence` : "Example capture evidence"}</h2><span className="demo-notice">{shownAttempts.length} {shownAttempts.length === 1 ? "attempt" : "attempts"} · no media</span></div>
          {selectedLearner ? <p className="review-scope">Showing this learner’s example captures. <PortalLink href="/review">All attempts</PortalLink></p> : null}
          {shownAttempts.length ? <AttemptReviewTable attempts={shownAttempts}
            recordHref={(id) => `/accessibility-preview/learners?learner=${encodeURIComponent(id)}`} /> : <p className="empty-state">No example captures for this learner.</p>}
        </section>
      ) : null}
      {view === "safety" ? (
        <div className="safety-page-body">
          <section className="content-section safety-ledger" aria-labelledby="preview-safety">
            <div className="section-heading-row"><div><p className="section-kicker">Example evidence</p><h2 id="preview-safety">Capture retry</h2></div><span className="demo-notice">Fictional record</span></div>
            <AttemptReviewTable attempts={previewAttempts.filter((attempt) => attempt.status === "retry-capture")}
              recordHref={(id) => `/accessibility-preview/learners?learner=${encodeURIComponent(id)}`} />
          </section>
        </div>
      ) : null}
      {view === "privacy" ? (
        <div className="privacy-page-body">
        <section className="content-section privacy-ledger" aria-labelledby="preview-privacy">
          <div className="section-heading-row"><div><p className="section-kicker">Data posture</p><h2 id="preview-privacy">Current foundation</h2></div><span className="demo-notice">Illustrative records</span></div>
          <dl className="privacy-list">
            <div><dt>Practice processing</dt><dd><strong>Audio only</strong><p>Requires current consent for each assignment. Visual processing is unavailable.</p></dd></div>
            <div><dt>Clinician review</dt><dd><strong>Separate choice</strong><p>Derived capture details only. Recordings are not retained.</p></dd></div>
            <div><dt>Research contribution</dt><dd><strong>Off by default</strong><p>Research permission is separate from practice consent. No model feedback is enabled.</p></dd></div>
            <div><dt>Consent changes</dt><dd><strong>Previous access ends</strong><p>Create a new assignment and device link before the learner resumes.</p></dd></div>
          </dl>
        </section>
        <aside className="privacy-aside" aria-labelledby="preview-privacy-record-heading">
          <p className="section-kicker">Consent records</p>
          <h2 id="preview-privacy-record-heading">Choices live with each learner.</h2>
          <p>Open a learner record to review the current choice and its history.</p>
          <PortalLink href="/accessibility-preview/learners">Browse example learners</PortalLink>
        </aside>
        </div>
      ) : null}
    </div>
  );
}
