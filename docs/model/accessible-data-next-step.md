# Accessible produced-phone data: bounded next step

Follow-up: the [public-example ingestion check](l2-arctic-public-example-report.md)
is now complete. Its original annotation bytes, provenance and derived records
passed independent audit. No audio or full corpus was acquired. The access
assessment below remains the earlier source check; the follow-up does not
remove those corpus-scale restrictions. A later [MRPL2 check](mrpl2-access-assessment.md)
also found no immediately usable acquired corpus; its older release requires
file-access approval and its latest release's access remains unverified.

Checked **September 27, 2026** against first-party pages and HTTP responses.
This narrows the earlier [survey](produced-phone-corpus-candidates.md) and
[child-data review](child-pronunciation-data-options.md). No audio, full metadata
archive, or evaluation split was downloaded or processed; no registration,
contact, upload, or training occurred.

**Result:** neither L2-ARCTIC nor the child candidate TinyVox supplies a verified,
immediately downloadable full audio/annotation corpus without registration in
this check. The immediately accessible item with timed human error annotations
is L2-ARCTIC's single public example. It is enough to validate ingestion logic,
not to train a useful model. Do not represent an observed archive link or an
HTTP 200 login page as acquired data.

## L2-ARCTIC: strongest annotation fit, access still gated

The official release is **v5.0 (March 12, 2020)**. Access requires name, email,
affiliation, agreement to terms, and an emailed Google Drive link. No form was
submitted and no full archive download URL was obtained. The stated license is
**CC BY-NC 4.0**, with separate permission needed for other uses. This supports
a candidate noncommercial method experiment; private/local execution alone
does not establish permission for commercial development or deployment.
[Official release, access and terms](https://psi.engr.tamu.edu/l2-arctic-corpus/)

The documented prompted corpus has **24 non-native speakers, 26,867 utterances,
27.1 hours**, with **3,599 manually reviewed utterances**. Those contain 14,098
substitutions, 3,420 deletions and 1,092 additions. The additional suitcase
subset is 26.1 minutes from 22 speakers. Reviewed `/annotation` TextGrids have
`words` and `phones` tiers, optional comments, and corrected intervals;
`/textgrid` files are automatic alignments. Phone labels are:

- unchanged ARPAbet: judged correct;
- `canonical,perceived,s`: substitution;
- `sil,perceived,a`: insertion;
- `canonical,sil,d`: deletion;
- `err`: uncertain perceived identity; `*`: pronunciation deviation.

Keep stress, deviation and uncertainty separately from the normalized phone.
Source labels are adult L2 pronunciation judgments, **not child SSD diagnoses**.
Archive byte size is not stated on the reviewed pages. Assuming mono 16-bit
PCM, the documented 44.1-kHz, 27.1-hour recordings would occupy approximately
**8.6 GB uncompressed**; this is a planning estimate, not verified encoding or
download size.
[Official annotation and corpus documentation](https://psi.engr.tamu.edu/l2-arctic-corpus-docs/)

**Direct small-file access verified:** the official public
[LXC arctic_a0018 TextGrid](https://psi.engr.tamu.edu/wp-content/uploads/2018/03/lxc_arctic_a0018.txt)
was returned as readable text. Its phone tier includes `R,AH0,s` at 0.20–0.28 s,
`Z,S,s` at 0.44–0.53 s and `JH,CH,s` at 0.94–1.01 s. These are three error types
by target phone, all substitutions; the example does not verify insertion or
deletion parser behavior, v5 coverage, all-phone support, or sufficient class
balance. The sample's 2018 path is not a pinned v5 archive. Its linked WAV was
not fetched.

## TinyVox: best broad child sequence lead, audio gate verified

The official release links **561,312 utterance WAVs** and a separate metadata
ZIP. The 238-GB parent-audio collection is available on demand; it is not the
utterance ZIP's stated size.
[First-party release links](https://talkbank.org/phon/access/Derived/TinyVox.html)

The current raw author README describes 560 children, ages approximately six
months–eight years, five languages and a normalized 57-phone inventory.
`phones` is the normalized manual production transcript; `sentence` is optional
orthography; onset/offset are **utterance** boundaries. This is not a complete
canonical/perceived error-pair dataset or human phone-time reference. Original
source paths and `child_pseudoid` enable lineage checks. **CC BY-NC-SA 3.0**
permits noncommercial development but explicitly excludes training/fine-tuning
models for commercial deployment. The raw README mentions 179 GB for original
audio, differing from the release page's 238 GB; do not budget from either as
the utterance archive size.
[Author README and explicit terms](https://raw.githubusercontent.com/MarvinLvn/tinyvox/main/README.md)

HTTP probes in this session establish:

| Published endpoint | Observed response | What is verified |
| --- | --- | --- |
| [Metadata ZIP](https://talkbank.org/phon/access/Derived/0docs/BaBAR.zip) | HEAD 200, `application/zip`, 34,624,213 bytes; modified March 17, 2026 | Archive endpoint and advertised size; body/schema/hash not verified |
| [Utterance-audio ZIP](https://media.talkbank.org/phon/0extra/TinyVox.zip) | HEAD 200, `text/html`, 319 bytes | Reading only this tiny HTML response showed a TalkBank authentication modal, not ZIP bytes |

PhonBank explicitly requires registration for transcript/media access. A public
metadata endpoint does not override that policy. No protected corpus content
was retrieved. [Access policy](https://talkbank.org/phon/access.html)
TalkBank's additional confidentiality/local-storage and web-processing terms
also apply. [Ground rules](https://talkbank.org/0share/rules.html)

## Bounded experiment and actual blockers

Proceed now with an **annotation-only L2 public-example ingestion check**:
store source URL/retrieval date/hash alongside one TextGrid; parse raw label,
canonical phone, perceived phone, error code, stress, uncertainty, deviation,
start/end and tier provenance. Validate monotonic in-range intervals and the
three observed substitutions. Keep the sample outside every eventual fit and
evaluation manifest. This checks real schema compatibility without inventing
training evidence; no GPU or Colab units are needed.

After authorized official L2 access is available, pin archive terms and hashes,
lock speaker and prompt partitions **before** opening development labels, and
inventory at most 300 manual training utterances across speakers. Report
per-phone correct/substitution/insertion/deletion support rather than assuming
all sounds are covered. Preserve `err`/`*`; exclude uncertain identity from
hard produced-phone targets. Only then decide whether a frozen-encoder
interval head merits local training. Leave held-out speakers and all published
test data untouched. This adult benchmark cannot validate child feedback.

For child work, TinyVox needs authorized registration and downloaded-training
schema/lineage verification first. A future bounded train-only English subset
could test produced-phone sequence recognition, with speaker/source grouping;
it cannot supply distortion-sensitive correctness by normalization alone.

**Genuine blockers:** official access remains absent, full archive terms and
per-phone support remain unverified, and neither source establishes deployable
commercial rights. No account creation/contact was authorized for this audit.
There is no basis to spend the existing 100 Colab units or claim broad
child-error evidence from these sources yet.
