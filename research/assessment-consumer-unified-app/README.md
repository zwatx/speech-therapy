# Unified local practice successor

This same-depth successor combines the delivered schema2 word-context backend from `assessment-consumer-word-context-app` with the sound-practice handler and UI. Whole-word checking accepts an honestly declared adult context or child age 6–12. Sound comparison remains an explicit, separately opted-in adult development preview for free practice of canonical bread. The sound wire remains schema1 with `adultConfirmed:true` and `selectedChildAge:null`; its policy, contract, service, frozen worker, and seven false claim limits are unchanged. The word feedback policy remains `consumer-recording-feedback-v2`, with eleven false claim limits. Neither route establishes pronunciation correctness, clinical validity or diagnosis.

The original source packages and delivered services on 8782, 8788, 8789 and 8791 retain their existing bindings. This successor uses a new feature binding and the exact delivered word-context binding; old declarations, request contexts, private request hashes and native fixtures cannot be relabelled. Native migration requires a separate reviewed origin and binding change.

## Closed source boundary

`source-pins.json` is a reviewed, closed schema2 inventory of 15 owned files and 32 Python dependencies. The sole `consumer_app` import root is `assessment-consumer-word-context-app`. All eight word-wrapper Python files are bound, including the dynamically executed `feedback_worker.py`, its new `feedback_contract.py`, and the wrapper-hashed `__main__.py`. Dependency discovery parses source without executing these modules and refuses added or missing word Python files. The imported word snapshot must come from that exact sibling and callable. The frozen external worker receipt, source layout and complete worker source snapshot retain their existing guards.

Full source verification precedes Catalog, runtime or listener creation. Launch through this package's `consumer_sound_app.launcher`; do not import both predecessor and successor copies of either module into one process. Relocation is unsupported. Root freezes the final feature digest after UI review; no placeholder digest is authorization to launch.

## Local configuration

The launcher defaults to port 8793 and refuses all delivered ports listed above. An actual launch requires an explicit fresh `--runtime-root` and the reviewed `--cache-dir`, plus `--feature-source-sha256`, `--worker-artifact-dir`, `--worker-source-sha256` and `--worker-receipt-sha256`. Do not reuse an existing live runtime or its ownership/tombstone files. `--check` verifies the same reviewed source metadata without constructing Catalog, runtime, observer, listener or model weights; runtime/cache arguments are optional for this check.

One word executor owns the shared heavy-job slot, cleanup intent and pause latch. Phone cleanup uncertainty blocks both processing routes. Capture reuse and cancelled/reset ownership remain fail closed; guided-owned and stale takes remain ineligible for sound comparison. Source changes suppress late results.

## Verification evidence and limits

Current bounded successor checks and generated binding vectors are recorded in `work/consumer-feedback-20261007/unified-app/backend`. Its `generated_fixtures.py` creates invented protocol evidence from scratch; synthetic `inferenceCalls=1` fields exercise the validator and never report an actual model call. No historical saved acoustic result is rebound. Tests cover exact dependency/module origins, source refusal, schema2/legacy separation, shared ownership and cleanup, cancellation, and generated context/request/private hash correspondence. Actual commands and observed counts belong in the dated evidence receipt after the final manifest is frozen.

This backend assignment does not launch an owner service, inspect private runtime/audio, execute real models, use sensors, or establish human accuracy. Browser integration, real-source review, optional launch and any later native migration are separately verified by the coordinating task.
