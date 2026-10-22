# All-occurrence lexical support inventory

This metadata and saved-feature inventory is declared before deriving its crossed
cell support results. It examines all 28,227 supported consonant occurrences in
2,500 author-training recordings, including the five recordings absent from the
original 14,837-position inventory. It does not train or evaluate a model.

Use the original five speaker folds and their exact inner-fit, inner-validation,
and outer speaker roles. Rebuild the expanded splits from those roles and require
exact equality to the saved expanded split artifact. Reconstruct the old canonical
inventory independently of the expanded calculation. Every original eligible row
must have one exact legacy identity, speaker, age, word/phone position, target, and
five-rater count join. Ineligible original rows are not silently added to that join.

For every recording, use the complete ordered canonical annotation words, including
words without a supported target, rather than raw transcript punctuation. Retain
the existing SHA-256 word assignment with seed `cadence-lexical-holdout-v1`, modulo
five, including any additional word types. No regrouping or speaker reassignment.

Calculate all 50 cells: two age regimes × five speaker folds × five word groups.
For inner fitting, full inner validation, selection, and outer refitting, exclude
the entire recording if any canonical word belongs to the held-out word group.
For outer evaluation membership, select rows by their target word's group; other
words in that held-out recording do not exclude the target. Child-only fitting,
selection and refitting use ages 6–12; full inner-validation and outer membership
remain all ages. Fitting plus selection must partition refitting. Every outer row
appears once across the 25 cells of each regime.

Require every original row's base, retained and excluded membership to equal its
old canonical cell under the legacy mapping, in all five partition types. Retain
all row indices and original/added/all support for retained and excluded rows,
pooled corpus and partition unions. Support includes all ages, ages 6–12 and ages
13+, all 23 phones, recordings, speakers, target word types, rating-vote totals,
positive/negative rating-0 and below-2 votes and speakers. Absent phones and absent
event classes stay explicit. No minimum-support filtering, model selection,
outcome threshold, accuracy claim or promotion rule is introduced.

List all five additional recordings with their tokens, word groups, row indices
and speaker roles in every fold. List any newly encountered canonical word types.
New occurrences from existing recordings do not constitute independent speakers
or recordings; repeated occurrences can carry different ratings.

Pin the original canonical plan/report and their sources; expanded data, geometry,
phonetic report/plan, upstream artifacts and arrays; this protocol, study/tests
and runtime. Revalidate the complete saved phonetic export with extraction disabled:
all clip units, original target/global-vector parity, repeat unit, and assembled
matrices. Additionally require exact original 13-scalar and 1,024-target-vector
joins and exact expanded concatenation. Hashing audio bytes verifies lineage but
does not decode audio; no audio encoder, head predictions, training, transform
fitting, label transfer or author-test access occurs.

Use fresh ignored outputs with exclusive plan/start/result files and preserve
failures. Freeze sources/protocol at declaration. Verify by complete reconstruction
and separate read-only review. This reused development inventory can motivate a
separately declared training experiment; it cannot establish improved predictions,
clinical validity or learner feedback eligibility. The broader goal remains active.
