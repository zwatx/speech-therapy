import type { LearnerDetail, LearnerDeviceSessionSummary } from "@speech-therapy/platform-data";
import { practiceAccess } from "@/lib/practice-access";
import { ConsentHistory } from "./consent-history";
import { ConsentLedgerForm } from "./consent-ledger-form";
import { DeviceSessionForm } from "./device-session-form";
import { DeviceSessionList } from "./device-session-list";
import { LearnerDataControls } from "./learner-data-controls";
import { PortalHeader } from "./portal-header";
import { PortalLink } from "./portal-link";
import "./learner-workspace.css";

function date(value: string): string {
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "UTC",
  }).format(new Date(value));
}

function reasonLabel(value: string): string {
  return value.replaceAll("-", " ");
}

export function LearnerRecord({ learner, deviceSessions, canManage, canDelete, preview = false }: {
  learner: LearnerDetail;
  deviceSessions: readonly LearnerDeviceSessionSummary[];
  canManage: boolean;
  canDelete: boolean;
  preview?: boolean;
}) {
  const consent = learner.latestConsent;
  const access = practiceAccess(consent);
  const showBenchmark = learner.recentAttempts.some((attempt) => attempt.benchmarkStatus);

  return (
    <div className={`learner-record-page${preview ? " learner-record-page-preview" : ""}`}>
      <PortalHeader
        eyebrow="Learner record"
        title={learner.displayLabel}
        description={preview
          ? "Review consent choices and capture details for this learner."
          : "Manage practice permissions, connect a device, and review capture details for this learner."}
        action={
          <PortalLink className="secondary-action" href="/learners">
            ← All learners
          </PortalLink>
        }
      />

      <dl className="record-status-strip" aria-label="Learner record status">
        <div>
          <dt>Practice access</dt>
          <dd className={access.className}>{access.label}</dd>
        </div>
        <div>
          <dt>Consent version</dt>
          <dd>{consent ? `v${consent.version}` : "Missing"}</dd>
        </div>
        <div>
          <dt>Recorded attempts</dt>
          <dd>{learner.attemptCount}</dd>
        </div>
        <div>
          <dt>Active devices</dt>
          <dd>{learner.activeDeviceSessionCount}</dd>
        </div>
      </dl>

      <div className="learner-workspace-grid">
        <div className="learner-workspace-main">
          <section aria-labelledby="consent-ledger-heading" className="content-section">
            <div className="section-heading-row">
              <div>
                <p className="section-kicker">Practice permissions</p>
                <h2 id="consent-ledger-heading">Consent choices</h2>
              </div>
              <span className="live-data-notice">
                {learner.consentSnapshots.length} {learner.consentSnapshots.length === 1 ? "recorded choice" : "recorded choices"}
              </span>
            </div>

            {learner.consentSnapshots.length === 0 ? (
              <div className="empty-state consent-empty">
                <strong>Practice is blocked until consent is recorded.</strong>
                <p>Record audio consent and assent before creating a device link code.</p>
              </div>
            ) : (
              <ConsentHistory current={consent} snapshots={learner.consentSnapshots} />
            )}

            {canManage ? (
              <ConsentLedgerForm current={consent} learnerId={learner.id} />
            ) : !preview ? (
              <p className="read-only-note">
                You can review consent choices. An owner or clinician can save a new choice.
              </p>
            ) : null}
          </section>

          <section aria-labelledby="attempts-heading" className="content-section">
            <div className="section-heading-row">
              <div>
                <p className="section-kicker">Practice evidence</p>
                <h2 id="attempts-heading">Recent captures</h2>
              </div>
              <span className="live-data-notice">No media retained</span>
            </div>
            {learner.recentAttempts.length === 0 ? (
              <div className="empty-state">
                <strong>
                  {learner.attemptCount > 0
                    ? "Earlier capture detail is not authorized under the current consent snapshot."
                    : "No practice attempts yet."}
                </strong>
                <p>
                  {learner.attemptCount > 0
                    ? "Operational counts remain visible, but attempt evidence must match the exact current snapshot with clinician review enabled."
                    : "Quality and routing evidence will appear after device practice."}
                </p>
              </div>
            ) : (
              <>
                <p className="recent-capture-method">
                  Capture checks describe recording quality only. No pronunciation score or audio recording is available.
                </p>
                <div className={`recent-capture-columns${showBenchmark ? "" : " without-benchmark"}`} aria-hidden="true">
                  <span>Received</span><span>Assigned prompt</span><span>Capture check</span>{showBenchmark ? <span>Research benchmark</span> : null}
                </div>
                <ol className="recent-capture-list" aria-label="Recent learner capture evidence">
                  {learner.recentAttempts.map((attempt) => (
                    <li className={`recent-capture-entry${showBenchmark ? "" : " without-benchmark"}`} key={attempt.attemptId}>
                      <div className="recent-capture-received">
                        <span className="recent-capture-mobile-label">Received</span>
                        <time dateTime={attempt.receivedAt}>{date(attempt.receivedAt)} UTC</time>
                      </div>
                      <div className="recent-capture-prompt">
                        <span className="recent-capture-mobile-label">Assigned prompt</span>
                        <strong>{attempt.prompt ?? "Prompt unavailable"}</strong>
                        <span>{attempt.targetLabel ?? "Target unavailable"}</span>
                      </div>
                      <div className="recent-capture-check">
                        <span className="recent-capture-mobile-label">Capture check</span>
                        <strong className={attempt.status === "accepted-silent" ? "status-on-track" : "status-review"}>
                          {attempt.status === "accepted-silent" ? "Capture accepted" : "Retry requested"}
                        </strong>
                        <span>
                          {(attempt.durationMilliseconds / 1000).toFixed(2)} s
                          {attempt.reasonCodes.length > 0
                            ? ` · ${attempt.reasonCodes.map(reasonLabel).join(" · ")}`
                            : " · capture checks passed"}
                        </span>
                      </div>
                      {showBenchmark ? <div className="recent-capture-benchmark">
                        <span className="recent-capture-mobile-label">Research benchmark</span>
                        <span>{attempt.benchmarkStatus
                          ? attempt.benchmarkStatus === "scored-ambiguous" ? "Ambiguous only" : "Unavailable"
                          : "Not run"}</span>
                      </div> : null}
                    </li>
                  ))}
                </ol>
              </>
            )}
          </section>
          {preview && deviceSessions.length > 0 ? (
            <section aria-labelledby="preview-device-history-heading" className="content-section">
              <h2 id="preview-device-history-heading">Device access history</h2>
              <DeviceSessionList canManage={false} learnerId={learner.id} sessions={deviceSessions} />
            </section>
          ) : null}
        </div>

        {!preview ? <aside className="learner-workspace-aside">
          <section aria-labelledby="device-access-heading" className="record-panel">
            <p className="section-kicker">Learner device</p>
            <h2 id="device-access-heading">Connect a device</h2>
            {canManage ? (
              <DeviceSessionForm
                activeCount={deviceSessions.filter(
                  (session) => session.status === "active",
                ).length}
                eligible={access.eligible}
                learnerId={learner.id}
              />
            ) : (
              <p className="read-only-note">Reviewer roles cannot issue device access.</p>
            )}
            <DeviceSessionList
              canManage={canManage}
              learnerId={learner.id}
              sessions={deviceSessions}
            />
          </section>

          <section aria-labelledby="data-controls-heading" className="record-panel data-panel">
            <p className="section-kicker">Learner data</p>
            <h2 id="data-controls-heading">Export or delete</h2>
            <LearnerDataControls
              canExport={canManage}
              canDelete={canDelete}
              learnerId={learner.id}
            />
          </section>
        </aside> : null}
      </div>
    </div>
  );
}
