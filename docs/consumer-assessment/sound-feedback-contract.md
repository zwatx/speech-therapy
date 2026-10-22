# Sound feedback: model-to-app contract

Status: design contract, October 22, 2026. Nothing here is enabled. It defines
what a future mispronunciation-detection (MDD) model must hand the app, and how
the Paper redesign's feedback screen shows it. The model strategy is in
`work/model-strategy-20261022/STRATEGY.md`; the first implementation lives in
`research/audio-head/mdd_v1/`.

## Gate

The app shows sound-level feedback only when a bundled model release carries a
validation record whose pre-registered gates passed for that exact contrast and
age band (precision lower bound ≥ 90%, false-correction upper bound ≤ 5%,
calibrated abstention; see the strategy, §5). Every other case falls back to
today's behavior: listen back, the example, and the optional word check.

A release enables contrasts one at a time, for example `r-initial: [w]`. A
contrast without a passing record never produces a finding, even if the model
emits one.

## Model output for one take

```json
{
  "modelRelease": "mdd-v1.3",
  "prompt": { "word": "rabbit", "canonical": ["R", "AE", "B", "IH", "T"] },
  "usable": true,
  "segments": [
    { "canonical": "R",  "heard": "W",  "event": "substitution", "confidence": 0.94 },
    { "canonical": "AE", "heard": "AE", "event": "match",        "confidence": 0.97 },
    { "canonical": "B",  "heard": "B",  "event": "match",        "confidence": 0.95 },
    { "canonical": "IH", "heard": "IH", "event": "match",        "confidence": 0.91 },
    { "canonical": "T",  "heard": null, "event": "uncertain",    "confidence": 0.41 }
  ]
}
```

- `event` is `match`, `substitution`, `deletion`, `distortion` or `uncertain`.
  The model must emit `uncertain` instead of guessing below its calibrated
  threshold.
- `usable: false` covers silence, clipping, nonspeech and the wrong word. The
  app then shows the existing recording advice, never a sound finding.

## What the child sees

Only the **target sound** of the current practice word can produce a finding.
Other segments never become findings, so practicing /r/ never surfaces an
unrelated vowel.

| Target segment | Gate passed | Screen |
| --- | --- | --- |
| `substitution` with an enabled contrast | yes | The word splits into sounds. The target is underlined in the accent color. Headline: "The R sounded like a W." One articulation tip, then Your try / Example / Try again. |
| `match` | yes | "That R sounded clear." No score, stars or percentage. |
| `uncertain`, `distortion` without a distortion gate, or any other case | yes | "We couldn't tell this time." Listen back and compare with the example. |
| anything | no | Current behavior: listen back, example, optional word check. |

Copy rules: describe the sound, never the child ("The R sounded like a W", not
"You said it wrong"). Recheck progress compares only results produced under the
same gated release.

## Not covered

Disorder diagnosis, severity scores and therapy recommendations need a separate
clinician-referenced study and stay out of the app.
