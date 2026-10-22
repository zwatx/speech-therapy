import type { LearnerConsentSummary } from "@speech-therapy/platform-data";

const assentLabels = {
  affirmed: "Affirmed",
  declined: "Declined",
  withdrawn: "Withdrawn",
  "not-applicable": "Not applicable",
};

function ConsentEntry({ snapshot, current = false }: {
  snapshot: LearnerConsentSummary;
  current?: boolean;
}) {
  return (
    <li>
      <div className="ledger-marker" aria-hidden="true">{snapshot.version}</div>
      <div>
        <div className="ledger-heading">
          <strong>Consent v{snapshot.version}{current ? <span>Current</span> : null}</strong>
          <time dateTime={snapshot.capturedAt}>
            {new Intl.DateTimeFormat("en-US", {
              dateStyle: "medium", timeStyle: "short", timeZone: "UTC",
            }).format(new Date(snapshot.capturedAt))} UTC
          </time>
        </div>
        <p>Assent: <b>{assentLabels[snapshot.assentStatus]}</b> · Notice: {snapshot.noticeVersion}</p>
        <ul aria-label={`Consent ${snapshot.version} processing choices`}>
          {([
            ["Audio", snapshot.audioProcessing],
            ["Visual", snapshot.videoProcessing],
            ["Clinician review", snapshot.clinicianReview],
            ["Research", snapshot.researchUse],
          ] as const).map(([label, enabled]) => (
            <li key={label} data-enabled={enabled}>{label} · {enabled ? "On" : "Off"}</li>
          ))}
        </ul>
      </div>
    </li>
  );
}

export function ConsentHistory({ current, snapshots }: {
  current: LearnerConsentSummary | undefined;
  snapshots: readonly LearnerConsentSummary[];
}) {
  const earlier = snapshots.filter((snapshot) => snapshot.id !== current?.id);
  return (
    <div className="consent-history">
      {current ? (
        <ol className="consent-ledger" aria-label="Current consent">
          <ConsentEntry snapshot={current} current />
        </ol>
      ) : null}
      {earlier.length > 0 ? (
        <details className="consent-history-disclosure">
          <summary>Earlier consent choices <span>({earlier.length})</span></summary>
          <ol className="consent-ledger" aria-label="Earlier consent choices">
            {earlier.map((snapshot) => <ConsentEntry key={snapshot.id} snapshot={snapshot} />)}
          </ol>
        </details>
      ) : null}
    </div>
  );
}
