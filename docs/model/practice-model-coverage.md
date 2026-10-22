# Native practice vocabulary and research-cohort overlap

Snapshot: September 26, 2026. This metadata-only audit matches the app’s **72 prompt/target pairs** to the existing author-training research cohort. It does not assess pronunciation, predict prompt performance, approve content, or change the app. All 72 SLP review decisions remain pending.

**29 of 72 pairs have at least one retained cohort position across all ages; 17 of 72 have at least one at ages 6–12.** Thus 43 and 55 pairs, respectively, have no matching retained position. A match can be as small as one example and is not a coverage-adequacy claim.

## Scope and matching rules

- The Swift library and pending [72-prompt worksheet](practice-content-review.md) agree exactly on prompt IDs, symbols, positions, spellings and row order.
- Match only the explicitly mapped canonical target phone and exact word spelling after removing surrounding ASCII whitespace and lowercasing ASCII A–Z. Preserve punctuation, hyphens, plurals and all other characters; for example, “yo-yo” is not “yoyo.” No pronunciation or dialect equivalences are invented.
- The cohort contains 14,843 canonical positions from 2,495 clips / 125 speakers. Its 6–12 subset contains 5,654 positions from 1,037 clips / 52 speakers. These positions already satisfy the study’s single-occurrence-per-target-phone-per-utterance rule; this is **not a search of every occurrence in the original corpus**. Repeated-target words or utterances can be absent because of that filter.
- Intended beginning/middle/end positions are shown below but are **not verified or required by this word-plus-phone join**. There is no timing, produced-phone or clinical verification.
- Counts are unique canonical positions `(clipId, wordIndex, phoneIndex)`, clips and speakers. Votes remain the five raters’ original categories in order 0/1/2; no votes were converted to new labels or accuracy.
- All six raw ZH positions remain visible in the audit: six clips / six speakers, votes **11/1/18**, none aged 6–12. ZH is still excluded from the research head’s supported target mask. None matches the three demo ZH words.
- Absence does not imply a word is unpronounceable or untrainable. Presence does not establish isolated-word transfer, clinical suitability or coverage for ages 2–5 or children with speech sound disorders. The source corpus has no verified SSD cohort.

## All 72 prompt/target pairs

Each “positions / clips / speakers” cell reports distinct counts. Votes are **0 / 1 / 2**. Zeros and unsupported targets are retained. “Supported” refers only to the research head’s fixed target inventory, not clinical readiness.

