import type {
  ActorContext,
  LearnerSummary,
  PlatformDataService,
  PracticeAssignmentSummary,
  ReviewAttemptSummary,
} from "@speech-therapy/platform-data";

export interface OverviewLearner {
  readonly id: string;
  readonly initials: string;
  readonly displayName: string;
  readonly target: string;
  readonly targetDetail: string;
  readonly phone: string | null;
  readonly lastPractice: string;
  readonly lastPracticeDetail: string;
  readonly attempts: number;
  readonly reviewAvailable: boolean;
  readonly status: string;
  readonly evidence: string;
}

export interface OverviewData {
  readonly mode: "live" | "preview";
  readonly canManageAssignments: boolean;
  readonly learners: readonly OverviewLearner[];
}

type OverviewService = Pick<PlatformDataService,
  "listLearners" | "listPracticeAssignments" | "listReviewableAttempts">;

export async function loadOverviewData(actor: ActorContext, service: OverviewService): Promise<OverviewData> {
  const [learners, assignments, attempts] = await Promise.all([
    service.listLearners(actor),
    service.listPracticeAssignments(actor),
    service.listReviewableAttempts(actor),
  ]);
  return projectOverviewData(actor, learners, assignments, attempts);
}

export function projectOverviewData(
  actor: ActorContext,
  learners: readonly LearnerSummary[],
  assignments: readonly PracticeAssignmentSummary[],
  attempts: readonly ReviewAttemptSummary[],
): OverviewData {
  const assignmentsByLearner = new Map(assignments.map((assignment) => [assignment.learnerId, assignment]));
  const reviewCounts = new Map<string, Map<string, number>>();
  for (const attempt of attempts) {
    const counts = reviewCounts.get(attempt.learnerId) ?? new Map<string, number>();
    counts.set(attempt.consentSnapshotId, (counts.get(attempt.consentSnapshotId) ?? 0) + 1);
    reviewCounts.set(attempt.learnerId, counts);
  }

  return {
    mode: "live",
    canManageAssignments: actor.role === "owner" || actor.role === "clinician",
    learners: learners.map((learner) => {
      const consent = learner.latestConsent;
      const latestAssignment = assignmentsByLearner.get(learner.id);
      const audioPermitted = consent?.audioProcessing
        && (consent.assentStatus === "affirmed" || consent.assentStatus === "not-applicable");
      const assignment = audioPermitted && latestAssignment?.consentSnapshotId === consent?.id
        ? latestAssignment : undefined;
      // The bulk review API is capped at 100 and consent-bound; these are not pending-review counts.
      const reviewCount = consent?.clinicianReview
        ? reviewCounts.get(learner.id)?.get(consent.id) ?? 0 : 0;
      const practiceDate = learner.lastPracticeAt ? new Date(learner.lastPracticeAt) : null;
      const validDate = practiceDate && Number.isFinite(practiceDate.getTime());
      const missingPractice = learner.attemptCount === 0 ? "No practice recorded" : "Date unavailable";
      const evidence = !consent?.clinicianReview
        ? "Clinician review is not enabled in the current consent choice. Attempt totals do not grant access to capture details."
        : reviewCount > 0
          ? `${reviewCount} ${reviewCount === 1 ? "attempt appears" : "attempts appear"} in the clinic’s latest 100 authorized review records. Recordings are not retained.`
          : "No attempts for this learner appear in the clinic’s latest 100 authorized review records. This is not a complete practice history.";
      return {
        id: learner.id,
        initials: learner.displayLabel.trim().split(/\s+/).map((part) => part[0]).slice(0, 2).join("").toUpperCase(),
        displayName: learner.displayLabel,
        target: assignment?.targetLabel ?? "No current assignment",
        targetDetail: assignment
          ? `“${assignment.prompt}” · ${assignment.attemptTarget} repetitions · ${assignment.retryLimit} ${assignment.retryLimit === 1 ? "retry" : "retries"}`
          : !audioPermitted
            ? "Current audio consent and assent are required for practice."
            : latestAssignment
              ? "The latest assignment uses an earlier consent choice. An owner or clinician can create a new assignment."
              : "An owner or clinician can assign a practice target.",
        phone: assignment?.targetLabel.match(/\/[^/]+\//)?.[0] ?? null,
        lastPractice: validDate
          ? new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" }).format(practiceDate)
          : learner.attemptCount === 0 ? "—" : "Unknown",
        lastPracticeDetail: validDate
          ? `${new Intl.DateTimeFormat("en-US", { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" }).format(practiceDate)} UTC`
          : missingPractice,
        attempts: learner.attemptCount,
        reviewAvailable: reviewCount > 0,
        status: reviewCount > 0 ? "Review available" : "No review listed",
        evidence,
      };
    }),
  };
}
