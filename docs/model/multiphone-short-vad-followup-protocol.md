# Conditional phone-evidence follow-up

This exploratory follow-up is selected after the completed fixed 250/100-ms
VAD comparison, report SHA-256
`936814170ea54b37addb84211b99d80153e53096b6c8892bc1b0b936710e9bae`.
It does not revise that report or represent an independent predeclared
combined-gate experiment. No segmentation setting or threshold changes.

Retain all 24 fresh environmental clips in the denominator. Derive the
conditional inference selection from all fresh records with short100=true in
the bound comparison report. Exactly two qualify: dog `4-182395-A-0.wav`
(both VAD policies) and helicopter `4-161579-A-40.wav` (100 ms only).
Run the existing raw adapter and fixed phone-evidence gate once for each.
For the remaining 22, phoneEvidence and recognizedPhoneTokens remain null,
phoneEvidenceMeasured is false, and each combined result is logically false
because its VAD decision is false. Never imply phone inference occurred there.
For a VAD-positive clip, combined equals its measured phone-gate decision.
Missing or extra phone measurements fail verification.

Reuse the original environment plan SHA-256
`1016d94bb15fab78929319da24f3706980c742505d50e805ea8bbbe60f45d9e9`:
replayed unweighted-all-age head, BALL prompt (`B AO1 L`, target B), contract,
node executable, phonetic snapshot and CPU/two-thread raw runtime. Bind all
24 fresh input identifiers/audio hashes, comparison report/plan/artifacts,
original plan/runtime/head/source pins, follow-up source/tests/protocol before
any inference. No new VAD acoustic inference, model fitting, uploads,
threshold tuning, label transfer or learner judgments occur.

The fresh ignored output is `outputs/multiphone-20260927/short-vad-followup-v1`.
Declare first, then run with the exact plan SHA. Existing output prevents
implicit restart. Pipeline exceptions abort and preserve partial evidence;
they are never counted as abstention. A complete report is published only
when both raw runs and gate results pass verification.

Read-only verification hashes every raw artifact and gated report, verifies
the fixed audio/prompt/head/contract/runtime inputs, binds the CTC job and
posterior bytes to the actual waveform, and recomputes the fixed phone gate
from cached posterior bytes. It reconstructs every conjunction and both
24-clip totals; it performs no acoustic inference and writes no artifacts.

Environmental labels are not speech ground truth. Acceptance establishes
neither speech nor prompt match nor pronunciation correctness. These clips
are source-disjoint from the previous twelve, but pretrained overlap remains
unknown. The two conditional measurements add no independent validation of
the development-selected 100-ms policy.

From research/audio-head, run `.venv/bin/python -m unittest
 test_multiphone_short_vad_followup`, then invoke the same interpreter with
`multiphone_short_vad_followup.py declare`. Review its plan and run with
`multiphone_short_vad_followup.py run --plan-sha256 <sha>`. Reconstruct using
`multiphone_short_vad_followup.py verify --plan-sha256 <sha>`.
