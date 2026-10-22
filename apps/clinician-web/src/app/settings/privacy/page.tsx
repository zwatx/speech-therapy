import { PortalHeader } from "@/components/portal-header";
import { PortalLink } from "@/components/portal-link";
import { requirePortalActor } from "@/lib/portal-page-access";
import "@/components/safety-privacy-workspace.css";

export const metadata = { title: "Privacy controls" };

const controls = [
  ["Practice processing", "Audio consent required", "Audio processing only; visual processing is unavailable"],
  ["Clinician review", "Separate choice", "Derived capture details only; recordings are not retained"],
  ["Research contribution", "Off by default", "Never inferred from product consent"],
  ["Raw video retention", "Not retained", "Optional developer-only camera framing stays on the device; frames are not saved or uploaded"],
  ["Data export", "Subject-scoped", "Includes retained consent and research-artifact impact evidence without provider secrets"],
] as const;

export default async function PrivacyPage() {
  await requirePortalActor();
  return (
    <div className="privacy-page">
      <PortalHeader
        eyebrow="Privacy and consent"
        title="Privacy and consent"
        description="Manage practice, review, and research choices separately. Changing consent ends access tied to the previous choice and preserves its history."
      />
      <div className="privacy-page-body">
      <section aria-labelledby="privacy-heading" className="content-section privacy-ledger">
        <div className="section-heading-row">
          <div>
            <p className="section-kicker">Data posture</p>
            <h2 id="privacy-heading">Foundation policy</h2>
          </div>
          <span className="live-data-notice">Versioned persistence connected</span>
        </div>
        <dl className="privacy-list">
          {controls.map(([term, status, detail]) => (
            <div key={term}>
              <dt>{term}</dt>
              <dd>
                <strong>{status}</strong>
                <p>{detail}</p>
              </dd>
            </div>
          ))}
        </dl>
      </section>
      <aside className="privacy-aside" aria-labelledby="privacy-record-heading">
        <p className="section-kicker">Consent records</p>
        <h2 id="privacy-record-heading">Choices live with each learner.</h2>
        <p>Open a learner record to review the current choice and its history.</p>
        <PortalLink href="/learners">Browse learners</PortalLink>
      </aside>
      </div>
    </div>
  );
}
