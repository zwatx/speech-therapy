# /R/ capture-sensitivity study

Completed locally on September 26, 2026. **Both saved whole-clip rating heads
changed their probabilities under added noise.** At either tested noise level,
each head changed its highest-probability class on 3 of 40 clips. This is a
capture-sensitivity result; it supplies no pronunciation accuracy estimate,
clinical decision threshold, or reason to select either encoder.

## Question and fixed method

How much do the existing subjective corpus-rating probabilities move when
the same recording is quieter or contains controlled white noise?

The [locked recipe](../../research/audio-head/experiments/speechocean-r-capture-sensitivity-v1.json)
reuses the established [annotation-feasibility selection](r-target-annotation-plan.md):
40 public SpeechOcean762 **author-training** clips, one per speaker, with ten
clips in each corpus child/adult × original rating ceiling/below-ceiling
stratum. The source archive, selected WAVs, metadata, saved heads, and encoder
weights are hash-verified. No reviewer packs or blinding keys are read. No
author-test waveform is decoded or inferred.

The selected ages are 6–37; 17 clips are from ages 6–12. None is from ages 2–5.
The sample's child band is ≤15, and its adult band is ≥19. The balanced sample
and existing public-corpus labels do not establish coverage of Cadence's
intended ages 2–12 or children with speech sound disorders.

Both heads were already fitted on all 766 selected author-training clips,
including these 40. They retain their original frozen encoders, full-clip mean
pooling, standardization, and three-class softmax heads. There is no fitting,
calibration, model selection, new reference label, or accuracy calculation.

The runner reuses the tested `stress.transform` implementation: original audio,
−6 dB gain, and deterministic white noise at 20 dB and 10 dB SNR. The seed is
derived from the original WAV hash and fixed seed 17; both encoders receive
identical transformed samples. SNR uses whole-recording RMS, including silence.
The transform scales the signal and noise together if necessary to avoid
clipping; no selected mixture needed this rescaling. Delivered SNR matched each
target within 0.000001 dB. Duration, pitch, and sample rate are unchanged.

## Observed probability movement

Total variation is half the sum of absolute class-probability changes, on a
0–1 scale. Expected rating is `p(class 1) + 2 × p(class 2)` on the original
subjective 0–2 corpus scale. A positive shift means a higher expected corpus
rating after the capture change. Highest-class changes use the lowest index
to resolve a tie and are **not** learner pass/fail decisions.

| Encoder | Condition | Mean total variation | Mean absolute expected-rating shift | Mean signed shift | Highest-class changes |
| --- | --- | ---: | ---: | ---: | ---: |
| wav2vec2 Base | Original | 0 | 0 | 0 | 0/40 |
| wav2vec2 Base | −6 dB gain | 0.000000236 | 0.000000455 | −0.000000002 | 0/40 |
| wav2vec2 Base | White noise, 20 dB | 0.09329 | 0.17989 | −0.08770 | 3/40 |
| wav2vec2 Base | White noise, 10 dB | 0.11202 | 0.21540 | −0.04772 | 3/40 |
| WavLM Base+ | Original | 0 | 0 | 0 | 0/40 |
| WavLM Base+ | −6 dB gain | 0.00600 | 0.01112 | +0.00092 | 1/40 |
| WavLM Base+ | White noise, 20 dB | 0.08488 | 0.15994 | +0.14764 | 3/40 |
| WavLM Base+ | White noise, 10 dB | 0.10284 | 0.19490 | +0.18509 | 3/40 |

The wav2vec2 checkpoint normalizes each waveform, which helps explain its very
small gain response. That invariance alone establishes no useful sound
judgment. WavLM's expected rating rose under noise on average: at 10 dB the
largest individual upward movement was 1.40075 on the 0–2 scale. Its
adult/below-ceiling stratum had a mean signed change of +0.55656 across ten
clips. The report retains all four strata and every condition; this small
descriptive slice does not establish a subgroup effect or its cause.

