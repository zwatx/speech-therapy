# Context of target positions outside detected speech

Most zero-center cases lie before the detector's first segment: 432 of 623
under the fixed 100 ms rule. Of these 432, 397 are the prompt's first canonical
phone and 375 have all five corpus ratings equal to 2. Children ages 6–12
account for 234 of those before-first cases, including 213 prompt-first phones
and 210 all-top positions. This identifies where the mismatch concentrates;
it does not establish that either the alignment or detector is wrong.

The [declared follow-up](multiphone-position-context-protocol.md) reuses the
completed [overlap study](multiphone-position-overlap-report.md): all 28,227
positions, 2,500 recordings, 125 speakers and all 23 consonants. No new acoustic
inference or model fitting occurred. These are previously examined author-training
data, not an independent validation set.

## Exhaustive category counts

“Before”, “after” and “gap” refer to padded detector segments, not verified
utterance boundaries or silence. A zero-center position has no occupied CTC
frame center inside any segment. Categories use exact half-sample coordinates,
retain the existing 30 ms padding and do not select a distance cutoff.

| Policy / age | Inside a segment | Before first | After last | Internal gap | No segments | Segment between centers |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 100 ms, all ages | 27604 | 432 | 18 | 173 | 0 | 0 |
| 100 ms, 6–12 | 9578 | 234 | 14 | 65 | 0 | 0 |
| 250 ms, all ages | 27584 | 450 | 26 | 167 | 0 | 0 |
| 250 ms, 6–12 | 9569 | 248 | 18 | 56 | 0 | 0 |

All-top positions remain common in every nonempty zero-center category. Under
100 ms they account for 375/432 before-first, 14/18 after-last and 135/173
internal-gap positions. Child counts are 210/234, 12/14 and 55/65, respectively.
Seventeen of the eighteen after-last positions are the prompt's final phone.
These prompt identities do not prove what was spoken or where it occurred.

Distances below are the minimum from any occupied-frame center to any padded
segment, with the exclusive endpoint interpreted as a distance infimum. They
are detector distances, not temporal alignment errors. A distance of zero means
at least one center is inside; a missing distance would mean no segments.

| 100 ms population | Count | Median distance (ms) | 90th percentile (ms) | Maximum (ms) |
| --- | ---: | ---: | ---: | ---: |
| All ages, all zero-center | 623 | 25.53 | 109.53 | 1573.53 |
| All ages, before first | 432 | 25.53 | 113.53 | 1573.53 |
| All ages, after last | 18 | 28.47 | 136.87 | 174.47 |
| All ages, internal gap | 173 | 25.53 | 89.53 | 1029.53 |
| Ages 6–12, all zero-center | 313 | 29.53 | 141.48 | 1573.53 |
| Ages 6–12, before first | 234 | 29.53 | 153.53 | 1573.53 |
| Ages 6–12, after last | 14 | 46.47 | 140.07 | 174.47 |
| Ages 6–12, internal gap | 65 | 37.53 | 104.31 | 529.53 |

The median is close to a detector boundary, but the long-distance cases prevent
treating the entire mismatch as a small timing offset. Neither these distances
nor top corpus ratings independently verify the target's true articulation time.
The saved report retains original/added, 13-plus and every phone's full tables.

## Existing alignment warnings

The fewer-than-two-frames warning occurs in 25,769 of all 28,227 positions
(91.3%), including 25,187 of 27,604 positions with a center inside VAD output.
It occurs in 582 of 623 zero-center positions (93.4%). For children it occurs
in 8,990/9,891 overall and 296/313 zero-center positions. A one-frame canonical
state is therefore broadly common here; its presence alone does not identify
a bad alignment or justify discarding a training example. The saved fixed
pooling window includes neighboring frames, and contextual encoder support is
wider still.

The existing target-not-argmax warning appears in 8,282/28,227 overall and
236/623 zero-center positions. Among children, the counts are 2,637/9,891 and
99/313. Under 100 ms the median target-token posterior is .77687 in the
zero-center group; the child median is .86948, compared with .86584 for child
positions having a center inside. These are recognizer posteriors at forced
canonical states, not probabilities of pronunciation correctness. Neither
warning is newly tuned, and neither establishes verified timing error.

All thirteen original scalar values and diagnostic flags remain in every
saved row. Mapping caveats are preserved at recording level; a caveat elsewhere
in an utterance is not attributed to each target. Word-first/last and
prompt-first/last indicators are separate and can overlap.

