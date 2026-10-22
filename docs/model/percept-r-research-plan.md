# PERCEPT-R research preflight

Status: source assessment only, September 23, 2026. No PERCEPT-R media or
transcripts have been downloaded, and no model has been trained on this corpus.

## Why this source matters

[PERCEPT-R](https://talkbank.org/phon/access/Clinical/PERCEPT-R.html) is closer
to the intended child /ɹ/ population than SpeechOcean762. The public corpus
contains isolated syllables, words, and some phrases from 280 participants,
mostly ages 6–17, including speakers with residual speech-sound disorders.
Its records have at most one target rhotic and include listener ratings of
rhotic accuracy. That supports a **word-level rating** research task. The
corpus explicitly does not transcribe each participant's actual phone
production, so it cannot supply produced-phone CTC targets or verified /ɹ/
boundaries. Ratings came from different listener groups across component
studies; they cannot be assumed interchangeable without auditing that field.

The [corpus research note](https://pmc.ncbi.nlm.nih.gov/articles/PMC12510240/) describes
the public `p` release as limited to minors with parental consent and child
assent for outside-study audio sharing, or adult participants with their own
consent. The
[signed distribution form](https://talkbank.org/phon/permissions/Clinical/PERCEPT-R.pdf)
lists no additional contributor restrictions, while the research note calls
the PhonBank distribution noncommercial. Until the precise access and use
terms for the acquired version are recorded, treat all media, derived features,
and weights as **local, noncommercial research assets**. Do not combine the
public release with a paper's private extension. PhonBank says transcripts
and media require [registration](https://talkbank.org/phon/access.html); this
plan does not bypass that access step.

## Acquisition gate

> **Access note (2026-09-30):** the official corpus and PhonBank access pages require only free TalkBank/PhonBank registration and login, plus citation of a corpus paper. The linked distribution PDF records the contributors' permission; users do not sign it. Unauthenticated download links return a login prompt.

1. An authorized project member registers with PhonBank and records the exact
   public corpus version, access date, applicable terms, required corpus paper
   citation, and PhonBank grant acknowledgment. The corpus page currently
   requires at least one relevant paper citation; the
   [PhonBank index](https://talkbank.org/phon/access/) also asks users to
   acknowledge NIH-NICHHD RO1-HD051698.
2. Save source files only in an ignored, access-controlled local research
   directory. Record file SHA-256s and a source manifest before parsing or
   filtering. Do not add child audio, transcripts with participant metadata,
   cached embeddings, or fitted weights to Git or product bundles.
3. Audit the acquired version's parser and fields before choosing a model:
   participant/study/session identity, target prompt and rhotic context,
   individual versus aggregate ratings, rater type, recording duration,
   missing data, and duplicated media. Confirm that all selected records
   belong to the public consent-cleared release.

## First locked experiment after access

Predict the available listener-rating distribution for a whole target-word
recording. Preserve rater counts and disagreement; do not convert an average
to a fabricated produced-phone transcript. Pin a participant-disjoint
development/test split before audio feature extraction. Group repeated visits
and treatment sessions from the same participant, and check identical decoded
audio across partitions. If identifiers cannot safely establish this split,
stop rather than report an apparent held-out score.

Compare a train-fold rating-prior baseline, a target-word/rhotic-context
baseline, and a small head on frozen open-weight speech features. Select
hyperparameters only within development speakers. Report per-rating log loss
and multiclass Brier score alongside disagreement and clearly sized speaker
subgroups. A participant-cluster uncertainty analysis can describe the fixed
held-out predictions; it cannot replace uncertainty from fitting and model
selection. Keep any one independent test partition untouched until the recipe
and exclusions are locked. Model outputs remain research-only regardless of
which candidate wins.

The separate [SpeechOcean annotation pilot](r-target-annotation-plan.md)
continues to answer a different question: whether qualified reviewers can
provide dependable target-word and /ɹ/ intervals. PERCEPT-R's shorter word
clips may reduce localization difficulty, but its existing ratings do not
remove the need for verified boundaries or clinician review before segment
feedback is considered.
