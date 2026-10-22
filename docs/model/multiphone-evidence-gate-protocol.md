# Research input-evidence check

Declared September 27, 2026 before inspecting full-corpus gate outcomes.
The earlier three nonspeech observations motivate this exploratory rule;
they are known examples, not an independent benchmark.

Withhold the research rating when every PCM sample is identical, or when
collapsed greedy decoding of the pinned full 392-token CTC recognizer contains
no non-special phone (IDs above 3). There is no fitted amplitude, confidence,
duration or phone-match cutoff. An alternate recognized phone is not a reason
to reject a recording: it could be the error that a future model should detect.
Malformed inputs remain failures, distinct from semantic abstention.

Acceptance means only that this necessary-evidence check passed. It does not
confirm speech, the requested word, the requested sound or correctness. A
recognizer can emit phones on noise and can miss genuine child speech. Keep
the check research-only and the existing raw adapter immutable.

Evaluate the fixed rule on every 2,495 eligible SpeechOcean author-training
waveform using the existing hash-bound CTC cache. Report retained and withheld
clips, speakers, target positions and lower-rating vote/position counts for
all ages, children ages 6–12, and each supported consonant. These are corpus
retention measurements, not clinical false-rejection estimates. The policy
was motivated by earlier observations in this corpus; do not label this an
untouched confirmatory study. Never use author-test audio.

Recheck all three previously saved generated nonspeech cases and at least
one real raw-adapter report. Verify that abstained reports expose no target
probabilities and retained reports preserve the exact original probabilities.
Record source, policy, corpus, waveform and posterior hashes. No fitting or
model-bundle change occurs. Broader independent environmental negatives and
genuine child-error recordings remain necessary for a speech detector.
