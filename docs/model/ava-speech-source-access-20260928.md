# AVA-Speech: accessible human speech-presence references

The current release provides **39,874 human-labelled intervals from 160 videos, covering almost 40 hours**. It supplies explicit speech/no-speech references for a future non-speech rejection check. No model has been run on these annotations and no improvement is claimed.

## Source contract

Google describes four labels over source-video timestamps 900–1800 seconds: `NO_SPEECH`, `CLEAN_SPEECH`, `SPEECH_WITH_MUSIC`, and `SPEECH_WITH_NOISE`. Its current release lists 160 videos and states CC BY 4.0 for the listed datasets. Preserve attribution; this is not an independent rights determination for each underlying movie. [Official release and terms](https://sites.research.google/gr/ava/download/).

The provider paper describes three raters per one-minute clip, merged into frame-level majority labels. Speech includes unintelligible and foreign-language speech, communicative fillers, singing, electronic speech and audible background voices. Coughs, grunts, sighs and laughter can be no-speech. Short pauses can remain inside speech-labelled regions. The original majority tie-resolution detail is undocumented; use the published resolved reference without inventing an algorithm. [Annotation instructions and dataset statistics](https://arxiv.org/html/1808.00606v1).

These are movie soundtracks with unknown speaker ages and identities. They do not establish pronunciation correctness, phone locations, child speech impairment, isolated-word retention or whether audible speech belongs to the intended learner. In particular, background voices are speech positives: this reference cannot evaluate rejecting the wrong speaker as an unwanted recording. Possible overlap with pretrained models' YouTube-derived data remains unknown.

CVDF publishes the annotation CSV, filename listing and movie object URL pattern. Its approximately 40-hour release is the acquired release; the larger historical paper counts do not describe this local inventory. [First-party mirror instructions](https://github.com/cvdfoundation/ava-dataset).

## Actual acquisition and independent checks

Only provider documentation, the small CSV and filename list were initially acquired. The full annotation CSV was then fetched from Google's official endpoint: it was **byte-identical** to the mirror, SHA-256 `9936403f9abcb9e768d1b6889ceeadb6d6797d70c39cf9cf1062cdc2f3577377`.

| Original reference | Intervals | Exact labelled duration (seconds) |
|---|---:|---:|
| NO_SPEECH | 17,624 | 68,425.99 |
| CLEAN_SPEECH | 6,433 | 20,351.63 |
| SPEECH_WITH_MUSIC | 5,311 | 19,107.29 |
| SPEECH_WITH_NOISE | 10,506 | 36,113.30 |
| Total | 39,874 | 143,998.21 |

All 160 video IDs exactly match the provider filename stems. Containers are 111 MKV, 43 MP4 and six WebM files. Metadata validation found one original zero-duration interval, row 17,263 (`uPJPNPbWMFk`, 1140–1140, NO_SPEECH), and 37 short unlabelled end tails totalling 1.79 seconds. There are no internal gaps, overlaps or reversed intervals. Every original label and timestamp remains unchanged; no tail is implicitly filled with no-speech.

The first audit failed on an assumption that every interval must have positive duration. A separate second audit recorded that case but failed on an incomplete container whitelist. Both failures and their sources remain preserved. A separate third audit completed. Root independently reconstructed every row, label count, exact duration, geometry issue, filename join and input hash using raw line parsing and rational arithmetic, without importing the audit implementations. It passed.

HEAD requests to all **160 listed media objects returned HTTP 200**. Their declared sizes total 100,983,167,949 bytes; those complete objects have **not** been downloaded. HEAD verifies response metadata only, not movie integrity, duration or clock alignment.

## Bounded container-header probe

A separate prospective scope selected the smallest declared object per observed container extension, with filename tie-breaking, for metadata feasibility only. It fetched each object's first and last 4 MiB using exact HTTP byte ranges and pinned ETags: **24 MiB total**. Header images retain byte offsets in sparse files; their missing ranges are holes, not acquired media. They must never be used for audio decoding or treated as complete movies.

All three local container metadata probes completed successfully:

| Provider object | Container duration (seconds) | Container and audio start (seconds) |
|---|---:|---:|
| N5UD8FGzDek.mkv | 2479.281000 | 0 |
| -IELREHX_js.mp4 | 2604.094694 | 0 |
| 8nO5FFbIAog.webm | 2663.741000 | 0 |

These headers describe longer media beginning at zero, rather than 900-second excerpts, and are compatible with the documented 900–1800 source-clock region. They do not independently establish annotation-to-waveform correspondence, audio completeness, or the same geometry for the other 157 files. No audio has been decoded, no model inference has run and no Colab runtime was allocated in this phase.

## Review and next use

Verified **Opus 5.5** independently read the provider contract, paper and filename listing. Its completed call reports only canonical `claude-opus-5-5`, with no errors or permission denials. Root preserved its raw review and qualified several suggestions: HEAD cannot measure container duration, known zero/tail intervals must not be repaired, the original voting tie policy must not be invented, and speech-presence labels cannot establish intended-speaker identity. Subsequent official/mirror byte comparison and availability checks resolve those two source-access questions.

Before any model outcomes, a separate bounded audio/evaluation protocol must fix the source-to-media clock mapping, video-disjoint data allocation, speech versus NO_SPEECH mapping, zero-duration and unlabelled-tail handling, scoring windows and video-level dependency treatment. A useful system also needs independent short child-word retention controls; success on movie audio alone cannot justify learner feedback or a general child-pronunciation claim. The existing pronunciation bundle and previously closed model comparisons remain unchanged.

Evidence is preserved under `work/ava-speech-source-audit-20260928/`: acquisition manifest and original files; all three metadata audit versions and failed logs; `metadata-result-v3.json`; `root-metadata-verification.json`; `availability-scope.json` and `availability-result.json`; media header scope/results; and the Opus source review, identity receipt and root assessment. The overall ages-6–12/all-23 research goal remains active.
