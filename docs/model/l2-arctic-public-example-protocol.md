# Public annotation schema check

September 27, 2026. This fixed check acquires only the public LXC
`arctic_a0018` annotation example and the official pages needed to preserve its
provenance, conventions and licensing notice. No audio, corpus archive,
registration, account, email or training is involved. The source is presented
as a manual example on the [official corpus page](https://psi.engr.tamu.edu/l2-arctic-corpus/).
The full corpus requires registration. Its stated license is
[CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/legalcode.en);
this schema check does not establish permission for commercial model use.

Fix the five source URLs in the acquisition script before retrieval: corpus
page, corpus documentation, public TextGrid, Creative Commons legal text and
Praat's TextGrid format documentation. Bind this protocol, reader, acquisition
script and tests in a fresh local plan before fetching. Cap each response at
250,000 bytes and total responses at 1,250,000 bytes, accept only same-host
HTTPS redirects, retain exact bytes and selected non-secret response metadata.
Record source URL, final URL, retrieval time, content type, byte length and
SHA-256. Stop and retain failure evidence if an endpoint, format or required
statement changes. Do not replace failed endpoints with an unofficial mirror.

The [annotation documentation](https://psi.engr.tamu.edu/l2-arctic-corpus-docs/)
distinguishes unchanged phones, substitutions, insertions and deletions, and
uses `err` for unresolved perceived identity and `*` for a perceived deviation.
Only verified manual-annotation provenance supports interpreting unchanged
labels as annotator acceptance. Automatic `/textgrid` files are a different
source. Stress, raw label, uncertainty and deviation stay separate. An inserted
phone has no canonical phone; a deleted phone has no produced phone. Do not
turn a deletion interval into an acoustic example of the absent consonant.

Implement a strict bounded reader for long-text IntervalTiers, including
UTF-8, BOM-marked UTF-16 and doubled quote escaping. Require positive adjacent
intervals, complete matching tier domains, unique tier names, expected index
counts and `words`/`phones`. Reject unsupported formats or labels; never repair,
drop or convert an unknown token to a confident class. Retain every auxiliary
tier without treating it as additional phone-error supervision. Preserve all
overlapping word links instead of arbitrarily choosing a word. The
[Praat format specification](https://www.fon.hum.uva.nl/praat/manual/TextGrid_file_formats.html)
documents the broader format; this reader intentionally accepts a strict subset.

The observed public sample must contain three tiers named `words`, `phones`,
`IPA`, with 7/16/7 intervals and the three substitutions R→AH at .20–.28 seconds,
Z→S at .44–.53 and JH→CH at .94–1.01. It contains ten unchanged speech labels
and the standalone `sil`, `sp` and empty labels. Keep `sp` unresolved because
the corpus page does not define it. Do not infer an audio duration from the
TextGrid domain. Do not call this a pinned v5 release; the example's own release
version and speaker age are unverified.

Synthetic tests separately exercise insertion, deletion, unknown/deviant
perceived phones, stress preservation, malformed labels/times/counts, quote
escaping, repeated/missing tiers, cross-word intervals, false manual provenance,
network bounds and artifact corruption. Those cases are fabricated schema
checks, not additional observed corpus examples. Actual example checks must
use downloaded original bytes. A read-only verifier re-parses saved source,
reconstructs the records and summary, and checks all bindings without network.

Every resulting artifact explicitly remains annotation-schema-only and
excluded from fitting, evaluation and learner feedback. Existing pronunciation
models, datasets, split manifests and historical sources stay unchanged. No
performance metric, child/SSD accuracy claim or GPU allocation follows from
this sample. The useful deliverable is an inspected label contract and verified
ingestion path; corpus-scale data availability remains a separate question.
