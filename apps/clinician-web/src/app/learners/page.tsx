import { ClinicalLearnerTable } from "@/components/clinical-learner-table";
import { CreateLearnerForm } from "@/components/create-learner-form";
import { PortalHeader } from "@/components/portal-header";
import { requirePortalActor } from "@/lib/portal-page-access";
import { getPlatformDataService } from "@/lib/platform-runtime";

export const metadata = { title: "Learners" };
export const dynamic = "force-dynamic";

export default async function LearnersPage() {
  const actor = await requirePortalActor();
  const learners = await getPlatformDataService().listLearners(actor);
  const canCreate = actor.role === "owner" || actor.role === "clinician";
  return (
    <div className="learner-directory-page">
      <PortalHeader
        eyebrow="Caseload"
        title="Learners"
        description="Keep consent, device access, and practice evidence together for each learner."
      />
      <div className="workspace-grid">
        <section aria-labelledby="learner-list-heading" className="content-section">
          <div className="section-heading-row">
            <div>
              <p className="section-kicker">Active tenant records</p>
              <h2 id="learner-list-heading">
                {learners.length} {learners.length === 1 ? "learner" : "learners"}
              </h2>
            </div>
            <p className="live-data-notice">Tenant-scoped · audited read</p>
          </div>
          <ClinicalLearnerTable learners={learners} />
        </section>
        <aside className="workspace-aside" aria-label="Create learner">
          {canCreate ? (
            <CreateLearnerForm />
          ) : (
            <div className="workspace-form read-only-card">
              <p className="section-kicker">Reviewer access</p>
              <h2>Read-only caseload</h2>
              <p className="form-intro">
                Reviewer roles can inspect consent and capture evidence but cannot
                create learner records.
              </p>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