## All supported consonants, 100 ms rule

The table shows every phone, including zero counts. Full five-vote, distinct
speaker/clip, original/added and age support remains in the JSON; the categories
partition positions, while distinct speakers and clips can occur in several
categories and must not be added.

| Phone | Before first | After last | Internal gap | Child before first | Child after last | Child internal gap |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| B | 13 | 0 | 3 | 10 | 0 | 2 |
| CH | 3 | 0 | 1 | 0 | 0 | 0 |
| D | 11 | 5 | 4 | 7 | 4 | 2 |
| DH | 38 | 0 | 2 | 14 | 0 | 0 |
| F | 22 | 0 | 18 | 17 | 0 | 8 |
| G | 1 | 0 | 3 | 1 | 0 | 3 |
| HH | 123 | 0 | 33 | 44 | 0 | 7 |
| JH | 9 | 0 | 1 | 8 | 0 | 1 |
| K | 31 | 2 | 23 | 21 | 2 | 8 |
| L | 9 | 0 | 5 | 9 | 0 | 3 |
| M | 1 | 0 | 0 | 0 | 0 | 0 |
| N | 14 | 0 | 7 | 10 | 0 | 5 |
| NG | 0 | 0 | 0 | 0 | 0 | 0 |
| P | 23 | 1 | 19 | 8 | 1 | 4 |
| R | 1 | 0 | 0 | 1 | 0 | 0 |
| S | 31 | 0 | 7 | 22 | 0 | 3 |
| SH | 28 | 0 | 1 | 10 | 0 | 0 |
| T | 52 | 9 | 36 | 36 | 6 | 15 |
| TH | 5 | 0 | 1 | 4 | 0 | 0 |
| V | 3 | 0 | 1 | 2 | 0 | 1 |
| W | 10 | 0 | 8 | 7 | 0 | 3 |
| Y | 3 | 0 | 0 | 2 | 0 | 0 |
| Z | 1 | 1 | 0 | 1 | 1 | 0 |

## Verification and next decision

Ten focused tests passed. Before declaration, independent review also passed
3,000 synthetic classification/distance checks covering all six categories,
including 46 segment-between-center cases. The actual calculation and offline
reconstruction both completed with exit zero. Independent saved-artifact and
narrative review passed: 7,677 pins covering 7,626 unique bindings; all 56,454
category/gap/distance records; 28,227 context rows; 366,951 scalar values; and
2,500 recording-level caveats. Separate aggregation reproduced all 432 cells,
3,456 support views and 13,824 numeric summaries. Independent quantiles used
sorted linear interpolation with a 1e-13 comparison tolerance. The
[independent audit](../../work/position-context-audit-20260927/verification.json)
has SHA-256 `539c7a390082edb2c0682f0dcca11dd41b6b9fe643a87bb1980f23491e52d8f2`.

Keep the current exploratory whole-recording filter and retain all training
positions. Close this bounded target-local VAD investigation without a distance,
padding or confidence-threshold search. The available evidence does not support
a new per-position rejection rule. Learner judgments remain disabled.

The next model-quality direction is a bounded probability-calibration experiment
using existing speaker-separated inner development predictions, with all settings
frozen before outer evaluation. Earlier [rating reliability evidence](multiphone-rating-reliability-protocol.md)
shows opposing average lower-rating biases in all-age and child-only models.
That is a reason to test a correction, not evidence that it will help; speaker
isolation, rare-vote ranking and every phone's support must remain visible.
No outer outcomes may fit the correction, and these reused development folds
cannot establish clinical calibration.

No new data, author-test access, model inference, training, threshold fitting or
Colab allocation occurred in this diagnostic. App builds and UI tests were not
run because app behavior did not change. The research bundles are unchanged.

- [Declaration](../../research/audio-head/outputs/multiphone-20260927/position-context-v1/plan.json): `cc392ee583b66622b23d3bfe5df81aaccabc705964f77bdd55488e88b26e600e`.
- [Complete report](../../research/audio-head/outputs/multiphone-20260927/position-context-v1/report.json): `f8ef87eecb6f1986cf17c3ba32a1b9aa578032b015c0288b162bffaa4c01ea92`.

Replay all saved calculations without inference, from `research/audio-head`:

```sh
.venv/bin/python -m position_context.study verify \
  --plan outputs/multiphone-20260927/position-context-v1/plan.json \
  --plan-sha256 cc392ee583b66622b23d3bfe5df81aaccabc705964f77bdd55488e88b26e600e
```
