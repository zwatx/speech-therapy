import { AttemptReviewTable } from "@/components/attempt-review-table";
import { PortalHeader } from "@/components/portal-header";
import { requirePortalActor } from "@/lib/portal-page-access";
import { getPlatformDataService } from "@/lib/platform-runtime";
import Link from "next/link";
import { notFound } from "next/navigation";

export const metadata = { title: "Attempt review" };
export const dynamic = "force-dynamic";

export default async function ReviewPage({ searchParams }: {
  searchParams: Promise<{ learner?: string | string[] }>;
}) {
  const actor = await requirePortalActor();
  const { learner: learnerId } = await searchParams;
  if (learnerId !== undefined && (typeof learnerId !== "string" || !learnerId || learnerId.length > 128)) notFound();
  const attempts = await getPlatformDataService().listReviewableAttempts(actor);
  const shownAttempts = learnerId ? attempts.filter((attempt) => attempt.learnerId === learnerId) : attempts;
  const selectedName = shownAttempts[0]?.learnerDisplayLabel;
  return (
    <div className="review-page">
      <PortalHeader
        eyebrow="Evidence review"
        title="Attempt review"
        description="Review capture details shared with current consent. Recordings are not retained, and experimental scores do not generate corrections."
      />
      <section aria-labelledby="attempt-heading" className="content-section">
        <div className="section-heading-row">
          <div>
            <p className="section-kicker">Current authorization</p>
            <h2 id="attempt-heading">{learnerId ? `${selectedName ?? "Selected learner"} capture evidence` : "Recent capture evidence"}</h2>
          </div>
          <span className="live-data-notice">
            {shownAttempts.length} {shownAttempts.length === 1 ? "attempt" : "attempts"} · no media
          </span>
        </div>
        {learnerId ? <p className="review-scope">Showing this learner’s captures in the clinic’s latest 100 authorized review records. <Link href="/review">All attempts</Link></p> : null}
        {learnerId && shownAttempts.length === 0
          ? <p className="empty-state">No captures for this learner appear in the clinic’s latest 100 authorized review records.</p>
          : <AttemptReviewTable attempts={shownAttempts} />}
      </section>
    </div>
  );
}
