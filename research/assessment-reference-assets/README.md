# Public reference asset acquisition

This isolated tool acquires public word recordings for the pinned engineering pack. It reads only `docs/consumer-assessment/proposed-engineering-pack.json` (SHA-256 `a957a9e3291f0d90b275d40cd914890836ee7e6fc4fd361f7589cd1444587ef3`) and a closed Commons file plan. Embedded catalog source paths are retained metadata and are never opened. The tool accepts no caller-supplied source URL.

Run from the repository root:

```sh
python3 research/assessment-reference-assets/reference_assets.py
python3 research/assessment-reference-assets/reference_assets.py --resume
PYTHONPATH=research/assessment-reference-assets python3 -W error -m unittest discover -s research/assessment-reference-assets/tests
```

The default output is `work/assessment-real-data-20261004/references`. Its directories must be owned by the current user and mode 0700; files are exclusively created as mode 0600. The initial run requires an empty root. Resume reuses stored source evidence and checks existing original/WAV/receipt bytes; it preserves the previous working registry in a new exclusive receipt before atomically updating `assets.json`. Existing originals, WAVs and source receipts are never overwritten. Private reads reject symlinks, hardlinks, FIFOs, unsafe permissions and oversized files.

Requests use an identified user agent without credentials, are paced, and stop at the first HTTP 429. The supplied `Retry-After` delay is retained with a local deadline. Resume refuses to make another request before that deadline. A failed or throttled download remains a gap; no synthetic audio fills that gap. Initial API failure leaves its retained files for diagnosis; it does not manufacture a completed registry.

## Sources and permission bases

Each recording is downloaded only after its own Commons API metadata and revision wikitext establish the selected license/release, author/source and original size/SHA-1. Full API/wikitext evidence and the rendered permanent file page are retained. Filename and source labels do not establish the recording's lexical correctness, dialect, speaker age, identity or clinical suitability.

| Source words | Selected license/release | Source attribution |
| --- | --- | --- |
| rabbit, bread, door, baby, banana, sky, vase, ring, treasure | [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/) | Dvortygirl; individual `File:En-us-WORD.ogg` pages |
| thumb, feather | Explicit [PD-self release](https://commons.wikimedia.org/wiki/Template:PD-self) on each file page | Dvortygirl; `File:En-us-thumb.ogg`, `File:En-us-feather.ogg` |
| backpack | [CC BY 3.0 US](https://creativecommons.org/licenses/by/3.0/us/) | Association Shtooka, Judith Franck; [file page](https://commons.wikimedia.org/wiki/File:En-uk-backpack.ogg) |
| yoyo (displayed yo-yo) | [CC0](https://creativecommons.org/publicdomain/zero/1.0/) | Flame, not lame; [file page](https://commons.wikimedia.org/wiki/File:LL-Q1860_(eng)-Flame,_not_lame-yoyo.wav) |

The backpack page reports a London, England speaker. The yoyo page specifies English without a regional variety. The remaining selected pages report US English. These are retained source labels, not independently verified dialect or age claims. In particular, the thumb page's description says “acronym”; no clinical or prompt-match judgment is inferred from that description.

Four purpose permissions—`referencePlayback`, `localInference`, `storage`, `redistribution`—record their public-license basis and conditions. They do not establish participant consent, identity, age, publicity permission or professional approval. CC BY-SA derivatives retain CC BY-SA 3.0; source, author, license and conversion attribution are recorded for every asset. Attribution is retained voluntarily for PD-self and CC0 assets too. License grants are the source permission for this engineering use; no legal agreement is signed and no licensor endorsement is claimed.

## Conversion and registry

`ffmpeg -version` is retained. The installed executable receives only already-licensed local original bytes. The conversion command changes channels to mono, sample rate to 16000 Hz and encoding to PCM16 WAV (`-ac 1 -ar 16000 -c:a pcm_s16le`). It performs no trimming, normalization, time stretch or speed change. Private file descriptors supply input/output; the exact argument list, version, original/derived SHA-256 and change attribution are retained in each receipt. Duration and PCM shape are measured from the saved WAV bytes.

`assets.json` has exact root fields `schemaVersion`, `sourcePackSha256`, `use`, `permissionMeaning`, `clinicalReferenceApproved`, `variantCoverageMeaning`, `assets`, `gaps`; throttled drafts may also include `retryAfterSeconds` and `retryNotBeforeUnixSeconds`. Assets follow normalized source-word order. Every asset contains:

- Identity: `id`, display `word`, normalized `sourceWord`.
- Source/grant: `sourcePageUrl`, `permanentSourcePageUrl`, `sourceRevisionId`, `sourceRevisionTimestamp`, `originalUrl`, `author`, `sourceCredit`, `licenseId`, `licenseUrl`, `apiSha1`, `apiSizeBytes`, `originalMime`.
- Evidence: absolute `sourceEvidencePath`/`sourcePageEvidencePath` and their SHA-256 values.
- Audio: absolute `originalPath`/`wavPath`, original/derived SHA-256, `durationSeconds`, `sampleRateHz`, `sampleWidthBytes`, `channels`, `sampleCount`.
- Lineage: `changes`, `derivativeLicenseId`, `attribution`, absolute `conversionReceiptPath`, `conversionReceiptSha256`.
- Scope: `declaredVariety`, false `varietyVerified`, `speakerAgeKnown`, `speakerIdentityVerified`, `participantConsentEstablished`, `promptMatchVerified`, `clinicalReferenceApproved`, `dictionaryVariantCoverageEstablished`; `permissionBasis`, purpose `permissions`, and `allowedUserResearchUse`.

Gap records contain only `sourceWord`, display `word`, `candidateTitle`, fixed `reason`, `audioAcquired:false`, `clinicalReferenceApproved:false`. A complete registry has exactly 13 assets and no gaps. One recording per distinct word does not claim coverage of all 17 dictionary variants; both rabbit/vase variants remain upstream metadata. Professional review remains unestablished.

## Validation API

`validate_registry(registry, require_complete=True)` returns a fresh validated registry or raises fixed `AssetError('invalid_registry')`. It never fetches a URL or converts media. It requires the exact fixed-pack roster and per-file license/permission records, binds all declared paths to closed names inside the default private root, rereads evidence/original/WAV/receipt bytes through bounded private descriptors, checks API SHA-1/size and SHA-256 values, measures PCM shape/duration, and validates the retained transformation command. The default refuses all gaps before inference. `require_complete=False` permits a checked partial inventory; it cannot turn a missing reference into an eligible model attempt.

Supporting APIs are `pack_words()`, `validate_metadata(word, page)`, `verify_original(metadata, bytes)`, `wav_details(bytes)`, `gap_record(word, reason)` and `acquire(output, resume=False)`. Tests use invented API metadata and short generated PCM bytes only. Hashes establish byte consistency, not authorship authentication or clinical truth. A later engine must verify the exact bytes it actually reads against the validated asset binding; the registry does not replace that check or current access permissions.
