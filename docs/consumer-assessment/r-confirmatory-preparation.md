# New blind R confirmation — preparation draft

**DRAFT / NOT DECLARED / NOT EXECUTED.** Prepared 2026-10-02. This is a new protocol proposal, not a revision or rerun of the closed [external check](../model/percept-r-external-check-result-20261001.md) or [binary-head development study](../model/percept-r-binary-head-result-20261002.md). Sources, protocols, runs, checkpoints and the reserved 80 TEST children remain preserved. No TEST/audio/archive/feature access, inference, fitting or outcome inspection is authorized by this document.

## Question and frozen comparison to prepare

Does the preserved full-DEV R specialist improve within-child ranking of binary listener judgments over the unchanged retained `p0+p1` score on the reserved children, while maintaining usable coverage and improving probability prediction versus an appropriate DEV-only calibration control?

The comparison concerns PERCEPT-R corpus listener judgments of consonantal R. It does not establish clinical correctness, treatment benefit, condition diagnosis, all-word transfer or native product readiness. Other 22 consonants and syllabic ER receive no confirmatory evidence from this study. The retained 23-sound model and product policy remain unchanged regardless of this result.

Proposed fixed arms:

1. Preserved full-DEV candidate from `percept-r-binary-head-20261002/v1/final/full-dev-candidate.npz`, ridge 0.01 under the closed development mode rule. Use its fit-only PCA16, 13 scalars and retained-score logit with the existing 1e-6 input clipping. Do not refit it or choose a different outer-fold model.
2. Unchanged retained ages-6–12 scalar/PCA16 mixture; binary ranking score is exactly `p0+p1`. Preserve the source distribution's different semantics.
3. One monotonic retained-score calibration control fitted only on DEV with the already documented calibration family/optimization rule, then fixed before TEST. The five OOF calibration controls in the DEV result are not a single full-DEV deployment control. Its full-DEV coefficients, source and fit receipt still need preparation under a separate declaration; do not invent them or silently reuse a fold fit. The fixed control is the meaningful proper-score comparator.

No threshold is required for the ranking question. If a thresholded research endpoint is retained, its task, costs, threshold selection algorithm, clipping and calibration must be fixed entirely on DEV and hash-bound before TEST. No threshold, clinical cutoff, power or significance claim is final here. Product thresholds require a separate reference-standard and product-domain study.

## Verified model/source bindings and historical receipts

Preparation freshly verified 68 byte bindings on 2026-10-02, including the preserved full-DEV candidate, its hash-bound final metadata/completion, all declared scientific sources, both retained bundle copies and constituents, occurrence extractor contracts/source/dependency files, and cached phonetic encoder constituents. The local receipt is [artifact-bindings.json](../../work/assessment-continuation-20261002/artifact-bindings.json). This is byte verification, not model execution, coefficient replay, original training-lineage verification or a new declaration. No corpus inputs were read. The CTC checkpoint contract is pinned; this receipt does not reverify the CTC cache's weight bytes.

The candidate checkpoint is `research/audio-head/outputs/percept-r-binary-head-20261002/v1/final/full-dev-candidate.npz`, SHA-256 **`7867466527c7f2edbeb2df12416c5b63b97bb66f9f95270f368b1a0d746a815d`**. Its distinct final metadata hash is `9383042b50b790cd02a6108c869b75db50c6ae963589424fa9dc6e42850233ab`; the completion receipt hash remains `c6d05b849527b7e4cb89024876fc20556afebb52c22e7556bdc1e41907849dfa`. These three roles must not be interchanged.

The table retains historical study receipts below. Archive/media/selection/extraction/prediction/outcome receipts in this table were copied from the closed result documents, not reopened or freshly verified during this preparation. The artifact receipt identifies exactly which files were verified.

