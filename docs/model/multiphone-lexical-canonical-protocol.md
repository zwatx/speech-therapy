# Canonical annotation revision of lexical feasibility

This explicitly revises the token source in the [first feasibility
protocol](multiphone-lexical-feasibility-protocol.md). That declared run stopped
before hashing words or calculating support:531 eligible rows across305 clips
have target words that differ from the literal whitespace transcript tokens,
for example `QUARTER` versus `QUARTER.`. Its source, protocol, declaration and
failure receipt remain unchanged. Do not strip punctuation heuristically or
merge mismatches without evidence.

Use the complete ordered canonical word annotations already verified in
`position-data-v1/cohort.json`, SHA256
`3b70d6822cf02e3d4be50274b99853784a454d8fb80f939ade3940cb7b2a6864`.
Restrict to the original2,495 clips; do not add the five additional clips or
13,390 additional target positions in this audit. Verify each clip's ID, raw
text, waveform hash, speaker, age and canonical-phone count against the original
cohort. Check the complete canonical-phone sequence against the word lists and
every original row's word/phone indices and target identity. Reconcile every
original eligible row with the annotation cohort's explicit legacy index/ID and
five-vote labels. All inputs are saved author-training metadata; no waveform
or author-test object is opened.

Use uppercase canonical `word.text` tokens, in their original order, including
words without eligible consonant targets and repeated words. Canonical tokens
must each be one nonempty whitespace-free token. Retain the raw transcript and
its whitespace tokens separately, recording every difference from the canonical
word sequence. Construct an explicit in-memory canonical transcript view for
the already frozen membership/support algorithm; never rewrite the old cohort.
This is canonical-annotation token separation. Do not claim punctuation,
inflection, homophone, semantic or pretrained-encoder novelty beyond that rule.

The seed/NUL/SHA256/full-big-endian-modulo5 word rule, full5×5 crossing, both age
regimes, whole-utterance exclusion from fitting/validation/selection/refit,
outer target membership, all23 support and explicit empty cells are unchanged.
No real grouping/support result was computed before this revision; the first
run failed at word identity. Pin the new wrapper source/tests, both protocols,
old failed declaration/receipt, canonical annotation source and original inputs
before running the revised audit. Use a fresh output directory. Preserve the
failure if further metadata disagreement appears, and do not revise word groups
to improve support.

All verification, fresh-head requirements, repeated-development limitations,
and prohibitions on learner feedback or model promotion in the first protocol
continue to apply. Independently reconstruct canonical/raw differences,
partitions, exclusions and support. This audit performs no model fit, encoder
inference, prediction evaluation, audio reading or Colab allocation.
