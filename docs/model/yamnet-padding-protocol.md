# YAMNet silence-padding sensitivity

Declared September 27, 2026, before derivative inference. The previous fixed
YAMNet rule retained all 1,037 full child utterances but rejected two estimated
short-word crops. A recording-length fallback could restore those exact crops;
it does not establish robustness when silence surrounds a short production.
This diagnostic tests that uncertainty before selecting a new filter.

Use all 1,117 inputs of the frozen YAMNet study, including all 17 word crops and
all 60 environmental recordings. The earlier fresh environmental panel is now
observed development material. No new speakers, recordings or labels are added.
Environmental categories remain unknown speech-presence labels, and whole-word
ratings are not transferred to estimated crops or their derivatives.

Keep the exact upstream model, parameters, Speech class and >=0.5 threshold.
For every original float32 waveform, infer these six fixed zero-padding variants:

| Variant | Leading silence | Trailing silence |
| --- | ---: | ---: |
| lead240 | 0.240 s | 0 |
| tail240 | 0 | 0.240 s |
| lead480 | 0.480 s | 0 |
| tail480 | 0 | 0.480 s |
| both480 | 0.480 s | 0.480 s |
| both960 | 0.960 s | 0.960 s |

These offsets cover half-hop/full-hop shifts and surrounding context using
YAMNet's fixed 480-ms hop. Preserve every original sample exactly; no gain,
trimming, resampling, repeating speech or noise injection. Derivatives are
processing probes, not new independent examples. Reuse the frozen original
scores for the reference; do not refit, optimize offsets, choose a maximum over
variants or change the classifier. Six variants ×1,117 inputs =6,702 new model
calls. CPU only, same isolated environment and two-thread settings.

Save every 521-class score array, original audio binding, derivative float32
hash, source sample span, sample count, padding, window geometry, decision and
runtime. Freeze all outputs before summarizing them. A fresh prediction of the
first original recording before and after the run must exactly reproduce its
saved reference. Errors fail the run; they are not withheld-speech decisions.

Report, for every variant and population, original acceptance, new acceptance,
accepted-to-rejected and rejected-to-accepted changes. For child utterances,
retain complete positions, children, recordings and rater-vote support, all 23
phones and ages 6–12. List every changed utterance and every word-crop result.
Report environmental category admissions separately, without accuracy claims.

Also list crop variants whose total recording length reaches 15,600 samples
while the Speech score remains below 0.5. Those are counterexamples to using
recording length alone as assurance of adequate speech context. This is a
diagnostic condition, not an implemented fallback policy. Baseline Silero/CTC
was not inferred on transformed audio; do not copy its original decisions to
derivatives or claim measured conjunction performance.

Tests must verify exact source preservation, sample offsets, no mutation,
boundary lengths, score validation, population/support accounting and changed
artifact rejection. Independently review sources before inference and verify
saved arrays, reconstruction, summaries and conclusions afterward. The original
failed universal-filter result remains unchanged. No learner policy, model
promotion, author-test access or additional data acquisition occurs.
