import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const schemaPath = resolve(packageRoot, "schema/attempt-evaluation.schema.json");
const typescriptPath = resolve(
  packageRoot,
  "src/generated/attempt-evaluation.ts",
);
const swiftPath = resolve(
  packageRoot,
  "swift/Sources/CadenceContracts/AttemptEvaluationModels.swift",
);
const checkOnly = process.argv.includes("--check");
const schema = JSON.parse(await readFile(schemaPath, "utf8"));

const objectDefinitionNames = [
  "CaptureQuality",
  "AudioEvidence",
  "ConsentSnapshot",
  "AttemptEvaluationRequest",
  "RoutingDecision",
  "AttemptEvaluationResponse",
  "LearnerAttemptReceipt",
];

const swiftTypeNames = {
  TargetProtocolId: "TargetProtocolID",
};

function definition(name) {
  const value = schema.$defs?.[name];
  if (!value || typeof value !== "object") {
    throw new Error(`Schema definition ${name} is missing.`);
  }
  return value;
}

function enumValues(name) {
  const values = definition(name).enum;
  if (
    !Array.isArray(values) ||
    !values.every((value) => typeof value === "string")
  ) {
    throw new Error(`Schema definition ${name} must contain a string enum.`);
  }
  return values;
}

function objectShape(name) {
  const value = definition(name);
  if (
    value.type !== "object" ||
    !value.properties ||
    typeof value.properties !== "object" ||
    !Array.isArray(value.required)
  ) {
    throw new Error(
      `Schema definition ${name} must contain object properties and required fields.`,
    );
  }
  return {
    properties: Object.entries(value.properties),
    required: new Set(value.required),
  };
}

function referencedType(value) {
  const reference = value?.$ref;
  if (typeof reference !== "string" || !reference.startsWith("#/$defs/")) {
    return undefined;
  }
  return reference.slice("#/$defs/".length);
}

function typescriptType(value) {
  const reference = referencedType(value);
  if (reference) return reference;
  if (value.type === "string") return "string";
  if (value.type === "number" || value.type === "integer") return "number";
  if (value.type === "boolean") return "boolean";
  if (value.type === "array") {
    return `readonly ${typescriptType(value.items)}[]`;
  }
  throw new Error(`Unsupported TypeScript schema shape: ${JSON.stringify(value)}`);
}

function swiftType(value) {
  const reference = referencedType(value);
  if (reference) return swiftTypeNames[reference] ?? reference;
  if (value.type === "string") return "String";
  if (value.type === "number") return "Double";
  if (value.type === "integer") return "Int";
  if (value.type === "boolean") return "Bool";
  if (value.type === "array") return `[${swiftType(value.items)}]`;
  throw new Error(`Unsupported Swift schema shape: ${JSON.stringify(value)}`);
}

function tsArray(name, values) {
  return `export const ${name} = ${JSON.stringify(values, null, 2)} as const;`;
}

function typescriptInterface(name) {
  const { properties, required } = objectShape(name);
  const fields = properties
    .map(([propertyName, value]) => {
      const optional = required.has(propertyName) ? "" : "?";
      return `  readonly ${propertyName}${optional}: ${typescriptType(value)};`;
    })
    .join("\n");
  return `export interface ${name} {\n${fields}\n}`;
}

function swiftCase(value) {
  const words = value.split(/[^A-Za-z0-9]+/).filter(Boolean);
  return words
    .map((word, index) => {
      const normalized = /^\d+$/.test(word) ? word : word.toLowerCase();
      return index === 0
        ? normalized
        : normalized.charAt(0).toUpperCase() + normalized.slice(1);
    })
    .join("");
}

function swiftEnum(name, values) {
  const cases = values
    .map((value) => `  case ${swiftCase(value)} = ${JSON.stringify(value)}`)
    .join("\n");
  return `public enum ${name}: String, Codable, CaseIterable, Sendable {\n${cases}\n}`;
}

function swiftStruct(name) {
  const { properties, required } = objectShape(name);
  const typedProperties = properties.map(([propertyName, value]) => ({
    name: propertyName,
    type: `${swiftType(value)}${required.has(propertyName) ? "" : "?"}`,
  }));
  const fields = typedProperties
    .map(({ name: propertyName, type }) => `  public let ${propertyName}: ${type}`)
    .join("\n");
  const parameters = typedProperties
    .map(({ name: propertyName, type }) => `    ${propertyName}: ${type}`)
    .join(",\n");
  const assignments = typedProperties
    .map(
      ({ name: propertyName }) =>
        `    self.${propertyName} = ${propertyName}`,
    )
    .join("\n");
  return `public struct ${name}: Codable, Equatable, Sendable {
${fields}

  public init(
${parameters}
  ) {
${assignments}
  }
}`;
}

const targetProtocolIds = enumValues("TargetProtocolId");
const captureReasonCodes = enumValues("CaptureReasonCode");
const likelyErrorKinds = enumValues("LikelyError");
const routingDecisionKinds = enumValues("RoutingDecisionKind");
const routingDecisionReasons = enumValues("RoutingDecisionReason");
const learnerAttemptStatuses = enumValues("LearnerAttemptStatus");

const typescript = `// Generated from schema/attempt-evaluation.schema.json. Do not edit by hand.

${tsArray("targetProtocolIds", targetProtocolIds)}
export type TargetProtocolId = (typeof targetProtocolIds)[number];

${tsArray("captureReasonCodes", captureReasonCodes)}
export type CaptureReasonCode = (typeof captureReasonCodes)[number];

${tsArray("likelyErrorKinds", likelyErrorKinds)}
export type LikelyError = (typeof likelyErrorKinds)[number];

${tsArray("routingDecisionKinds", routingDecisionKinds)}
export type RoutingDecisionKind = (typeof routingDecisionKinds)[number];

${tsArray("routingDecisionReasons", routingDecisionReasons)}
export type RoutingDecisionReason = (typeof routingDecisionReasons)[number];

${tsArray("learnerAttemptStatuses", learnerAttemptStatuses)}
export type LearnerAttemptStatus = (typeof learnerAttemptStatuses)[number];

${objectDefinitionNames.map(typescriptInterface).join("\n\n")}
`;

const swift = `// Generated from schema/attempt-evaluation.schema.json. Do not edit by hand.
import Foundation

${swiftEnum("TargetProtocolID", targetProtocolIds)}

${swiftEnum("CaptureReasonCode", captureReasonCodes)}

${swiftEnum("LikelyError", likelyErrorKinds)}

${swiftEnum("RoutingDecisionKind", routingDecisionKinds)}

${swiftEnum("RoutingDecisionReason", routingDecisionReasons)}

${swiftEnum("LearnerAttemptStatus", learnerAttemptStatuses)}

${objectDefinitionNames.map(swiftStruct).join("\n\n")}
`;

async function emit(path, content) {
  if (checkOnly) {
    let current;
    try {
      current = await readFile(path, "utf8");
    } catch {
      throw new Error(`Generated file is missing: ${path}`);
    }
    if (current !== content) {
      throw new Error(
        `Generated file is stale: ${path}. Run pnpm --filter @speech-therapy/contracts generate.`,
      );
    }
    return;
  }

  await mkdir(dirname(path), { recursive: true });
  await writeFile(path, content);
}

await Promise.all([emit(typescriptPath, typescript), emit(swiftPath, swift)]);

console.log(
  checkOnly
    ? "Generated contracts are current."
    : "Generated TypeScript and Swift contracts.",
);
