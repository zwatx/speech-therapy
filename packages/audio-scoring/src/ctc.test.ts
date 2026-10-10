import assert from "node:assert/strict";
import test from "node:test";

import {
  ctcSequenceLogProbability,
  scoreConstrainedPronunciation,
} from "./ctc.ts";
import {
  evaluationManifestSha256,
  validateLockedEvaluationManifest,
} from "./evaluation.ts";
import type {
  AudioScoringPolicy,
  CalibrationArtifact,
  ClinicalLexiconEntry,
  FramePosterior,
} from "./types.ts";

const manifestItems = [
  {
    attemptId: "attempt-train",
    speakerHash: "1".repeat(64),
    householdHash: "2".repeat(64),
    split: "train" as const,
    targetProtocolId: "audio-only-v1",
  },
  {
    attemptId: "attempt-calibration",
    speakerHash: "3".repeat(64),
    householdHash: "4".repeat(64),
    split: "calibration" as const,
    targetProtocolId: "audio-only-v1",
  },
  {
    attemptId: "attempt-test",
    speakerHash: "5".repeat(64),
    householdHash: "6".repeat(64),
    split: "test" as const,
    targetProtocolId: "audio-only-v1",
  },
];
const manifestHash = evaluationManifestSha256(manifestItems);
const verifiedManifest = validateLockedEvaluationManifest({
  version: "evaluation-v1",
  sha256: manifestHash,
  lockedAt: "2026-07-10T00:00:00.000Z",
  items: manifestItems,
});

const calibration: CalibrationArtifact = {
  version: "calibration-v1",
  datasetManifestHash: manifestHash,
  temperature: 1,
  bias: 0,
  validated: true,
  fitSplit: "calibration",
  speakerIndependent: true,
  householdIndependent: true,
};

const policy: AudioScoringPolicy = {
  version: "audio-policy-v1",
  blankToken: "<blank>",
  minimumHypothesisCoverage: 0.3,
  ambiguityMargin: 0.2,
};

const ballLexicon: ClinicalLexiconEntry = {
  id: "ball-final-l",
  version: "lexicon-v1",
  prompt: "ball",
  targetPhone: "l",
  hypotheses: [
    { id: "expected", kind: "expected", phones: ["b", "a", "l"] },
    {
      id: "l-omission",
      kind: "omission",
      phones: ["b", "a"],
      likelyError: "omission",
    },
  ],
};

function frame(
  blank: number,
  b: number,
  a: number,
  l: number,
): FramePosterior {
  return { "<blank>": blank, b, a, l };
}

function bruteForceCtcProbability(
  frames: readonly FramePosterior[],
  phones: readonly string[],
  blankToken: string,
): number {
  const vocabulary = Object.keys(frames[0]!);
  let total = 0;
  function visit(frameIndex: number, alignment: string[], weight: number): void {
    if (frameIndex === frames.length) {
      const collapsed: string[] = [];
      let previous: string | undefined;
      for (const token of alignment) {
        if (token !== previous && token !== blankToken) collapsed.push(token);
        previous = token;
      }
      if (collapsed.join("\u0000") === phones.join("\u0000")) total += weight;
      return;
    }
    for (const token of vocabulary) {
      visit(
        frameIndex + 1,
        [...alignment, token],
        weight * frames[frameIndex]![token]!,
      );
    }
  }
  visit(0, [], 1);
  return total;
}

test("CTC sums all paths that collapse to one phone", () => {
  const frames = [
    { "<blank>": 0.1, a: 0.9 },
    { "<blank>": 0.8, a: 0.2 },
  ];
  const probability = Math.exp(
    ctcSequenceLogProbability(frames, ["a"], "<blank>"),
  );

  assert.ok(Math.abs(probability - 0.92) < 1e-12);
});

test("CTC forward recursion matches brute-force alignments for repeated phones", () => {
  const frames = [
    { "<blank>": 0.2, l: 0.7, a: 0.1 },
    { "<blank>": 0.6, l: 0.3, a: 0.1 },
    { "<blank>": 0.2, l: 0.7, a: 0.1 },
    { "<blank>": 0.5, l: 0.4, a: 0.1 },
  ];
  for (const phones of [["l", "l"], ["a", "a", "l"]]) {
    const dynamicProgramming = Math.exp(
      ctcSequenceLogProbability(frames, phones, "<blank>"),
    );
    const bruteForce = bruteForceCtcProbability(frames, phones, "<blank>");
    assert.ok(Math.abs(dynamicProgramming - bruteForce) < 1e-12);
  }
});

