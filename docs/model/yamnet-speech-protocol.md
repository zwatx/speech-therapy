# Fixed YAMNet speech-evidence comparison

Declared before corpus or challenge inference, September 27, 2026. Test one
different event-classification model as a whole-recording input check for the
ages-6–12 research pipeline. No pronunciation-model fitting or learner changes.

## Frozen detector and inputs

Use Google's YAMNet source commit
`c14bf9ad91962cf189f9f58db2132c06247fcd53` and original official HDF5 weights.
Preserve Apache-2.0 source/license and the verified weight manifest. Use an
isolated TensorFlow/tf-keras CPU environment with two threads. Preserve the
complete 16-kHz mono PCM16 waveform, divide integers by 32768, and use upstream
padding only. No gain normalization, resampling, trimming or model adaptation.

The only candidate rule is **maximum Speech class-0 score across windows >=
0.5**. Confirm class MID `/m/09x0r`. Do not substitute child-speech scores,
combine event classes, veto dog scores or search thresholds. Save all 521
scores. These uncalibrated outputs are event scores, not speech probabilities.
Upstream windows require 15,600 waveform samples with 7,680-sample hops after
padding; short-word retention is a specific risk.

Include every one of the 1,037 original author-training child recordings:
52 children ages 6–12 and 5,654 original eligible consonant positions, all 23
phones. Exclude older speakers from the new retention experiment. Include all
17 previously studied estimated word crops as a separate regression panel;
do not transfer whole-utterance ratings to crops or treat them as new natural
isolated-word recordings. Include all 36 known ESC-10 challenges and the three
known synthetic cases. Preserve the existing 100-ms Silero/phone-evidence
conjunction B from its hash-bound reports, with waveform identity checks.

Acquire exactly 24 additional ESC-10 clips from commit
`33c8ce9eb2cf0b1c2f8bcf322eb349b6be34dbb6`: in order dog, rain, sea_waves,
crackling_fire, helicopter, chainsaw, choose the first four lexicographic fold-5
filenames with distinct source IDs, excluding all 36 previously used source
IDs globally. Declare selection before downloading audio. Preserve metadata,
CC BY 3.0 terms and each source attribution, original five-second 44.1-kHz
PCM16 audio and complete unnormalized 16-kHz conversions. No replacement after
listening or inference. These are new source-disjoint challenge recordings,
not known to be disjoint from pretraining or representative of home recordings.

## Comparison and reporting

For child utterances and known regression panels compare B, YAMNet Y and B AND
Y. For the fresh 24 report **Y alone**; B and B AND Y are explicitly unmeasured
there. This bounded experiment does not run another CTC/Silero acoustic pass.
Report every challenge individually and category totals, keeping known and
fresh separate. Environmental categories do not establish absence of speech;
without independent blinded speech-presence annotations, call these admissions
by category rather than false-acceptance or rejection-accuracy estimates.

For children, report total/retained recordings, children, positions and all
five-vote rating supports; retain all 23 phones and ages 6–12 separately. List
every newly withheld recording and its support. For crops report every decision
and original sample length separately. Do not count withheld low-rated speech
as correctly detected pronunciation errors. Whole-recording acceptance does
not establish prompt compliance or speech at every requested target.

Any loss of previously retained child recordings or word crops prevents
adoption under this experiment. Even complete retention plus fewer known
challenge admissions would justify further independent validation only.
No threshold changes, alternate candidates or automatic release follow results.
Learner, clinical and promotion eligibility remain false. Missing younger-age
evidence is outside current scope.

## Execution and verification

Pin sources, tests, protocol, installed versions, vendor manifest, all audio,
prior reports and cohort before real-audio inference. Review the implementation
independently. Synthetic setup smoke checks do not select settings. Require
fresh output directories, record each completed clip durably, and preserve
partial evidence on failure. Check hash, PCM geometry, finite float32 scores,
window count and exact coverage. Errors are failures, never abstentions.
Repeat the first declared recording after intervening recordings and require
identical scores. Reconstruct decisions/tables from saved scores in a separate
pass; independently verify the artifacts and conclusions afterward.

Primary-source rationale, license evidence, API constraints and metadata-only
fresh-source feasibility are in the [research memo](../../work/input-quality-next-20260927/RECOMMENDATION.md).