| Prompt ID | Canonical target | Intended position | Model target | All-age positions / clips / speakers | All-age votes | Age 6–12 positions / clips / speakers | Age 6–12 votes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `b-beginning-ball` | /b/ → B | beginning | Supported | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| `b-beginning-boat` | /b/ → B | beginning | Supported | 1 / 1 / 1 | 0 / 0 / 5 | 0 / 0 / 0 | 0 / 0 / 0 |
| `b-beginning-bee` | /b/ → B | beginning | Supported | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| `p-beginning-pig` | /p/ → P | beginning | Supported | 1 / 1 / 1 | 0 / 0 / 5 | 1 / 1 / 1 | 0 / 0 / 5 |
| `p-beginning-pear` | /p/ → P | beginning | Supported | 1 / 1 / 1 | 0 / 0 / 5 | 1 / 1 / 1 | 0 / 0 / 5 |
| `p-beginning-pie` | /p/ → P | beginning | Supported | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| `m-beginning-moon` | /m/ → M | beginning | Supported | 3 / 3 / 3 | 0 / 0 / 15 | 0 / 0 / 0 | 0 / 0 / 0 |
| `m-beginning-mouse` | /m/ → M | beginning | Supported | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| `m-beginning-milk` | /m/ → M | beginning | Supported | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| `t-beginning-tiger` | /t/ → T | beginning | Supported | 1 / 1 / 1 | 0 / 0 / 5 | 1 / 1 / 1 | 0 / 0 / 5 |
| `t-beginning-toe` | /t/ → T | beginning | Supported | 1 / 1 / 1 | 0 / 0 / 5 | 1 / 1 / 1 | 0 / 0 / 5 |
| `t-beginning-tent` | /t/ → T | beginning | Supported | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| `d-beginning-dog` | /d/ → D | beginning | Supported | 2 / 2 / 2 | 0 / 0 / 10 | 2 / 2 / 2 | 0 / 0 / 10 |
| `d-beginning-duck` | /d/ → D | beginning | Supported | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| `d-beginning-door` | /d/ → D | beginning | Supported | 4 / 4 / 4 | 1 / 0 / 19 | 0 / 0 / 0 | 0 / 0 / 0 |
| `n-beginning-nest` | /n/ → N | beginning | Supported | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| `n-beginning-nose` | /n/ → N | beginning | Supported | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| `n-beginning-net` | /n/ → N | beginning | Supported | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| `k-beginning-cat` | /k/ → K | beginning | Supported | 4 / 4 / 4 | 0 / 0 / 20 | 3 / 3 / 3 | 0 / 0 / 15 |
| `k-beginning-key` | /k/ → K | beginning | Supported | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| `k-beginning-kite` | /k/ → K | beginning | Supported | 1 / 1 / 1 | 0 / 0 / 5 | 0 / 0 / 0 | 0 / 0 / 0 |
| `g-beginning-goat` | /ɡ/ → G | beginning | Supported | 3 / 3 / 3 | 0 / 0 / 15 | 3 / 3 / 3 | 0 / 0 / 15 |
| `g-beginning-gate` | /ɡ/ → G | beginning | Supported | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| `g-beginning-gum` | /ɡ/ → G | beginning | Supported | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| `f-beginning-fish` | /f/ → F | beginning | Supported | 5 / 5 / 5 | 0 / 0 / 25 | 3 / 3 / 3 | 0 / 0 / 15 |
| `f-beginning-fan` | /f/ → F | beginning | Supported | 1 / 1 / 1 | 0 / 0 / 5 | 0 / 0 / 0 | 0 / 0 / 0 |
| `f-beginning-feet` | /f/ → F | beginning | Supported | 1 / 1 / 1 | 1 / 0 / 4 | 0 / 0 / 0 | 0 / 0 / 0 |
| `v-beginning-van` | /v/ → V | beginning | Supported | 2 / 2 / 2 | 0 / 3 / 7 | 2 / 2 / 2 | 0 / 3 / 7 |
| `v-beginning-vase` | /v/ → V | beginning | Supported | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| `v-beginning-vest` | /v/ → V | beginning | Supported | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| `s-beginning-sun` | /s/ → S | beginning | Supported | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| `s-beginning-sock` | /s/ → S | beginning | Supported | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| `s-beginning-soap` | /s/ → S | beginning | Supported | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| `z-beginning-zebra` | /z/ → Z | beginning | Supported | 1 / 1 / 1 | 0 / 0 / 5 | 1 / 1 / 1 | 0 / 0 / 5 |
| `z-beginning-zipper` | /z/ → Z | beginning | Supported | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| `z-beginning-zoo` | /z/ → Z | beginning | Supported | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| `sh-beginning-ship` | /ʃ/ → SH | beginning | Supported | 3 / 3 / 3 | 0 / 0 / 15 | 1 / 1 / 1 | 0 / 0 / 5 |
| `sh-beginning-shoe` | /ʃ/ → SH | beginning | Supported | 1 / 1 / 1 | 0 / 0 / 5 | 1 / 1 / 1 | 0 / 0 / 5 |
| `sh-beginning-shell` | /ʃ/ → SH | beginning | Supported | 1 / 1 / 1 | 0 / 0 / 5 | 0 / 0 / 0 | 0 / 0 / 0 |
| `ch-beginning-chair` | /tʃ/ → CH | beginning | Supported | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| `ch-beginning-cheese` | /tʃ/ → CH | beginning | Supported | 1 / 1 / 1 | 0 / 1 / 4 | 0 / 0 / 0 | 0 / 0 / 0 |
| `ch-beginning-chick` | /tʃ/ → CH | beginning | Supported | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| `j-beginning-juice` | /dʒ/ → JH | beginning | Supported | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| `j-beginning-jam` | /dʒ/ → JH | beginning | Supported | 3 / 3 / 3 | 0 / 0 / 15 | 3 / 3 / 3 | 0 / 0 / 15 |
| `j-beginning-jacket` | /dʒ/ → JH | beginning | Supported | 1 / 1 / 1 | 0 / 0 / 5 | 0 / 0 / 0 | 0 / 0 / 0 |
| `l-beginning-leaf` | /l/ → L | beginning | Supported | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| `l-beginning-lion` | /l/ → L | beginning | Supported | 1 / 1 / 1 | 0 / 0 / 5 | 0 / 0 / 0 | 0 / 0 / 0 |
| `l-beginning-lamp` | /l/ → L | beginning | Supported | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| `r-beginning-rabbit` | /ɹ/ → R | beginning | Supported | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| `r-beginning-rain` | /ɹ/ → R | beginning | Supported | 2 / 2 / 2 | 0 / 0 / 10 | 1 / 1 / 1 | 0 / 0 / 5 |
| `r-beginning-ring` | /ɹ/ → R | beginning | Supported | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| `w-beginning-web` | /w/ → W | beginning | Supported | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| `w-beginning-wing` | /w/ → W | beginning | Supported | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| `w-beginning-wagon` | /w/ → W | beginning | Supported | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| `y-beginning-yarn` | /j/ → Y | beginning | Supported | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| `y-beginning-yo-yo` | /j/ → Y | beginning | Supported | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| `y-beginning-yogurt` | /j/ → Y | beginning | Supported | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| `h-beginning-hat` | /h/ → HH | beginning | Supported | 1 / 1 / 1 | 0 / 0 / 5 | 0 / 0 / 0 | 0 / 0 / 0 |
| `h-beginning-horse` | /h/ → HH | beginning | Supported | 2 / 2 / 2 | 0 / 0 / 10 | 2 / 2 / 2 | 0 / 0 / 10 |
| `h-beginning-house` | /h/ → HH | beginning | Supported | 14 / 14 / 13 | 0 / 1 / 69 | 4 / 4 / 3 | 0 / 0 / 20 |
| `th-beginning-thumb` | /θ/ → TH | beginning | Supported | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| `th-beginning-thorn` | /θ/ → TH | beginning | Supported | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| `th-beginning-thread` | /θ/ → TH | beginning | Supported | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| `voiced-th-middle-feather` | /ð/ → DH | middle | Supported | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| `voiced-th-middle-weather` | /ð/ → DH | middle | Supported | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| `voiced-th-middle-mother` | /ð/ → DH | middle | Supported | 4 / 4 / 4 | 2 / 1 / 17 | 3 / 3 / 3 | 2 / 1 / 12 |
| `ng-end-ring` | /ŋ/ → NG | end | Supported | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| `ng-end-wing` | /ŋ/ → NG | end | Supported | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| `ng-end-king` | /ŋ/ → NG | end | Supported | 1 / 1 / 1 | 0 / 0 / 5 | 0 / 0 / 0 | 0 / 0 / 0 |
| `zh-middle-treasure` | /ʒ/ → ZH | middle | **Unsupported** | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| `zh-middle-measure` | /ʒ/ → ZH | middle | **Unsupported** | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| `zh-middle-television` | /ʒ/ → ZH | middle | **Unsupported** | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |

