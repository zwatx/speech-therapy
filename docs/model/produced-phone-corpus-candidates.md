# Produced-phone corpus candidates for the /ɹ/ research head

Source check: September 23, 2026. No new candidate corpus was downloaded or
trained on in this assessment. The existing pinned SpeechOcean training
metadata was audited locally; candidate-corpus labels were not inspected.

September 26 update: the current [multi-target study](multiphone-training-plan.md)
now trains rating models for 23 consonants, including /Z/, on a newly locked
125-speaker map. The earlier /Z/ counts and proposed experiment below remain
historical context. This expansion does not create produced-phone labels.

The already pinned [SpeechOcean762](https://openslr.org/101/) metadata has a
limited `pronounced-phone` note for averaged phone scores below 0.5, as its
[authors' guide](https://github.com/jimbozhang/speechocean762#the-mispronunciations-block)
explains. The locked one-`R` author-training audit found 49 such notes in 766
clips, including only five child-band clips. Note presence duplicates the
existing score threshold and does not supply manual /R/ times or complete
produced-phone transcriptions. The research-only full-clip rating fit therefore
remains the honest use of this source. The original OpenSLR release is CC BY
4.0; a repackaged dataset card's license tag does not replace those terms.

An author-**train-only** check of other SpeechOcean rating targets found no
clearer phone-model training set. Selecting utterances with exactly one
canonical `Z` yields 841 clips from 125 speakers and 148 target words
(sorted-ID SHA-256
`55b3154694769d1398490cc47c9591e7ec917a57eaeb749ec7e67185d78ab571`).
The five expert scores total 254 zeros, 585 ones, and 3,366 twos; 516 clips
have mixed rater judgments. `IS` and `WAS` alone account for 459 clips. With
the existing five seeded speaker folds and an exact target-word purge, only
129–159 clips remain in each outer fit and 79–106 in each inner fit. The
existing paired frozen-feature caches cover only 291 of the 841 training
clips. A future `/Z/` full-clip *rating-distribution* probe could test an
exploratory question after locking lexical/capture controls and extracting
the remaining features, but these labels still give neither actual produced
phones nor verified target times. No `/Z/` head was fitted or published-test
score decoded in this audit.

## Concrete phone-level research candidate: L2-ARCTIC

[L2-ARCTIC v5](https://psi.engr.tamu.edu/l2-arctic-corpus/) is the clearest
available next *engineering* experiment. Its official
[documentation](https://psi.engr.tamu.edu/l2-arctic-corpus-docs/) reports 24
non-native English speakers and 3,599 manually annotated prompted utterances;
v5 separately adds a small annotated spontaneous-speech subset. The
manual TextGrids contain corrected word and phone boundaries. Their phone tier
distinguishes the canonical phone from the perceived phone for substitutions,
and explicitly marks deletions and additions. This is materially different
from the canonical-only phone sequence or whole-clip rating used in the current
SpeechOcean work. Only the `/annotation` TextGrids have these reviewed labels;
the much larger `/textgrid` directory contains forced alignments.

The corpus page states [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/)
and requires a name, email, affiliation, and license agreement before sending
a Google Drive link. Its initial-release
[paper](https://psi.engr.tamu.edu/wp-content/uploads/2018/08/zhao2018interspeech.pdf)
describes university-recruited speakers aged 22–43; the current v5 page does
not establish a child SSD cohort. The public documentation does **not** give
the number or class balance of manually annotated target `R` phones. These
facts make it a conditional, local noncommercial method benchmark, not
evidence for child /ɹ/ feedback, commercial reuse, or a usable /ɹ/ classifier.

A public [processed L2-ARCTIC (Perceived) rehost](https://huggingface.co/datasets/changelinglab/l2arcticperceived-pr/blob/main/README.md)
does not remove that access and rights gate for this experiment. Its card's
machine-readable tag says CC BY 4.0, while the same card's prose and the
[original corpus page](https://psi.engr.tamu.edu/l2-arctic-corpus/) say CC BY-NC
4.0. The rehost exposes `id`, audio, and a concatenated IPA transcript, but no
corrected phone intervals or error tags. Do not infer broader rights from the
conflicting tag or substitute that transcript for the reviewed target-localized
labels.

An [official example annotation](https://psi.engr.tamu.edu/wp-content/uploads/2018/03/lxc_arctic_a0018.txt)
contains a timed `R,AH0,s` substitution, so the manual tier can express a
relevant error. That example does not establish usable v5 counts. The gated
archive's own LICENSE, README, and any separate access terms have not been
reviewed; inspect them before importing audio or fitting a head. The
[CC BY-NC legal code](https://creativecommons.org/licenses/by-nc/4.0/legalcode.en)
turns on the purpose of the use, so a commercial product-development study or
later weight distribution needs a separate rights decision even if the fit is
run locally.

After access and intended-use review, the first bounded experiment would:

1. Record the intended use and access holder; review the exact archive terms.
   Pin the archive/version, WAV and TextGrid hashes. Audit only
   manual annotations for canonical `R` and related rhotic contexts, their
   speaker counts, correct/error balance, interval validity, and uncertain
   `err` or deviation tags. Stop the /ɹ/ experiment if coverage is too small.
2. Lock speaker-disjoint development and untouched test sets before fitting.
   Keep repeated CMU ARCTIC prompts and the shared 100 annotated sentences
   from acting as an unmeasured shortcut; report a prompt-only baseline and
   the possibility of overlap with encoder pretraining.
3. Compare a small frozen-encoder head using verified target intervals with a
   whole-utterance head and prompt/capture controls. Report error-type and
   rhotic-context results, abstentions, and speaker uncertainty. Keep every
   output in private research storage under the applicable terms.

## Additional adult manual-transcript leads

The [GMU Speech Accent Archive](https://accent.gmu.edu/howto/) is a stronger
adult-English *sequence* lead than an automatic alignment: each speaker reads
the same elicitation paragraph, and the archive says 2–4 phonetically trained
judges transcribe perceived segments in IPA. The paragraph contains several
rhotic contexts. [Audio and available text transcriptions](https://accent.gmu.edu/download/)
are public through OSF, but the archive states **CC BY-NC-SA 4.0** for both;
not every recording has a transcription. The public pages do not provide
verified phone times, error tags, or a child SSD population. A metadata-only
inventory of transcription coverage and rhotic conventions is worthwhile,
but a local fit needs an intended-use rights determination first. The single
fixed paragraph also requires a speaker-disjoint split and lexical baseline;
sentence content alone cannot establish target-error detection. No archive
media or transcriptions were downloaded in this assessment.

[Tusom2021](https://github.com/dmort27/tusom2021) publishes audio and manually
checked narrow phonetic transcriptions, but its
[authors' paper](https://www.isca-archive.org/interspeech_2021/mortensen21_interspeech.pdf)
describes one adult East Tusom speaker. The repository's
[MIT file](https://github.com/dmort27/tusom2021/blob/main/LICENSE) describes
software and associated documentation without explicitly granting WAV and
annotation reuse. It is not an English child /ɹ/ cohort and cannot support a
speaker-disjoint evaluation; do not weaken the current manifest to fit it.

## Closer population, missing part of the required label pair

September 26 recheck: the official Preston, PERCEPT-R, PERCEPT-GFTA, PhonBank
access, and TalkBank usage pages still describe the constraints below. Official
transcript links returned no readable dataset content in this session; no
account, media, transcript, or alternate access route was obtained. Candidate
versions and their actual schemas therefore remain unverified locally.

The [PhonBank Preston corpus](https://talkbank.org/phon/access/Clinical/Preston.html)
has 44 American English children aged 4–5 with speech sound disorders and
single-word probes targeting all English sounds. Its page says a trained
transcriptionist completed phonetic transcriptions, but does not establish
manually reviewed *phone times* or enough /ɹ/ examples. It merits a
transcript-tier and provenance audit after access, not an assumed segment
training set. PhonBank media and transcripts require
[registration](https://talkbank.org/phon/access.html), and the default
[TalkBank rules](https://talkbank.org/0share/rules.html) are CC BY-NC-SA 3.0
with explicit limits on commercial model use.

[PERCEPT-R](https://talkbank.org/phon/access/Clinical/PERCEPT-R.html) directly
covers American English child rhotics and perceptual accuracy, but explicitly
uses ratings in lieu of actual-production IPA transcriptions.
[PERCEPT-GFTA](https://talkbank.org/phon/access/Clinical/PERCEPT-GFTA.html)
likewise says actual-production IPA has not been obtained. Both can answer
different rating questions, not the produced-phone training question.

[UltraSuite UXSSD](https://ultrasuite.github.io/data/uxssd/) includes child SSD
speech and some therapist labels, but its phone labels are automatic; even
its small reference set revised speaker/word boundaries rather than every
phone. The repository's [CC BY-NC 4.0 terms](https://ultrasuite.github.io/)
also limit reuse. The [STAR child speech-error examples](https://www.seeingspeech.ac.uk/speechstar/disordered-speech-errors-database/?type=prompt)
show target/actual transcriptions, including /r/ errors, but describe central
Scottish targets as unsuitable for other English accents and do not establish
downloadable, licensed phone-time training data.

**Decision:** L2-ARCTIC can test whether the target-localized method works on
real manual phone-error labels if its use and /ɹ/ coverage checks pass. It
cannot close the child SSD data and licensing gap. The prepared SpeechOcean
two-reviewer interval pilot and a separately governed child-corpus audit
remain necessary before any learner-facing /ɹ/ decision.
