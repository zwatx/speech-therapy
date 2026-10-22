import type { LearnerRowData } from "@/lib/demo-data";

interface LearnerTableProps {
  learners: readonly LearnerRowData[];
}

export function LearnerTable({ learners }: LearnerTableProps) {
  if (learners.length === 0) {
    return (
      <div className="empty-state">
        <strong>No learners match this view.</strong>
        <p>Adjust the filter or add a learner after consent is complete.</p>
      </div>
    );
  }

  const statusClasses: Record<LearnerRowData["status"], string> = {
    "Practice recorded": "status-neutral",
    "Review available": "status-review",
    "No practice recorded": "status-neutral",
  };

  return (
    <div
      aria-label="Learner practice records"
      className="table-scroll"
      role="region"
      tabIndex={0}
    >
      <table className="learner-table">
        <caption className="sr-only">
          Learner targets, recent activity, attempts, and status
        </caption>
        <thead>
          <tr>
            <th scope="col">Learner</th>
            <th scope="col">Current target</th>
            <th scope="col">Last practice</th>
            <th scope="col">Attempts</th>
            <th scope="col">Status</th>
          </tr>
        </thead>
        <tbody>
          {learners.map((learner) => (
            <tr key={learner.id}>
              <td>
                <span className="learner-identity">
                  <span aria-hidden="true">{learner.initials}</span>
                  <strong>{learner.displayName}</strong>
                </span>
              </td>
              <td>{learner.target}</td>
              <td>{learner.lastPractice}</td>
              <td>{learner.attempts}</td>
              <td>
                <span
                  className={`status-label ${statusClasses[learner.status]}`}
                >
                  {learner.status}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
