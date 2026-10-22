import assert from "node:assert/strict";
import test from "node:test";

import { benchmarkScoringProfile } from "./benchmark-profiles.ts";
import { scoreConstrainedPronunciation } from "./ctc.ts";

test("the candidate exercise has a benchmark-only unvalidated profile", () => {
  const profile = benchmarkScoringProfile("foundation-ball-initial-b-v1");
  assert.ok(profile);
  assert.equal(profile.releasePosture, "benchmark-only");
  assert.equal(profile.calibration.validated, false);
  assert.equal(profile.lexicon.targetPhone, "b");
  assert.equal(benchmarkScoringProfile("unknown-exercise"), undefined);
});

test("a benchmark profile cannot emit calibrated or non-ambiguous evidence", () => {
  const profile = benchmarkScoringProfile("foundation-ball-initial-b-v1");
  assert.ok(profile);
  const score = scoreConstrainedPronunciation(
    [
      { "<pad>": 0.05, b: 0.8, "ɔ": 0.05, "ɑ": 0.03, "ɒ": 0.02, l: 0.05 },
      { "<pad>": 0.05, b: 0.02, "ɔ": 0.75, "ɑ": 0.08, "ɒ": 0.05, l: 0.05 },
      { "<pad>": 0.05, b: 0.02, "ɔ": 0.03, "ɑ": 0.03, "ɒ": 0.02, l: 0.85 },
    ],
    profile.lexicon,
    profile.calibration,
    undefined,
    profile.policy,
  );

  assert.equal(score.evidence.calibrated, false);
  assert.equal(score.evidence.ambiguous, true);
  assert.equal(score.evidence.likelyError, undefined);
});
