# Fixed child/adult encoder comparison — closed

Completed September 29, 2026. The M10 child encoder failed the fixed advancement screen. Neither new encoder replaces the retained research model. This closes this exact representation/head comparison; it does not rule out child adaptation generally.

## Primary results

Same 5,654 original positions from 52 children, with five observed expert ratings per position. Lower NLL, macro NLL and Brier are better; higher average precision (AP) is better. All new acoustic arms use a fixed equal mixture with cached scalar predictions.

| Arm | Pooled NLL | Phone macro NLL | Brier | Rating-0 AP | Below-2 AP |
| --- | ---: | ---: | ---: | ---: | ---: |
| Scalar confidence features only | 0.18012408 | 0.19311432 | 0.08160528 | 0.08843164 | 0.16020708 |
| Retained scalar/PCA mixture | 0.17745892 | 0.18909544 | 0.08037162 | 0.09207970 | 0.16987552 |
| Adult M6 mixture | 0.17860963 | 0.19144999 | 0.08089622 | 0.08649809 | 0.16318000 |
| Child M10 mixture | 0.17900132 | 0.19198111 | 0.08098953 | 0.08543221 | 0.16427044 |

## Fixed decision and uncertainty

- child-adult: NLL difference +0.00039169; fixed whole-child bootstrap range [-0.00085462, +0.00160516].
- child-retained: NLL difference +0.00154240; fixed whole-child bootstrap range [-0.00050067, +0.00373936].
- adult-retained: NLL difference +0.00115071; fixed whole-child bootstrap range [-0.00033468, +0.00287119].

The child arm is worse than retained on all five pooled endpoints. The interval spanning zero for child versus adult means a clear difference was not established; it does not establish equivalence. The original screen requires at least .005 NLL improvement against both adult and retained, both bootstrap upper bounds below zero, and favorable NLL after every child deletion. All six advancement checks fail; all four secondary regression guards pass. The batching diagnostic changes no screen decision.

The 4,237 added positions are descriptive only. Their child NLL is slightly better than retained, while macro NLL, Brier and both AP endpoints worsen. These positions do not replace the fixed primary population.

## Execution and evidence

- 100 new head fits (50 M6, 50 M10), plus 50 control verification fits on Mac CPU. Control refits reproduced cached epochs, weights and predictions for all 25 cells. No new encoder inference or decoded audio in this fitting phase.
- Fifteen synthetic worker tests and Fable 5.1 source reviews were completed in the preceding Claude session. This report does not claim those synthetic tests establish real model accuracy.
- No Colab allocation in this comparison. The preceding account check reported 299.97 units; this report is not a new balance check.
- The data are extensively reused adaptive development data. Bootstrap and child deletions are conditional stability diagnostics, not fresh population validation. Ratings are not produced-phone truth. Differing checkpoint lineage, training amounts and precision prevent causal attribution to child-domain training.
- Retained bundle unchanged; no clinical eligibility or learner judgments enabled.

[Machine-readable report](/Users/zacharywilson/Documents/speech-therapy/work/child-acoustic-heads-20260929/v1/evaluation/report.json) — SHA-256 `42bf7fbc29f860b228507849eae4b0b27f1c657af7a382b0f6f568d4cdec323f`.
[Execution declaration](/Users/zacharywilson/Documents/speech-therapy/work/child-acoustic-heads-20260929/v1/declaration.json) — SHA-256 `470cb35f7dfc28ac77bf73807377e2cffb547e81f754200734111b875f51b89d`.
[Fixed protocol](child-acoustic-transfer-protocol-20260928.md).
