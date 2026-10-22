# Fresh heads on canonical word- and speaker-disjoint splits

Use the completed [canonical lexical inventory](multiphone-lexical-feasibility-report.md)
as the exact membership source. This bounded experiment tests the current
combined phonetic/scalar representation against a scalar-only head and same-fit
rating priors under stricter downstream word separation. It does not reuse old
supervised checkpoints or fit a new temperature correction.

## Fixed comparison and training

Use all 25 speaker×word cells for both all-age and child-only fitting. The two
neural families are 13 confidence scalars alone and the original 1,024-dimensional
estimated target-local phonetic vector concatenated with those same 13 scalars.
Reuse the frozen feature matrices and canonical row mapping; no encoder is
updated or rerun. Both families use the existing phone-conditioned shared MLP:
128 hidden units, 24 phone-embedding slots, GELU and dropout0.1. Only the existing
23 supported phone IDs are fitted/evaluated. Input width and parameter counts
differ, so this is a comparison of practical model families, not a capacity-
controlled proof that extra information alone causes any difference.

There are 100 inner fits:2 families×2 regimes×5 speaker folds×5 word groups.
Start every head from a fresh seed7 initialization. No old head/model state or
optimizer is loaded into a training trajectory. Fix AdamW learning rate0.0003,
weight decay0.01, batch size64, gradient norm cap5, CPU with2 threads, maximum
100 epochs, and patience15 epochs since the last improvement. Use the existing
recipe's initialization/architecture conventions and one NumPy seed7 shuffle
stream per job. There is no rate, seed, weighting or architecture sweep.

Every position contributes equal weight to soft three-class cross-entropy using
its original five-rater counts divided by five. Feature population mean/std
are computed in float64 from that job's fitting rows only, stored float32; a
standard deviation below1e-6 becomes1. The same fitting rows determine the
per-phone prior with one pseudocount per class. No selection/outer row enters
moments, priors or optimization. All fitting cells contain all23 phones.

After each epoch, evaluate the fixed purged selectionRows:all ages for the
all-age regime, ages6–12 for child-only. Select by per-rater NLL, not macro-phone
NLL or rare-event AP, because seven child selection cells lack phones. Compute
selection NLL from stable float64 log-softmax of the model's float32 logits,
without clipping. An improvement must exceed1e-7; keep the earlier state on
smaller changes/ties. Epoch0 is saved for initialization verification but is not
eligible for selection. Stop at100 epochs or when epoch−bestEpoch reaches15.

Retain initial, best and last model states, optimizer/RNG state where applicable,
fit-only moments/priors, every epoch's shuffle digest, updates/train loss, complete
selection probabilities/log probabilities and selection NLL. Reproduce the
selected prediction/log/NLL output exactly from its saved checkpoint. Record
failures in fresh exclusive run directories without overwriting historical data.

## Freeze, refit and outer evaluation

Freeze all100 selected inner checkpoints and epoch counts before any outer
refit. Then initialize100 new heads with the same recipe and seed, and refit
on each cell's exact purged outerFitRows for its selected epoch count. Recompute
moments/priors from that refitting set. This is fresh fitting, not continuation
of the inner head. No validation stopping, calibration or outer prediction is
allowed during refitting. Freeze every final refit checkpoint before any outer
inference, requiring content hashes between phases.

Only then predict each matching outer cell. Its target word group is absent
from every word in all supervised fitting and selection utterances for that
pipeline. Verify this against the complete canonical-token lists, not just
eligible target rows. Preserve the existing disjoint speaker sets. Pool all25
cells once per family/regime to exactly14,837 positions, including5,654 child
positions from52 children. Outer results are not used to reselect/refit a model.
Generate per-phone Laplace-prior predictions from the matching outer fitting
rows, identical for both neural families in a cell.

Save raw float32 softmax outputs for numerical provenance, plus stable float64
log-softmax and its ordinary probabilities for all reported metrics. Preserve
exact NLL/conditional NLL/entropy rather than legacy probability floors. Report
all-age, child6–12 and age13-plus NLL, macro-phone NLL, Brier, rating0/below2 AP
and AUROC, fixed reliability bins and confidence measures. Keep all23 phone
cells, including absent/undefined metrics and five-vote/speaker support. Every
outer target type is absent from this supervised fitting/selection vocabulary;
no seen/unseen split may silently use a different vocabulary.

## Interpretation and fixed assessment

Compare combined minus scalar and each neural family minus its same-fit prior.
Retain all25 cell results, pooled results, and five speaker-fold summaries that
pool the five word groups. The 25 cells are not independent replications and
shared training populations must not be counted as additional participants.

Primary endpoints are pooled child per-rater NLL and pooled vote-weighted
rating0/below2 AP. For each regime, report a descriptive combined-vs-scalar
consistency screen:pooled child NLL improves by more than1e-7; each of five
speaker-fold child NLL values is no worse within1e-7; pooled child macro-phone
NLL and Brier are no worse within1e-7; pooled child rating0 and below2 AP are no
worse within1e-7. Retain all checks and differences even if this fails. Do not
use undefined per-cell rare AP as a hidden selection filter. This screen cannot
enable learner feedback or automatically replace any released research bundle.

The canonical grouping fixed word membership before support inspection. The
architecture/hyperparameters have been developed using this corpus before;
these are repeatedly studied author-training speakers, not an untouched final
test. Pretrained encoder lexical exposure is unknown. Separation concerns new
supervised heads and selection only, not the full model's lifetime. No clinical
or all-age child-SSD generalization claim follows from this experiment.

## Verification

Test fit-only normalization/prior membership, deterministic initialization and
training, stable extreme-logit NLL, stopping/tie semantics, fixed-epoch refitting,
row/speaker/word exclusion and freeze-order guards. Independently review source,
replay selected/refit checkpoints, reconstruct histories/selection, all input
bindings, all outer metrics/support and interpretation. Keep author-test closed,
learner judgments disabled and old bundles unchanged. The Mac is sufficient;
no Colab allocation is planned. App builds/tests are unnecessary because this
change is restricted to research training/evaluation code and documents.
