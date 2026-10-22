import Link from "next/link";

import type { LearnerSummary } from "@speech-therapy/platform-data";
import { practiceAccess } from "@/lib/practice-access";
import "./learner-workspace.css";

function initials(label: string): string {
  return label
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

function date(value: string | undefined): string {
  if (!value) return "No practice yet";
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeZone: "UTC",
  }).format(new Date(value));
}

export function ClinicalLearnerTable({
  learners,
  recordHref = (id) => `/learners/${encodeURIComponent(id)}`,
}: {
  learners: readonly LearnerSummary[];
  recordHref?: (id: string) => string;
}) {
  if (learners.length === 0) {
    return (
      <div className="empty-state">
        <strong>No learner records yet.</strong>
        <p>Create a minimal record, then capture consent before practice access.</p>
      </div>
    );
  }
  return (
    <div className="clinical-learner-table">
      <div
        aria-label="Tenant learner records"
        className="table-scroll"
        role="region"
        tabIndex={0}
      >
        <table className="learner-table">
        <caption className="sr-only">
          Learner consent, recent practice, attempts, and active device access
        </caption>
        <thead>
          <tr>
            <th scope="col">Learner</th>
            <th scope="col">Consent state</th>
            <th scope="col">Last practice</th>
            <th scope="col">Attempts</th>
            <th scope="col">Active devices</th>
            <th scope="col"><span className="sr-only">Open record</span></th>
          </tr>
        </thead>
        <tbody>
          {learners.map((learner) => {
            const consent = practiceAccess(learner.latestConsent);
            return (
              <tr key={learner.id}>
                <th scope="row">
                  <span className="learner-identity">
                    <span aria-hidden="true">{initials(learner.displayLabel)}</span>
                    <strong>{learner.displayLabel}</strong>
                  </span>
                </th>
                <td>
                  <span className={`status-label ${consent.className}`}>
                    {consent.label}
                  </span>
                </td>
                <td>{date(learner.lastPracticeAt)}</td>
                <td>{learner.attemptCount}</td>
                <td>{learner.activeDeviceSessionCount}</td>
                <td>
                  <Link className="row-link" href={recordHref(learner.id)} aria-label={`Open record for ${learner.displayLabel}`}>
                    Open <span aria-hidden="true">→</span>
                  </Link>
                </td>
              </tr>
            );
          })}
        </tbody>
        </table>
      </div>
      <ul className="clinical-learner-list" aria-label="Tenant learner records">
        {learners.map((learner) => {
          const consent = practiceAccess(learner.latestConsent);
          return (
            <li key={learner.id}>
              <Link className="clinical-learner-item" href={recordHref(learner.id)}>
                <span className="clinical-learner-primary">
                  <strong>{learner.displayLabel}</strong>
                  <span>Open record <span aria-hidden="true">→</span></span>
                </span>
                <span className={`status-label ${consent.className}`}>{consent.label}</span>
                <dl className="clinical-learner-facts">
                  <div><dt>Last practice</dt><dd>{date(learner.lastPracticeAt)}</dd></div>
                  <div><dt>Attempts</dt><dd>{learner.attemptCount}</dd></div>
                  <div><dt>Active devices</dt><dd>{learner.activeDeviceSessionCount}</dd></div>
                </dl>
              </Link>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
