# Research-service worker cleanup — October 24, 2026

The existing same-Mac research assessment service could finish an attempt while
its audio-processing child was still running. The bridge waited for the Python
worker alone, although that worker launches Node in the same process group.
After a leader crash, the old finalizer skipped termination, removed private
scratch and released the service slot. A subsequent caller could start overlapping
work. This repair changes that actual research route; it adds no sound finding.

## Observed failure and implementation

A generated-process control executed the frozen original bridge. Python leader
37129 exited 7; child37130 remained active in group37129, adopted by PID1, after
the original call returned and scratch was already gone. The independent fixture
then terminated the child and verified an empty group. The control used no model,
recorded voice, participant data or network call.

The repaired bridge uses `waitid` with `WNOWAIT` to retain its child leader until
cleanup. This reserves the process identity through inspection and signalling;
ordinary `Popen.poll()`/`wait()` would reap it too soon. The bridge inspects the
owned group before signalling, sends SIGKILL only when active members remain,
checks group drain within a two-second cleanup budget, and reaps its own leader
only after confirming no active members remain. Each process-table query has a
0.5-second timeout. Inactive orphan zombies cannot execute or hold scratch open;
the OS owns their eventual reaping. This is an active-member guarantee, not an
assertion that every zombie row disappears before the response.

A result is read/exported only after group closure. Scratch is explicitly owned
instead of subject to a temporary-directory destructor. If group inspection,
termination or scratch removal cannot be confirmed, `CleanupUnconfirmed` retains
the owner and directory, and escapes the ordinary unavailable-result handling.
The HTTP service retains that exception, closes the uncertain attempt without a
completion response, reports unavailable health, and refuses subsequent workers.
There is no automatic retry or recovery. Private scratch needs deliberate operator
recovery; restarting is not evidence that an old group stopped or files were removed.

The benchmark also propagates cleanup uncertainty immediately rather than treating
it as a routine failed repetition. Remaining repetitions do not run, a reserved
report is removed, and its CLI prints only the existing generic failure message.
The single-attempt CLI already handles exceptions generically. Reviewed reference
validation and admission callers do not swallow this new exception in their named
error handling. Public request/response schemas, model/source pins, scientific
thresholds, research flags and native eligibility remain unchanged. Two old tests
now mock the dedicated worker-launch seam so process inspection remains real.

## Actual verification and preserved failure

The first current-source run completed 23 tests with21 passes and2 errors. Both
errors occurred in independent fixture cleanup: macOS rejected `killpg` on a group
containing only an exited leader. All seven generated children were already
inactive, but two fixture leaders were not reaped by that cleanup path. The test
parent then exited; a subsequent actual process query found those two PIDs absent.
This exposed a real clean-exit edge case as well. The correction inspects before
signalling and adds a real clean-parent/no-child success case. Original source,
failed logs and receipts remain preserved in `executed-v1/` and `checks-v1/`.

The corrected run passed **32 tests, zero failures, errors or skips**:

| Group | Tests | Actual scope |
| --- | ---: | --- |
| New worker lifecycle | 9 | Clean parent, normal exit with live child, crashed parent with live child, timeout with both alive, prelaunch failure, retained ownership on inspection uncertainty, and HTTP pause for inspection/termination/scratch-removal uncertainty |
| Existing bridge selection | 15 | Input/capture and binding rules, unavailable/privacy behavior, real loopback host/origin/busy behavior, timeout and generated contract fixture |
| Benchmark report tests | 8 | Cleanup uncertainty stops repeats and produces no report/private error; existing failure denominators, binding, output/input protection and silence CLI behavior |

Generated parent/child fixtures use atomic startup barriers and verify exact
PID/PGID relationships. Their independent cleanup does not use the bridge's
cleanup helpers. Eight generated leaders returned; all seven generated children
were absent in final actual checks. The real HTTP tests verify that an uncertain
attempt receives no result, retained scratch remains present, health returns503,
and a later assessment starts zero additional workers. Uncertainty cases are deliberately cleaned by the independent fixture after
asserting production retention; final absence in those cases is not successful
product cleanup. Failure injection tests exercise uncertainty handling; they do
not reproduce a real filesystem failure.

Root personally observed the original control exit0, the first test outer session
16075 exit1, and corrected outer session28197 exit0. The corrected owned test
process40315 closed normally after2.057 seconds without monitor signals, remaining
group members or cleanup errors. The test runner reported1.883 seconds. These
measurements cover generated tests, not speech inference latency or full-system
memory. The owner monitors its test process group; fixture groups have their own
finite lifetimes and independent cleanup. Source compilation and final whitespace
checks also passed.

`POSTCHECK.json` verified14 executed input bindings, all322 preceding handoff
artifacts and10 preceding external bindings unchanged. This turn never operated
a simulator/device, changed the app build, read app Data, loaded model payloads,
opened participant/holdout data, uploaded recordings or sent external messages.
No Torch, NumPy, Transformers, retained-bundle or feature-extractor modules were
loaded in the selected test process. The private-bundle test was explicitly
excluded. No Git publication or deployment occurred.

## Remaining limits

Evidence is in `work/research-worker-group-20261024/`, including the dirty baseline,
source delta, original reproduction, both test runs, executed-v1 source, reviews,
postcheck and final delivery bindings. This is Mac process/HTTP verification; no
new real speech inference, SDK build, mobile UI or physical capture was tested.
It assumes the fixed worker/Node programs retain their inherited group. Escaped
sessions and abrupt host/service death are outside this guarantee. `WNOWAIT`
support is checked before launch; the actual run used Python3.13.14 on macOS.
Filesystem removal is synchronous, so the two-second group budget is not a hard
whole-request deadline. Operator recovery is deliberate, not an implemented
self-healing flow.

Sound correctness, individualized error feedback and clinical diagnosis remain
unsupported. Native acoustic composition/resources remain unqualified, the closed
q8/public-head screens stay closed, and independent sound references, measurement
reliability and reviewer acceptance remain outstanding. The broad app goal stays
active.
