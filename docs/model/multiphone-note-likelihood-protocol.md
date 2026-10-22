# Direct pronunciation-note likelihood diagnostic

Declared September 27, 2026, after a metadata-only note inventory began and
before joining notes to model likelihoods. This is a descriptive development
diagnostic of the fixed recognizer, not a new training or promotion study.

Question: for an explicitly annotated, exact single-phone substitution at an
already exported consonant position, does the recognizer assign greater
complete-sequence CTC likelihood to the noted phone than the canonical phone?
This addresses whether the acoustic evidence distinguishes some real severe
errors, rather than only predicting corpus ratings.

Use only SHA-bound SpeechOcean author-training metadata and the completed
`sequence-features-v1` export. Preserve every note and account for exclusions.
Decode only author-training score objects. The 23 existing supported consonants
define the target inventory. Only exact unstarred single ARPAbet production
notes can enter this comparison. Unknown, approximate, deletion, multi-phone
and unsupported descriptions stay separate; do not invent their semantics.
Missing notes never become correct productions. Do not restrict by model scores.

Join by utterance, word index and phone index, checking canonical identity,
speaker, age, utterance-wide canonical index and original cohort row identity.
The earlier export includes only targets occurring once per utterance, so
repeated-target notes and other absent rows remain explicit exclusions.
Map noted phones through the existing provisional ARPAbet-to-decoder mapping;
retain its vowel, rhotic, flap and lateral limitations. A noted phone mapping to
the same decoder token as the canonical phone is an unresolved comparison,
not a recognizer success. Keep every raw note string.

For each eligible event, read the saved 388 replacement likelihoods and its
canonical likelihood. Verify the source export hash, each consumed clip binding,
candidate identity and finite values. Do not recompute audio or tune mappings.
Retain noted-minus-canonical log likelihood; greater than +1e-8 favors the note,
less than -1e-8 favors the canonical, and the inclusive middle is a tie.
Report the noted token's strict rank (one plus the count of higher likelihoods)
among all 388 non-special replacement tokens, its exact tie count, and whether
it is the unique maximum. Deletion is not included in this rank denominator.

Report all-age, child 6–12, and older-than-12 tables, each with all 23 targets,
including zero-support cells. Include distinct speaker and recording counts,
comparison outcomes, median log-likelihood difference, and unique-maximum counts.
Separate events in utterances with exactly one annotation note from those with
multiple notes: all remaining positions still use the canonical transcript.
Do not transfer these conditional likelihoods to produced-phone truth for an
entire utterance, or interpret them as calibrated probabilities.

No absent-note controls, sensitivity/specificity, detection accuracy, clinical
performance, confidence interval, fitted model, threshold optimization, or
promotion follows from this selected-note-only sample. Labels are selectively
provided for very low average ratings; the analysis cannot measure false
positives or all error types. Previously inspected author-training speakers
remain development data. Author-test remains unopened, learner feedback stays
disabled, and no Colab allocation is required.

Verification: focused tests cover selection/exclusions, exact positional joins,
mapping collisions, finite likelihoods, rank ties and zero-support summaries.
Bind source/tests/protocol and input evidence before the outcome calculation.
Rebuild the result without model inference, and independently audit its raw
note joins, consumed likelihoods and summary tables before reporting findings.
