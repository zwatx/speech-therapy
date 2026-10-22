import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import test from "node:test";

import {
  foundationExerciseRegistryVersion,
  foundationExercises,
  getFoundationExercise,
} from "./exercises.ts";

test("the assignable foundation registry is bounded and definition-hashed", () => {
  assert.equal(foundationExerciseRegistryVersion, "foundation-exercises-v1");
  assert.deepEqual(Object.keys(foundationExercises), [
    "foundation-ball-initial-b-v1",
  ]);
  const exercise = getFoundationExercise("foundation-ball-initial-b-v1");
  assert.ok(exercise);
  const canonical = JSON.stringify({
    id: exercise.id,
    protocolId: exercise.protocolId,
    prompt: exercise.prompt,
    releasePosture: exercise.releasePosture,
    targetLabel: exercise.targetLabel,
  });
  assert.equal(
    createHash("sha256").update(canonical).digest("hex"),
    exercise.definitionSha256,
  );
  assert.equal(getFoundationExercise("l-tip-lift-research-v1"), undefined);
});
