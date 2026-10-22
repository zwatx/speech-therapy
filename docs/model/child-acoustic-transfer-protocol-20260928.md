# Fixed school-age acoustic representation comparison

This is a prospective development experiment, not clinical validation. The proposed BASE pair was stopped before model execution because its actual backbones differed. The replacement adult control below was selected from architecture metadata before any new model predictions or ratings outcomes. Original proposals, inspections and reviews remain preserved.

## Question and fixed checkpoints

Does a child-adapted acoustic representation improve prediction of the existing five expert ratings when compared with both an adult representation and the retained pronunciation representation? Compare these exact files from the [C3Imaging release](https://huggingface.co/C3Imaging/childASR_w2v2/tree/d8d776851b222b7609bf387d57a56eaa50aabd97):

| Arm | File | Original bytes | SHA-256 |
| --- | --- | ---: | --- |
| Adult | `M6_wav2vec_big_960h.pt` | 3154734128 | `59d0b41638198c3bd73550b7ad55643f73452096801c184b86ecb2bf1372f89f` |
| Child | `M10_ls_to_myst_55h.pt` | 3785745609 | `29d26d046f754e4cb2baf9a25df0ea7c4467c389afb2d86d9635ebaa4cd00822` |

All 405 parameter names and shapes match: width 1024, 24 blocks, 16 attention heads and FFN width 4096. The child file contradicts the author's BASE table label. Adult weights were stored in float16 and child weights in float32; both will execute in float32, with exact adult upcasting. This does not recover precision lost before publication.

The provider identifies adult LibriLight/LibriSpeech training and child MyST training. Stored child metadata contains MyST/55-hour markers. Exact pretrained parent identity, historical framework version, training schedules and complete training-data contents are unverified. Different training amounts, objectives and stored precision prevent a causal child-domain claim. Corpus provenance and known/unknown speaker, audio and lexical exposure must be recorded separately. Different corpus names are not proof of disjointness.

The model release specifies CC BY 4.0. Preserve provider/study/source/license attribution and identify conversions. Underlying dataset permissions are separate; no new raw MyST acquisition is included. Project use remains strictly noncommercial.

## Faithful, safe implementation before features

1. Verify complete original-file lengths and hashes before reading tensors. Partial metadata is not complete weight validation.
2. Interpret bounded pickle metadata as inert data using the reviewed finite `pickletools` parser. Never unpickle, execute checkpoint globals/classes/reducers or evaluate configuration expressions. M10 uses ZIP storage; M6 uses legacy storage headers and ordered raw blocks. Verify member uniqueness, metadata boundaries, CRC where applicable, endian/type/count/offset/stride/shape and file bounds. Skip optimizer contents. Unexpected views or encoder keys stop conversion.
3. Map every encoder parameter exactly once to the native model; explicitly exclude the two CTC projection parameters. Validate complete target key/shape coverage, positional-convolution weight normalization and the unused mask embedding. Save contiguous float32 safetensors and a complete conversion manifest.
4. Use the explicit standard Fairseq interpretation documented in `work/child-acoustic-native-source-20260928/standard-implementation-contract.json`. Older M6 metadata omits two fields. Official Fairseq v0.10.2 `base_architecture` supplies `extractor_mode=default` and `layer_norm_first=False`; v0.12.2 declares the same defaults. This supports the declared implementation, not an assertion about the exact historical author runtime.
5. Native forward contract: group-normalized convolutional frontend, post-LN transformer, GELU, seven 512-channel convolutions with kernels `[10,3,3,3,3,2,2]` and strides `[5,2,2,2,2,2,2]`, no convolution bias, positional kernel 128/groups 16, normalization epsilon 1e-5. Raw mono 16-kHz float32 input, no waveform normalization or padding/attention mask, eager attention, frozen evaluation mode, no masking/dropout/layerdrop.
6. Independently calculate the Fairseq forward from raw named tensors using functional primitives, covering convolution, feature normalization/projection, position convolution, global encoder normalization and all post-LN attention/FFN blocks. Check native versus reference stage outputs at convolution, projection, position, encoder input, blocks 1/12/24 and final output. The fixed tolerance is maximum absolute difference at most `1e-4 * reference-stage RMS`; zero RMS requires zero difference. Recognizable decoding is not parity evidence. Failure stops this implementation without altering tolerance or choosing another checkpoint.

The exact implementation, inputs, libraries, original/converted weights and parity runtime must be bound and independently reviewed before real forward execution. CPU parity uses float32, two threads and the same inputs for both implementations. Any later CUDA verification must be declared separately; CPU agreement does not establish CUDA agreement.

## Input geometry and bounded calls

Bind the existing grade-free expanded manifest: 1040 recordings, 9891 target positions and their original output indices, global row identities, canonical estimated pooling windows and scalar-cache hash. Preserve every target/window and original clip order. Historical age eligibility is inherited from the audited cohort; this manifest does not independently verify ages.

For each original PCM file verify its hash, mono PCM16/16-kHz geometry and sample count. Analytic convolution geometry is `floor((N-400)/320)+1`; it must equal the existing frame count. Verify actual forward counts too. Pool the final transformer output over the original window, including its original context padding. Canonical windows remain estimated locations, not observed produced phones. No new trimming, resampling, waveform normalization, interpolation or window repair is permitted.

The fixed real parity selection uses the first original clip, then longest, then shortest by `(sampleCount, clipId)`, then distinct clips in SHA-256 rank of `child-acoustic-parity-v1|clipId` until four unique clips exist. Four synthetic signals each contain 16000 samples: zero, an impulse with `x[0]=1` and all other samples zero, 220-Hz sine of amplitude .1, and Gaussian noise of standard deviation .01 using seed 20260928. Exact impulse position and signal formulas must be bound in the execution declaration. Real audio is used without ratings.

The throughput sample consists of 16 clips at indices `floor(k*(1040-1)/15)`, `k=0..15`, after sorting by `(sampleCount, clipId)`. It is chosen before timings. Maximum planned calls are 32 parity forwards (8 inputs × 2 models × 2 implementations), 32 benchmark forwards and 2080 extraction forwards. Any additional replay calls must be specified before their phase begins.

Measure actual GPU throughput and account usage before estimating complete extraction. Initial caps are 2 CU for preflight and 20 CU for extraction, including setup and cleanup; the monthly authorization remains at most 300 existing CU. Stop only this experiment's named runtime if a cap is reached. No global account shutdown or other session modification is included. Persist pooled vectors, identities and verification records; full frame outputs need not be retained after their checks.

## Unchanged fitting and controls

Use the existing 25 child-only speaker-fold × word-group jobs from the expanded study. Preserve original inner-selection order, expanded purged inner-fit/outer-refit membership and selected epoch refit procedure. The 9891 positions support extraction/fitting; they are **not** all primary held-out predictions. Primary evaluation remains the original outer rows remapped to original indices, historically 5654 child positions. Confirm that count and every identity from the frozen jobs. Added outer rows are descriptive only; do not create new outer cells.

Reuse unchanged `lexical_compact/core.py`: fit-row float64 centering/population covariance, PCA16, existing rank/sign rules, no whitening or raw standardization. Project in float64 **then cast to float32**. Concatenate `[PCA16, original 13 CTC scalars]`, then apply fit-only head normalization. Native width is 1024 for both models, so no generic-width adapter or zero padding is needed.

Keep the original seed-7 head/optimizer/batch/early-selection/refit recipe. Two new arms × 25 jobs × inner/refit yields 100 head fits. No layer, pooling, rank, seed, fusion or epoch-zero search is included.

Compare scalar alone; retained `.5 cached scalar + .5 cached expanded phonetic compact`; adult `.5 same scalar + .5 new M6 compact`; child `.5 same scalar + .5 new M10 compact`. Cached controls must have exact matching expanded-job and original outer-row identities. The portable full-fit bundle is not an OOF control. Compute mixture logs with `logaddexp(logScalar, logCompact)-log(2)`, without clipping/floors. A cache-integrity failure stops the phase; do not silently relearn controls.

## Fixed evaluation and advancement

Primary: equal-position pooled five-vote soft-label NLL on original outer rows. Secondary: existing phone-macro NLL, **pooled per-rater Brier**, weighted tie-aware rating-0 AP (`p0`, zero votes) and below-2 AP (`p0+p1`, votes 0+1), with exact existing support, ties and undefined handling. Report both model contrasts, all 23 phone supports and all child/fold/cell summaries. Five expert ratings are not produced-phone truth or binary majority labels.

Use 2000 paired child resamples, seed 20260928, **within the original five speaker-fold strata**, retaining each stratum's original child count. Keep all selected child rows and arms together with draw multiplicity, recompute the same pooled estimands, and report 2.5/97.5 NumPy linear-percentile endpoints. Count undefined replicates explicitly without redrawing or silently dropping them. Also report every leave-one-child-out pooled contrast. These are conditional stability diagnostics on extensively reused adaptive development data; they are not fresh confirmatory population intervals. Ages 8/10 have only two fitting children each, and rare events are clustered.

The child representation becomes a candidate for separately declared fresh validation only if:

- NLL improves by at least .005 nats/position versus **both** adult and retained mixtures.
- Both bootstrap upper endpoints are below zero and every child deletion preserves a favorable sign.
- Versus retained, phone-macro NLL worsens by at most .005, pooled per-rater Brier by at most .002, and each event AP decreases by at most .02 absolute.

These margins are prospective practical judgments, not power-derived guarantees. The AP screens can permit material relative rare-event loss; a passing candidate must disclose that tradeoff and does not satisfy the overall rare-error goal by passing these screens. If over 5% of bootstrap replicates lack a guard endpoint, label its stability analysis unstable/descriptive; keep its point-estimate screen unchanged.

Report all gains and regressions even if the advancement screen fails. A smaller gain is limited development evidence, not a claimed strong pass. Similar adult/child estimates do not establish equivalence or capacity effects; the retained encoder is itself LARGE. Failure closes this exact comparison only, not child adaptation generally. No outcome-driven checkpoint substitution, threshold/metric edits, exclusions or refits are permitted.

The retained bundle stays unchanged during this experiment. A pass supports a research candidate and a fresh validation priority. It neither completes the broader model goal nor permits clinical claims, learner judgments or product promotion.
