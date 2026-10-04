# Encoder-output validation — October 25, 2026

The native word recognizer now checks contiguous encoder output using a scoped
Float buffer. This removes repeated boxed index access while preserving the exact
shape/type/count admission, every logical finite-value check, the cancellation
check before each of 1,500 frames, and the existing error categories. Unusual
strides retain the original indexed scan. The decoder, model inputs, recognition
policy, cooperative deadline and cleanup ownership are unchanged.

## Measured scope

A generated-array comparison used the preserved indexed loop and the actual new
production helper, compiled with Swift 6 and `-O` on this Mac. The array shape was
`[1, 1500, 512]`, Float32, with 768,000 logical values and contiguous strides
`[768000, 512, 1]`. Allocation and initialization occurred before timing. Each
measurement included metadata admission, buffer acquisition where applicable,
finite checks and the same 1,500 locked cancellation reads. Two warmups per scan
preceded ten paired trials, alternating execution order.

| Actual-helper comparison | Median | Range |
| --- | ---: | ---: |
| Preserved indexed scan | 340.038 ms | 336.503–354.904 ms |
| Canonical scoped scan | 0.250 ms | 0.239–0.269 ms |

This is a measurement of generated tensor validation, **not full word-check
latency**. It does not establish fewer timeouts, recognition accuracy, individual
sound correctness or clinical benefit. The earlier saved encoder-to-decoder time
window was a lead for investigation, not an isolated measurement of this scan.

The first prototype also passed before the production edit; its medians were
340.786 ms and 0.253 ms. The final comparison calls
`WhisperEncoderStateValidation.validate` from the canonical source. Its Mac-only
harness projects the two error cases used by that helper; the iOS tests below
compile the full actual app and production error/stop types.

## Correctness and integration

All 23 differential cases passed before either timing run: finite extrema, signed
zero and subnormals; NaN and both infinities at the first, interior and last
logical positions; wrong type and shapes/ranks; padded and transposed layouts;
logical NaN rejection while ignoring NaN padding; pre-cancellation and exact
cancellation at frame checks 1, 2, 750 and 1,500.

Six focused XCTest methods passed in the canonical Debug iOS app on the owned
iPhone SE third-generation simulator, iOS 26.2. These additionally cover negative
finite extrema, a wrong-count shape, the actual previously cancelled operation,
and all four deterministic cancellation boundaries on contiguous, padded and
transposed arrays. The Debug unit host is inert. No model or recording was loaded
for recognition, and no sensor or playback flow was requested by these tests.

Both Mac compiler/measurement processes and the iOS test process exited normally,
with no signalled termination or remaining owned process-group members. The iOS
result reports six passed, zero failed, zero skipped, zero expected failures and
no result runtime warnings. Raw tool diagnostics are retained; this is not a claim
that every Xcode log line is warning-free. The owned and protected simulators were
both confirmed shut down afterward; the protected simulator was only listed.

The implementation uses Apple's scoped
[typed buffer API](https://developer.apple.com/documentation/coreml/mlmultiarray/withunsafebufferpointer(oftype:_:))
and checks the current strides inside that scope. A pointer never escapes the
closure. No new production `dataPointer` access was added. The installed SDK
declares the API available since iOS 15.4, within the app's iOS 17 minimum.

## Retained evidence and limits

Task-local evidence is in `work/encoder-scan-performance-20261025/`:

- `prototype-v1/RESULT.json` and `actual-v1/RESULT.json`: all correctness outcomes
  and individual paired durations, including medians and ranges.
- `unit-checks-v1/Tests.xcresult`, exported summary/test records and `VERIFIED.json`:
  exact six-test selection, compiler admission and retained results.
- Before/executed copies, frozen tool/source pins, process receipts and final
  bindings distinguish the historical baseline from the current implementation.

No shipping candidate was replaced. This increment does not qualify an ordinary
Release word-check run, physical device, real microphone, mirror, VoiceOver or
end-to-end model inference. Historical demo candidate 5 and limited QA candidate 6
retain their prior roles and limits. Existing accessibility findings and external
rights, qualified-review and clinical-validation requirements remain open.
