import type { LearnerConsentSummary } from "@speech-therapy/platform-data";

export function practiceAccess(consent: LearnerConsentSummary | undefined): {
  label: string;
  className: string;
  eligible: boolean;
} {
  if (!consent) return { label: "Consent needed", className: "status-review", eligible: false };
  if (consent.assentStatus === "declined" || consent.assentStatus === "withdrawn") {
    return { label: "Practice paused", className: "status-review", eligible: false };
  }
  if (!consent.audioProcessing) {
    return { label: "Processing off", className: "status-not-started", eligible: false };
  }
  return { label: "Audio permitted", className: "status-neutral", eligible: true };
}
