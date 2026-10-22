# Conditional phone-evidence result

September 27, 2026. After the fixed duration comparison, the two fresh
environmental recordings admitted by the 100 ms VAD rule received actual
phone-evidence inference. The helicopter clip produced zero recognized phone
tokens and was withheld. The dog-category clip produced two and remained
admitted. **Both combined policies admit one of the 24 fresh recordings.**

| Recording | 250 ms VAD | 100 ms VAD | Phone tokens | 250 ms combined | 100 ms combined |
| --- | --- | --- | ---: | --- | --- |
| `4-161579-A-40.wav` — helicopter | Withheld | Admitted | 0 | Withheld | Withheld |
| `4-182395-A-0.wav` — dog | Admitted | Admitted | 2 | Admitted | Admitted |
| Other 22 recordings | Withheld | Withheld | Unmeasured | Withheld | Withheld |

The [follow-up protocol](multiphone-short-vad-followup-protocol.md) explicitly
selects these two clips after seeing VAD outcomes. This is conditional pipeline
characterization, not an independent predeclared combined-model experiment.
The other 22 have null phone-evidence fields: conjunction with a false VAD
decision is false without measuring their phone evidence. No recording is
removed from the denominator, and both actual runs completed without failure.

The fixed raw adapter used the original BALL prompt, target B, unweighted
all-age head and CPU with two threads. The phone check reads greedy CTC tokens;
it does not require an exact canonical prompt match. No VAD inference, fitting
or threshold adjustment was repeated. Raw diagnostic scores are not correctness
labels and are not learner feedback.

Together with the [duration comparison](multiphone-short-vad-report.md), this
supports an explicit 100 ms research-filter option: it preserves all seventeen
observed crops while showing the same combined admission count as the 250 ms
rule on this extension. This does not prove equivalent population rejection
rates. The admitted dog-category recording still illustrates the limit of a
necessary-input check; category labels do not establish whether incidental
speech is present. Speech presence, prompt matching and correct articulation
are different questions.

Seven focused tests passed before inference. A separate verifier rehashed all
raw artifacts, reconstructed the fixed prompt and runtime metadata, bound
posterior bytes to the actual waveform, recomputed both phone decisions and
reconstructed all 24 conjunctions. All raw CTC jobs record zero model-fetch
attempts. No learner-feedback or app-default change follows.
Independent read-only review reproduced all artifact/prompt/runtime checks,
both phone decisions and all combined outcomes; no blocker remained.

- Plan SHA-256: `02b267938394cdc9970d8458ea3e1aaabfbe8d8fd7e2a758b1d45af6c761985d`.
- Result SHA-256: `94ecd1e3a19ba744ca3a8b8f74dde74d88fcb41853f09da0c2c71fa98aceeae4`.
- Evidence: `research/audio-head/outputs/multiphone-20260927/short-vad-followup-v1/`.