test("a phone path that cannot fit in the available frames has zero mass", () => {
  const probability = Math.exp(
    ctcSequenceLogProbability(
      [{ "<blank>": 0.5, a: 0.5 }],
      ["a", "a"],
      "<blank>",
    ),
  );
  assert.equal(probability, 0);
});

test("constrained scoring favors the expected phone path without word decoding", () => {
  const score = scoreConstrainedPronunciation(
    [
      frame(0.05, 0.9, 0.03, 0.02),
      frame(0.05, 0.02, 0.9, 0.03),
      frame(0.05, 0.01, 0.04, 0.9),
    ],
    ballLexicon,
    calibration,
    verifiedManifest,
    policy,
  );

  assert.ok(score.evidence.pCorrect > score.evidence.pError);
  assert.equal(score.evidence.calibrated, true);
  assert.equal(score.evidence.ambiguous, false);
  assert.equal(score.lexiconVersion, "lexicon-v1");
  assert.ok(score.evidence.pCorrect + score.evidence.pError <= 1);
});

test("the highest constrained error path supplies the error family", () => {
  const score = scoreConstrainedPronunciation(
    [
      frame(0.05, 0.9, 0.03, 0.02),
      frame(0.05, 0.02, 0.9, 0.03),
      frame(0.9, 0.03, 0.04, 0.03),
    ],
    ballLexicon,
    calibration,
    verifiedManifest,
    policy,
  );

  assert.ok(score.evidence.pError > score.evidence.pCorrect);
  assert.equal(score.evidence.likelyError, "omission");
});

test("equally likely different error families do not depend on lexicon order", () => {
  const lexicon: ClinicalLexiconEntry = {
    ...ballLexicon,
    hypotheses: [
      { id: "expected", kind: "expected", phones: ["b", "l"] },
      { id: "omitted", kind: "omission", phones: ["b"], likelyError: "omission" },
      {
        id: "replaced", kind: "substitution", phones: ["b", "d"],
        likelyError: "substitution",
      },
    ],
  };
  for (const hypotheses of [lexicon.hypotheses, [...lexicon.hypotheses].reverse()]) {
    const score = scoreConstrainedPronunciation(
      [
        { "<blank>": 0, b: 1, l: 0, d: 0 },
        { "<blank>": 0.45, b: 0, l: 0.1, d: 0.45 },
      ],
      { ...lexicon, hypotheses }, calibration, verifiedManifest, policy,
    );
    assert.ok(Math.abs(score.evidence.pCorrect - 0.1) < 1e-12);
    assert.ok(Math.abs(score.evidence.pError - 0.9) < 1e-12);
    assert.equal(score.evidence.ambiguous, false);
    assert.equal(Object.hasOwn(score.evidence, "likelyError"), false);
  }
});

test("tied paths within one error family retain that family", () => {
  const score = scoreConstrainedPronunciation(
    [
      { "<blank>": 0, b: 1, l: 0, d: 0, k: 0 },
      { "<blank>": 0, b: 0, l: 0.1, d: 0.45, k: 0.45 },
    ],
    {
      ...ballLexicon,
      hypotheses: [
        { id: "expected", kind: "expected", phones: ["b", "l"] },
        {
          id: "d", kind: "substitution", phones: ["b", "d"],
          likelyError: "substitution",
        },
        {
          id: "k", kind: "substitution", phones: ["b", "k"],
          likelyError: "substitution",
        },
      ],
    },
    calibration, verifiedManifest, policy,
  );
  assert.equal(score.evidence.ambiguous, false);
  assert.equal(score.evidence.likelyError, "substitution");
});

test("a strictly higher error path retains its family without a tie tolerance", () => {
  const score = scoreConstrainedPronunciation(
    [
      { "<blank>": 0, b: 1, l: 0, d: 0 },
      { "<blank>": 0.4499999999, b: 0, l: 0.1, d: 0.4500000001 },
    ],
    {
      ...ballLexicon,
      hypotheses: [
        { id: "expected", kind: "expected", phones: ["b", "l"] },
        { id: "omitted", kind: "omission", phones: ["b"], likelyError: "omission" },
        {
          id: "replaced", kind: "substitution", phones: ["b", "d"],
          likelyError: "substitution",
        },
      ],
    },
    calibration, verifiedManifest, policy,
  );
  assert.equal(score.evidence.ambiguous, false);
  assert.equal(score.evidence.likelyError, "substitution");
});

test("unvalidated calibration can never produce non-ambiguous evidence", () => {
  const score = scoreConstrainedPronunciation(
    [
      frame(0.05, 0.9, 0.03, 0.02),
      frame(0.05, 0.02, 0.9, 0.03),
      frame(0.05, 0.01, 0.04, 0.9),
    ],
    ballLexicon,
    { ...calibration, validated: false },
    verifiedManifest,
    policy,
  );

  assert.equal(score.evidence.calibrated, false);
  assert.equal(score.evidence.ambiguous, true);
});

