import Link from "next/link";

import type { ReviewAttemptSummary } from "@speech-therapy/platform-data";
import "./review-workspace.css";

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

function benchmarkLabel(attempt: ReviewAttemptSummary): string {
  if (attempt.benchmarkStatus === "scored-ambiguous") return "Ambiguous only";
  if (attempt.benchmarkStatus) return "Unavailable";
  return "Not run";
}

export function AttemptReviewTable({
  attempts,
  recordHref = (learnerId) => `/learners/${learnerId}`,
}: {
  attempts: readonly ReviewAttemptSummary[];
  recordHref?: (learnerId: string) => string;
}) {
  if (attempts.length === 0) {
    return (
      <div className="empty-state">
        <strong>No capture evidence is authorized for review.</strong>
        <p>
          Attempts appear only when they are bound to the learner&apos;s current
          consent snapshot with clinician review enabled.
        </p>
      </div>
    );
  }

  const showBenchmark = attempts.some((attempt) => attempt.benchmarkStatus);

  return (
    <div className={`attempt-review-results${showBenchmark ? "" : " without-benchmark"}`}>
      <p className="attempt-review-method">Capture checks describe recording quality only. No pronunciation score or audio recording is available.{showBenchmark ? "" : " No research benchmark was run."}</p>
      <div className="attempt-review-columns" aria-hidden="true">
        <span>Record</span><span>Assigned prompt</span><span>Capture check</span>{showBenchmark ? <span>Research benchmark</span> : null}
      </div>
      <ol className="attempt-review-list" aria-label="Authorized attempt evidence">
        {attempts.map((attempt) => (
          <li className="attempt-review-entry" key={attempt.attemptId}>
            <div className="attempt-review-identity">
              <strong>
                <Link className="text-link" href={recordHref(attempt.learnerId)}>
                  {attempt.learnerDisplayLabel}
                </Link>
              </strong>
              <time dateTime={attempt.receivedAt}>{date(attempt.receivedAt)} UTC</time>
              <span className="attempt-review-consent">Consent v{attempt.consentVersion}</span>
            </div>
            <div className="attempt-review-prompt">
              <span className="attempt-review-mobile-label">Assigned prompt</span>
              <strong>{attempt.prompt}</strong>
              <span>{attempt.targetLabel}</span>
              <small>Repetition {attempt.repetitionIndex} · retry {attempt.retryIndex}</small>
            </div>
            <div className="attempt-review-capture">
              <span className="attempt-review-mobile-label">Capture check</span>
              <strong className={attempt.status === "accepted-silent" ? "attempt-review-accepted" : "attempt-review-retry"}>
                {attempt.status === "accepted-silent" ? "Capture accepted" : "Retry requested"}
              </strong>
              <span>{(attempt.durationMilliseconds / 1000).toFixed(2)} s · {attempt.reasonCodes.length > 0 ? attempt.reasonCodes.map(reasonLabel).join(" · ") : "capture checks passed"}</span>
            </div>
            {showBenchmark ? <div className="attempt-review-benchmark">
              <span className="attempt-review-mobile-label">Research benchmark</span>
              <strong>{benchmarkLabel(attempt)}</strong>
              <span>No learner feedback</span>
            </div> : null}
          </li>
        ))}
      </ol>
    </div>
  );
}
