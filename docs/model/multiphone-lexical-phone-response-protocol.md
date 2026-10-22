# Complete phone response and expanded fitting composition

Declare this protocol, new source/tests and all input/audit bindings before computing
these descriptions; keep them immutable afterward. Use fresh exclusive output files.
This is a descriptive follow-up to the [expanded fitting](multiphone-lexical-expanded-heads-report.md)
and [conditional uncertainty](multiphone-lexical-expanded-uncertainty-report.md)
studies. No fitting, resampling, model selection, threshold selection or new inference.

Retain all eight previously declared contrasts across both fitting regimes: expanded
scalar, compact PCA16/scalar and equal mixture versus their original counterparts,
and expanded equal mixture versus corrected original mixture (secondary). Use exactly
the original 5,654 positions from all 52 children aged 6–12, all 23 sounds, original
row indices, five speaker folds and 25 speaker/word cells. Reuse the frozen parent's
complete pairing validation; preserve every original consistency decision.

For each position and each class c, calculate the additive NLL difference
`-count[c] * (candidateLogP[c] - referenceLogP[c]) / 5`. Sum across classes for
position loss difference. Use finite normalized stable logs without probability
clipping. For every sound retain position/child/recording/vote support, mean NLL
difference and contribution to pooled difference. Provide every class, every speaker
fold, all 25 word cells and every child, including explicit zero support. Cell
contributions divide summed loss differences by the entire sound's position count;
pooled contributions divide by all 5,654 positions. Class conditional NLL divides
its unscaled summed vote loss difference by that class's vote count. Missing means
are null; empty additive contributions are zero. Require class/fold/cell/child sums
to reconcile to sound NLL and sound contributions to reconcile to pooled NLL. Match
pooled and all five fold means against the original expanded fitting report.

Reuse the verified expanded support inventory for original, added and all positions,
for the whole corpus and every inner-fit/outer-refit cell in both regimes. Verify
its exact ordered indices against both scalar and compact jobs. Retain all-age,
ages 6–12 and ages 13+ support, all 23 sounds, position/speaker/vote counts, phone
mass fraction and three-class vote fractions. Add complete-canonical-occurrence
composition: normalize only terminal stress digits 0/1/2 in the full ordered
canonical phone sequence, and count every same-sound occurrence in that recording.
A row is single if that count is one and repeated otherwise, even if only one of
the occurrences belongs to the original subset or current fitting partition.
Verify flattened words equal the complete sequence and canonical row indices,
word/phone indices, raw/normalized phones, speaker and age match; require all
supported canonical positions exactly once. Report distinct recording/sound units
and both categories' position/speaker/recording/vote support. These are descriptions
of composition, not a claim about timing, pronunciation truth or a defective sample.

Test full-sequence repetitions across words, gaps from unsupported phones, geometry
corruption, original/addition/family lineage, cached support, empty cells, malformed
multiplicities, no-analysis declaration and immutable/exclusive outputs. Test pure
loss math against independent explicit-vote and loop oracles, including extreme
stable logs and every partition. Independently review source before declaration;
reconstruct the actual result offline and independently audit the numerical result.

No sound, speaker, word cell or example is excluded. No sound-specific reweighting
or data-quality verdict is justified by an outer outcome. These reused development
folds do not constitute independent final validation. No causal attribution follows
from a composition/loss association. No new data/audio, author-test decoding, encoder
work, Colab allocation, application change or learner policy change. Learner judgments
remain disabled. Missing expert labels, ages 2–5 and an established speech-sound
disorder cohort remain limitations. Use the complete evidence to define the next
separately declared modeling hypothesis; do not search it within this diagnosis.
