# Fresh nonspeech admission check, Part A

This worker implements the fixed revision-2 protocol in
`docs/model/nonspeech-robustness-protocol-draft-20260929.md`. It changes no model,
prompt, policy, threshold, or learner behavior. Results are admissions by category
label, with combined250 and combined100 as co-primary outcomes. Part B remains
blocked; this check cannot establish speech retention or satisfy the campaign
handoff requirement.

Run from `research/audio-head` with the existing `.venv/bin/python`:

```sh
.venv/bin/python -m unittest nonspeech_robustness.test_study
.venv/bin/python -m nonspeech_robustness.study declare --output outputs/nonspeech-robustness-20260929/v1
.venv/bin/python -m nonspeech_robustness.study acquire --output outputs/nonspeech-robustness-20260929/v1 --declaration-sha256 DECLARATION_SHA
.venv/bin/python -m nonspeech_robustness.study run --output outputs/nonspeech-robustness-20260929/v1 --declaration-sha256 DECLARATION_SHA --acquisition-sha256 ACQUISITION_SHA
.venv/bin/python -m nonspeech_robustness.study verify --output outputs/nonspeech-robustness-20260929/v1 --declaration-sha256 DECLARATION_SHA --acquisition-sha256 ACQUISITION_SHA --report-sha256 REPORT_SHA
```

Declaration uses existing, approved ESC metadata. It recursively audits all
historical folders, file names, and textual records, excluding `esc50.csv`, with
bounded-memory reads. It asserts the exact union of 60 historical selections,
excludes their sources, then selects 60 fresh clips in the fixed category order.
Source, helper, test, protocol, runtime, binary, checkpoint, head, prompt, and
approved filter bindings are frozen before audio acquisition. The approved
environment check precedes all network requests. Public Git commit/tree metadata
binds each original audio blob to its commit and expected size before acquisition.

The separate acquisition stage checks the original Git blob identity, records
original and converted SHA256, and uses the unchanged environment conversion
helper: mono 16-kHz PCM16, no trimming or normalization. Network and integrity
errors stop globally. Other conversion, adapter, or filter failures stay in the
denominator as failed clips. Each stage has a fresh output guard; there is no
resume, retry, substitution, or rescue command. Interrupted stages preserve their
outputs for inspection and cannot produce a verified complete report.

The existing raw adapter and short filter run on CPU with two threads. One Silero
pass produces both policies. Per-clip reports bind phone evidence and recognized
token count, both VAD decisions, and both combined decisions. Failed raw stages
can leave `.partial` directories; the final manifest discloses their inventory.
Offline verification reads and hashes the bound lineage and raw artifacts, checks
the arithmetic and common probability trace, and reconstructs every count. It
never downloads, converts, runs models, or reruns filters. Keep audio in ignored
outputs and do not redistribute it. Use is strictly noncommercial research.

Downloads use the pinned system curl with TLS verification, disabled user config,
HTTPS-only redirects, a size limit, and zero retries. Run and verification require
the acquisition SHA returned by acquisition, as well as the declaration SHA.
