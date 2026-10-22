# Fixed-seed confirmation of the middle-layer candidate

The discovery experiment at seed 7 reduced mixture NLL by 0.84% on the existing original-child development cells. It passed the directional screen but missed the stronger material-gain target and worsened age-6 NLL. This study checks repeatability across optimization seeds on the **same children and words**. It cannot establish generalization to new participants or clinical validity.

## Frozen design

- Use exactly seeds **17, 29, 43**, all 25 existing speaker-fold × word-group cells per seed, child-only unweighted training, and all 5,654 original-child outer positions. Preserve ordered fit, selection, added-validation and refit membership. Report all 23 phones and all ages 6–12.
- Reuse the frozen normalized block-12 vectors and 13 cached CTC scalars from `middle-layer-features-v2`. No encoder inference, new data, label changes, feature selection, layer search, PCA search, seed selection, ensembles across seeds or age gating.
- Use the unchanged seeded trainer: fit-only centered PCA16 without whitening or column scaling; concatenate 13 scalars; fit-only head normalization; hidden 128, dropout .1, AdamW learning rate .0003 and decay .01, batch 64, gradient clip 5, at most 100 inner epochs, patience 15 and improvement tolerance 1e-7. No epoch-zero candidate. Fresh refit uses the selected epoch count. CPU, two threads, recorded deterministic settings.
- Compare each middle compact head with the frozen final-layer compact control at the **same seed**. Each mixture combines its compact prediction with that seed's same frozen scalar prediction using equal probability weights. The primary comparison is middle mixture minus final mixture. The compact-head NLL comparison is a co-condition.

## Required control and evaluator parity

Before any new middle fits, freeze source, protocol, runtime, features, membership and historical artifacts in the plan and obtain independent source review. The historical child-only unweighted controls may be reused only after:

1. Exact ordered fitting/selection/refit membership, original-child outer membership and scientific training configuration agree for all 150 controls. The frozen final vectors and scalars must equal the original cached values at every child row.
2. The new evaluator reconstructs the discovery seed's primary/compact pooled and subgroup metrics, screens and co-condition exactly from its frozen predictions. Seed 7 remains separate from replication summaries.
3. Retrain prechosen cell speaker-fold 0 × word-group 0 for both scalar and final families at each of the three seeds: **six inner fits and six fresh refits**. Require identical selected epochs, exact model-state tensors and exact full historical outer predictions. File hashes can differ because paths and provenance differ. These probes use the complete original feature bundle and original outer batch grouping.
4. Validate both saved fitting phases and replay selected-checkpoint and full outer predictions for **all 150 controls**. Confirm the new middle and same-seed final compact initial model states match in each fitting phase.

The old `experiment` configuration tag is retained solely for compatibility with the unchanged strict trainer validator. New `study`, representation, feature bindings and plan identify this study. No frozen historical source is edited. Repeating all historical fits or duplicating every new training run is unnecessary: bounded real trainer parity plus complete saved-state replay supplies the checks here. This is a deliberate adaptation of the external method review.

Any control, infrastructure or integrity failure makes execution **invalid**, never a model-quality pass or fail. Preserve partial artifacts. Investigate and independently review any correction before a separately recorded restart; do not automatically replace failed controls or alter scientific settings.

## Execution and decision

Freeze successful control parity, then all **75 new inner fits**, then all **75 fresh refits**, then all **75 outer predictions**. Revalidate fitting lineage and replay predictions before scoring. Never evaluate an incomplete seed or phase.

For each seed the six-part primary screen requires:

1. Pooled mixture NLL improves by more than 1e-7.
2. Every one of five speaker folds has mixture NLL change ≤1e-7.
3. Macro-phone mixture NLL change ≤1e-7.
4. Mixture Brier change ≤1e-7.
5. Rating-0 average precision change ≥−1e-7.
6. Below-rating-2 average precision change ≥−1e-7.

The compact co-condition requires compact NLL change <−1e-7. Undefined primary endpoints invalidate evaluation.

The **all-age guard fails if any age from 6 through 12 has mixture NLL change >1e-7 at all three new seeds**. One- or two-seed regressions remain visible but do not fail this guard. Every age must have the same nonzero support at each seed. The 1e-7 threshold is the established numerical tolerance, not a claimed clinically meaningful threshold.

Replication passes only if **all three** seeds pass the complete primary screen and compact co-condition **and** the all-age guard passes. An across-seed mean cannot rescue a failed seed or age guard. The separate material target remains at least 5% relative NLL reduction and +.01 rating-0 AP with the directional screen; it is descriptive and cannot erase its seed-7 failure.

## Reporting and next action

Report each seed's metrics, changes, screen, compact co-condition and material target; five folds; seven ages with support; 23 phones; 52 children; and counts of regressions. Report mean/minimum/maximum of each metric change and counts of seeds with worse NLL for every age, phone and child. These are descriptive summaries, not an ensemble or independent confidence interval.

PASS makes the candidate eligible for a separate participant-confirmation design. FAIL closes automatic replacement with this fixed recipe; report failure details without seed or recipe retries. Either outcome leaves the existing packaged model unchanged, the author test unopened and learner/clinical use ineligible. Independent post-run review is required. This modest-effect confirmation alone does not achieve the broader model-quality goal.

No Colab allocation is needed for this CPU head experiment. The user's monthly compute authorization remains available for justified future experiments.