Noise can change what is audible, and no SLP has judged these transformed
clips. Probability instability therefore must not be relabeled as an error
rate; nor should stability be treated as correctness. The result supports
keeping capture feedback separate from pronunciation feedback and including
capture conditions in a future evaluation with qualified reference labels.

## Runtime, provenance, and reproduction

The final run completed **320 real inferences in 38.68 seconds**, including
2.98 seconds of source verification, with zero failed clips. On this arm64
Mac, Python 3.13.14 / PyTorch 2.8.0 / NumPy 2.2.6 used CPU inference with Torch
configured for two threads. The recipe's `maxCpuMathThreads` and report's
`threads` fields record that Torch setting; they are not a machine-wide CPU
limit. Encoder construction took 1.73 seconds for wav2vec2 and 0.30 seconds
for WavLM. Across 160 calls per encoder, measured inference median / nearest-rank
p95 was 81.48 / 201.79 ms and 87.48 / 217.12 ms, respectively. These figures
exclude browser/mobile recording and network overhead; they are not iOS or
production latency measurements. Host load and filesystem cache were uncontrolled.

The ignored local artifacts are
[`final-report.json`](../../research/audio-head/outputs/speechocean-r-capture-sensitivity-v1/final-report.json)
and its separate
[`final-replay.json`](../../research/audio-head/outputs/speechocean-r-capture-sensitivity-v1/final-replay.json).
The fresh-process replay completed in 38.01 seconds with zero failures. All
320 probability vectors, transformed-waveform hashes, source bindings, and
subgroup summaries matched exactly; maximum probability difference was zero.
The report contains source-WAV hashes, row order, exact probabilities,
transformed-waveform hashes, all subgroup summaries, timing, encoder identities,
and source-code/dependency hashes. Raw waveforms and new frame features remain
in memory only. The existing private-research artifact and license scope is
unchanged; no audio or model weights are published.

| Artifact | SHA-256 |
| --- | --- |
| Study recipe | `cdffc96949240e965570b84c8f1253df88f04ebbae38a65058e46d252cd60a30` |
| Saved two-head bundle | `376e387a7a57da7ef1fb94fb0e948f2847a571c194cd05be9ce3a933d5ba7485` |
| Ordered selected source IDs | `211ee79baa34d3c13993c9a146775513542f41112633f14dd529da9f13ee45b6` |
| Runner source | `12775ab9db647cb79b3a22ac584cf3050c58308b1c91ec3ec0c1b311c2238fe5` |
| Final report | `f10a4a20c4a428505d65e9ece7d5648604d049b62705035d1babe6ec00086b86` |
| Fresh-process replay | `1c1a9ef7f2b98449e78c4eb6d5e7896ffc52afb19cf3d71983bccbd974dbc897` |

From the repository root, with the existing local environment and pinned
artifacts available:

```sh
research/audio-head/.venv/bin/python -m unittest discover \
  -s research/audio-head -p 'test_speechocean_r_capture_sensitivity.py' -v
PYTHONPATH=research/audio-head research/audio-head/.venv/bin/python \
  -m unittest test_stress.TransformTests -v
research/audio-head/.venv/bin/python \
  research/audio-head/speechocean_r_capture_sensitivity.py \
  --output research/audio-head/outputs/speechocean-r-capture-sensitivity-v1/reproduction.json
```

Choose a new report filename for every run: existing files are never
overwritten. Output paths outside ignored research outputs, changed recipes,
corrupt pinned artifacts, malformed probabilities, changed source files during
inference, and invalid samples fail closed. Model downloads are disabled by
both offline environment settings and `allow_download=False`; paid or remote
compute is unused.

Seven new numerical/boundary tests and four existing waveform-transform tests
passed. The run emitted two existing upstream deprecation warnings about
gradient-checkpointing configuration and attention-mask types; neither aborted
inference. No new qualified annotations or held-out evaluation were performed.
The [SLP handoff](slp-handoff.md) describes the content-review and reference-label
decisions that can make the next model step meaningful.
