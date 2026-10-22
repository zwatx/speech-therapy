export const visualCueLabels = [
  "closure-observed",
  "closure-not-observed",
  "indeterminate",
  "unobservable",
] as const;

export type VisualCueLabel = (typeof visualCueLabels)[number];

export const visualAnnotationConfidence = ["low", "medium", "high"] as const;
export type VisualAnnotationConfidence = (typeof visualAnnotationConfidence)[number];

export const visualAnnotationQualityReasons = [
  "low-light",
  "face-off-center",
  "head-turned",
  "mouth-occluded",
  "motion-blur",
  "multiple-faces",
  "target-window-unclear",
] as const;

export type VisualAnnotationQualityReason =
  (typeof visualAnnotationQualityReasons)[number];

export interface VisualCueAnnotation {
  readonly schemaVersion: "visual-cue-annotation-v1";
  readonly annotationID: string;
  readonly itemID: string;
  readonly cueFamily: "bilabial-closure";
  readonly labelPolicyVersion: "bilabial-closure-observation-v1";
  readonly reviewerID: string;
  readonly annotatedAt: string;
  readonly label: VisualCueLabel;
  readonly confidence: VisualAnnotationConfidence;
  readonly qualityReasons: readonly VisualAnnotationQualityReason[];
  readonly blinding: {
    readonly modelOutputHidden: true;
    readonly peerRatingsHidden: true;
  };
}

export const adjudicationResolutions = [
  "agreement",
  "resolved-disagreement",
  "unresolvable",
] as const;

export type AdjudicationResolution = (typeof adjudicationResolutions)[number];

export interface VisualCueAdjudication {
  readonly adjudicatorID: string;
  readonly adjudicatedAt: string;
  readonly finalLabel: VisualCueLabel;
  readonly resolution: AdjudicationResolution;
}

export interface VisualCueAnnotationBundle {
  readonly schemaVersion: "visual-cue-adjudication-v1";
  readonly itemID: string;
  readonly labelPolicyVersion: "bilabial-closure-observation-v1";
  readonly ratings: readonly [VisualCueAnnotation, VisualCueAnnotation];
  readonly adjudication?: VisualCueAdjudication;
}

export interface VisualCueAgreementReport {
  readonly schemaVersion: "visual-cue-agreement-report-v1";
  readonly labelPolicyVersion: "bilabial-closure-observation-v1";
  readonly reviewerPair: readonly [string, string];
  readonly itemCount: number;
  readonly rawAgreement: number;
  readonly cohenKappa: number | null;
  readonly labelCounts: Readonly<Record<VisualCueLabel, number>>;
  readonly disagreementCount: number;
  readonly unobservableCount: number;
  readonly indeterminateCount: number;
  readonly adjudicatedDisagreementCount: number;
  readonly unresolvedCount: number;
}

export class VisualAnnotationError extends TypeError {
  override readonly name = "VisualAnnotationError";
}
