# Child pronunciation data: practical next options

Source check: **September 26, 2026**. This is a public-documentation assessment,
not an acquired-data audit. No child audio, transcripts, dataset archives, or
model weights were downloaded; no registration, contact, submission, or training
was performed. It extends the earlier
[produced-phone survey](produced-phone-corpus-candidates.md) and
[PERCEPT-R preflight](percept-r-research-plan.md).

**Recommendation:** pursue a small, rights-cleared audit of original **Preston
and Cummings** annotations for English child speech-sound-disorder (SSD)
research. **TinyVox** is a substantial new route to child phone recognition,
but its noncommercial terms and normalization need explicit treatment. None of
the sources reviewed establishes an unrestricted, immediately usable corpus
covering ages 2–12, English SSD errors, verified phone boundaries, and commercial
Cadence deployment rights together. Running locally does not itself settle use
rights.

## What each label can establish

Keep four different fields separate in any future manifest: intended/canonical
phone, perceived produced phone, auditory correctness judgment, and manually
reviewed acoustic interval. A produced-phone sequence can train recognition
with CTC without phone times. It does not automatically supply a clinical
correct/incorrect label. Conversely, a correctness rating does not identify the
substituted sound. Automatic alignment is an estimated localization, even when
the transcript is human-authored.

## Best population and annotation matches

