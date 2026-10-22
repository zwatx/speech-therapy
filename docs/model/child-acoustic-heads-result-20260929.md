# Child acoustic representation comparison: result

**The child-trained encoder (M10) did not improve rating prediction.** It was slightly worse than the adult encoder (M6) and worse than the retained model on every primary metric. It fails the fixed advancement screen. This closes this exact comparison only; it is not evidence against child adaptation in general. The retained research bundle is unchanged.

This is development evidence on extensively reused data, not fresh validation. The five expert votes are observed ratings, not produced-phone truth. Different pretraining lineage, training amounts and stored precision rule out any causal claim about child-domain training.

## Primary result

The primary population is 5,654 original outer positions from 52 children, across all 23 consonants. The metric is pooled five-vote NLL (lower is better).

| Arm | NLL | Phone-macro NLL | Per-rater Brier | Rating-0 AP | Below-2 AP |
| --- | ---: | ---: | ---: | ---: | ---: |
| Scalar only | .18012 | .19311 | .08161 | .08843 | .16021 |
| **Retained** (scalar + cached compact) | **.17746** | **.18910** | **.08037** | **.09208** | **.16988** |
| Adult (scalar + M6 compact) | .17861 | .19145 | .08090 | .08650 | .16318 |
| Child (scalar + M10 compact) | .17900 | .19198 | .08099 | .08543 | .16427 |

| Contrast | NLL Δ | 95% bootstrap | Leave-one-child-out favorable |
| --- | ---: | --- | ---: |
| Child − adult | +.00039 | [−.00085, +.00161] | 0 / 52 |
| Child − retained | +.00154 | [−.00050, +.00374] | 0 / 52 |
| Adult − retained | +.00115 | [−.00030, +.00290] | 0 / 52 |

The bootstrap uses 2,000 paired child resamples within the five original speaker folds (9/10/14/9/10 children). No replicate was undefined for any metric.

- **Screen checks.**
  - Failed: the NLL-gain checks (need ≥ .005 against both adult and retained; the child arm was worse against both), both bootstrap upper endpoints, and both leave-one-child-out sign checks.
  - Passed: the four guards against retained (macro NLL, Brier, and both APs), but the child arm is still worse than retained on each of them.
- **Heterogeneity.**
  - Speaker fold 4 favored the child arm (−.0035 vs adult, −.0024 vs retained). Folds 0–3 did not.
  - Per child, the child arm beat retained for 20/52 children and beat adult for 22/52.
  - Per phone, it beat retained on 5/23 consonants (DH, L, M, P, W) and adult on 12/23. CH, TH, Z, NG and R were among the largest losses against retained. Rare-event support is clustered, so none of these per-phone patterns is a finding.
- **Added population (descriptive only, 4,237 positions).** Both new arms edged out retained on pooled NLL (adult −.00091, child −.00040), and child was again worse than adult. These positions never enter the screen.

## Verification

- **Pipeline check against controls.** Before any new-arm outer prediction, the worker refit all 25 cached control jobs from the retained features through the same code path. It reproduced the frozen controls exactly: selected epochs 25/25, tensor-equal refit weights 25/25, and exact predictions 25/25. Features through the cache mapping were byte-identical, and frozen checkpoints replayed exactly.
- **Batching.** New arms predict child rows in 64-row batches, while the cached controls were predicted over all outer rows. This shifts mixture log-probabilities by at most 7.5e-7 and every primary metric by at most 2.6e-12. Rebuilding the retained arm from child-only batches changed no screen check.
- **Evaluator replay.** The evaluator replayed every new-arm refit from its own feature cache and matched the saved predictions exactly. It also asserted that its lean bootstrap metric path equals the frozen summary path within 1e-12.
- **Fits.** The 100 protocol fits (M6 and M10, 25 cells × inner/refit), plus the 50 verification-only control fits, ran on the Mac CPU (2 threads, seed 7, unchanged recipe) in about 2 minutes. No Colab compute was used.
- **Reviews.**
  - GPT-6 Astra (Codex, read-only) first returned three blocking lineage/binding findings, which were fixed.
  - Fable 5.1 (Claude CLI, `claude-fable-5-1` confirmed from usage metadata) then cleared the full review and the follow-up delta.
  - Synthetic tests: 15 pass.

## Artifacts

- Workers and tests: `work/child-acoustic-heads-20260929/` (`heads.py`, `evaluate.py`, `test_heads.py`, `test_evaluate.py`)
- Declaration: `v1/declaration.json`, SHA-256 `470cb35f7dfc28ac77bf73807377e2cffb547e81f754200734111b875f51b89d`
- Control checks: `v1/control-replay.json`, `v1/control-refit-check.json`
- Evaluation: `v1/evaluation/report.json`, SHA-256 `42bf7fbc29f860b228507849eae4b0b27f1c657af7a382b0f6f568d4cdec323f`
- Reviews: `review-astra-v1.md`, `review-fable-v1.md`, `review-fable-v2.md`

Protocol: [child-acoustic-transfer-protocol-20260928.md](child-acoustic-transfer-protocol-20260928.md). Prior status: [child-acoustic-transfer-status-20260928.md](child-acoustic-transfer-status-20260928.md).
