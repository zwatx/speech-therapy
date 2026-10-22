# Fixed48 strict reference comparison — October 13, 2026

The comparison completed and passed independent operational qualification. It produced **no defined accuracy estimate**: all 48 predictions completed and all 48 manual references were read, but every reference was unscorable under the unchanged frozen rules. No item was paired for scoring. Zero accumulated edits therefore does not mean zero errors.

| Outcome | Count |
| --- | ---: |
| Planned / completed predictions | 48 / 48 |
| References read / not read | 48 / 0 |
| Scorable / unscorable references | 0 / 48 |
| Scored pairs | 0 |
| Speakers with a defined / undefined rate | 0 / 4 |
| Completed hypothesis tokens / unsupported tokens | 1,363 / 90 |

Micro and speaker-macro strict mapped-token error rates are both null. Reference reasons are nonexclusive: unresolved nonlexical labels occurred in 48 items, unsupported deviation tags in 15, and malformed annotations in 2. The parser treats `sp` or empty phone labels as unresolved, accepts exact `sil` as silence, and rejects deviation-marked phones. These reasons describe the frozen reference policy; they do not establish model accuracy or the cause of each private annotation.

The publisher describes manual canonical/perceived substitution, addition and deletion annotations, including uncertain and deviation-marked phones. Its documentation does not explicitly settle `sp` and empty-label interpretation. Any future policy needs a documented prospective reference definition; this completed result will remain unchanged. [Publisher documentation](https://psi.engr.tamu.edu/l2-arctic-corpus-docs/), checked October 13, 2026.

Predictions and failures were locked before annotations opened. The cohort, waveform handling, model, vocabulary, mapping, parser, metric and thresholds were not changed after outcomes. No replacement, rescue run or reserve annotation opening occurred. Twenty reserve speakers remain untouched. This adult research run establishes neither produced-phone ground truth nor child, clinical, commercial or learner-feedback eligibility.

The first V1 launch failed before worker creation or label reading because its generic source-manifest adapter rejected the metric's provenance fields. V2 corrected only that adapter and mechanical paths/pins, with independent source review; the failed V1 attempt remains preserved in the [preflight report](l2-strict-scoring-preflight-result-20261013.md).

Actual V2 terminals: enclosing session 21008 exit 0 (`4b8b22`); independent collector session 38217 exit 0 (`57e2c2`); final terminal-binding session 80692 exit 0 (`c87de4`). Final binding completed 335.870 seconds after the original root origin, within 1,200 seconds. The independent collector recomputed full reference parsing, edit aggregation and current source/model/runtime/input/output/archive checks. Known parent/worker PIDs were absent; final binding also checked the completed collector. No process-group absence is claimed.

Private evidence in `work/l2-pilot-scoring-draft-v2`:

- `ROOT-ACTUAL-QUALIFICATION-v1.json`: 2,742 bytes; SHA256 `5432e49138bea44323f65897dc83c7f2230b31c98abd63fff7f6017cf609bdc7`.
- `ROOT-COLLECTOR-TERMINAL-v1.json`: 962 bytes; SHA256 `b943afa7074e9dbef88a4be9a2b5dd52673750851bd35da3f54783fa5a3584f8`.
- `execution-v1/PUBLIC-AGGREGATE.json`: 2,049 bytes; SHA256 `b7f604e53ce7aa24bb786682c043ab55eccdc6eff331bb67a726fbed6c354201`.

Raw references, participant-level results, hypotheses, arrays and confusions remain local. The public aggregate retains all planned outcomes and undefined denominators. Sound-specific corrective findings remain disabled.
