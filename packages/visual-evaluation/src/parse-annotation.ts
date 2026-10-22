import {
  adjudicationResolutions,
  visualAnnotationConfidence,
  VisualAnnotationError,
  visualAnnotationQualityReasons,
  visualCueLabels,
  type VisualCueAnnotation,
  type VisualCueAnnotationBundle,
} from "./annotation-types.ts";

const labelPolicyVersion = "bilabial-closure-observation-v1" as const;

export function parseVisualCueAnnotation(value: unknown): VisualCueAnnotation {
  const root = object(value, "annotation", [
    "schemaVersion",
    "annotationID",
    "itemID",
    "cueFamily",
    "labelPolicyVersion",
    "reviewerID",
    "annotatedAt",
    "label",
    "confidence",
    "qualityReasons",
    "blinding",
  ]);
  literal(root.schemaVersion, "visual-cue-annotation-v1", "schemaVersion");
  const annotationID = uuid(root.annotationID, "annotationID");
  const itemID = opaqueID(root.itemID, "itemID");
  literal(root.cueFamily, "bilabial-closure", "cueFamily");
  literal(root.labelPolicyVersion, labelPolicyVersion, "labelPolicyVersion");
  const reviewerID = opaqueID(root.reviewerID, "reviewerID");
  const annotatedAt = timestamp(root.annotatedAt, "annotatedAt");
  const label = enumeration(root.label, visualCueLabels, "label");
  const confidence = enumeration(
    root.confidence,
    visualAnnotationConfidence,
    "confidence",
  );
  const qualityReasons = uniqueEnumerationArray(
    root.qualityReasons,
    visualAnnotationQualityReasons,
    "qualityReasons",
  );
  const uncertain = label === "indeterminate" || label === "unobservable";
  if (uncertain !== (qualityReasons.length > 0)) {
    fail(
      "qualityReasons must explain indeterminate/unobservable labels and be empty for observed labels",
    );
  }
  const blinding = object(root.blinding, "blinding", [
    "modelOutputHidden",
    "peerRatingsHidden",
  ]);
  literal(blinding.modelOutputHidden, true, "blinding.modelOutputHidden");
  literal(blinding.peerRatingsHidden, true, "blinding.peerRatingsHidden");

  return {
    schemaVersion: "visual-cue-annotation-v1",
    annotationID,
    itemID,
    cueFamily: "bilabial-closure",
    labelPolicyVersion,
    reviewerID,
    annotatedAt,
    label,
    confidence,
    qualityReasons,
    blinding: { modelOutputHidden: true, peerRatingsHidden: true },
  };
}

