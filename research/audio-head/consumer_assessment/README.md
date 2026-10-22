# Local research assessment bridge

This engineering bridge runs supplied mono PCM16 audio through the frozen,
occurrence-aware feature extractor and the retained ages 6–12 research mixture.
It returns subjective corpus rating class 0/1/2 distributions internally. It
provides no pronunciation verdict, diagnosis, practice selection or learner
feedback. Prompt matching is always `unverified`; a forced canonical path can
assign an interval to a phone that the child did not produce. Completed age is
caller supplied and is a scope guard, not an identity or acoustic estimate.
All responses keep `researchOnly: true`, `learnerFeedbackEligible: false`,
`clinicalUseEligible: false` and `productionUseEligible: false`.

From the repository root, start the local service with the existing environment:

```sh
PYTHONPATH=research/audio-head research/audio-head/.venv/bin/python \
  -m consumer_assessment.service --port 8765
```

The service binds only `127.0.0.1`. There is no external bind option. An iOS
simulator on this Mac can reach it; a physical phone cannot reach this loopback
endpoint. `/health` reports service liveness and that model availability is
checked per attempt. Successful inference was observed locally with the existing
cached encoders; it requires their unchanged pinned bytes and the retained bundle.
Missing, corrupt or changed model/source bindings fail closed.

`POST /v1/assessment` takes JSON described by [contract.json](contract.json):
`schemaVersion: 1`, a canonical lowercase UUID `attemptId`, integer `ageYears`
6–12, strict-base64 `audioBase64`, and an explicit schema-2 canonical English
prompt. Words include caller-chosen ARPAbet phones; the bridge neither consults a
pronunciation dictionary nor chooses among variants. Targets identify unique
caller IDs and zero-based word/phone positions, preserving caller order and
repeated consonants. Up to 512 phones and 512 targets are accepted. /ZH/ and
syllabic /ER/ are unsupported assessment targets, although they can appear in
canonical context. A canonical sequence that cannot fit the CTC frame grid is
unavailable. No request accepts a filesystem path, checkpoint, child identity
or executable choice.

The WAV reader requires an exact RIFF container with a single format and data
chunk, PCM format 1, mono, 16 kHz, 16-bit samples and consistent byte rate/block
alignment. Captures must be 0.1–4 seconds and at most 132,096 WAV bytes. The
capture policy is deliberately an engineering policy: exact all-zero samples
produce `silence`; any integer sample at -32768 or 32767 produces `clipping`.
These checks do not establish speech presence, prompt matching, clinical audio
quality or nonspeech rejection. No VAD threshold was fitted or selected.