| Source | Population and available evidence | Access and next use |
| --- | --- | --- |
| **Preston** | 44 monolingual American English children aged 4–5, all with clinician-identified SSD. A 125-picture naming probe samples English sounds across word positions. An SLP transcribed productions and categorized typical/atypical changes and distortions. The public description does not establish verified phone times or released per-token error-code coverage. [Corpus](https://talkbank.org/phon/access/Clinical/Preston.html) | PhonBank registration and terms below. Strongest small first audit for target/actual sequences and distortion preservation; inspect the acquired schema before promising labels. |
| **Cummings** | About 30 English-speaking children with SSD aged 3–7; repeated pre/post-treatment and intermediate single-word probes. The linked four-child study used trained narrow-IPA transcription; that paper alone does not establish every field across the larger release. [Corpus](https://talkbank.org/phon/access/Clinical/Cummings.html), [original study, methods](https://talkbank.org/phon/access/Clinical/0docs/cummings2011.pdf) | Same PhonBank terms. Useful extension below age 4 and across treatment; all visits from one child must remain together. The [source index](https://talkbank.org/phon/access/Clinical/) says 3–6, while the detailed page says 3–7: use verified record ages. |
| **Torrington Eaton** | Corpus page lists 51 children aged 4;0–5;11, including SSD and typical-development groups, with naming, nonword repetition, and play tasks. The study describes broad Phon transcription of naming responses; some diacritics were recorded, but its PCC-R measure counted within-category distortions as accurate. [Corpus](https://talkbank.org/phon/access/Clinical/TorringtonEaton.html), [study, speech production methods](https://talkbank.org/phon/access/Clinical/0docs/eaton2016.pdf) | Same PhonBank terms. A possible cross-corpus comparison after checking participant independence and actual tier coverage. Do not equate PCC-R with distortion-sensitive correctness. |
| **PERCEPT-R / PERCEPT-GFTA** | PERCEPT-R lists 280 participants, mainly ages 6–17, including rhotic SSD and typical speech. It has rhotic listener ratings **instead of actual-production IPA**. PERCEPT-GFTA also states actual-production IPA has not been obtained. [PERCEPT-R](https://talkbank.org/phon/access/Clinical/PERCEPT-R.html), [PERCEPT-GFTA](https://talkbank.org/phon/access/Clinical/PERCEPT-GFTA.html) | Same PhonBank terms; existing [preflight](percept-r-research-plan.md) covers the consent-cleared public release. Useful for a separate rhotic-rating task, not broad produced-phone training. |
| **UltraSuite** | Scottish-English UXSSD: 8 children aged 5–10; UPX: 20 aged 6–13; UXTD: 58 typically developing children aged 5–12. SLT annotations cover some target intervals, but distributed `phone_labels` are automatic. Even reference phone labels are forced-aligned within revised word boundaries. [UXSSD](https://ultrasuite.github.io/data/uxssd/), [UPX](https://ultrasuite.github.io/data/upx/), [UXTD](https://ultrasuite.github.io/data/uxtd/) | Public repository, **CC BY-NC 4.0** data; Apache-2.0 code does not relicense recordings. Could support an interval/annotation audit after intended-use review. [Terms](https://ultrasuite.github.io/#license) |

UltraSuite's later **UX2020** release adds 37 English-speaking children aged
5–12 who consented to sharing, out of 43 recorded. It lists optional manual SLT
TextGrids but does not promise complete produced-phone labels. Its ultrasound
hardware synchronization failed, which matters for multimodal use.
[Official UX2020 description](https://ultrasuite.github.io/data/ux2020/).
The original UltraSuite paper explicitly distinguishes limited SLT word/phone
annotations from automatic alignment and says it did not provide speech
transcriptions for UXSSD/UPX. It also reports excluding participants without
guardian consent. [Original paper, sections 2–4](https://ultrasuite.github.io/papers/ultrasuite_IS18.pdf).

## TinyVox: meaningful new training path, with boundaries

The [official PhonBank release page](https://talkbank.org/phon/access/Derived/TinyVox.html)
lists **561,312 utterance WAVs**, plus metadata and fixed train/validation/test
tables. The [authors' README](https://github.com/MarvinLvn/tinyvox) describes
560 children, approximately 6 months–8 years, across English, French,
Portuguese, German, and Spanish. Published metadata fields include:

- `phones`: normalized manual phonetic transcript;
- `sentence`: orthographic interpretation where available;
- `onset` / `offset`: **utterance**, not phone, boundaries;
- `age_months`, `language`, `file_activity`, `child_pseudoid`;
- `original_audio_path` and `original_transcript_path` for parent-source lineage.

The [March 2026 paper, section 2.1 and Table 1](https://arxiv.org/html/2603.05213v1#S2.SS1.SSS1)
reports 387.7 hours and includes **Preston (44 children), Cummings (21), and
TorringtonEaton (53)** among its 31 source corpora. These are overlapping source
materials, not independent additional cohorts. The table's derived counts
differ from some current parent pages. Clinical membership and cross-corpus
identity therefore require original-source reconciliation; the published
metadata schema has no explicit SSD-diagnosis field.

The paper maps 967 surface categories into 57 targets, removes unidentified
sounds and ages above 8, and uses a child-disjoint 80/10/10 split. Its small
quality audit found some imprecise/overlapping utterance boundaries. These are
reasons to audit the intended subset, not evidence of phone-time accuracy or
diagnostic validation. The published task is phoneme recognition and
developmental measurement.

The executable [normalization map](https://github.com/MarvinLvn/tinyvox/blob/main/ipa/mapping.py)
confirms that distinctions are collapsed—for example, `ɹ̥` becomes `ɹ` and `s̠`
becomes `s`. **Inference for Cadence:** the normalized inventory can support
coarse recognition but cannot preserve every distortion an SLP may judge.
Retain original IPA tiers and review any target-specific mapping before making
an error-classification dataset.

The [rebuild guide](https://github.com/MarvinLvn/tinyvox/blob/main/REBUILDING.md)
filters automatic transcripts, requires `pho`/`xpho` tiers, and describes
timestamp checks and normalization. Its full-corpus scraper is not a necessary
first step. The [training repository](https://github.com/MarvinLvn/BabAR_training)
provides CTC fine-tuning recipes and uses original recordings for surrounding
context; its example enables external experiment/audio logging. A later local
experiment should use our local-only logging and an explicitly bounded corpus
subset, rather than execute that recipe unchanged.

### Dataset rights and BabAR model rights are separate

TinyVox's author README explicitly says: **“TinyVox cannot be used in commercial
products or services.”** It also excludes training/fine-tuning for commercial
deployment, permits academic/noncommercial development, and specifies
**CC BY-NC-SA 3.0**, attribution, and ShareAlike.
[Exact author terms](https://github.com/MarvinLvn/tinyvox#license-and-usage-restrictions).
A noncommercial research experiment may be feasible after authorized PhonBank
access and confirmation of its intended use. It is not a cleared source for
training Cadence's deployable product weights.

**BabAR has conflicting published license signals.** The
[authors' Hugging Face weight card](https://huggingface.co/MarvinLvn/BabAR/blob/main/README.md)
advertises `license: mit`. The current
[BabAR repository LICENSE](https://raw.githubusercontent.com/MarvinLvn/BabAR/main/LICENSE)
instead contains a custom v1.0 license inherited from BabyHuBERT. It restricts
use and redistribution, includes a commercial benefit-sharing exception, and
requires obligations for creators of derivatives, including community
notification. Its definition of derivatives includes using model activations
or outputs. It explicitly says **“The Data is not licensed under this License.”**
Several definitions still name BabyHuBERT, adding scope ambiguity.

**Decision:** do not resolve this mismatch by choosing the more permissive
metadata tag. Obtain a version-specific determination from the rights holder
before adopting the weights or creating a derivative. No such determination,
notification, or acceptance was obtained in this assessment. Corpus permission
would remain separate even if model permission were clarified.

## Access, consent, and no-cost availability

[PhonBank access policy](https://talkbank.org/phon/access.html) permits public
description browsing; transcript/media access requires email registration and
confirmation. It describes access as open to all, with no purchase listed.
[TalkBank's current rules](https://talkbank.org/0share/rules.html) default to
**CC BY-NC-SA 3.0** unless otherwise indicated and require corpus citations.
They restrict commercial incorporation, redistribution of protected data, and
web processing with retention; identifiable downloaded material must remain on
a local device under their confidentiality rules. The same page contains a
limited algorithm-development allowance for commercial enterprises granted
password access, while disallowing incorporation of the data into models.
That wording does **not** establish an unambiguous product-weight license for
Cadence. Record exact intended use and corpus-specific terms before acquisition.

The [TalkBank ethics policy](https://talkbank.org/0share/ethics.html) ties sharing
to participant rights, confidentiality, and the original consent framework.
Hosting is not evidence that families consented to every downstream commercial
or clinical use. Individual Preston/Cummings/Torrington consent documents were
not reviewed here. Do not publish participant-level examples or send corpus
content to external AI services as part of this project.

Thus **no-cost, local noncommercial research candidates exist**—PhonBank's
original clinical sources/TinyVox and UltraSuite—but access conditions and
use restrictions remain. None has been imported into this campaign.

## Promising lead that is not presently a Cadence data grant

The **On Top of Pasketti phonetic challenge** supplies normalized sequences of
actual child productions, including omissions/substitutions, with child/session
IDs and age buckets from 3–4 upward. It includes typical and disordered U.S.
English speech; normalization and source annotation practices vary. It is not
a set of clinical correctness labels or verified phone intervals.
[Official schema](https://www.drivendata.org/competitions/309/childrens-phonetic-asr/page/979/).

Its [terms](https://www.drivendata.org/competitions/309/) limit data use to the
competition, require encrypted portable storage, prohibit third-party uploads
and unauthorized sharing, and require destruction/return after the competition
without a separate license. The challenge ended April 2026. The
[current owner update](https://www.drivendata.org/competitions/group/childrens-asr-competition/)
says refined open weights and some annotations will be released later; that
announcement is not a present data license. Recheck the eventual release's own
terms before considering it. No enrollment or download was attempted.

**Targeted release check, October 15:** the [organizer's current update](https://www.drivendata.org/competitions/group/childrens-asr-competition/)
still describes open weights and annotations as forthcoming. The linked
[official winners repository](https://github.com/drivendataorg/on-top-of-pasketti)
publishes solution code under MIT; that does not license competition recordings
or establish an independently usable annotation release. The [current track
page](https://www.drivendata.org/competitions/309/childrens-phonetic-asr/)
retains challenge-only data use and post-competition deletion requirements absent
a separate license. The checked pages do not establish a new data route for
Cadence. No enrollment, mailing-list submission, dataset/weight download or
participant material was accessed. This bounded follow-up does not repeat the
broader corpus survey or change existing data exclusions. A later release needs
its own terms and population/annotation audit; code availability cannot validate
child pronunciation corrections.

Two additional leads do not change the immediate recommendation:

[ASMDD's original paper](https://arxiv.org/abs/2111.01136) describes expert
segmental-error annotations from 100 Egyptian Arabic-speaking children aged
2–8, but no independently verified dataset license/consent grant was found in
the public paper page; it also does not provide English evidence.
[AusKidTalk's 2026 methods paper](https://link.springer.com/article/10.1007/s10579-026-09929-5)
describes research-only access through a data custodian, not public release,
and its presented workflow is orthographic transcription. Neither was acquired.

## Concrete next experiment after access and rights are settled

1. **Audit before training.** Pin original source and any derived release,
   terms, hashes, participant/session IDs, actual versus target tiers,
   distortion symbols, and available timestamps. Have the available SLP inspect
   40–60 stratified examples for annotation meaning and boundary usability.
   This is a feasibility review, not a final evaluation cohort.
2. **Choose one task.** Start with produced-phone sequence recognition on a
   bounded English subset using our already pinned encoder and a CTC head.
   Preserve raw IPA; predeclare an SLP-reviewed coarse inventory. Keep auditory
   correctness/error typing as separately annotated outcomes. CTC-estimated
   alignment remains estimated unless reviewers supply interval references.
3. **Protect independent evaluation.** Group all visits and therapy phases by
   child; reconcile aliases across original corpora, TinyVox, and any model's
   training data. Deduplicate decoded waveforms and source intervals. Never
   test BabAR on a PhonBank parent corpus assumed unseen merely because it has
   a different download name. Hold out children and a separate source/site;
   report repeated-word and unseen-word performance separately.
4. **Measure the actual task.** Use phone error rate with substitution,
   deletion, and insertion breakdowns; age/dialect/SSD support; and child-cluster
   uncertainty. For manually timed subsets, report interval error separately.
   No adult norm or dialect difference becomes an SSD label automatically.
5. **Build the deployment evidence separately.** With the SLP, scope a small
   prospectively consented English child cohort that explicitly permits the
   intended model use, preserves rater disagreement, and includes an untouched
   evaluation group. Cover ages 2–5 and 9–12 deliberately: TinyVox alone does
   not span Cadence's intended age range. No recruitment/contact is authorized
   by this document.

The next user decision is whether this branch is deliberately **noncommercial
method research** or intended to produce **deployable Cadence weights**. The
latter needs suitable data/model permission before using these restricted
sources. Existing SpeechOcean experiments can continue independently under
their already documented scope.
