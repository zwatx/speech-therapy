export interface DashboardMetric {
  label: string;
  value: string;
  detail: string;
  tone: "neutral" | "attention" | "positive";
}

export interface LearnerRowData {
  id: string;
  initials: string;
  displayName: string;
  target: string;
  lastPractice: string;
  attempts: number;
  status: "Practice recorded" | "Review available" | "No practice recorded";
}

export interface SafetyItemData {
  id: string;
  title: string;
  detail: string;
  category: "Evidence" | "Consent" | "Capture";
  count: number;
  countLabel: string;
}

export const dashboardMetrics: readonly DashboardMetric[] = [
  {
    label: "Assigned today",
    value: "14",
    detail: "across 5 target protocols",
    tone: "neutral",
  },
  {
    label: "Deep vision status",
    value: "Off",
    detail: "no target protocol validated yet",
    tone: "positive",
  },
  {
    label: "Needs review",
    value: "5",
    detail: "no automated cause asserted",
    tone: "attention",
  },
  {
    label: "Capture retries",
    value: "7%",
    detail: "excluded from error counts",
    tone: "neutral",
  },
] as const;

export const learnerRows: readonly LearnerRowData[] = [
  {
    id: "demo-learner-01",
    initials: "AM",
    displayName: "Avery M.",
    target: "Beginning /b/ · bilabial closure",
    lastPractice: "Sep 21, 2026",
    attempts: 12,
    status: "Review available",
  },
  {
    id: "demo-learner-02",
    initials: "JL",
    displayName: "Jordan L.",
    target: "Beginning /b/ · bilabial closure",
    lastPractice: "Sep 21, 2026",
    attempts: 9,
    status: "Review available",
  },
  {
    id: "demo-learner-03",
    initials: "SK",
    displayName: "Sam K.",
    target: "Initial /m/ · bilabial closure",
    lastPractice: "Sep 19, 2026",
    attempts: 15,
    status: "Practice recorded",
  },
  {
    id: "demo-learner-04",
    initials: "RN",
    displayName: "Riley N.",
    target: "Interdental /th/ · visibility",
    lastPractice: "—",
    attempts: 0,
    status: "No practice recorded",
  },
  {
    id: "demo-learner-05",
    initials: "TP",
    displayName: "Taylor P.",
    target: "Audio-only /s/ contrast",
    lastPractice: "Sep 19, 2026",
    attempts: 8,
    status: "Practice recorded",
  },
] as const;

export const safetyItems: readonly SafetyItemData[] = [
  {
    id: "safety-demo-01",
    title: "Three research benchmark attempts",
    detail: "Experimental evidence remains uncalibrated and ambiguous; no pronunciation correction is shown.",
    category: "Evidence",
    count: 3,
    countLabel: "3 attempts",
  },
  {
    id: "safety-demo-02",
    title: "Practice consent changed",
    detail: "Previous device access is invalid. Confirm audio consent, then create a new assignment and device link before practice resumes.",
    category: "Consent",
    count: 1,
    countLabel: "1 consent change",
  },
  {
    id: "safety-demo-03",
    title: "Repeated quiet recordings",
    detail: "Audio level checks requested another recording. Capture quality does not measure pronunciation accuracy.",
    category: "Capture",
    count: 2,
    countLabel: "2 attempts",
  },
] as const;