## Review and reproducibility

The [SLP handoff](slp-handoff.md) and [content worksheet](practice-content-review.md) remain the places for content/dialect/readiness/cue/audio decisions. This overlap table supplies context for that review; it supplies no approval and selects no prompts by model scores. New representative consented isolated-word data and expert annotation remain separate work.

- Swift SHA-256: `0adbc140bbec3ab92e27853f60967bc55523c0d0bb50cf1ef5eeb939ea5fc8b5`.
- Worksheet SHA-256: `7c19fc0f4ced7ce88261179521a687e55200bf9b78a4d30d336de09abc894fa8`.
- Cohort SHA-256: `33967da3dfb3e41a5c7b14dbd0355ceb36574ecbdcb042c8e99137f6344ec805`.
- Reviewed helper SHA-256: `f10fab800a43b9bbb0e69b7068c0ca3b433cb641668b3d0ea2139993851d1371`.
- [Final JSON](../../research/audio-head/outputs/multiphone-20260926/practice-coverage-v1/final/report.json) retains every matching row index and canonical identity; [CSV](../../research/audio-head/outputs/multiphone-20260926/practice-coverage-v1/final/coverage.csv) contains the complete table. Final plan SHA-256: `9774389815ad77eae9e7d22025d054f74701ee8c2146c85cf0ef47adc9a760f9`; final report SHA-256: `5dbbcf51b716ec388acfa55815cb824e9e67362ca67ac52b2fe00712ec40b609`.
- The initial parent-directory result is superseded by the reviewed `final/` declaration. It is retained with the pre-review source snapshot to explain the plan-byte integrity correction; do not use it as the final reproducibility artifact.
- Independent metadata-only audit re-enumerated all 14,843 cohort rows for each of the 72 manually mapped joins and reproduced every identity, count, CSV cell and Markdown row: 29 all-age pairs / 67 matched positions and 17 child pairs / 33 matched positions. Audit: `/tmp/cadence-practice-coverage-independent-audit.json`, SHA-256 `875388671d9acee70387afe5602bd77ada59fbdf83d485a20b7af69318b9439f`.
- Eleven focused tests cover strict source parsing, worksheet mismatch/approval rejection, word normalization, exact phone joins, child boundaries, duplicates, invalid votes, unsupported and unmatched rows, immutable plan bytes and late input mutation. No audio, fitting or inference was performed.
