import type { TargetProtocolId } from "./types.ts";

export interface FoundationExercise {
  readonly id: string;
  readonly protocolId: TargetProtocolId;
  readonly prompt: string;
  readonly targetLabel: string;
  readonly releasePosture: "candidate-silent-only";
  readonly definitionSha256: string;
}

export const foundationExerciseRegistryVersion = "foundation-exercises-v1";

export const foundationExercises: Readonly<
  Record<string, FoundationExercise>
> = {
  "foundation-ball-initial-b-v1": {
    id: "foundation-ball-initial-b-v1",
    protocolId: "bilabial-closure-v1",
    prompt: "ball",
    targetLabel: "Beginning /b/",
    releasePosture: "candidate-silent-only",
    definitionSha256:
      "01536629b96183f165e583ff56839196d0695848c1fe2b5b4ce868912cebccb2",
  },
};

export function getFoundationExercise(
  id: string,
): FoundationExercise | undefined {
  return foundationExercises[id];
}
