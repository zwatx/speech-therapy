import Link from "next/link";

import { AttemptReviewTable } from "@/components/attempt-review-table";
import { PortalHeader } from "@/components/portal-header";
import { requirePortalActor } from "@/lib/portal-page-access";
import { getPlatformDataService } from "@/lib/platform-runtime";
import "@/components/safety-privacy-workspace.css";

export const metadata = { title: "Safety desk" };
export const dynamic = "force-dynamic";

export default async function SafetyPage() {
  const actor = await requirePortalActor();
  const canReview = actor.role !== "support";
  const attempts = canReview
    ? await getPlatformDataService().listReviewableAttempts(actor)
    : [];
  const retries = attempts.filter((attempt) => attempt.status === "retry-capture");
  return (
    <div className="safety-page">
      <PortalHeader
        eyebrow="Safety operations"
        title="Safety desk"
        description="Capture retries visible under current clinician-review consent. These are recording-quality checks, not pronunciation judgments."
      />
      <div className="safety-page-body">
        <section aria-labelledby="queue-heading" className="content-section safety-ledger">
          <div className="section-heading-row">
            <div>
              <p className="section-kicker">Recent evidence</p>
              <h2 id="queue-heading">Capture retries</h2>
            </div>
            {canReview ? <span className="live-data-notice">{retries.length} shown · latest 100 authorized attempts</span> : null}
          </div>
          {!canReview ? (
            <p className="empty-state">Capture evidence is available to owners, clinicians, and reviewers.</p>
          ) : retries.length > 0 ? (
            <AttemptReviewTable attempts={retries} />
          ) : (
            <p className="empty-state">No capture retries appear in the clinic&apos;s latest 100 authorized review records. This is not a complete issue history.</p>
          )}
          {canReview ? <p className="safety-review-link"><Link href="/review">All authorized attempt evidence →</Link></p> : null}
        </section>
      </div>
    </div>
  );
}
