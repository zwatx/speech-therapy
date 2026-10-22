import { learnerRows } from "./demo-data.ts";
import type { OverviewData } from "./overview-data.ts";
import { previewLearnerRecords } from "./preview-learner-records.ts";

const recordsById = new Map(previewLearnerRecords.map((record) => [record.id, record]));

function practiceDate(value: string | undefined): string {
  return value
    ? new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" }).format(new Date(value))
    : "—";
}

// Imported only by the explicitly gated preview routes, never by the signed-in overview.
export const overviewPreviewData: OverviewData = {
  mode: "preview",
  canManageAssignments: true,
  learners: learnerRows.map((learner) => ({
    ...learner,
    target: learner.target.split(" · ")[0]!,
    targetDetail: learner.target.split(" · ")[1] ?? "Audio practice",
    phone: learner.target.match(/\/[^/]+\//)?.[0] ?? null,
    lastPractice: practiceDate(recordsById.get(learner.id)?.lastPracticeAt),
    lastPracticeDetail: practiceDate(recordsById.get(learner.id)?.lastPracticeAt),
    reviewAvailable: learner.status === "Review available",
    evidence: learner.attempts === 0
      ? "This sample learner has not started practice."
      : "This preview includes a practice summary. Individual recordings and attempt details are not included.",
  })),
};