test("malformed calibration artifacts fail closed without producing NaN", () => {
  const score = scoreConstrainedPronunciation(
    [
      frame(0.05, 0.9, 0.03, 0.02),
      frame(0.05, 0.02, 0.9, 0.03),
      frame(0.05, 0.01, 0.04, 0.9),
    ],
    ballLexicon,
    { ...calibration, temperature: 0, bias: Number.NaN },
    verifiedManifest,
    policy,
  );

  assert.equal(score.evidence.calibrated, false);
  assert.equal(score.evidence.ambiguous, true);
  assert.ok(Number.isFinite(score.evidence.pCorrect));
  assert.ok(Number.isFinite(score.evidence.pError));
});

test("unmodeled acoustic mass forces abstention", () => {
  const score = scoreConstrainedPronunciation(
    [
      frame(0.97, 0.01, 0.01, 0.01),
      frame(0.97, 0.01, 0.01, 0.01),
      frame(0.97, 0.01, 0.01, 0.01),
    ],
    ballLexicon,
    calibration,
    verifiedManifest,
    policy,
  );

  assert.ok(score.hypothesisCoverage < policy.minimumHypothesisCoverage);
  assert.equal(score.evidence.ambiguous, true);
});

test("duplicate phone paths are rejected instead of double-counted", () => {
  assert.throws(
    () =>
      scoreConstrainedPronunciation(
        [frame(0.1, 0.3, 0.3, 0.3)],
        {
          ...ballLexicon,
          hypotheses: [
            { id: "expected", kind: "expected", phones: ["b"] },
            {
              id: "duplicate",
              kind: "omission",
              phones: ["b"],
              likelyError: "omission",
            },
          ],
        },
        calibration,
        verifiedManifest,
        policy,
      ),
    /unique/,
  );
});

test("scoring rejects empty and blank-token lexicon paths", () => {
  for (const phones of [[], ["<blank>"]]) {
    assert.throws(
      () =>
        scoreConstrainedPronunciation(
          [frame(0.1, 0.3, 0.3, 0.3)],
          {
            ...ballLexicon,
            hypotheses: [
              { id: "expected", kind: "expected", phones: ["b"] },
              {
                id: "invalid-error",
                kind: "omission",
                phones,
                likelyError: "omission",
              },
            ],
          },
          calibration,
          verifiedManifest,
          policy,
        ),
      /non-blank phones/,
    );
  }
});

test("encoder and lexicon phone inventories must match", () => {
  assert.throws(
    () =>
      scoreConstrainedPronunciation(
        [
          { "<blank>": 0.05, b: 0.9, a: 0.03, L: 0.02 },
          { "<blank>": 0.05, b: 0.02, a: 0.9, L: 0.03 },
          { "<blank>": 0.05, b: 0.01, a: 0.04, L: 0.9 },
        ],
        ballLexicon,
        calibration,
        verifiedManifest,
        policy,
      ),
    /does not include l/,
  );
});

test("a calibration artifact is bound to the verified dataset manifest", () => {
  const score = scoreConstrainedPronunciation(
    [
      frame(0.05, 0.9, 0.03, 0.02),
      frame(0.05, 0.02, 0.9, 0.03),
      frame(0.05, 0.01, 0.04, 0.9),
    ],
    ballLexicon,
    { ...calibration, datasetManifestHash: "f".repeat(64) },
    verifiedManifest,
    policy,
  );

  assert.equal(score.evidence.calibrated, false);
  assert.equal(score.evidence.ambiguous, true);
});

test("ambiguous evidence never carries an error-family claim", () => {
  const score = scoreConstrainedPronunciation(
    [
      frame(0.05, 0.9, 0.03, 0.02),
      frame(0.05, 0.02, 0.9, 0.03),
      frame(0.9, 0.03, 0.04, 0.03),
    ],
    ballLexicon,
    { ...calibration, validated: false },
    verifiedManifest,
    policy,
  );

  assert.equal(score.evidence.ambiguous, true);
  assert.equal(score.evidence.likelyError, undefined);
});

test("even a valid-looking calibration fails closed without its verified manifest", () => {
  const score = scoreConstrainedPronunciation(
    [
      frame(0.05, 0.9, 0.03, 0.02),
      frame(0.05, 0.02, 0.9, 0.03),
      frame(0.05, 0.01, 0.04, 0.9),
    ],
    ballLexicon,
    calibration,
    undefined,
    policy,
  );

  assert.equal(score.evidence.calibrated, false);
  assert.equal(score.evidence.ambiguous, true);
});
