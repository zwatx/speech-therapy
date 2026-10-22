# Fixed short-speech segmentation comparison

Declared September 27, 2026 before this comparison or inference on the fresh
environmental extension. The previous default detector retained all corpus
utterances but withheld five of seventeen estimated word crops. Each withheld
crop first crossed the speech threshold with less than 250 ms remaining.

## Exactly two policies

Compare the unchanged official 250 ms minimum-speech rule against one fixed
**100 ms minimum-speech** rule. Keep the same pinned Silero model, 0.5 speech
threshold, 0.35 negative threshold, 100 ms minimum silence, 30 ms padding,
unlimited maximum duration, and all other original settings. The comparison
is strictly greater than the minimum duration. No fitting, probability
threshold adjustment, additional duration grid, or outcome-based replacement
is permitted in this study.

The 100 ms choice is informed by the observed short-crop failures and the
adapter's minimum supported recording duration. It is a development choice,
not an independently selected or clinically established constant. Do not
claim independent validation on previously observed data.

## Data and computation

Reuse all saved probabilities from the complete VAD-v1 study: 2,495 corpus
utterances, twelve previously observed environmental recordings and three
synthetic negatives. Reuse all seventeen crop probability sequences from
vad-crops-v1 (23 target positions, sixteen sounds, five children). Verify the
original reports and declared inputs using their existing hash chains and
reproduce the original 250 ms decisions before comparing the 100 ms rule.
Do not rerun acoustic inference for these recordings. No human ratings are
transferred from utterances to crops.

Additionally evaluate all 24 recordings in the separately predeclared
[environmental extension](multiphone-environment-extension-protocol.md): four
fold-four ESC-10 recordings per fixed nonhuman category, with distinct original
source IDs excluding every previous source. Selection uses metadata only,
before audio download or inference. Preserve full five-second waveforms and
the pinned conversion/attribution chain. These clips are fresh to this
experiment; upstream pretrained-model overlap is unknown, and category labels
do not establish absence of incidental speech.

The initial fold-two proposal was infeasible: it contained only two distinct
helicopter sources. Fold three had three; fold four was the first single fold
with at least four sources in every category. This metadata-only revision was
made before downloading or evaluating any extension audio.

Run the same frozen VAD once per fresh waveform on CPU with two threads and
the approved runtime. Apply both segmentation policies to exactly the same
saved frame probabilities and true audio length. Preserve recurrent state
within a recording and reset between recordings using the tested helper.
Do not run new CTC or pronunciation-head inference on the fresh extension.
Report only VAD decisions there, not an unmeasured combined-gate result.

## Declaration, reporting and verification

Bind this protocol, comparison source/tests, both historical reports and
plans, fixed model/helper/runtime, extension plan and every new waveform before
inference. Use fresh outputs, save each new result durably, and preserve
failures without implicit retries. Integrity or execution failures must not
be reported as successful abstentions. Require exact recording coverage,
finite bounded probabilities, expected frame count, valid interval geometry,
and reproduction of every historical baseline decision.

Report each rule and its conjunction with the previous phone-evidence gate
on cached inputs where that decision is known. For the corpus, retain all
23-phone, child/all-age, rare-rating-position and vote denominators. For crops,
report every word and its target identities without rating labels. Show each
fresh environmental clip and category, total retention/rejection, and changes
between the two rules. No population accuracy or confidence interval is
justified by this small purposive sample. The shortened minimum cannot be
called an improvement solely because it retains more crops; any environmental
acceptances remain visible.

A separate verification process must reconstruct both sets of intervals and
every table from saved probabilities, verify all bindings, and compare the
stored report. Independent read-only review is required. Prior research
sources, reports and bundles stay unchanged; no learner-feedback or app default
changes follow automatically. Further representative short-speech and child
SSD evidence remains necessary.
