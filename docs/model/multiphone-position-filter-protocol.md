# Speech-evidence filtering for repeated positions

Verify the existing fixed 100 ms phone-evidence/Silero filter with occurrence-
aware raw reports. No runtime filter, thresholds, schema-1 adapter, schema-2
adapter or model bundle changes. The filter's result envelope remains schema 1;
it accepts source raw reports of either schema and preserves every requested
ID, word/phone position and target order. Whole-recording rejection must set
every rating vector to null; acceptance must preserve the original vectors
exactly. This does not establish speech at each individual target.

## Fixed cases

Reuse all seven completed schema-2 position-audio cases (66 positions, all 23
phones and all four bundles). Reuse the previously verified schema-1 BE crop
as a short-speech regression control. It does not validate short repeated-
position crops.

Run five fresh schema-2 raw inferences on the exact previously retained WAVs:
zero, Gaussian noise, 440 Hz sine, dog `4-182395-A-0.wav`, and helicopter
`4-161579-A-40.wav`. Use the existing unweighted all-age bundle and the fixed
explicit prompt BOB B, canonical phones B AA1 B / B. Request its three B
positions in order (word 1, phone 0), (word 0, phone 0), (word 0, phone 2),
with distinct last-b, first-b and middle-b IDs. This exercises repeated sounds
within/across words and adjacent equal tokens with non-chronological requests.
The prompt is an implementation challenge, not a claim that these sounds were
spoken. CTC must match the prior same-WAV run byte-for-byte because the canonical
prompt is not a recognizer input.

Apply the actual existing short filter to all thirteen cases. It runs the
unchanged 250 ms baseline once and resegments those same saved probabilities
at 100 ms. Retain both results and the phone-evidence decision. Do not tune
thresholds or discard failures. The known dog admission must remain visible;
these are regression cases, not a new independent rejection experiment.

## Verification

Freeze the cases, raw references, audio, prompts, bundles, parent studies,
runtime sources, protocol and current runner/tests before inference. Use fresh
output directories, exclusive phase markers and retained failure records.
Check raw and filtered source hashes, CTC audio/job/posterior chains, canonical
occurrence geometry, saved-head replay, waveform lengths, VAD probabilities,
both segmentations and their exact conjunction with phone evidence. Check all
target identities and vectors, and retain false/null as distinct from missing
or unmeasured fields. Rehash inputs before publishing results.

Focused repeat-position tests run through the existing filter's mocked baseline
boundary, including all-target masking, exact restoration, caller order and
source/parameter failure paths. Actual integration cases provide acoustic
evidence. An offline verifier reconstructs decisions and saved model predictions
without acoustic inference; an independent reviewer checks artifacts and claims.

Raw/intermediate files can contain unfiltered rating vectors. Consumers must
read the final filter report. Acceptance establishes neither prompt match nor
pronunciation correctness. Environmental category labels do not establish
speech ground truth. No corpus labels transfer to synthetic/environmental
inputs or cropped audio. No author-test access, fitting, learner feedback or
Colab allocation occurs.
