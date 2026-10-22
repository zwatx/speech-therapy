import {
  visualCueLabels,
  type VisualCueAgreementReport,
  type VisualCueAnnotationBundle,
  type VisualCueLabel,
} from "./annotation-types.ts";
import { parseVisualCueAnnotationBundle } from "./parse-annotation.ts";

export function evaluateVisualCueAgreement(
  values: readonly VisualCueAnnotationBundle[],
): VisualCueAgreementReport {
  if (values.length === 0) {
    throw new TypeError("At least one double-labeled item is required.");
  }
  const bundles = values.map(parseVisualCueAnnotationBundle);
  const itemIDs = new Set(bundles.map((bundle) => bundle.itemID));
  if (itemIDs.size !== bundles.length) {
    throw new TypeError("Agreement input cannot contain duplicate items.");
  }
  const reviewerPair = bundles[0]!.ratings.map((rating) => rating.reviewerID) as [
    string,
    string,
  ];
  if (bundles.some((bundle) =>
    bundle.ratings[0].reviewerID !== reviewerPair[0]
    || bundle.ratings[1].reviewerID !== reviewerPair[1])) {
    throw new TypeError("Cohen's kappa requires one consistently ordered reviewer pair.");
  }

  const firstCounts = emptyCounts();
  const secondCounts = emptyCounts();
  const labelCounts = emptyCounts();
  let agreements = 0;
  let adjudicatedDisagreementCount = 0;
  let unresolvedCount = 0;
  for (const bundle of bundles) {
    const [first, second] = bundle.ratings;
    firstCounts[first.label] += 1;
    secondCounts[second.label] += 1;
    labelCounts[first.label] += 1;
    labelCounts[second.label] += 1;
    if (first.label === second.label) agreements += 1;
    else if (bundle.adjudication?.resolution === "resolved-disagreement") {
      adjudicatedDisagreementCount += 1;
    } else if (bundle.adjudication?.resolution === "unresolvable") {
      unresolvedCount += 1;
    }
  }

  const rawAgreement = agreements / bundles.length;
  const expectedAgreement = visualCueLabels.reduce(
    (total, label) => total
      + (firstCounts[label] / bundles.length) * (secondCounts[label] / bundles.length),
    0,
  );
  const cohenKappa = expectedAgreement === 1
    ? null
    : (rawAgreement - expectedAgreement) / (1 - expectedAgreement);

  return {
    schemaVersion: "visual-cue-agreement-report-v1",
    labelPolicyVersion: "bilabial-closure-observation-v1",
    reviewerPair,
    itemCount: bundles.length,
    rawAgreement,
    cohenKappa,
    labelCounts,
    disagreementCount: bundles.length - agreements,
    unobservableCount: finalCount(bundles, "unobservable"),
    indeterminateCount: finalCount(bundles, "indeterminate"),
    adjudicatedDisagreementCount,
    unresolvedCount,
  };
}

function finalCount(
  bundles: readonly VisualCueAnnotationBundle[],
  label: VisualCueLabel,
): number {
  return bundles.filter((bundle) =>
    (bundle.adjudication?.finalLabel ?? bundle.ratings[0].label) === label).length;
}

function emptyCounts(): Record<VisualCueLabel, number> {
  return {
    "closure-observed": 0,
    "closure-not-observed": 0,
    indeterminate: 0,
    unobservable: 0,
  };
}
