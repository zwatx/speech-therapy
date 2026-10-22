# Practice vocabulary provenance

The consumer practice library contains **892 distinct hand-selected English words** and **2,398 sound/position entries** across the original 24 consonants. A word can support several targets and positions; entry counts are not distinct-word counts. All selected display words are at most 12 characters long. The original 72 starter prompts (70 distinct words) keep their displayed words, order, IDs, positions, and symbols.

Selection favors familiar objects, foods, animals, places, people, actions, and everyday words. The vocabulary has not been validated as an age-appropriate or prescribed therapy sequence. It is not a diagnostic instrument, pronunciation score, or treatment recommendation. Pronunciation metadata checks placement against a dictionary; it does not establish a user's pronunciation or the clinical suitability of an exercise.

## Source and license

Pronunciations come from the official [CMUdict repository maintained by CMU Sphinx](https://github.com/cmusphinx/cmudict), specifically [commit `74790861f652b15e4ac49015a90074ad62a27690`](https://github.com/cmusphinx/cmudict/tree/74790861f652b15e4ac49015a90074ad62a27690), committed on 2025-10-24. The pinned source and license were retrieved and verified on 2026-10-02.

| File | Pinned source | SHA-256 |
| --- | --- | --- |
| `cmudict.dict` | [Dictionary at pinned commit](https://raw.githubusercontent.com/cmusphinx/cmudict/74790861f652b15e4ac49015a90074ad62a27690/cmudict.dict) | `81917843c7f44ce2b094ac63873c2c7a4cf802040792c455ba3ca406891c3d22` |
| `LICENSE` | [License at pinned commit](https://raw.githubusercontent.com/cmusphinx/cmudict/74790861f652b15e4ac49015a90074ad62a27690/LICENSE) | `bd4ce8e44170a5f9f481310ca85c51de3c4f851a65e679b40e603b143bd3542a` |

CMUdict copyright, redistribution conditions, acknowledgments, and disclaimer are retained verbatim in `CMUDICT-LICENSE.txt` and in the generated Swift `PracticeVocabulary.license`, exposed as `PracticeLibrary.sourceLicense` for app credits. Binary distributions must reproduce the terms in documentation or other accompanying materials. The source acknowledges that dictionary errors and omissions can remain; it represents US English rather than all accents or dialects. [CMUdict README](https://github.com/cmusphinx/cmudict/blob/74790861f652b15e4ac49015a90074ad62a27690/README).

No SpeechOcean lexicon, audio, corpus, or other scientific dataset is redistributed in this library. No recordings, models, or training data are downloaded by the app. Its vocabulary is bundled Swift data and works offline.

## Reproduction

`practice-library-words.txt` is the original hand-selected candidate list. Its categories are editorial organization, not treatment or difficulty labels. Repeated candidate tokens are collapsed; output display words are sorted alphabetically. The generator rejects candidates missing from CMUdict, candidates without a consonant target shared across all listed pronunciations, unexpected source hashes, and an altered license.

From the repository root, using Python 3 and the project's installed Swift formatter:

```sh
python3 docs/content/generate-practice-library.py
python3 docs/content/generate-practice-library.py --check
python3 docs/content/test-practice-library-generator.py
```

The generator downloads only the approximately 3.6 MB dictionary from its pinned URL, verifies its hash, selects the specified words, strips source comment annotations, retains all source pronunciation variants after removing vowel stress digits, embeds the license, and applies `swift format`. It does not clone a repository or download a large dataset. `--check` compares regenerated formatted output with the existing file without editing it.

To reuse a previously retrieved copy while verifying the same source hash:

```sh
python3 docs/content/generate-practice-library.py --dictionary-path /path/to/cmudict.dict --check
```

The output is `apps/ios-learner/Sources/DirectPractice/PracticeVocabulary.swift`. Do not edit generated rows manually. Change the candidate list and rerun the generator. The sole display/source spelling mapping is **`yo-yo` → `yoyo`**, using CMUdict's real `yoyo Y OW1 Y OW0` entry; its pronunciation is not fabricated from spelling.

## Position rules and variation

Targets use CMUdict's ARPABET phones, not letters:

- **Beginning:** the target is the first phone in the word.
- **Middle:** the target occurs at an interior phone index, after the first and before the last phone.
- **End:** the target is the last phone in the word.

A word is included for a target/position only when that pair exists in **every pronunciation variant listed for that source word**. `vase`, for example, can end in S or Z and therefore appears for beginning V, but neither end S nor end Z. `close` similarly has no S/Z end entry. The first pronunciation is exposed as `phones`; all listed variants remain available as `pronunciationVariants`.

These are literal phone positions, including consonant clusters. In `sky` (`S K AY`), S is beginning and K is middle; in `bread` (`B R EH D`), R is middle. They do not imply singleton consonants, syllable position, an easy-to-hard sequence, or a word-initial-cluster classification. Syllable and cluster-filter metadata are not provided.

R targets the CMUdict **R phone**, including explicit postvocalic R, and excludes the **ER rhotic vowel**. `bird B ER D` consequently has no R entry, while `door D AO R` has an end R entry. TH and voiced TH map separately to TH and DH; CH and J map to CH and JH. NG maps to NG, not the separate N + G phones. Y and W map to consonantal Y and W, not spelling at the end of a word.

There are no beginning NG or ZH words in the selected catalog. This is a statement about the selected words, not a claim that no English word can begin with ZH. W, Y, and H have no end-phone entries. Unsupported positions return an empty list and cannot create a session; the app should display that state clearly rather than invent examples.

## Caller behavior

`PracticeLibrary.sounds` retains the original 24 sound definitions and their three starter prompts; `starterSound` remains beginning B. `entries(soundID:position:query:)` offers the expanded catalog with optional sound and position filters. Search uses case-insensitive and diacritic-insensitive substring matching against both the displayed word and its source spelling after trimming surrounding whitespace. For example, either `yo-yo` or `yoyo` finds the retained display word `yo-yo`. A blank query returns the selected full list; an unknown sound or unmatched query returns an empty list. Catalog order is the original sound order, beginning/middle/end, starter prefix at each sound's default position, then alphabetical remaining words. Filtering preserves order.

`session(soundID:position:query:startingAt:limit:)` returns a sound containing the selected matching word followed by up to two later matching words. It never wraps or backfills with earlier words. A final session may have one or two words. `limit` permits a shorter session and is capped at three; a nonpositive limit, empty list, invalid sound, or selected ID outside the filter returns nil. All prompts in a session are distinct. Passing no selected ID starts at the first result.

`nextEntryID(after:soundID:position:)` finds the next entry in the complete sound/position list and returns nil at the end or for a mismatched ID. Callers can continue from the last completed prompt without restarting the same three words. A UI that uses search only to select a word should pass its ID into a session with the default empty query, continuing through the full chosen sound/position list. Callers that intentionally pass a query receive sessions confined to those matches.

## Counts by sound

| Sound ID | Beginning | Middle | End |
| --- | ---: | ---: | ---: |
| b | 90 | 32 | 12 |
| p | 65 | 41 | 32 |
| m | 40 | 40 | 33 |
| t | 53 | 68 | 102 |
| d | 37 | 29 | 46 |
| n | 20 | 104 | 98 |
| k | 86 | 70 | 57 |
| g | 27 | 21 | 13 |
| f | 51 | 17 | 16 |
| v | 15 | 21 | 15 |
| s | 97 | 49 | 40 |
| z | 11 | 22 | 18 |
| sh | 16 | 9 | 9 |
| ch | 16 | 13 | 15 |
| j | 21 | 10 | 16 |
| l | 38 | 101 | 83 |
| r | 40 | 137 | 24 |
| w | 27 | 16 | 0 |
| y | 8 | 12 | 0 |
| h | 41 | 10 | 0 |
| th | 20 | 12 | 19 |
| voiced-th | 10 | 17 | 3 |
| ng | 0 | 19 | 25 |
| zh | 0 | 18 | 5 |