export function parseVisualCueAnnotationBundle(
  value: unknown,
): VisualCueAnnotationBundle {
  const root = object(
    value,
    "bundle",
    ["schemaVersion", "itemID", "labelPolicyVersion", "ratings"],
    ["adjudication"],
  );
  literal(root.schemaVersion, "visual-cue-adjudication-v1", "schemaVersion");
  const itemID = opaqueID(root.itemID, "itemID");
  literal(root.labelPolicyVersion, labelPolicyVersion, "labelPolicyVersion");
  if (!Array.isArray(root.ratings) || root.ratings.length !== 2) {
    fail("ratings must contain exactly two independent annotations");
  }
  const first = parseVisualCueAnnotation(root.ratings[0]);
  const second = parseVisualCueAnnotation(root.ratings[1]);
  for (const rating of [first, second]) {
    if (rating.itemID !== itemID) fail("every rating must reference bundle.itemID");
    if (rating.labelPolicyVersion !== labelPolicyVersion) {
      fail("every rating must use bundle.labelPolicyVersion");
    }
  }
  if (first.annotationID === second.annotationID) {
    fail("rating annotation IDs must be unique");
  }
  if (first.reviewerID === second.reviewerID) {
    fail("ratings must come from two distinct reviewers");
  }

  const labelsAgree = first.label === second.label;
  if (root.adjudication === undefined) {
    if (!labelsAgree) fail("disagreements require adjudication");
    return {
      schemaVersion: "visual-cue-adjudication-v1",
      itemID,
      labelPolicyVersion,
      ratings: [first, second],
    };
  }

  const adjudication = object(root.adjudication, "adjudication", [
    "adjudicatorID",
    "adjudicatedAt",
    "finalLabel",
    "resolution",
  ]);
  const adjudicatorID = opaqueID(adjudication.adjudicatorID, "adjudicatorID");
  if ([first.reviewerID, second.reviewerID].includes(adjudicatorID)) {
    fail("the adjudicator must be independent of both original reviewers");
  }
  const adjudicatedAt = timestamp(adjudication.adjudicatedAt, "adjudicatedAt");
  if ([first.annotatedAt, second.annotatedAt].some(
    (value) => Date.parse(adjudicatedAt) < Date.parse(value),
  )) {
    fail("adjudicatedAt cannot precede an original rating");
  }
  const finalLabel = enumeration(
    adjudication.finalLabel,
    visualCueLabels,
    "adjudication.finalLabel",
  );
  const resolution = enumeration(
    adjudication.resolution,
    adjudicationResolutions,
    "adjudication.resolution",
  );
  if (labelsAgree && (resolution !== "agreement" || finalLabel !== first.label)) {
    fail("agreeing ratings may only be confirmed with their agreed label");
  }
  if (!labelsAgree && resolution === "agreement") {
    fail("disagreeing ratings cannot use the agreement resolution");
  }
  if (resolution === "unresolvable" && finalLabel !== "indeterminate") {
    fail("an unresolvable disagreement must remain indeterminate");
  }

  return {
    schemaVersion: "visual-cue-adjudication-v1",
    itemID,
    labelPolicyVersion,
    ratings: [first, second],
    adjudication: { adjudicatorID, adjudicatedAt, finalLabel, resolution },
  };
}

function object(
  value: unknown,
  path: string,
  required: readonly string[],
  optional: readonly string[] = [],
): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    fail(`${path} must be an object`);
  }
  const record = value as Record<string, unknown>;
  const allowed = new Set([...required, ...optional]);
  const unknown = Object.keys(record).filter((key) => !allowed.has(key));
  if (unknown.length > 0) fail(`${path} contains unknown fields: ${unknown.join(", ")}`);
  const missing = required.filter((key) => !(key in record));
  if (missing.length > 0) fail(`${path} is missing fields: ${missing.join(", ")}`);
  return record;
}

function literal<T>(value: unknown, expected: T, path: string): asserts value is T {
  if (value !== expected) fail(`${path} must equal ${String(expected)}`);
}

function enumeration<const T extends readonly string[]>(
  value: unknown,
  allowed: T,
  path: string,
): T[number] {
  if (typeof value !== "string" || !allowed.includes(value)) {
    fail(`${path} must be one of ${allowed.join(", ")}`);
  }
  return value as T[number];
}

function uniqueEnumerationArray<const T extends readonly string[]>(
  value: unknown,
  allowed: T,
  path: string,
): readonly T[number][] {
  if (!Array.isArray(value) || value.length > allowed.length) {
    fail(`${path} must be a bounded array`);
  }
  const parsed = value.map((item, index) => enumeration(item, allowed, `${path}[${index}]`));
  if (new Set(parsed).size !== parsed.length) fail(`${path} cannot contain duplicates`);
  return parsed;
}

function uuid(value: unknown, path: string): string {
  if (
    typeof value !== "string"
    || !/^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/i.test(value)
  ) {
    fail(`${path} must be a version-4 UUID`);
  }
  return value;
}

function opaqueID(value: unknown, path: string): string {
  if (
    typeof value !== "string"
    || !/^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$/.test(value)
  ) {
    fail(`${path} must be a bounded opaque identifier`);
  }
  return value;
}

function timestamp(value: unknown, path: string): string {
  if (
    typeof value !== "string"
    || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/.test(value)
    || !Number.isFinite(Date.parse(value))
    || new Date(value).toISOString() !== value
  ) {
    fail(`${path} must be a canonical UTC timestamp with milliseconds`);
  }
  return value;
}

function fail(message: string): never {
  throw new VisualAnnotationError(message);
}
