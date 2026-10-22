import {
  targetProtocolRegistryVersion,
  targetProtocols,
} from "@speech-therapy/clinical-domain";

import { PortalHeader } from "@/components/portal-header";
import { PracticeAssignmentForm } from "@/components/practice-assignment-form";
import { requirePortalActor } from "@/lib/portal-page-access";
import { getPlatformDataService } from "@/lib/platform-runtime";
import { notFound } from "next/navigation";

export const metadata = { title: "Assignments" };

export default async function AssignmentsPage({ searchParams }: {
  searchParams: Promise<{ learner?: string | string[] }>;
}) {
  const actor = await requirePortalActor();
  const { learner: learnerId } = await searchParams;
  if (learnerId !== undefined && (typeof learnerId !== "string" || !learnerId || learnerId.length > 128)) notFound();
  const service = getPlatformDataService();
  const [learners, assignments] = await Promise.all([
    service.listLearners(actor),
    service.listPracticeAssignments(actor),
  ]);
  if (learnerId && !learners.some((learner) => learner.id === learnerId)) notFound();
  const protocols = Object.values(targetProtocols);
  const canManage = actor.role === "owner" || actor.role === "clinician";

  return (
    <div className="assignment-page">
      <PortalHeader
        eyebrow="Practice planning"
        title="Assignments"
        description={canManage
          ? "Choose a learner, confirm that beginning /b/ fits their plan, then set a bounded practice dose."
          : "Review current learner assignments and the available target protocol."}
      />
      {canManage ? (
        <section id="assignment-form" aria-label="Prepare a practice dose" className="content-section">
          <PracticeAssignmentForm key={learnerId ?? "all"} learners={learners} selectedLearnerId={learnerId} />
        </section>
      ) : null}
      <section aria-labelledby="active-assignments-heading" className="content-section">
        <div className="section-heading-row">
          <div>
            <p className="section-kicker">Current dose</p>
            <h2 id="active-assignments-heading">Latest learner assignments</h2>
          </div>
          <span className="live-data-notice">{assignments.length} latest</span>
        </div>
        {assignments.length === 0 ? (
          <div className="empty-state">
            <strong>No learner has a practice dose yet.</strong>
            <p>Record audio consent, then create a bounded silent assignment.</p>
          </div>
        ) : (
          <ul className="protocol-list assignment-list">
            {assignments.map((assignment) => (
              <li key={assignment.id}>
                <div>
                  <span className="protocol-status candidate">v{assignment.version}</span>
                  <strong>{assignment.learnerDisplayLabel}</strong>
                  <p>
                    {assignment.prompt} · {assignment.attemptTarget} repetitions · {assignment.retryLimit} {assignment.retryLimit === 1 ? "retry" : "retries"}
                  </p>
                </div>
                <code>{assignment.releasePosture}</code>
              </li>
            ))}
          </ul>
        )}
        {!canManage ? (
          <p className="read-only-note">
            Reviewer roles can inspect assignments but cannot create a version.
          </p>
        ) : null}
      </section>
      <section aria-labelledby="protocol-heading" className="content-section">
        <div className="section-heading-row">
          <div>
            <p className="section-kicker">Target registry</p>
            <h2 id="protocol-heading">Versioned protocols</h2>
          </div>
          <span className="demo-notice">{targetProtocolRegistryVersion}</span>
        </div>
        <ul className="protocol-list">
          {protocols.map((protocol) => (
            <li key={protocol.id}>
              <div>
                <span className={`protocol-status ${protocol.status}`}>
                  {protocol.status}
                </span>
                <strong>{protocol.label}</strong>
                <p>{protocol.phonemes.map((phone) => `/${phone}/`).join(" · ")}</p>
              </div>
              <code>{protocol.id}</code>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