| Artifact / role | Documented SHA-256 |
| --- | --- |
| Retained bundle manifest, caller-pinned | `bc62f1e4f1727379161d0f3f7d8e6074e645e7578b5c25661fd9da53e4fde1bf` |
| Retained portable ZIP | `9a178efed3f412fef655cfc8a7b97188722828330d91aa0effcd45ddb1cb9258` |
| Acquired PERCEPT-R archive identity, from Oct 1 result | `589535842e92a53a79c2614a0e07e9d357b79a4a421d61e5df7ecaebfd651a62` |
| Media manifest documented in Oct 1 result | `e1b32a81ac9147df9e7191c9a9ed75b14e212f778e1224d477a70df28f242d11` |
| Closed DEV selection | `d25d2acd45692e8f1998298c5ae7b66d9843e3e8be2ce16a51382106822c0421` |
| Closed DEV extraction receipt | `c71b6a675b78f2a23fd01b048905a1f590864912d3c7e570352cc38f961a0ca2` |
| Closed DEV retained predictions, before outcome join | `501eaf418ab8e466043d6bbedc052f488894db263a71f8187848323841eae0a1` |
| Binary-head DEV declaration | `acfc03efc1ed349f206e8e98be9500fb1232c9a9928b5400401956bc57502610` |
| Binary-head locked OOF predictions | `64c0c7b94db969322dea20740435de0abc46453966c6627632ec511b7ce6426a` |
| Binary-head evaluation | `9ec72ff0bb388b22c4566c30588ab7def644fc12f486a58d5bffe08bc4ecf76e` |
| Binary-head final completion receipt (not checkpoint bytes) | `c6d05b849527b7e4cb89024876fc20556afebb52c22e7556bdc1e41907849dfa` |
| Binary-head independent audit | `7542efa15448cc60783f49966775b5427d60d4a44383e020ee7c400752e35b6b` |

Candidate byte identity, retained constituents and current occurrence-extractor source/dependency identity are now verified. New TEST selection/declaration and fixed full-DEV calibration bytes remain unbound. CTC runtime checkpoint bytes and the complete execution environment need verification at the eventual new declaration. No placeholder digest poses as a real binding.

## Reserved cohort, selection and lineage

Reserve all 80 numeric TEST child IDs once only for the new confirmatory comparison. DEV (119 children, 4,534 completed selected words) is consumed development evidence. No tuning, debugging, listening screen or subgroup selection may use TEST outcomes. A new declaration must lock the reserved ID list, metadata-only eligible-row/selection recipe, expected denominator, target definition, cap/order, pre-audio exclusions, decoding/extraction and failure rules before any TEST decoding, feature extraction, prediction or rating access.

Propose reusing the external check's deterministic at-most-40 Part 1 tokens per child and declared supported-phone exclusion recipe, without redefining them from TEST outcomes. This still needs explicit TEST applicability and eligible-row manifest review before freeze. The five DEV AX0 exclusions do not imply five TEST exclusions. Do not copy DEV token counts into TEST expected coverage or substitute rejected tokens. Formal selection does not silently drop a child with zero eligible tokens.

Numeric speaker disjointness is the available split mechanism; it is not proof of unique biological participants or household independence. Cross-corpus participant identity overlap between retained training and PERCEPT-R has not been independently established. The Oct 1 exact-WAV-byte audit found no duplicate group spanning IDs/DEV–TEST, but same-child repeated files existed; exact bytes do not prove perceptual/decoded uniqueness or independent utterances. Preserve session, study, phase, word and numeric ID lineage, report duplication provenance, and do not add a deduplication exclusion after seeing outcomes.

The relationship between retained training features and occurrence-aware extraction remains documented rather than hash verified. New extractor bindings/parity can reduce a forward-run ambiguity; they cannot retroactively prove the closed training lineage. A fixed cached-extraction comparison also does not establish equivalence to prospective native microphone behavior. Model/feature dimensional agreement is insufficient provenance.

## Metrics and uncertainty to freeze

Derhotic votes are positive (`n-k`), rhotic votes negative (`k`); mixed votes within a token remain mixed. Preserve tie half-credit and the established vote-weighted AUROC definition. Do not majority-convert votes into clinical truth. The primary unit is the child, not the token or listener vote.

Proposed primary endpoint is the unweighted mean of paired per-child candidate-minus-unchanged-retained AUROC, alongside each arm's mean/median and all 80 child coverage rows. Ranking improvement must be defined with a prospectively fixed minimum effect and confidence criterion before declaration; the DEV gate 0.02 is not silently imported as the TEST target. Retain negative/tied child gains and the fraction improved/worsened, without subgroup rescue.

