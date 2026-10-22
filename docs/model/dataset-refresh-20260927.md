# Dataset refresh: actionable additions and remaining label gap

Checked **September 27, 2026**. This extends the earlier
[access assessment](accessible-data-next-step.md) and
[child survey](child-pronunciation-data-options.md) with newer releases and
additional public reference/quality sources. Public documents and a 1.99-MB
reference index were saved; **no audio archive was acquired, no training ran,
and no registration, contact, purchase or agreement submission occurred**.

**Decision:** this bounded search found no newly verified, immediately usable
English child produced-phone/error training corpus within the authorized access
scope. It did identify public acquisition routes for a small English reference
set, child microphone robustness data, and an English speech-quality subset.
These address different tasks; none supplies child error supervision for all
23 Cadence consonants. This is a finding about the checked sources, not a claim
that no suitable dataset exists.

## Priority and exact next acquisition

1. **Smallest concrete reference-data step: OpenSLR83 Midlands female subset.**
   Acquire the publisher-linked
   [103,085,118-byte ZIP](https://openslr.trmal.net/resources/83/midlands_english_female.zip),
   retain the already saved license/index, hash the archive, and inspect the
   member list before extracting. Audit 20 clips initially for transcript/audio
   matching and capture quality. The saved index contains 246 matching rows;
   its two apparent speaker-ID components need confirmation before using them
   as split keys. This is an ingestion/reference pilot, not enough speakers for
   a convincing generalization study. Do not turn dictionary-derived phones
   into perceived-production ground truth.
2. **Child microphone robustness:** acquire the official Kennedy archive below
   only for a predefined cross-microphone stability question, then group every
   microphone version and utterance from one child in the same partition.
   It has no documented phone-error labels, so it ranks below expanding the
   already permitted SpeechOcean supervision for pronunciation learning.
3. **Speech-quality labels:** inspect the official NISQA archive documentation
   and extract only `NISQA_TRAIN_LIVE` for a quality-head pilot; leave validation
   and test audio/ratings unopened until a protocol is locked. Avoid an
   undifferentiated full-corpus training import. The public archive is large
   and its subsets have different rights.

These are next actions, **not acquisitions completed by this report**. Full
archive contents and checksums remain unverified.

## Public acquisition candidates

| Candidate | Population and labels | Rights, split, availability and intended use |
| --- | --- | --- |
| **OpenSLR83 / English dialect speech (2020 publication)** | UK/Ireland English volunteers; ages and child coverage not established by the release metadata inspected. WAV plus orthographic transcript; no error judgments, produced-phone transcript or phone times. Locally verified 17,877 index rows, each with three fields. | Publisher states **CC BY-SA 4.0**, and the linked license bytes were saved. Official mirrors are explicitly listed by OpenSLR. No published train/test split was established; group speakers and shared `LINE_ID` prompts before analysis. The small Midlands female ZIP returned HEAD 200 with ZIP content type. Useful as a reference/capture and dialect sensitivity pilot. [Release](https://www.openslr.org/83/), [dialect and prompt conventions](https://openslr.trmal.net/resources/83/dialect_info.txt). |
| **Kennedy et al. children speech recordings (2016/2017)** | 11 children, mean age 4.9; native and non-native English. Picture-book retelling, five repeated sentences and counting, recorded through studio, portable and robot microphones. Manual utterance segmentation is described for free speech. No produced-phone/error labels or human quality ratings established. | Author-deposited Zenodo record and saved DOI metadata identify **CC BY 4.0 / open access**. Official archive HEAD 200; **607,539,935 bytes**. No predefined split established; child and parallel-microphone grouping is mandatory. This is a small child capture-robustness resource, not clinical correctness data. [Official record](https://zenodo.org/records/200495), [license metadata](https://api.datacite.org/dois/10.5281/zenodo.200495). |
| **NISQA TRAIN_LIVE / VAL_LIVE (2021)** | English LibriVox material replayed through telephone/Skype capture. Ages not documented here. Training: 1,020 files / 486 speakers; validation: 200 / 102. Human overall-quality and noise/coloration/discontinuity/loudness ratings, not pronunciation labels. | Authors explicitly allow commercial/noncommercial **research** for LIVE under the original public-domain source terms; archive-specific notices still need checking. Preserve supplied train/validation split and reconcile source speakers if mixing SIM/LIVE. The author-linked Zenodo archive returned HEAD 200, **15,945,499,507 bytes**. Other subsets and pretrained weights have different restrictions. Relevant to an abstention/recording-quality component, not SSD feedback. [Author terms and subset definitions](https://github.com/gabrielmittag/NISQA/wiki/NISQA-Corpus), [official mirror record](https://zenodo.org/records/4728081). |

## Newer close matches that remain unavailable for this task

| Candidate | Evidence and access decision |
| --- | --- |
| **On Top of Pasketti phonetic track, completed April 2026** | US English children from age 3, typical development and SSD; normalized actual-production IPA sequences, child/session IDs, age bands 3–4, 5–7, 8–11 and 12+. This is an unusually close population/label match, but the official page restricts use to the competition, prohibits third-party API processing and redistribution, and requires platform/TalkBank access. No acquisition or usable Cadence license. Published evaluation is separate from training; child/source overlap would need checking. A promised later annotation release is not current permission. [Official task, schema and restrictions](https://www.drivendata.org/competitions/309/childrens-phonetic-asr/page/979/). |
| **Storiza, CoNLL July 2026** | 63 US children in grades 1–3 with typical reading development; 320 story recordings, about nine hours. Manual word/sentence times, IPA and reading-error categories include consonant substitution/omission/insertion. Phone boundaries and an SSD diagnosis are not established. Paper says 239 consent-cleared recordings **will** be deposited through LDC; other annotations are linked through OSF, which was not retrievable here. Dataset license, downloadable audio, schema and train/test split remain unverified. Read-only future-release lead, not training-ready data. [Author paper](https://aclanthology.org/2026.conll-main.35.pdf). |
| **MRP native English v2, June 10, 2026** | Different from MRPL2: 29 native Modern Received Pronunciation speakers, over 7,000 utterances and word/phone transcripts. Ages and split not established. Author repository and DOI metadata declare **CC BY 4.0**, but both v1 and v2 Zenodo pages explicitly mark files **restricted** and require an access request. No corpus acquired. [Author description](https://github.com/tweddan/MRP_Corpus), [v2 access status](https://zenodo.org/records/20628795). |
| **Ocular Multi-Accent English v1, April 2026** | 7,377 recordings / 10.25 hours, 11 L1 backgrounds; verbatim word transcripts and speaker/prompt IDs, no phone-error labels or verified child support. Publisher advertises ODC-By commercial training permission, but full bundles require contact and a licensing step. No established split; group speakers/prompts if later acquired. Not immediately actionable under current scope. [Publisher release and explicit access conditions](https://www.useocular.com/blog/multi-accent-english-asr-dataset). |

New public L2-ARCTIC rehosts appeared in search, but this check found no
first-party endorsement/provenance sufficient to promote them to approved
mirrors. Their existence does not resolve the earlier access/intended-use
assessment. No alternate protected-data route was used. MRPL2 was not
repeatedly probed; its [existing assessment](mrpl2-access-assessment.md) stands.

## Evidence and verification limits

The [evidence manifest](../../work/dataset-refresh-20260927/manifest.json)
records exact URLs, retrieval method, observed headers and SHA-256 for saved
original document/index bytes. HEAD responses verify endpoint metadata, not
archive integrity or audio-label consistency. Web-only findings above are
linked observations, not falsely represented as saved HTTP bodies.

All eight saved payloads passed size/hash verification; the SLR83 index parsed
as 17,877 three-field records. The archive headers were checked without local
audio acquisition. Application checks and model inference were not run because
this change is a sourced research report and metadata audit. Existing held-out
SpeechOcean labels and learner-facing behavior were untouched.