Responses bind the attempt ID, SHA-256 of the exact HTTP request body bytes,
SHA-256 of the decoded WAV bytes and SHA-256 of sorted-key compact UTF-8 prompt
JSON (Python's default ASCII escaping). Valid unavailable requests retain their
bindings. Input fields that could not be parsed safely have null bindings.
`targets` is always an array, empty for unavailable outcomes; a processed result
contains the original target identities plus internal
`subjectiveCorpusRatingProbabilities`. Native learner UI must not render these
probabilities. `timingMilliseconds` has `total` and `inference`; `captureMetrics`
is null or contains sample count, duration, RMS, peak and rail sample count.
The response offers no verified phone boundary or produced-phone label.

The endpoint requires exact `Content-Type: application/json`, a bounded
`Content-Length`, no transfer encoding, no duplicate security headers and no
`Origin` header. It validates `Host` as `localhost:<configured port>` or
`127.0.0.1:<configured port>`; it supplies no CORS headers. Bodies are capped at
220,000 bytes, reads have a five-second absolute deadline, model work has a
90-second timeout, and one model worker runs at a time. The Debug native client
waits up to 100 seconds per request and 105 seconds for the resource, leaving
time for worker termination and the bound response. A virtual-input diagnostic
observed the CTC result file at 38.797 seconds and timed out at the former
45-second limit before the full pipeline returned. The exact remaining bottleneck
is unvalidated; the negative results are retained. No model, admission or judgment
threshold changed. Four request threads
and a two-socket backlog are allowed; excess sockets are closed and otherwise
concurrent attempts receive bound `busy` responses. This is a local engineering
endpoint, without authentication or an assertion of child identity.

HTTP uses a fresh private temporary directory for each worker. Raw request,
audio, features, CTC artifacts and temporary runtime model copies are removed
on worker completion, failure, cancellation of the parent call or timeout.
Timeout kills the worker process group, including its CTC child. Client
disconnection after the request is read can leave bounded work running until
completion or timeout; its files are still removed. Abrupt host/process death
cannot guarantee cleanup. There are no request logs, private error strings,
tracebacks or retained HTTP attempt artifacts. Responses use `Cache-Control:
no-store`. No model download is permitted; the CTC worker denies fetch and
Python loaders use pinned local files with offline configuration.

For deliberate local engineering artifact export from supplied permitted audio:

```sh
PYTHONPATH=research/audio-head research/audio-head/.venv/bin/python \
  -m consumer_assessment.cli --wav /absolute/permitted.wav \
  --prompt /absolute/schema2-prompt.json --age-years 9 \
  --output /absolute/fresh-engineering-output
```

`--output` is optional and never overwrites an existing directory. With it, the
CLI deliberately retains `request.json` (including base64 audio),
`response.json`, and, on success, `features.npy` plus `engineering.json`.
These may contain private research inputs. Without it, only the public response
is printed and worker artifacts are deleted. Both CLI and HTTP call the same
bridge; CLI request hashing uses its exact canonical request bytes. Saved
scientific outputs and checkpoints are read-only. The bridge never invokes the
old audio runner's incompatible `--bundle` argument or any study fitting code.
The preserved PERCEPT-R specialist remains a separate candidate; it is not
mixed into the SpeechOcean 0/1/2 response.

Run focused tests:

```sh
PYTHONPATH=research/audio-head research/audio-head/.venv/bin/python \
  -m unittest consumer_assessment.test_bridge
```

The synthetic fixtures provide a processed response shape and a self-consistent
silence request/response pair. The processed fixture's hash placeholders and
probabilities are illustrative, not model evidence. Silence-fixture times are
fixed zero for stable tests. Real engineering evidence is separate in
`work/assessment-milestone-20261002/bridge/` and must not be confused with a
clinical study. One permitted age-6 fitting fixture (000010011, 2.58 seconds,
six targets) processed in 9.106 seconds. All 6,222 fresh feature values and CTC
posterior bytes match the saved fitting references exactly. Direct retained
loader probabilities match exactly. Original fitting-batch predictions differ
by at most 3.16e-8 probability and 4.14e-7 log-probability, within the loader's
established 1e-6 log-probability tolerance. Source hashes stayed unchanged and
CTC fetch attempts were zero. This is implementation parity, not new accuracy,
prospective child evidence or a sealed TEST evaluation.


## Repeated runtime and sampled memory

Use supplied permitted engineering inputs and a fresh aggregate report path:

```sh
PYTHONPATH=research/audio-head research/audio-head/.venv/bin/python \
  -m consumer_assessment.benchmark --wav /absolute/permitted.wav \
  --prompt /absolute/schema2-prompt.json --age-years 6 \
  --repeats 3 --output /absolute/fresh-runtime-report.json
```

The tool reports every attempted outcome, exact input/source/model hashes, elapsed
time and sampled process-tree RSS. It exports no audio, features or probabilities.
It refuses existing output paths. Workers start fresh for each call; OS disk cache
is uncontrolled and no resident-model warm measurement exists. Sampling can miss
peaks, count shared pages twice and observe process rows at different instants.

Three calls on the previously permitted 2.58-second fitting fixture took
8.179, 6.381 and 6.454 seconds, all processed, with about 1.61 GiB sampled descendant
RSS on an Apple M3 Max. Background host activity was uncontrolled. These are
one-fixture Mac engineering observations, not phone performance or clinical
accuracy. Temporary copies/stages were removed. See the
[runtime checkpoint](../../../docs/implementation/consumer-assessment-runtime-20261002.md)
for receipts, limitations and the real synthetic native model-loopback check.

The combined bridge and benchmark suite is:

```sh
PYTHONPATH=research/audio-head research/audio-head/.venv/bin/python \
  -m unittest consumer_assessment.test_bridge consumer_assessment.test_benchmark
```

### October 15 fresh-worker follow-up

A fixed T-then-N measurement used two existing permitted training-derived word
recordings, with two calls each and the unchanged 90-second worker limit. All four
processed: T took 8.300/6.434 seconds and N took 6.396/6.526 seconds. Maximum sampled
aggregate descendant RSS was approximately 1.57 GiB, with zero sampling errors.
All four workers exited zero, known process groups were absent, scratch was empty,
and fixed source/input bindings were unchanged. The actual enclosing command
exited zero; reports and closure were independently read afterward.

Each worker was a fresh process, but OS disk cache and other host activity were
uncontrolled. N follows the two T calls. These direct-bridge timings exclude the
native recognizer, HTTP, recording and UI, and provide no machine-cold, exact
peak-memory, phone-performance or accuracy guarantee. The earlier 45-second
startup failures remain preserved and were not reproduced here. No additional
budget or model change was made. See the [current integration report](../../../docs/consumer-assessment/native-guided-model-integration-20261014.md#fresh-worker-runtime-check-october-15)
and local evidence in `work/model-fresh-worker-runtime-20261015/`.