The new preparation evaluator uses a paired whole-child bootstrap on the explicitly reported **defined paired-child subset**, lexicographically sorted, with NumPy `default_rng`/PCG64 seed `20261002`, 2,000 draws of that subset's size with replacement, and linear 2.5%/97.5% quantiles. This estimates a conditional mean over defined children; it does not represent missing or undefined children. Empty subsets return a null mean/interval and skip all draws; singleton subsets report a degenerate interval. No resampling rescue occurs. These are implemented preparation settings, still subject to review and the final new declaration, not frozen acceptance criteria. Resampling children conditions on fixed models and does not estimate refitting, study independence or population variation beyond this cohort. Do not treat tokens/votes as independent observations. A qualified statistical reviewer must settle precision/reliability requirements and what the 80-child design can support; no power is asserted here.

Secondary proper scores: child-balanced binomial log loss and expected per-vote Brier for candidate, unchanged retained and fixed calibration control, preserving listener weighting within child. The preparation evaluator clips probabilities to `[1e-6, 1-1e-6]` for these proper scores only; AUROC uses raw probabilities. This differs from the closed DEV study's logarithm-only 1e-12 clipping and is explicitly a new proposal. Report calibration-minus-candidate proper-score gains on the same shared processed/rated tokens, and candidate-minus-retained AUROC gains on its shared tokens; positive gains consistently indicate improvement. Each arm's own-coverage metrics and both comparison intersections are reported separately. A difference between own-coverage arm summaries cannot replace a paired result. Pooled AUROC/AP, Spearman and study/context/phase/age/word breakdowns remain proposed secondary/descriptive additions; the new evaluator does not implement them. Pooled ranking can reflect severity/study/recording/word differences and cannot replace the primary within-child finding.

## All failures and undefined results

Publish complete selected → excluded-by-predeclared-rule → decoded → extracted → predicted → rating-joined → metric-defined counts, per arm and child. Every selected token retains one terminal outcome/reason; no inference retries or substitution unless an exact pre-outcome retry policy was declared. Include empty selection, decoder errors, unsupported phonetic inputs, mapping ambiguity, nonfinite features, artifact mismatch, missing/malformed votes, and model failures. Lock predictions and coverage externally before the sole outcome-rating join.

Within-child AUROC is undefined when positive or negative vote mass is absent. Define paired comparison only for children with both arms and a defined metric; report that subset explicitly plus its excluded child IDs/reasons and the full 80-child denominator. Failed/undefined children cannot be assigned 0.5, silently removed or treated as success. The final declaration must fix the minimum paired-defined coverage, effect/interval criteria, subgroup coverage floor (if any), and failure rule. Until these are resolved this protocol cannot produce a pass/fail claim. Report all undefined bootstrap replicates and intervals that cannot be supported; never resample until a favorable interval appears.

## Generalization and once-only outcome

All age years 6–12 are intended but prior DEV support is sparse at ages 6 and 7 (2 and 8 children). Record age missingness and each age's actual coverage; no independent youngest-age claim follows from an overall result. Study/context groups overlap; do not sum them as independent children. Words/studies were not held out during development. A within-child gain may reflect word difficulty encoded in prompt features/embeddings. Repeated familiar prompts, isolated words, microphones, dialects, nonspeech rejection and product false-correction rates need separate evidence. No favorable study, context, word or age slice rescues an overall failure.

After the once-only run: retain all outcomes, immutable inputs/outputs and independent numerical audit; report bounded passed/failed/inconclusive findings under the frozen rule. A failure closes this candidate's confirmatory claim; it does not authorize checkpoint replacement or another TEST-informed attempt. New research must use new reserved evidence and a new declaration. Passing does not change product eligibility or permit clinical rollout.

## What remains before declaration

- Owner/statistical/reference-standard review through existing study records: exact question, minimal worthwhile effect, coverage/definedness, uncertainty and multiplicity choices; no invented signoff.
- Full-DEV calibration preparation under its own new declaration, isolated from TEST; bind its recipe, coefficients and fit receipt. Candidate/source/retained byte verification is completed, with runtime limitations above.
- Exact metadata-only TEST selection and full denominator manifest; verify predeclared rules without viewing outcomes or decoding.
- Review the new synthetic-tested evaluation implementation and prepare independent audit/prediction-lock/join stages. No permitted DEV fixture evaluation or independent scientific audit has run during this preparation.
- New immutable signed/dated declaration and execution authorization, independent audit responsibilities and local receipts. None exists for this draft.

No clinical/content approval, participant recruitment, release, contact, publication or protocol freeze is claimed.
