import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { evaluateVisualCueAgreement } from "./agreement.ts";
import {
  parseVisualCueAnnotation,
  parseVisualCueAnnotationBundle,
} from "./parse-annotation.ts";

test("the prospective bilabial fixture preserves independent ratings", async () => {
  const value = JSON.parse(await readFile(
    new URL("../fixtures/visual-cue-adjudication.valid.json", import.meta.url),
    "utf8",
  )) as unknown;

  const bundle = parseVisualCueAnnotationBundle(value);

  assert.equal(bundle.ratings.length, 2);
  assert.equal(bundle.ratings[0].label, "closure-observed");
  assert.equal(bundle.ratings[1].label, "closure-not-observed");
  assert.equal(bundle.adjudication?.finalLabel, "closure-not-observed");
});

test("annotations fail closed on unblinding, identity fields, and uncertainty without reasons", () => {
  const unblinded = annotation(1, "reviewer-slp-001", "closure-observed");
  unblinded.blinding.modelOutputHidden = false;
  assert.throws(() => parseVisualCueAnnotation(unblinded), /modelOutputHidden/);

  const identity = annotation(
    1,
    "reviewer-slp-001",
    "closure-observed",
  ) as Record<string, unknown>;
  identity.learnerName = "Not allowed";
  assert.throws(() => parseVisualCueAnnotation(identity), /unknown fields/);

  const unexplained = annotation(1, "reviewer-slp-001", "unobservable");
  unexplained.qualityReasons = [];
  assert.throws(() => parseVisualCueAnnotation(unexplained), /qualityReasons must explain/);

  const contradictory = annotation(1, "reviewer-slp-001", "closure-observed");
  contradictory.qualityReasons = ["low-light"];
  assert.throws(() => parseVisualCueAnnotation(contradictory), /qualityReasons must explain/);

  const nonCanonicalTime = annotation(1, "reviewer-slp-001", "closure-observed");
  nonCanonicalTime.annotatedAt = "July 10, 2026 18:00 UTC";
  assert.throws(() => parseVisualCueAnnotation(nonCanonicalTime), /canonical UTC timestamp/);

  const impossibleTime = annotation(1, "reviewer-slp-001", "closure-observed");
  impossibleTime.annotatedAt = "2026-02-30T18:00:00.000Z";
  assert.throws(() => parseVisualCueAnnotation(impossibleTime), /canonical UTC timestamp/);
});

test("double-label bundles require distinct reviewers and adjudicate disagreements", () => {
  const sameReviewer = bundle(
    annotation(1, "reviewer-slp-001", "closure-observed"),
    annotation(2, "reviewer-slp-001", "closure-observed"),
  );
  assert.throws(
    () => parseVisualCueAnnotationBundle(sameReviewer),
    /two distinct reviewers/,
  );

  const unadjudicated = bundle(
    annotation(1, "reviewer-slp-001", "closure-observed"),
    annotation(2, "reviewer-slp-002", "closure-not-observed"),
  );
  assert.throws(
    () => parseVisualCueAnnotationBundle(unadjudicated),
    /disagreements require adjudication/,
  );

  const selfAdjudicated = {
    ...unadjudicated,
    adjudication: adjudication("reviewer-slp-001", "closure-observed"),
  };
  assert.throws(
    () => parseVisualCueAnnotationBundle(selfAdjudicated),
    /adjudicator must be independent/,
  );
});

test("agreement is calculated from original ratings, not adjudicated labels", () => {
  const bundles = [
    agreeingBundle(0, "closure-observed"),
    agreeingBundle(10, "closure-not-observed"),
    parseVisualCueAnnotationBundle({
      ...bundle(
        annotation(21, "reviewer-slp-001", "closure-observed", "item-study-0003"),
        annotation(22, "reviewer-slp-002", "closure-not-observed", "item-study-0003"),
        "item-study-0003",
      ),
      adjudication: adjudication("reviewer-slp-003", "closure-not-observed"),
    }),
    agreeingBundle(30, "unobservable"),
  ];

  const report = evaluateVisualCueAgreement(bundles);

  assert.equal(report.itemCount, 4);
  assert.deepEqual(report.reviewerPair, ["reviewer-slp-001", "reviewer-slp-002"]);
  assert.equal(report.rawAgreement, 0.75);
  assert.equal(report.cohenKappa, 7 / 11);
  assert.equal(report.disagreementCount, 1);
  assert.equal(report.adjudicatedDisagreementCount, 1);
  assert.equal(report.unobservableCount, 1);
});

test("agreement rejects duplicate items and reports degenerate kappa honestly", () => {
  const one = agreeingBundle(0, "closure-observed");
  assert.throws(
    () => evaluateVisualCueAgreement([one, one]),
    /duplicate items/,
  );
  assert.equal(evaluateVisualCueAgreement([one]).cohenKappa, null);
  assert.throws(() => evaluateVisualCueAgreement([]), /At least one/);

  const differentPair = agreeingBundle(10, "closure-observed");
  const replacement = annotation(
    100,
    "reviewer-slp-004",
    "closure-observed",
    differentPair.itemID,
  );
  const inconsistentPair = parseVisualCueAnnotationBundle({
    ...differentPair,
    ratings: [differentPair.ratings[0], replacement],
  });
  assert.throws(
    () => evaluateVisualCueAgreement([one, inconsistentPair]),
    /consistently ordered reviewer pair/,
  );
});

function annotation(
  index: number,
  reviewerID: string,
  label: "closure-observed" | "closure-not-observed" | "indeterminate" | "unobservable",
  itemID = "item-study-0001",
) {
  const uncertain = label === "indeterminate" || label === "unobservable";
  return {
    schemaVersion: "visual-cue-annotation-v1",
    annotationID: `00000000-0000-4000-8000-${String(index + 1).padStart(12, "0")}`,
    itemID,
    cueFamily: "bilabial-closure",
    labelPolicyVersion: "bilabial-closure-observation-v1",
    reviewerID,
    annotatedAt: "2026-07-10T18:00:00.000Z",
    label,
    confidence: uncertain ? "medium" : "high",
    qualityReasons: uncertain ? ["target-window-unclear"] : [],
    blinding: { modelOutputHidden: true, peerRatingsHidden: true },
  };
}

function bundle(
  first: ReturnType<typeof annotation>,
  second: ReturnType<typeof annotation>,
  itemID = "item-study-0001",
) {
  return {
    schemaVersion: "visual-cue-adjudication-v1",
    itemID,
    labelPolicyVersion: "bilabial-closure-observation-v1",
    ratings: [first, second],
  };
}

function agreeingBundle(
  offset: number,
  label: Parameters<typeof annotation>[2],
) {
  const itemID = `item-study-${String(offset + 1).padStart(4, "0")}`;
  return parseVisualCueAnnotationBundle(bundle(
    annotation(offset + 1, "reviewer-slp-001", label, itemID),
    annotation(offset + 2, "reviewer-slp-002", label, itemID),
    itemID,
  ));
}

function adjudication(
  adjudicatorID: string,
  finalLabel: Parameters<typeof annotation>[2],
) {
  return {
    adjudicatorID,
    adjudicatedAt: "2026-07-10T18:10:00.000Z",
    finalLabel,
    resolution: "resolved-disagreement",
  };
}
