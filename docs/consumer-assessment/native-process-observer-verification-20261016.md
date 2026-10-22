# Native process-observer component verification — October 16, 2026

The macOS process-observation component now has actual live-to-exit and late-observation evidence, plus separate passing EXEC and FORK negative controls. The full observer, simulator transport and Q8 numerical investigation remain unqualified. Q8 remains WITHHELD; these results do not change pronunciation feedback or establish diagnostic accuracy.

The public KERN_PROC_PID helper decodes only the sourced 48-byte process prefix. An actual self-process probe returned a 648-byte record from a 3,888-byte sizing capacity. Two preliminary copies and two explicitly qualified copies agreed with four actual 136-byte BSD records on PID and exact microsecond birth; separate BSD and target-ps checks verified ownership. The helper freezes the returned extent, rather than treating the larger capacity as the record size. A candidate profile requires its matching complete root receipt and digest chain; its existence alone is insufficient.

The helper's 15 pure tests passed once. The control's five separate pure tests passed once, including preservation of a non-ESRCH permission error without invoking ps. Independent source and result reviews cleared both groups. These synthetic tests cover validation and failure evidence; actual process results follow separately.

| Actual run | Case | Result | Scope |
| --- | --- | --- | --- |
| V4 | Positive | PASS | Actual registration, bound EXIT, same-birth status-5 proof bracketing target ps, natural wait 0 and fresh PID/group absence. |
| V4 | Late arm | PASS | Independent same-birth status-5 proofs before and after the live API's exact ESRCH rejection; no registration, then normal wait/absence. |
| V4 | EXEC | FAILED | Observed executable was the Python launcher. Exact worker-path verification rejected it before registration. |
| V4 | FORK | NOT RUN | Sequence stopped at the EXEC failure. |
| V5 | EXEC | PASS | Direct pinned-worker startup, successful registration, actual bound EXEC rejection, same-birth status-5 proof and normal closure. |
| V5 | FORK | PASS | Direct pinned-worker startup, successful registration, actual bound FORK rejection, same-birth status-5 proof and normal closure. |

V4 remains a failed four-case sequence. V5 is a new two-case negative sequence; these are separate versioned results, not one fresh all-four pass. The V5 control changed only its negative fixture's initial executable and report schema. It retained the same existing binaries, finite snippets, exact-path checks, event rules, birth checks and deadlines. Earlier failures remain preserved.

Every successful control retained the fixed launch+1.3-second unreaped boundary, native five-second deadline, once-anchored two-second closure window and ten-second enclosing mode limit. Owned wait returned 0; fresh numeric ps selection found neither the PID nor its group. All actual owner terminals, including the failed V4 EXEC attempt, recorded no signals, cleanup errors or remaining worker-group members. V4's sequence took 4.138 seconds and stopped on its third attempt; V5's separate two-case sequence took 3.270 seconds. The owner RSS limit is sampled worker-group coverage, not full descendant resource qualification.

Evidence is stored in work/native-q8-kinfo-prefix-20261016, work/native-q8-kinfo-self-probe-20261016, work/native-q8-adapter-controls-20261016-v4 and work/native-q8-adapter-controls-20261016-v5. The self profile's delivery bound 243 current artifacts; V4's partial-failure closure bound 333; V5's closure bound 357, preserving the earlier chain. Independent reviews distinguish source clearance, actual results and remaining scope. The independent V5 actual result review is CLEAR for the two negative controls.

The next step is the smallest integration that establishes immutable ownership, complete resource/process observation, exit-pending handling and independently checked normal completion, followed by a harmless simulator transport check. Existing numerical guards, tolerances, model/input/reference identities and the separately frozen two-call numerical plan remain unchanged. These component checks used local process fixtures and did not start a simulator, speech-recognition task, model inference or recording operation. Apple English assets and prior capability are established separately; the earlier Apple Speech authorization denial remains unresolved, and bundled word recognition remains the previously verified app default.
