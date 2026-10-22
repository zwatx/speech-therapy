# NISQA training-data discovery results

September 27, 2026. **The download and metadata import work. This is data preparation, not evidence of a better pronunciation model.** No model was fitted or replaced. The broader model-quality goal remains active.

The official archive directory contains 27830 entries. Five fixed metadata members were selectively acquired, and the combined file table joins exactly 1020 TRAIN_LIVE recording identities. No validation/test audio or training audio was acquired. Quality scores have not been interpreted numerically, used for selection or exposed in derived reports.

## Actual acquisition

| Member | Original member bytes | Local SHA-256 |
| --- | ---: | --- |
| NISQA_Corpus/NISQA_TRAIN_LIVE/NISQA_TRAIN_LIVE_con.csv | 276821 | `2377aaf8126bb81684cb6ca595663ad6075a0055d1e782b5767ee452708ef0a8` |
| NISQA_Corpus/NISQA_TRAIN_LIVE/NISQA_TRAIN_LIVE_file.csv | 444710 | `5bcf1972cff64c8c1690d3f36ca6a9ada0e19e72f72503cdd67d7cf40ad932ff` |
| NISQA_Corpus/NISQA_TRAIN_LIVE/readme.txt | 3021 | `b90d3698e92483951fdd26d0592946bef787183d39652377590faec9aa653e10` |
| NISQA_Corpus/NISQA_corpus_file.csv | 5724911 | `01341878d66d3a877e1d52fbf4d3fce6fad381b36fc9afb4351ac9cac8fada26` |
| NISQA_Corpus/readme.txt | 2078 | `0c68b07860dcf9c0d73e6969ba78f6026b94866f697fc1549d837096f12e4a54` |

Total archive response body bytes read: **10,816,534 (10.32 MiB)** across 116 completed HTTP 206 ranges. This includes repeated directory discovery and member headers; it is below the 16 MiB metadata and 256 MiB total limits. The ledger records zero uncertain bytes and zero outstanding reservations. Every member passed the transport CRC/size checks and its local SHA-256 is bound in the metadata receipt. The advertised full 15.9 GB archive MD5 has not been verified by partial retrieval.

The first v1 attempt stopped before reading a range body because Last-Modified was omitted from 206. The separately reviewed v2 handles the permitted If-Range omission while rejecting conflicting headers, wrong ranges, full 200 responses and budget overruns. In the actual run, HEAD had no ETag; Date and Last-Modified satisfy the declared conservative 60 second gap. This relies on correct server enforcement of If-Range and is not a cryptographic archive-wide identity proof.

## What the metadata establishes

The TRAIN_LIVE notice permits research use under its original LibriVox public-domain source terms. It describes phone and Skype replay recordings and per-file mean ratings. The metadata explicitly gives capture descriptions `Skype` and `VoIP-landline to mobile`, source `DNS`, English language and source-reference filenames/paths. These fields were imported as opaque strings for all 1,020 training paths; no reader grammar or 20-file sample was applied.

The five rating columns are `mos`, `noi`, `col`, `dis`, `loud`. Standard-deviation and vote fields also exist; they have not been accessed by the identity/lineage routers. Whole-recording recording-quality means are distinct from produced-phone, child-pronunciation and speech-presence references.

The combined raw CSV contains other splits and their score strings. Its bytes were acquired and tokenized for routing. Only headers and permitted identity fields were exported; evaluation scores were never converted to numbers, summarized, previewed or used. The training-only lineage router discards other splits before accessing its metadata fields. Do not describe the combined object as unopened.

## What remains

Reader tokens have intended source-number semantics, but a reported original-source ID discrepancy remains unresolved. They are not verified human identities. The exact five-column range/direction and release missingness declaration also needs stronger evidence before supervised use. The predeclared 20-file pilot has not yet reached selection, target parsing, audio acquisition or waveform audit. Independent review will determine whether source-code grouping is adequate for an explicitly qualified ingestion-only sample.

This corpus does not establish age 6–12 applicability, learner feedback accuracy, a usable quality threshold, nonspeech rejection or improvement on unfamiliar children/words. No Colab allocation was needed for metadata discovery.

## Evidence and verification

- [Original ingestion protocol](nisqa-training-ingestion-protocol.md) and [versioned transport correction](nisqa-discovery-transport-v2.md).
- [Discovery plan](../../research/audio-head/outputs/nisqa-20260927/discovery-v2/plan.json), [directory receipt](../../research/audio-head/outputs/nisqa-20260927/discovery-v2/directory-freeze.json), [metadata receipt](../../research/audio-head/outputs/nisqa-20260927/discovery-v2/metadata-freeze.json) and [identity receipt](../../research/audio-head/outputs/nisqa-20260927/discovery-v2/identity-inventory-freeze.json).
- [Independent source review](../../work/nisqa-ingest-20260927/discovery-v2-source-review.json). All 66 test invocations passed, including repeated legacy cases; the new lineage module adds two focused passing cases. Syntax checks passed. The reviewer independently tested a complete pipeline with the actual v2 date-mode transport.
- [Opaque training lineage receipt](../../research/audio-head/outputs/nisqa-20260927/lineage-inventory-v1/freeze.json).
- [Primary semantic research](../../work/nisqa-ingest-20260927/semantics-primary-research.md) and [reader-lineage findings](../../work/nisqa-ingest-20260927/reader-lineage-primary-research.md).
- Official [Zenodo record](https://zenodo.org/records/4728081), [author corpus documentation](https://github.com/gabrielmittag/NISQA/wiki/NISQA-Corpus#nisqa_train_live-and-nisqa_val_live) and [HTTP standard](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.3.7).

Independent [post-discovery evidence review](../../work/nisqa-ingest-20260927/discovery-v2-results-review.json) is clear for integrity. The reviewed report version is preserved alongside the receipt; this final status sentence was updated as the reviewer allowed. A separately declared [source-code pilot](nisqa-source-code-pilot-v2.md) qualifies the grouping claim before selection. Neither review establishes model improvement or clears target/audio implementation.


## Follow-up: fixed source-code sample and primary scale evidence

The separately reviewed source-code pilot now fixes exactly 20 identities: 10 phone, 10 Skype, 20 approximate publisher-code groups. All 1,020 eligible rows, 486 approximate source-code groups, reference/book/chapter/code lineage and fixed-selector exclusions are preserved. These are not verified 20 people. Root replay reproduced all eligibility, choices and identity hashes. No target values or waveform files have been accessed yet. [Selection receipt](../../research/audio-head/outputs/nisqa-20260927/source-code-selection-v2/selection-freeze.json), [independent implementation review](../../work/nisqa-ingest-20260927/source-code-selection-source-review.json).

The author's thesis directly supplies the nominal 1–5 and higher-is-better quality conventions and connects them to the LIVE listening experiment. Independent review agrees this supports a separately fixed selected-only score audit with strict bounds, explicit accepted missing tokens and failure on unexplained values. Nominal endpoint overshoots must not be clipped or rescued after inspection. [Primary findings](../../work/nisqa-ingest-20260927/thesis-scale-findings.md), [independent method review](../../work/nisqa-ingest-20260927/thesis-scale-method-review.md).

Next is the bounded acquisition and waveform/selected-label audit for the exact frozen sample. That code and its review are still required. No fitting, calibration, new pronunciation-model gain or learner use has been established.
