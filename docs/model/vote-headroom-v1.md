# Empirical vote-loss decomposition

Declared September 28, 2026, before computing any per-position vote entropy.
This arithmetic diagnostic follows the failed posterior-pooling comparison.
The earlier reliability report measures fixed-bin event residuals, not this
decomposition. No model is fitted, selected, corrected or promoted here.

Use every one of the same 5,654 original child outer positions at seeds
17, 29 and 43, with the same five expert votes, ordered cell memberships and
speaker folds. Read only the frozen cohort, completed study plan, scalar
records, 150 outer predictions and results, and the existing independent
source/result audit receipts. Bind their hashes and this source/protocol/tests
before calculation. Preserve all original artifacts. Do not open author-test
data, audio, hidden states, weights or other model predictions.

For position i let r_i=c_i/5 be the empirical three-class vote distribution.
The exact minimum NLL against these five observed votes is
H_i=-sum(r_ik log(r_ik)), taking zero terms as zero. For each saved prediction
q, decompose its stable-log NLL into H_i + KL(r_i || q_i). Separately decompose
per-rater Brier into 1-sum(r_ik^2) + sum((q_ik-r_ik)^2). Require both identities
and nonnegative gaps within absolute numerical audit tolerance 1e-12. This
tolerance checks arithmetic; it does not change any model improvement gate.

Report each seed's scalar, fresh-hard acoustic, posterior acoustic, and the
two equal acoustic/scalar mixtures. The shared scalar and all original rows
must match across arms. Reconstruct mixture logs with logaddexp minus log(2).
Cross-check pooled/per-group NLL and Brier against the frozen result within
1e-12. Preserve identical support: positions, recordings, distinct children,
votes, and unanimous/mixed vote-position counts. Report the pooled population,
all five folds, seven ages, 23 phones and 52 children, plus equal-phone pooled
means. No subgroup selection or exclusion follows.

For each model report the empirical loss floor, NLL/Brier excess, excess as a
fraction of observed model NLL, and whether the empirical floor would allow
at least a 5% NLL reduction arithmetically. This is only a bound on this finite
evaluation target. A large gap does not prove an acoustic model can achieve
it; a small gap says nothing about a different cohort, target or clinical
utility. Do not use a leave-one-rater-out predictor as an achievable acoustic
ceiling, estimate population irreducibility, close all model families, fit
smoothing constants, select models or claim clinical pronunciation truth.

All positions have only five observed ratings. Empirical entropy can severely
underestimate population rating uncertainty. Raters, children and recordings
recur; five votes do not create five independent participants. This cohort
has been extensively explored. No inference about statistical superiority,
independent confirmation, SSD validity or learner judgments is produced.

Declaration loads metadata/previous summaries and hashes payloads, but does
not read cohort votes or compute entropy. Calculation requires a separate
independent review bound to the actual declaration. Use exclusive local
outputs, write a preserved failure on error, and allow no implicit restarts.
Check every bound input/source/review/plan hash before and after calculation.
Root must independently reconstruct the arithmetic before interpreting it.
