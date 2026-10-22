# Ages 6–12 research candidate export

Declared before fitting on September 27, 2026. The user narrowed the current
model target to ages 6–12. Younger children are outside this milestone, not a
blocking requirement. This does not remove the need for appropriate labels or
independent validation before learner-facing pronunciation judgments.

Create a usable full-fit version of the retained unweighted expanded child
scalar/PCA16 mixture. Use all 9,891 existing eligible expanded author-training
positions from 52 children aged 6–12, all 23 supported consonants. No author-test
recordings, new audio, synthetic labels, adult fitting rows or Colab allocation.
This is an export milestone, not a new efficacy experiment.

Use the unchanged established training cores, seed 7, and equal 0.5 probability
weights. For each head independently, fix its epoch count to the median of the
25 corresponding child-only inner-selected epochs in the already frozen
expanded-data study. No outer scores choose a seed, epoch, transform or weight.
Refit both heads from fresh initialization on the complete child population;
fit PCA and normalizers only on those rows. Keep provenance, original training
histories and checkpoint hashes. Do not attach the cross-fit scores to this new
full-fit checkpoint or calculate a training-set accuracy as evidence of efficacy.

Export two minimal heads and the fitted PCA into a hash-bound feature-only
bundle. Its loader accepts raw float32 [N,1037] features in the existing order
(1,024 pinned target-window features followed by the 13 ordered CTC scalars),
canonical target IDs 0–22 and an explicit age. Age is in years, with 6 <= age < 13
representing completed ages 6–12. Preserve row order and repeated occurrences.
Reject invalid or nonfinite features, invalid ages/IDs, altered files and
incompatible state. Do not infer age from audio. ZH remains unsupported.

Verify predictions against the established fitting cores over all fitting rows
as an implementation parity check, not held-out performance. Require maximum
absolute probability difference <=1e-7 and log-probability difference <=1e-6;
report actual values. Test relocation without access to the original corpus,
normalization/PCA and equal-probability mixture behavior, row order/repeats,
age boundaries, malformed inputs and tampered bundles. Independently review
source and actual fitting/export evidence. No automatic feedback enablement,
release, clinical claim or production deployment. Keep eligibility flags false.

Report fitting support by each integer age and consonant, explicitly including
missing or sparse cells. The export targets 6–12; this does not promise equal
performance across all ages or phones.
