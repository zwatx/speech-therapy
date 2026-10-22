# Active GPT-6 Sol / High continuation — September 23

## 07:59 America/Chicago checkpoint — September 23

Goal ACTIVE; ordinary Codex use remains available (weekly use 27%), and both
reset credits remain untouched. No patient media, paid compute, gated corpus
download, learner feedback, real reviewer labels, commit/PR, or deployment.

- Model: The completed HuBERT 200-step seed-7 head received a supplementary
  fresh-process runtime check on the same 24 public adult holdout clips, three
  passes, 72 timed calls. Median/p95 were 62.99/78.22 ms; peak whole-process
  RSS was 1,309.95 MiB. Independent review replayed run identity, timing
  arithmetic, repeated posterior hashes, and the first real inference output.
  This post hoc check extends engineering evidence, not the earlier locked
  two-encoder timing recipe or any model selection. A primary-source corpus
  search found GMU Speech Accent Archive human IPA transcriptions with multiple
  English speakers, but CC BY-NC-SA 4.0 rights and unknown transcript coverage
  prevent a fit for the product-development purpose without review. Tusom2021
  has one adult East Tusom speaker and ambiguous WAV/annotation rights despite
  a repo MIT file; do not weaken speaker-disjoint validation. The candidate
  document records both leads. No new corpus media or annotations were fetched.
- UI: Learner record now shows practice access from the same audio-consent and
  assent predicate as device linking/caseload status, preventing “audio On”
  beside a paused practice state. Recent captures omits the research benchmark
  column when no attempt has one. The 390px preview was visually inspected;
  320/390px browser checks have no overflow. Focused and full JS tests
  (clinician-web 55/55), browser/a11y 11/11, typecheck, lint, production JS
  build, and independent read-only review pass. No card layout added.

## 07:48 America/Chicago checkpoint — September 23

Goal ACTIVE; ordinary Codex use available (weekly use 27% at the last read),
and both reset credits remain untouched. No paid compute, patient media,
gated corpus download, real reviewer labels, learner feedback, commit/PR, or
deployment.

- Model: Added a pinned offline HuBERT Base encoder and ran the locked
  four-speaker CMU Arctic third-encoder comparison: six local fits at 200/800
  steps × head seeds 7/17/29, plus twelve preserved wav2vec2/WavLM anchors.
  All 18 partitions and per-seed initial heads match. Mean test automatic-label
  token error rates were 15.83%/14.86% for HuBERT, versus 12.75%/10.64% for
  WavLM and 59.54%/51.10% for wav2vec2. The adult labels are automatic, the
  holdouts reused, and no encoder winner or clinical claim was selected.
  Independent post-fit audit recomputed all six HuBERT calibration/test metrics
  and exact report contents without blockers. Two fixed public recording
  posterior exports passed 18 TypeScript/PyTorch CTC parity and rejection cases
  with maximum finite difference 4.45×10⁻¹⁶. The full Python suite passed
  219/219; artifacts are ignored and owner-only. The target-localized /r/
  produced-phone fit still requires reviewed labels/intervals or approved
  access to a suitable manually annotated corpus.
- UI: Generic Assignments entry now requires an explicit learner choice;
  eligible learner-specific entry still preselects that learner. Plan-fit
  confirmation resets on learner change, and stale success feedback clears
  when submitted values change. Independent review found no final blocker.
  Full JS tests (clinician-web 54/54), workspace typecheck/lint, optimized JS
  build, and browser/a11y 11/11 pass. No card treatment added.

## 07:26 America/Chicago checkpoint — September 23

Goal ACTIVE; ordinary Codex use remains available (weekly use 26% at the last
read), and both reset credits remain untouched. No paid compute, patient
media, learner feedback, gated corpus download, new head fit, commit/PR, or
deployment.

- Model: Rechecked current sources for a target-localized /r/ label fit.
  Original L2-ARCTIC has manual phone times/error tags but a license-form
  access gate and CC BY-NC 4.0 terms; no authorized archive is local. A public
  processed rehost has a conflicting permissive machine-readable license tag
  and lacks the target intervals/error tags. The corpus candidate document
  now records that trap. A separate author-train-only SpeechOcean phone
  selection audit identified 841 exact-one-`Z` clips with five-rater scores,
  but 516 have mixed judgments, `IS`/`WAS` account for 459 clips, exact-word
  purging leaves 129–159 outer-fit clips, and paired frozen caches cover only
  291. Root independently reproduced the selected-ID hash, rating counts,
  fold sizes, and cache overlap; the document records the no-go for a stronger
  generalizable phone model. No author-test score was decoded for selection.
  Reviewed target intervals or an access-approved manual-error source remain
  necessary for the next target-localized fit.
- UI: Learners directory mobile records now use compact ruled rows with
  labeled last practice, attempt, and active-device facts instead of a
  run-on metadata line. Root inspected 320/390px screenshots without visible
  overflow. Full browser/a11y 10/10, clinician-web tests53/53, typecheck,
  JS production build, and independent read-only review passed. The preview
  returns HTTP200. No card treatment was added.


## 07:18 America/Chicago checkpoint — September 23

Goal ACTIVE; weekly Codex use was 26%, ordinary use allowed, both reset credits
untouched. No paid compute, patient media, learner feedback, real reviewer
labels, gated corpus download, commit/PR, or deployment.

- Model: Prior actual 766-clip speaker-only and speaker+word-purged fits remain
  exploratory: all eight paired speaker-bootstrap intervals cross zero. Two
  independent audits advised against another rating fit on unverified forced
  boundaries. Instead, a locked train-only CMU Arctic /r/ crop preflight
  encoded 276 of 279 automatic intervals (three shorter than the 400-sample
  receptive field) to 829 frozen wav2vec2 frames. A separate 40-clip
  SpeechOcean author-train integration check paired forced canonical word
  spans from three cached WavLM CTC heads with cached wav2vec2 positions and
  explicit off-word row indices; 22/40 clips have at least one internal
  support flag. Both outputs are ignored, owner-only, and hash-pinned; the
  SpeechOcean recipe explicitly sets `trainingEligible:false`, and neither
  preflight feeds learner feedback. Neither preflight measured
  timing truth, fitted a head, or established pronunciation accuracy. Full
  Python suite215/215 and independent focused/research artifact review passed
  without blockers. The next meaningful target-localized fit still needs
  independently reviewed intervals/labels or an approved manual phone-error
  source; do not elevate automatic alignments to truth.
- UI: Learner record Recent captures is now a ruled responsive evidence list
  rather than a 660px horizontal table. It shows the historical assigned
  prompt/target where available, capture quality, and research benchmark
  status. A review caught legacy captures with NULL assignment IDs being
  dropped by an inner join. The final tenant/learner-scoped LEFT JOIN preserves
  current-consent-authorized legacy rows and marks missing prompt/target
  unavailable. A real PGlite regression covers visibility under current
  consent and disappearance after supersession. Desktop/390px captures have
  no overflow. Full JS suite, workspace typecheck, clinician lint, production
  JS build, browser/a11y suite, and independent re-review pass. No new card
  layout was introduced.


## 07:00 America/Chicago checkpoint — September 23

Goal ACTIVE; weekly Codex usage was 25% and ordinary use allowed. Reset credits
untouched. No paid compute, patient media, learner feedback, real reviewer
labels, gated corpus download, commit/PR, or deployment.

- UI: Replaced the live Safety desk's fictional incident queue with a
  consent-authorized recent capture-retry view, limited to the latest 100
  reviewable attempts. The preview labels its single linked learner example
  as fictional. Independent review caught missing route CSS imports; fixed in
  both live and preview routes and confirmed direct-load max-width and no
  mobile overflow. Web typecheck/lint, JS suite, browser/a11y10/10, and build
  pass. Overview is now a compact numbered worklist with a clearer learner,
  review, and action hierarchy; desktop and 390/320px captures show no
  overflow. Its typecheck/lint and browser/a11y10/10 pass, and the final
  production build passes. No card grid was introduced.
- Model: Ran a new locked 766-clip/124-speaker author-train incremental fit:
  word+age+duration+RMS capture control log loss 0.331949 versus 0.313094
  after adding frozen wav2vec2 and 0.310753 after adding WavLM. Full Python
  suite195/195 passed and the private output is owner-only. Independent review
  verified pairing/metrics but identified that this is **speaker-only**,
  target words repeat across folds, and a read-only speaker bootstrap of the
  fixed predictions gives intervals crossing zero. The upstream feature
  recipe is path-pinned but not SHA-pinned in v1; actual cache hashes were
  recorded. Keep v1 immutable and exploratory. A separate locked
  word-and-speaker-purged incremental fit SHA-pins the upstream recipe and
  produced paired log loss 0.360987 for capture, 0.334255 with wav2vec2,
  0.332117 with WavLM. Independent review replayed its splits and metrics
  without blockers; outer fits have only 264–318 clips and 7–20 class-1
  judgments. A new locked 10,000-draw whole-speaker bootstrap covers both
  incremental runs and both log loss and Brier. All eight descriptive 95%
  intervals cross zero, so no reliable incremental gain or encoder winner is
  established. Full Python suite202/202 passes, private outputs 0700/0600.
  Independent bootstrap review replayed all eight intervals and found no
  blockers. These are not clinical or target-localized training results.

## 06:35 America/Chicago addendum — September 23

Continued beyond the 06:26 checkpoint while usage remained available. The
read-only Learner record preview now omits disabled device/data panels and
role-denial copy, shows a truthful review-focused description, and uses one
evidence column. Live role controls and optional nonempty device history are
preserved. Independent review found no blocker. Desktop/mobile captures show
no page overflow; web typecheck/lint, full JS suite, browser/a11y10/10, and
optimized build pass. The Attempt review preview now links each fictional
learner to that read-only record, with a browser navigation test; typecheck,
lint, and browser/a11y10/10 pass after this small follow-up. Research suite
remains193/193; no new model fit or
reviewer labels were created. The two asynchronous user questions about SLP
signoff and noncommercial corpus use have not been answered at this checkpoint.

## 06:26 America/Chicago checkpoint — September 23

Goal ACTIVE; ordinary usage remained available at 06:18 (weekly Codex use
25%, reset credits untouched). User reaffirmed model training as high
priority. No patient media, learner feedback, real reviewer labels, paid
compute, corpus download, commit/PR, or deployment. The audit preview on
port 3211 served Assignments HTTP 200 and was opened in a Codex browser panel.

- Model: Added a read-only, fail-closed single-reviewer export validator for
  the existing 40-clip SpeechOcean /R/ draft pilot. It binds exact six-field
  records to one reviewer and their hashed pack order, reusing complete
  intake interval and response rules. Updated the draft merge to require that
  validator for each input; independent review found a reversed-order bypass
  and confirmed the fix. Added a disabled-by-default, loopback-only reviewer
  page for a *future approved* pilot. It serves one blinded pack, keeps draft
  answers only in browser memory, and exports ordered JSON. An independent
  review found potential rating-key access and mutable WAV playback; the
  final setup requires study-owner launch with an owner-only sample directory
  and separate reviewer OS/browser account, and serves hash-checked in-memory
  WAV snapshots. Re-review found no remaining blocker under that operational
  separation. Full Python suite193/193 and focused annotation tests pass;
  synthetic Chromium completed a 40-record export accepted by the validator.
  No real annotation occurred. L2-ARCTIC rights/label audit found a viable
  *conditional* noncommercial adult-L2 method source with manual phone errors,
  but gated archive terms, intended use, and v5 /R/ counts remain unresolved;
  no download/fit occurred. The 766-clip local training result from the prior
  checkpoint remains the latest actual model fit.
- UI: The compact Assignments form now compares the preview learner's example
  target with the proposed /b/ exercise and requires a clinician plan-fit
  check, resetting it on learner change. The live server action and assignment
  API both require confirmation; independent review found and closed the API
  bypass plus a success-message race after form edits. Desktop/mobile visual
  captures checked, no new card layout. Web typecheck/lint, full JS suite,
  a11y browser10/10, and optimized build pass. User was asked asynchronously
  whether SLP/study-owner signoff is available and whether intended research
  use is commercial; neither answer is required for the safe work above.

## 06:07 America/Chicago checkpoint — September 23

Goal ACTIVE; ordinary usage was available at last check. The user continues to
prioritize model training. No reset credit, paid compute, patient media,
learner feedback, commit/PR, or deployment. Audit-mode preview on port 3211
returns HTTP 200 after the final build; browser captures are possible via
Playwright even though the Codex IAB panel has remained unreliable.

- Model: Added and ran a locked, author-train-only speaker-and-target-word
  purge stress test on the existing SpeechOcean /R/ five-rater task. It kept
  766 existing speaker-held-out evaluations, removed each holdout's target
  words from its outer fit, and repeated the purge for inner selection. The
  real CPU fit produced per-rater log loss/Brier WavLM .345606/.182765,
  wav2vec2 .350184/.185241, fit-only prior .373878/.191899. Outer fits had
  264–318 clips and only 7–20 class-1 judgments, so this is a small,
  imbalanced shortcut stress test, not an encoder winner or proof of /R/
  localization. Six unselected inner fits reached the iteration cap; no
  selected outer fit did. Outputs are ignored/private 0700/0600. Independent
  reviewer replayed split disjointness, predictions, baselines, metrics,
  hashes, and permissions with no blockers. Full Python suite181/181 passes.
  A shared cache index still contains author-test rows, but they are never
  selected, fit, or scored; the runner docstring now says that precisely.
- UI: Replaced Overview's redundant selected-detail pane with a full-width
  compact practice worklist exposing target, last practice, attempts, review
  availability, and one contextual action per row. Search/filter remain.
  Aligned fictional preview targets with the only example reviewed /b/
  captures, used stable dates from linked records, and placed older hidden
  capture examples before the current consent snapshot. Independent review
  found the initial fixture inconsistencies and confirmed the fixes; no
  remaining blocker. Desktop/mobile screenshots checked; no overflow from
  320–1440px. Final typecheck, lint, JS tests, browser/a11y10/10, and
  optimized build pass. The preview responds HTTP200.

## 05:48 America/Chicago checkpoint — September 23

Goal ACTIVE; ordinary usage remains available and both reset credits are
untouched. The user reiterated model training as high priority. No paid
compute, patient media, learner feedback, commit/PR, or deployment. Audit-mode
preview session 75174 still served Overview HTTP 200 at the last check; the
IAB panel remains unreliable after its loading-skeleton issue, while
independent browser tests rendered and passed.

- Model: Real local extraction produced private, hash-verified full-clip frame
  arrays for both pinned encoders on the 40 author-train annotation-pilot
  clips; 9,511 frames each, verified reuse, `trainingEligible:false`.
  Independent review found no blocker. A second independent research check
  found the only existing SpeechOcean `pronounced-phone` notes at /R/ are
  sparse and not a new binary target: 49 of 766 one-R author-training clips,
  5 child clips, with note presence exactly equivalent to existing aggregate
  /R/ score <0.5. Added a reproducible read-only, aggregate-only audit and
  synthetic tests; real pinned run reproduced 49/49/717 counts, Python suite
  175/175 passes, and independent code/science review found no blockers.
  Training a target-localized /R/ head still needs approved independent
  reviewer labels or access-reviewed manual phone-error data. Do not turn the
  sparse notes, rating threshold, or automatic alignment into ground truth.
- UI: Safety desk remains reduced to its actionable queue; earlier web
  typecheck, lint, browser/a11y 10/10, and optimized build pass. This turn
  prioritized model evidence as requested.

## 05:35 America/Chicago checkpoint — September 23

Goal ACTIVE. The user reiterated that model training is a high priority. No
reset credit, paid compute, patient media, learner feedback, commit/PR, or
deployment. The audit-mode preview server is live in session 75174 at port
3211 and Overview returns HTTP 200. The IAB panel remains an unreliable
visual surface after its earlier loading skeleton; browser/a11y tests rendered
the pages independently.

- Model: Independent read-only cache review found no blockers. Ran real local
  extraction of the locked 40 author-training pilot clips through both pinned
  frozen encoders, producing 9,511 contextual frames per encoder. The second
  run verified source/provenance and cached-array hashes and reused both
  owner-only arrays. This is a preparation artifact, not a new fit or target
  localization; `trainingEligible` remains false. The private index contains
  WAV hashes that can reidentify public clips and must not go to blinded
  reviewers. Full Python suite 172/172 passes. A further read-only review is
  assessing the smallest valid next fit against the missing qualified labels.
- UI: Removed static governance text from live and preview Safety desks and
  narrowed the operational concern ledger while preserving the release rule
  in governance docs. Web typecheck, lint, browser/a11y 10/10, and optimized
  build pass. The work stays secondary to model evidence this turn.

## 05:24 America/Chicago checkpoint — September 23

Goal ACTIVE; ordinary usage remains available. No reset credit, paid compute,
patient media, learner feedback, commit/PR, or deployment. The audit-mode
preview server is live in session 23762 at port 3211; Assignments returns
HTTP 200. IAB tab7 is marked for handoff, but after the latest server restart
its browser automation surface remained on a loading skeleton and screenshot
capture failed. A fresh panel-open attempt also timed out. The earlier
post-edit screenshot and independent Playwright browser suite did render the
Assignments form correctly, so this is a current app-panel limitation rather
than an untested page claim. Do not claim the visible tab is healthy until it
is checked again.

- Model: Added a truly bounded `crop_audio_interval` path alongside contextual
  frame-position pooling. It validates finite mono 16 kHz waveform, reviewed
  interval bounds, and minimum encoder convolution length; floor/ceil sample
  boundaries retain the interval with at most one edge sample beyond it and
  return inspectable bounds. Arbitrary 0.1–0.3 s crop from one hash-verified
  public author-training WAV produced 3,200 samples and 9×768 encoder frames
  with each cached wav2vec2 and WavLM model. This is a smoke check, not an
  /R/ example or fit. Independent read-only review found no blockers and its
  fractional-boundary caveat is now documented and tested. Full Python
  suite169/169 passes. No real reviewer intervals exist yet.
- UI: Removed the duplicate “Before practice” aside from demo Assignments,
  consolidated the one consequential consent/device-reset warning near the
  dose/action, and collapsed the view to a single compact form column. The
  refreshed IAB screenshot before server restart showed the new structure;
  read-only reviewer found no blockers. Web typecheck, lint, a11y10/10,
  optimized build and full JS test suite (including clinician53/53) pass.

## 05:14 America/Chicago checkpoint — September 23

Goal ACTIVE; usage still available. The 05:00 reset checkpoint has passed and
the usage tool did not show a reset at 05:06. No reset credits, paid compute,
patient media, learner feedback, commit/PR, or deployment. Local preview now
runs with the required `CADENCE_ACCESSIBILITY_AUDIT_MODE=1` in session 62692;
IAB tab7 is visible at Overview and marked for handoff.

- Model: Read-only artifact audit established that pinned SpeechOcean762 has no
  author phone timestamps; full-clip pooled caches cannot be cropped, and the
  20-speaker forced alignment pilot's 9/20 internal flags are not timing truth.
  Added `research/audio-head/target_pool.py`, a small research-only primitive
  for pooling pinned encoder positions by a future supplied interval. It checks
  convolution geometry, frame count, finite floating values, duration, and
  interval coverage; a returned range makes selection inspectable. Unit tests
  pass and a smoke check on one verified public reviewer-pack WAV succeeded for
  both cached wav2vec2 and WavLM (342×768 frames, selected positions 5–14 for
  an arbitrary 0.1–0.3 s interval). This is no new fit or /R/ time claim:
  transformer positions remain whole-utterance contextual states. Independent
  reviewer found and verified fixes for that contract caveat and integer dtype
  failure. Python full suite 167/167 passes.
- UI: Overview learner selection uses `aria-current` on a plain button rather
  than `aria-pressed` toggle semantics, while preserving the compact selected
  row treatment. Typecheck, lint, browser/a11y 10/10, optimized build pass;
  refreshed mobile Overview AX and visual output were checked. The first a11y
  run failed only because the preview server held Next's dev lock; after
  stopping it the same suite passed, then the preview was restarted with its
  required audit-mode env flag and returned HTTP 200.

## 05:06 America/Chicago checkpoint — September 23

Goal remains ACTIVE and ordinary usage is still allowed (23% weekly used;
the anticipated 05:00 reset was not reflected). Both reset credits remain
untouched. The local preview is running in session 48201 with fresh visible
IAB tab7 at Overview. No paid compute, patient media, learner feedback,
commit/PR, or deployment occurred in this continuation.

- UI: Removed the redundant rail caption and a global development-only/no-
  patient-data footer that inaccurately appeared on signed-in routes. The
  preview retains its own fictional-data disclosure. Typecheck, JS lint,
  browser/a11y 10/10, and optimized build pass; refreshed Overview was visually
  checked.
- Model: Added a primary-source [produced-phone corpus assessment](../docs/model/produced-phone-corpus-candidates.md).
  L2-ARCTIC v5 offers manual phone times and canonical/perceived error tags in
  `/annotation` for a conditional noncommercial method benchmark, unlike its
  automatic `/textgrid` alignments. The actual /R/ coverage is unknown; access
  requires a form and license acceptance. No source was downloaded and no new
  fit was made. Current decision and roadmap now link the conditional audit.
  Independent read-only review found no blockers; its minor prompted-vs-
  spontaneous count clarification was applied. The signed SLP pilot and
  child SSD reference-label gaps remain open.

## 05:00 America/Chicago checkpoint — September 23

Goal remains ACTIVE. At 05:00, ordinary Codex usage was still allowed and
weekly usage showed 23% used; the anticipated 05:00 reset was not reflected in
the usage tool. Both reset credits remain untouched. This turn stops at the
user's requested time checkpoint with the local preview running in session
34670 and IAB tab6 visible at Overview. No paid compute, patient recordings,
clinical feedback, commit/PR, or deployment occurred.

Final checks after the last code changes: Python 165/165; web typecheck,
lint, clinician unit53/53, browser/a11y10/10, and optimized build passed.
Independent reviews found no remaining blockers. The repository is still
initially untracked, so no Git commit was made. Native simulator validation
remains blocked by the unaccepted Xcode license; authenticated provider-backed
browser flows still require Clerk/Postgres provisioning. The next model gate is
qualified SLP/study-owner approval of the drafted 40-clip pilot, then real
independent labels and a separate untouched cohort; do not enable feedback.

## Current checkpoint — September 23, ~04:51 America/Chicago

Goal ACTIVE; the user's 05:00 Chicago checkpoint is ~9 minutes away. Ordinary
usage available (23% weekly used at ~04:43), two reset credits untouched. No
paid compute, patient recordings, clinical feedback, commit/PR, or deployment.
Dev preview remains live in session 34670 with IAB tab6 visible at Overview
and marked for handoff.

- Model/labels: Read-only pilot gap audit identified unresolved clinical
  decisions about altered-segment interval meaning, minimum paired timing
  coverage, shared playback rules, and conditional adjudication. Root added
  these to the signoff/protocol/plan without choosing thresholds or collecting
  labels. Sample/pack generators now create private 0700 directories and
  0600 JSON/WAV artifacts, use private atomic temporary writes, reject symlink
  output ancestors, and detach hard-linked pack WAVs before chmod. Real pinned
  40×2 packs reran with unchanged hashes and owner-only modes. Independent
  privacy review found and then confirmed fixes for hard-link and ancestor
  symlink cases; final no blockers. Root full Python suite165/165 after fixes.
- UI: Final compact neutral Overview remains open; latest typecheck/lint,
  clinician unit53/53, a11y10/10, and optimized build pass. No further UI
  changes since the Review-column simplification recorded below.

## Current checkpoint — September 23, ~04:39 America/Chicago

Goal ACTIVE; ~21 minutes remain to the 05:00 Chicago checkpoint. Local
open-weight work stays high priority. No reset credit, paid compute, patient
recording, clinical feedback, commit/PR, or deployment. Dev preview has been
restored after checks in session 34670; fresh IAB tab6 is visible at Overview
and marked for handoff.

- Model: Research-only offline final-head replay CLI now accepts only exact
  SHA-verified public author-train WAVs. It checks locked final report,
  provenance, NPZ, current trainer/final-fit code, cached feature index,
  encoder files, and preprocessing; no network or author-test inference.
  Both real open-weight encoders replayed one train clip within 1e-6 of saved
  feature-row probabilities; this is smoke/integrity verification, not
  held-out performance. Root full Python164/164 and focused4/4 pass; an
  independent read-only reviewer found no blockers. Current model decision
  and README now link this boundary.
- UI: Attempt Review omits the repeated Research benchmark column when every
  row is unscored, with a single explicit note instead. Browser showed
  three-column desktop and no 320px overflow. Typecheck, lint, clinician
  unit53/53, Playwright/a11y10/10, and optimized JS build pass after final
  web edits. Native iOS source-only checks remain as recorded below.

## Current checkpoint — September 23, ~04:35 America/Chicago

Goal ACTIVE and model work prioritized. Current preview is still live in
session 69949/IAB tab5, overview marked for handoff. No reset credits, paid
compute, patient media, clinical feedback, commit/PR, or deployment.

- Model: A locked age-slice of fixed capture-control and acoustic OOF results
  adds child349/57 and adult417/67 cohort metrics plus 2,000 whole-speaker
  within-band draws. All four capture-minus-acoustic log-loss percentile
  intervals cross zero. Independent read-only reviewer reproduced every
  source hash, cohort join, age metric, draw hash and interval to1e-12; no
  blockers. Root linked the finding from the model decision note. Separate
  research-only offline final-head replay CLI is being finished; it accepts
  only exact pinned public author-training WAVs, not patient or author-test
  audio. No new clinical claim.
- UI: Removed decorative northeast arrows from internal links in Overview,
  preview Privacy and live Privacy. Browser reconfirmed Overview labels and
  screenshot. Typecheck, lint and full JS unit suite pass after these edits.

## Current checkpoint — September 23, ~04:30 America/Chicago

Goal ACTIVE; model work remains the priority until the user's 05:00 Chicago
checkpoint. Ordinary usage available, reset credits untouched. No paid compute,
patient recordings, clinical feedback, commit/PR, or deployment. Dev preview
still runs in session 69949 with fresh IAB tab5 at the desktop overview.

- Model: The provisional two-reviewer merge now exists alongside locked intake
  and agreement commands. It accepts only complete separate 40-record exports,
  verifies the pinned public WAVs and schema before writing, and creates a new
  private combined output without replacing a file. Root reran all 158 Python
  tests; independent read-only review found no blockers, and malformed JSON
  CLI produced no output file or leaked input. No real labels were processed.
  Added a draft SLP/study-owner signoff worksheet for categories, timing,
  agreement thresholds, permitted use, and controlled signatures; no signoff
  is implied. A bounded independent agent is examining age-stratified capture
  control metrics on the existing train-only OOF predictions.
- UI: Compact neutral web and native iOS pass stays intact. Latest web
  typecheck, lint, unit53/53, browser/a11y10/10, build, Swift strict lint and
  parse passed. Independent web/iOS reviewers found no blockers. Simulator
  verification remains blocked by the unaccepted Xcode license.

## Current checkpoint — September 23, ~04:23 America/Chicago

Goal ACTIVE; 5am Chicago remains ~37 minutes away. Model training and label
readiness have priority. No reset credits spent, paid compute, patient media,
clinical feedback, commit/PR or deployment. Dev preview remains live in
session 69949, with fresh IAB tab5 at overview and marked for handoff.

- Model: Independent reviewer exactly replayed the new 766-clip/124-speaker
  word+age+duration/RMS control, all WAV hashes, 10 fold-head predictions and
  pooled metrics; no blockers. New locked 2,000-draw whole-speaker bootstrap
  compares that fixed control with saved wav2vec2 and WavLM OOF predictions.
  Capture minus wav2vec2 log-loss point +.013909, 95% percentile
  [−.010597,+.037816]; capture minus WavLM +.010198
  [−.018496,+.038877]. Both intervals cross zero. Independent reviewer
  separately replayed all draws and hashes exactly, no blockers. Root full
  Python suite153/153. Added a concise current /R/ decision note and linked
  it from README: no encoder winner or clinical target cue, prioritize signed
  two-SLP 40-clip feasibility pilot. Existing public-audio final heads remain
  research-only and disconnected from feedback.
- UI: Root visually checked 320px mobile Overview selection/focus and reset
  viewport. Web preview tab5 remains at desktop overview. Latest web
  a11y10/10 and optimized build pass after the final Review/Assignment CSS.
  Native neutral pass independently reviewed and strict lint/parse pass;
  simulator blocked by Xcode license as recorded below.

## Current checkpoint — September 23, ~04:20 America/Chicago

Goal ACTIVE and ordinary usage available. Model training remains priority;
5am Chicago checkpoint is still ahead. No reset credits, paid compute, patient
recordings, clinical feedback, commit/PR, or deployment. The repository remains
initially untracked. Dev preview restarted after the final web build in session
69949; fresh IAB tab5 is at overview and marked for handoff.

- Model: New locked train-only capture confound probe used the exact 766
  SpeechOcean author-training clips/124 speakers and five nested speaker-fold
  fits. All 766 WAV bytes matched the pinned archive. Paired word+age softmax
  log loss/Brier was .369881/.193606; adding only full-clip duration and RMS
  improved to .331949/.174185, versus saved acoustic wav2vec2
  .318040/.170639 and WavLM .321751/.171995. Every outer fold improved over
  its paired word+age softmax; acoustic advantage varies by fold. Root reran
  full Python suite151/151. Independent reviewer CURRENTLY checking source,
  folds, leakage, metrics and research-only claims. This cannot identify a
  target /R/ cue; SLP reference times and production labels remain the gate.
- UI: Root tightened Attempt Review rows and Assignment spacing; at1280×720
  assignment learner, exercise, dose and preview action now fit without scroll.
  CUA clicked the action and saw the unsaved local summary. Full web
  typecheck/lint/unit suite and10 browser/a11y checks pass; optimized build
  rerun after latest CSS changes. Native Practice/Enrollment moved to semantic
  neutral system surfaces, sans type and blue actions; strict Swift lint/parse
  pass. Independent iOS reviewer found no blocking source/interaction issue.
  Simulator and rendered contrast checks still blocked by unaccepted Xcode
  license; no license action taken.

## Current checkpoint — September 23, ~04:10 America/Chicago

Goal ACTIVE; GPT-6 Sol/High and model work prioritized. Ordinary usage still
allowed at 04:04 (22% weekly used); two reset credits untouched. No paid
compute, patient recordings, clinical feedback, commit/PR, or deployment.
Entire repository was initially untracked, so preserve it. Dev preview was
restarted after final web checks in session 44438; fresh IAB tab4 is on preview
overview and marked for handoff. Earlier tabs were left alone after controlled
server restarts.

- UI: Learners directory/detail now match the compact neutral line-based
  workspace; all five demo learners fit in the first 1280×720 view. Root also
  compacted Safety/Privacy body typography and spacing. Independent read-only
  review found no blocking behavior/accessibility issues in Learners,
  Safety, or Privacy at 1280/320, including no horizontal overflow or axe
  violations; consent history keyboard expansion and preview-only disabled
  export/delete/device controls stayed intact. Full JS suite, typecheck,
  lint, 10 Playwright/a11y tests, and optimized build pass after these edits.
- Model: Paired speaker-bootstrap reviewer exactly reproduced both acoustic
  versus word+age intervals and found no blockers. The read-only next-step
  assessment advised deferring a third Conformer/CMU run because automatic
  adult alignments cannot resolve /R/ target times, produced-phone truth, or
  child SSD generalization. A new bounded **train-only** word+age+duration/RMS
  confound probe is CURRENTLY being implemented and locally fit on the same
  766 public author-train clips/five speaker folds; it must stay research-only
  and be independently reviewed before interpretation. The 40-clip two-SLP
  annotation feasibility pilot still needs qualified task/criteria signoff;
  no real reference labels have been collected.

## Current checkpoint — September 23, ~04:00 America/Chicago

Goal ACTIVE; GPT-6 Sol/High; model work prioritized and the user's 5am Chicago
checkpoint is about one hour ahead. Ordinary usage allowed,22% weekly used at
04:00, two reset credits untouched. No paid compute, patient recordings,
clinical feedback, commit/PR or deployment. Entire repo initially untracked;
preserve it. Dev preview running on127.0.0.1:3211 in session6481; fresh IAB
tab3 is at overview and marked for handoff. Older tabs became browser error
pages during controlled server restarts and were left alone.

- Model: New locked non-acoustic canonical-word+corpus-age baseline trained
  with exact same five outer speaker folds and inner-only smoothing selection.
  OOF log loss .348362/Brier .185346 vs saved wav2vec2 .318040/.170639 and
  WavLM .321751/.171995. Independent reviewer replayed all766 probabilities,
  all135 inner trials, hashes and metrics exactly; no blockers. Root fixed the
  documentation to state the runner is one-shot when ignored output exists.
  New locked fixed-OOF 2,000-speaker paired bootstrap compares acoustic heads
  to this control: wav2vec2 delta−.03032 [−.05504,−.00459], WavLM delta−.02661
  [−.05501,+.00267]. Independent reviewer subsequently cleared. No clinical
  result or produced-phone/timing truth. Full Python149/149 and py_compile
  pass. Previous annotation agreement and age bootstrap independently cleared.
- UI: Compact neutral density pass across Overview, Assignments and shared
  Review/Safety/Privacy headers plus root-access page alignment. Desktop
  Overview fits all5 learners in first1280×720 view and assignment first
  viewport shows learner/exercise/dose. Root CUA checked pages and filter;
  agent checked320px no overflow. Independent UI reviewer cleared live/preview
  boundaries, keyboard/focus and responsive CSS; caught stale Playwright h1
  assertion, which root fixed. Full JS test suite, lint, typecheck,10 browser
  accessibility tests and optimized build all pass after final UI edits.
  Native build/provider-backed signed-in UI still unverified as before.

## Current checkpoint — September 23, ~03:45 America/Chicago

Goal ACTIVE; GPT-6 Sol/High; model training remains the priority and the
user's 5am Chicago checkpoint is ahead. Ordinary usage allowed at03:43; 21%
weekly used, two reset credits untouched. No paid compute, patient audio,
clinical feedback, commit/PR or deployment. Entire repository was initially
untracked, so preserve every existing file. Dev preview is still running on
127.0.0.1:3211 in session98609; IAB tab2 is usable (currently inspecting
Assignments), and should return to overview with viewport reset/markHandoff.

- Model: The locked20-seed rating permutations and fixed-alpha age transfer
  have independent exact replays and no blockers. New speaker-within-age-band
  fixed-OOF bootstrap used 2,000 paired draws per band. Child WavLM minus
  train prior log-loss point +.0035, 95% percentile [−.0305,+.0433], while
  child wav2vec2 −.0377 [−.0512,−.0242]. Adult wav2vec2 −.0670
  [−.1151,−.0264], WavLM −.0947 [−.1499,−.0477]. Independent reviewer
  recomputed every interval, checked all IDs train-only, no blockers; root
  tightened purpose/metric recipe pins afterward. New draft aggregate
  two-reviewer agreement CLI first runs locked intake and reports only
  confusion/exact agreement/paired interval summaries. Independent reviewer
  cleared and negative CLI check produced generic failure/no stdout. No real
  SLP labels. Full Python144/144 and py_compile pass. Agent
  `prompt_age_baseline` CURRENTLY fitting a train-only non-acoustic
  word+age comparator to probe whether acoustic gain survives that confound.
- UI: All web/iOS Notebook work and prior checks from03:30 remain. Agent
  `ui_density_pass` CURRENTLY tightening Overview/Assignments first-viewport
  density, respecting the compact neutral low-card preference. Root rendered
  current overview/assignment at desktop; only ~3.5 of5 learners fit first
  viewport due large heading and target display. Native build remains blocked
  by unaccepted Xcode license; direct strict Swift lint and parse passed.

## Current checkpoint — September 23, ~03:30 America/Chicago

Goal ACTIVE; GPT-6 Sol/High, model training prioritized, 5am Chicago still
ahead. Usage21% weekly used and ordinary work allowed at03:25; no reset credits
spent, paid compute, patient recordings, clinical feedback, commit/PR/deploy.
Entire repository initially untracked. Dev preview restarted as session98609
on127.0.0.1:3211 after final web checks; fresh IAB tab2 is at preview overview,
viewport reset and markHandoff called. Old user IAB tab1 became a browser error
page during restart and was left untouched.

- Model: Train-only /R/ final fit from earlier checkpoint remains pinned and
  reviewed. New negative-control fit permuted intact five-score rating blocks
  within outer-fold/equal-size-speaker groups; 690 source IDs and233 actual
  rating vectors changed. Wav2vec log loss rose .318040→.418762, WavLM
  .321751→.438817 while fold prior stayed .371679. One fixed permutation is
  not a null distribution/significance claim and can break prompt cues. New
  age diagnostic on fixed OOF shows child-band WavLM .2556 vs fold prior .2521,
  adult .3771 vs .4717; wav2vec below prior both bands. Child n349/57 speakers
  with only one unanimously0 clip, so no child error-detection/clinical claim.
  Independent model reviewer replayed all766 control OOF metrics/permutation
  and age bands, no blockers. Full Python131/131 and py_compile pass. Agent
  `permutation_sensitivity` CURRENTLY running a separate predeclared20-seed
  train-only sensitivity, not product integration.
- UI: Warm Notebook now includes Learners directory/detail, Attempt Review,
  Safety, Privacy, and access boundary on top of Overview/Assignments. Learners
  independent reviewer cleared privacy/consent/device/export/delete branches.
  Independent Review/Safety/Privacy reviewer cleared live-vs-preview gates;
  root fixed shared mobile header landmark and root visually inspected
  desktop/mobile review, Safety/Privacy, access. After access style, web
  typecheck/lint,10 browser/a11y and optimized build all pass; prior integrated
  53 unit tests pass. iOS agent `ios_practice_notebook` CURRENTLY refining
  PracticeView; native build still blocked by unaccepted Xcode license.

## Current checkpoint — September 23, ~03:15 America/Chicago

Goal ACTIVE; GPT-6 Sol/High, model training prioritized, 5am Chicago checkpoint
ahead. Usage allowed; no reset credits, paid compute, patient audio, clinical
feedback, commit/PR or deployment. Entire repo initially untracked. Dev server
`127.0.0.1:3211` was stopped only to run Playwright/build then restarted as
session 51036; current IAB tab1 returned to
`/accessibility-preview/overview`, viewport reset and markHandoff called.

- Final-fit /R/ heads independently refitted byte-identical, source/feature and
  train-only alpha selection pinned; full Python126/126 pass. Draft annotation
  intake independently reviewed all80 WAVs and synthetic complete export;
  no real SLP labels, test inference or clinical enablement. README/roadmap now
  link final fit, intake, PERCEPT preflight and cautious Cummings metadata-only
  lead. Independent corpus scan found no immediately permissioned child /r/
  produced-phone plus verified-time dataset; no clinical corpus acquired.
- Warm low-card Notebook is live shared overview and now also Assignments page,
  including shared live/preview exercise and three ruled form steps. Root CUA
  visually checked selected Jordan and learner-scoped links, mobile Back focus,
  assignments 638; agent screenshot audit320/638/900/1280. Independent
  reviewer cleared overview and assignment live/preview code semantics, no
  blockers. Root added heading `tabIndex=-1` so mobile Back link focuses Learners,
  verified by CUA. Root reran web typecheck/lint/53 unit tests, 10 Playwright
  browser/a11y tests, optimized build after final UI; all pass. First a11y
  attempt failed only because Next refused concurrent dev servers; stopped3211,
  reran successfully, rebuilt, restarted3211. Live authenticated tenant UI
  remains untested without provider credentials.
- iOS learner PracticeView now moves passive camera-off status below Record
  controls and trims prompt bottom padding to24; agent and root reran direct
  Xcode-toolchain swift-format strict and swiftc parse successfully. Native
  build/simulator still unavailable due unaccepted Xcode license. No license
  acceptance performed.

## Current checkpoint — September 23, ~03:05 America/Chicago

Goal ACTIVE, GPT-6 Sol/High; model work prioritized and 5am Chicago checkpoint
still ahead. Usage allowed, no resets consumed. No paid compute, patient audio,
clinical feedback, commit/PR or deployment. Entire repo was initially
untracked; preserve. Current IAB tab is on `/accessibility-preview/assignments`
with viewport override reset; return to `/accessibility-preview/overview` and
mark handoff before turn ends. Dev server3211 live. Native Xcode/provider-backed
signed-in verification blockers unchanged.

- Model final-fit: locked `speechocean_r_rater_final_fit.py`/recipe/test fitted
  three-class wav2vec/WavLM heads on all766 author-train clips/124 speakers,
  3830 ratings, fixed alpha0.1 selected in all five nested folds. Saved ignored
  `outputs/speechocean-r-rater-final-fit-v1/{heads.npz,provenance.json,report.json}`.
  Optimizer77/75 iterations below400 cap, probability simplexes valid. Root
  full Python suite126/126. Independent reviewer refitted both heads and
  reproduced exact NPZ SHA, source/feature/recipe chain and diagnostics, no
  blockers. No author-test inference/metrics, calibration, release or feedback.
- Model source scan: official PERCEPT-R word-rating source remains gated by
  PhonBank registration/noncommercial terms and lacks produced-phone truth.
  Cummings ~30 child SSD word-probe corpus is metadata-only audit candidate:
  a linked study transcribed four children, but no proof every deposited
  record has actual IPA or verified timing; default TalkBank CC BY-NC-SA.
  Pasketti actual-production labels explicitly competition-only, no-go.
  No newly found immediately usable child /r/ produced-phone timing source.
  Root documented cautious Cummings lead in roadmap, no clinical media acquired.
- UI: Notebook is now live `OverviewWorkspace`; prototype picker removed.
  Browser root visually inspected desktop and mobile, selected Jordan and
  observed learner-scoped assignment/review links, mobile inspector focus.
  Independent reviewer cleared live/preview semantics, responsive widths,
  axe, search/filter/empty, and removed compare route, no blockers. Agent
  typecheck/lint,53 JS,10 browser/a11y,build pass; root independently reran
  typecheck/lint/53 JS pass. `review_ui_sol` CURRENTLY carrying same visual
  language into Assignments page without changing form/consent behavior.

## Current checkpoint — September 23, ~03:00 America/Chicago

Goal remains ACTIVE with model training prioritized; 5am Chicago checkpoint
has not arrived, usage allowed. No reset credit, paid compute, patient audio,
clinical feedback, commit, PR, or deployment. Repo remains initially entirely
untracked; preserve all files. Current task and agents use GPT-6 Sol/High.

- Model: Draft local-only /R/ reviewer-intake validator/schema/tests and README
  now pin the 40-clip author-train sample, two local packs, all 80 WAV hashes and
  durations, and require 80 distinct structured reviewer records with bounded
  intervals and no forbidden metadata. No actual reviewer labels. Root full
  Python suite122/122, compile pass. Independent model reviewer verified all80
  media files and a synthetic complete export, no blockers. Qualified SLP task
  and threshold signoff still needed for use. Root added a source-cited
  `docs/model/percept-r-research-plan.md` for the closer child-clinical corpus;
  no PERCEPT media acquired. Reviewer cleared sources with one consent wording
  correction, which root applied.
- Model agent `rating_probe_sol` is CURRENTLY implementing a locked final fit
  on all766 author-train clips, alpha0.1 selected in every nested fold, both
  encoders. No author-test inference/metrics or clinical claim. Root will run,
  inspect and request independent read-only review when ready.
- UI: Notebook prototype keyboard/focus/mobile issues fixed; independent
  reviewer rechecked 320/638/900/901/1280, no overflow/axe or blocking issue.
  Agent `review_ui_sol` is CURRENTLY integrating Notebook into live overview,
  preserving mode-aware disclosure, links and consent semantics, and removing
  prototype picker. Root browser tab currently at compare v2 with temporary
  viewport1280; revisit live preview, reset viewport and mark handoff before
  turn ends. No provider-backed signed-in browser due credentials; no native
  build due unaccepted Xcode license.

## Current checkpoint — September 23, ~02:50 America/Chicago

Goal stays ACTIVE; user prioritizes local model training while requesting a
less generic low-card UI. Current task and delegated agents use GPT-6 Sol/High.
No reset credit, paid compute, patient audio, clinical feedback, commit, or
deployment. User has not answered two optional asynchronous questions about
UI direction and available SLP reviewers; proceed on public-data work and a
warm notebook comparison in the meantime. The 5am Chicago checkpoint has not
arrived; usage available.

- Public SpeechOcean /R/ sample and two local blinded reviewer packs remain
  train-only, source/WAV hash-verified and undistributed. Root added a focused
  pack test for opaque queue/80 files, damaged-copy repair and stale-file
  rejection; an independent reviewer previously verified all80 actual WAVs.
- A locked three-class probabilistic head now trains locally on five ratings
  per each of766 author-train clips using two existing frozen feature caches,
  nested five-fold speaker CV, inner hyperparameter selection and train-only
  priors. V1 OOF log loss/Brier: wav2vec .318038/.170638, WavLM
  .321751/.171995, train prior .371679/.191641, word .367545/.191921.
  Independent reviewer fully replayed all766 predictions and selections.
  Seven/ten v1 outer fits hit80-iteration cap, so agent predeclared a numerical
  v2 with only max iteration400 changed; all selections unchanged, metric
  deltas <.000002, 0/10 outer and1/30 unselected inner hits new cap. Reviewer
  replayed v2 and cleared. No independent test/clinical claim.
- Source score reader for NEW rater CV selectively opens only766 selected
  author-train objects. Existing feature-index JSON still parses prior
  test-row metadata but never uses test labels/settings. Root similarly changed
  earlier ridge train CV to selectively parse only2500 author-train score
  objects; actual OOF SHA `dadef13f...6725e` and provenance SHA
  `1fe059f4...c1eda` remained byte-identical, confirmed by reviewer.
- A locked, read-only diagnostic on v2 OOF shows611 unanimous2,29 unanimous0,
  126 mixed. Wav2vec mixed-group log loss1.1394 vs train prior1.1719 (small
  gain); WavLM mixed1.2055 worse than prior. Paired 2000-resample speaker
  bootstrap on fixed predictions: wav2vec−trainPrior −.05364 with percentile
  interval[−.07979,−.03188], WavLM−wav2vec +.00371
  [−.01736,+.02796]. This omits retraining/selection uncertainty. Independent
  reviewer recomputed all6000 differences and cleared. Root reran full Python
  suite112/112 and py_compile after docs; all pass. Docs/README updated.
- Attempt review flat evidence-ledger UI is independently cleared after root
  fixed desktop screen-reader labels and preview consent/attempt parity. Web
  typecheck/lint,53 unit,10 browser/a11y,optimized build passed after those
  fixes. A guarded prototype picker now compares current overview with warm
  notebook layout; visual inspection favors notebook, but read-only reviewer
  found global variant keyboard shortcuts that remount while a learner row is
  focused. `review_ui_sol` is CURRENTLY fixing shortcut scope and mobile back
  navigation/density before root decides on live integration. Prototype is
  guarded 404 in production. Browser tab currently on the comparison route;
  return to normal overview and `markHandoff()` before turn ends.
- Repo remains initially entirely untracked. No native Xcode/provider-backed
  signed-in verification; existing license/credentials blockers unchanged.

## Current checkpoint — September 23, ~02:25 America/Chicago

Goal stays ACTIVE. The user's latest priority is local model training, with
continued compact low-card UI revision. GPT-6 Sol/High, no reset credits, paid
compute, patient recordings, clinical feedback, commits, or deployment. The
intended 5am Chicago checkpoint has not arrived; usage remains available.

- A locked train-only 40-clip /R/ annotation-feasibility recipe now selects 40
  distinct speakers, ten per child≤15/adult≥19 × aggregate2/<2 group. It
  validates pinned metadata, official 520MB archive SHA and every selected WAV;
  candidate counts are 301/48 child and310/107 adult. Ignored internal
  manifest holds source IDs/age/ratings/key; blinded queue holds opaque IDs,
  prompt/target positions only. Full Python suite100/100 pass, deterministic
  rerun byte-identical; independent Sol/High reviewer independently rebuilt
  selection/HMAC hashes and cleared. No SLP annotations yet.
- Root added `speechocean_r_annotation_pack.py` and ran it locally. Two ignored
  40-WAV reviewer packs have opaque filenames, different keyed presentation
  orders, CC BY4 author attribution, no ratings/model outputs. Independent
  reviewer checked both queues and all80 copied WAV hashes, no embedded WAV
  metadata, safe failed-copy recovery and idempotent reruns; no blockers. Packs
  remain local and undistributed. Docs/README describe limitations and next
  qualified SLP gate.
- A Sol/High model agent is CURRENTLY building a predeclared train-only
  three-class rater-distribution head on the existing verified frozen feature
  caches, with nested speaker-held-out validation and proper-scoring baselines;
  no published test labels. Root will integrate/test and request independent
  review before citing results.
- Attempt review preview/live shared component was redesigned as a compact
  evidence ledger. Root visually checked selected and all-attempt pages in the
  running browser; independent Sol/High UI reviewer is CURRENTLY checking
  function/a11y/responsive behavior. Agent reports typecheck/lint, focused
  browser a11y test, no overflow/axe issues at320/638/1280. Browser currently
  on `/accessibility-preview/review` and must return to overview and
  `markHandoff()` before turn ends. Existing dev server3211 remains running.
- A nonblocking UI preference question was asked asynchronously; continue
  productive work if unanswered. Repo initially all untracked; preserve.

## Latest authoritative checkpoint — September 23, 01:25 America/Chicago

Latest Sol/High continuation: `research/audio-head/speechocean_audit.py` and `test_speechocean_audit.py` now source-pin nine author-repository metadata files at revision `613968e3b0b789fc33936fb5eba1973176ba7d11` (29,539,513 bytes, CC BY 4.0 OpenSLR attribution). Ignored actual `outputs/speechocean762-metadata-v1/audit-report-final.json` independently reproduced byte-for-byte: 5,000 scored utterances, train/test each 125 nonoverlapping speakers, 31,816 words, 94,445 canonical phone positions, every aggregate phone rating matching the five annotations, 2,653 marked insertions across raters, 3,403 selective mispronunciation notes. Five-rater descriptive agreement: 78,492 unanimous, 15,953 nonunanimous; score-range counts 0→78,492, 1→7,205, 2→8,748. No audio/archive, patient data, model inference, training, calibration or feedback. Strict validator explicitly rejects relabeling canonical phones as produced-phone CTC targets and current trainer rejects the audit report. Root ran all 70 Python tests with `research/audio-head/.venv/bin/python` and actual audit replay/cmp; independent read-only reviewer recomputed all report counts/hashes and cleared both passes. Root first tried system `python3` full suite, which lacks torch/numpy; corrected to documented `.venv` and all 70 passed. `docs/model/local-training.md` now has actual metadata outcomes, agreement/reproduction; roadmap includes a carefully limited PERCEPT-R/GFTA next-source note (noncommercial, ratings/targets not produced-phone transcriptions). Browser wide overview/review manual visual inspection still showed flat clinical layout. CUA viewport reset, tab returned to overview and markedHandoff. Usage currently 13% weekly used, ordinary allowed; goal remains ACTIVE, no reset credits consumed. Preview server3211 still live.

Goal remains ACTIVE; do not mark it complete or pause. User explicitly requested GPT-6 Sol and High reasoning. Current task was restarted with those settings using `send_message_to_thread`. The last goal turn changed the model setting; this turn made concrete code, evidence, and UI progress. User wants continued work on both UI and local model work until usage is unavailable or the intended 5am Chicago checkpoint. Current usage read reports 11% weekly used, `ordinaryUsageAllowed: true`, no hard limit; two reset credits remain unused. Do not redeem them or spend on paid compute. No patient audio or clinical feedback enabled.

Model: Root added actual Python↔unchanged TypeScript CTC parity bridge/checker and tests; first saved `research/audio-head/outputs/cmu-arctic-ctc-parity-v1.json` had 22 checks from one preserved public recording under four heads. A Sol/High model agent extended the checker with explicit `--export` inputs and a verified 4-head × 3-distinct-recording grid. New ignored `outputs/cmu-arctic-ctc-parity-v2.json` has 12 full-vocabulary public exports, 38 cases (32 finite, 2 impossible, 4 rejected), max absolute log-probability difference 1.4210854715202004e-14 against torch float64. IDs: `cmu-rms-arctic_a0102`, `cmu-slt-arctic_a0201`, `cmu-slt-arctic_a0212`. Research-only, calibration/selection/production/learner-feedback flags false; no training/downloads for parity. Full Python suite 63/63 passed; bridge strict TypeScript and audio-scoring typechecks passed. Independent reviewer reverified all v1/v2 actual results, hashes, provenance and authority flags; no blockers. Docs/model/local-training.md has reproducible v2 Bash commands from `research/audio-head`; roadmap accurately limits math parity and names the next rating-data path.

UI: Root fixed preview `On track` and `Needs review` claims to factual activity/review labels, removed nested mobile overview list scrolling, and made every learner record action visible in a compact mobile list. Mobile Attempt review now shows capture status/reasons in flat stacked rows; desktop retains table. Selecting a learner then opening review passes a scoped `?learner=` link; live route filters the existing tenant-authorized latest-100 service result after authentication, and preview restricts to known fictional IDs in proxy and page. Scoped empty copy says latest 100, with All attempts link. 10/10 browser/a11y checks passed on development server bound to `127.0.0.1`; 53/53 web tests, typecheck, lint, production build passed. A final focused overview browser check passed after changing the review-filter label. Manual CUA at 320/375px confirmed no horizontal overflow, visible record actions, capture status, and full overview list. Production3212 smoke returned404 for preview review/scoped review/learner even with audit flag, then was intentionally stopped. Separate read-only reviewer cleared both UI increments; actual signed-in provider browser is still unprovisioned. Native runtime/build still blocked by unaccepted Xcode license69; do not accept it automatically.

Development preview is live at `http://127.0.0.1:3211/accessibility-preview/overview`, launched with `CADENCE_ACCESSIBILITY_AUDIT_MODE=1 pnpm --filter clinician-web dev --hostname 127.0.0.1 --port 3211`, exec session95681. The old session4226 is missing and 65149 was deliberately stopped; do not restart merely on observation timeout. Current CUA IAB browser2 tab1 is on a mobile Attempt review view with temporary 375px viewport; RESET the viewport, return to overview, and markHandoff before ending the turn. README command now uses the same hostname as browser to avoid Next development cross-origin hydration failures. Browser tests initially failed when server used localhost but tests used127; after restart with hostname127 and mobile locator update, 10/10 pass. No production deployment or Git commit; entire repo remains initially untracked, preserve all files.

Next model work: Read-only primary-source research verified [SpeechOcean762](https://openslr.org/101/) CC BY4 ratings, 5000 utterances/250 Mandarin L1 speakers, 5 expert raters. Authors' `scores.json` phones are canonical, not complete produced-phone transcripts; cannot feed existing CTC `targetPhones`. L2-ARCTIC has manual error labels but CC BY-NC4 and identity-gated access. Roadmap now states distinction. Sol/High `expert_corpus_sol` agent is CURRENTLY working on a metadata-only, official-source-pinned rating-data validator/report under a 30MB metadata cap, no audio/download of520MB archive or training; it may report a concrete source blocker if official metadata unavailable. Root owns integration and review after its result. Do not claim clinical validity. Other agents/reviewer completed and can be reused with Sol/High as needed.

User requested sustained UI + local model work until usage/reset and explicitly High rather than Ultra. Current task was changed with supported send_message_to_thread thinking:high, then stopped/restarted. Goal remains ACTIVE; don't pause/complete prematurely. All current replacement agents are High. Do not resume old Ultra agents. No paid compute, reset-credit redemption, clinical feedback activation, or patient audio authorized. Entire repo was initially untracked; no commits requested.

## Latest verified checkpoint — usage reports100%
Previous turn progress:actualruntimebenchmarktool+144calls+review. This turn progress:connectedread-onlylearnerrecordpreview andfixedrealmobileoverflow.
- Extracted presentation from app/learners/[learnerId]/page.tsx into components/learner-record.tsx. Live route keeps sameauth,2authorizedreads,rolesanderrors. Recordcomponentbacklink usesPortalLink. Reviewer comparedbaseline/tmp/cadence-record-before/page.tsx andcleared.
- ClinicalLearnerTable now uniqueaccessibleOpenrecordlabels andoptionalserverrecordHref callback; defaultliveIDsencoded. Previewlearnerlist usesrealcomponent, links/accessibility-preview/learners?learner=demo-learner-01. lib/preview-learner-records.ts containsONLYfivefictionalrecords; [view]route passescanManage/canDeletefalse,emptydevices,readonlybanner, no dataservicecalls. Proxy importsfixturemoduleonlyforallowlistvalidation; no fixtureimport inclientnavigationmodule. Invalid/repeated/wrong-viewlearnerqueries404beforestreaming. Productionguardunchanged.
- Browsertestcaught390pxmobilepagewidened680px fromgridchildtablemin-content. Addedmin-width:0 tolearner-workspace-main/aside; actualDOMnow390/390 andmanualmobilescreenshotverified. All9browsercheckspass (/tmp/cadence-record-a11y-final.log), typecheck/lintpass, finalproductionbuildpasswithoutwarnings (/tmp/cadence-record-build-final.log). 404productionHTTPcheckedrootpreview/list/validrecordwithauditflag1. Temporaryproduction3212session24892 deliberatelystoppedexit130; don'trestart. Development3211session4226remainsrunning.
- CUAworkingtab3 connectedPreview nowAveryreadonlyrecord; mobileoverrideRESET andtabmarkedHandoff. Oldbroken1/2tabsavoid. UsercanopenlearnerrecordsfromLearnerslist. Sharedlayoutread-onlypreviewverificationisnotprovisionedClerk/Postgresruntimeverification. NativeXcodelicenseblockstillapplies.
- README/accessibilityauditupdated. Independentreviewallsubstantivechangesclear; finalCSSfixfocusedbrowserverified. Entiregitreporemainsinitiallyuntracked; no commits/staging/deployments.
- LatestusageusedPercent100weekly, ordinaryUsageAllowedtrue, rateLimitReachedTypenull (mayberounding; don'tclaimhardexecutiondenialyet). Toolshowsno5hourwindow/5amreset; weeklyresetSep26~03:10CDT. No resetcredits consumed. GoalACTIVE; do notmarkcompletebecauseusageexhausted, do notpausewithoutuserrequest. UserrequestedHigh; allcurrentagentsHigh, oldUltraagentsnotresume.

## Previous goal turn — actual local runtime measurements
Previous turn classifiedprogress:consentUI+8newtrainingruns, allreviewed. Root added measure_runtime.py/test_measure_runtime.py,4focusedtests and full58Python tests pass; prereviewclear. Predeclared experiments/cmu-arctic-runtime-v1.json pins runner/data/source-lock/inputreporthashes. Two separate sequentialfreshCLI processes with offlineenvflags completedexit0 in session79404 (TERMINAL; do notrestart). Outputs/cmu-arctic-runtime-{wav2vec2,wavlm}-v1.json eachcontain72calls on24publicholdouts×3passes, exactrepeatposteriorhashes,firstcallseparate,profiledCPU2threads. HostsysctlAppleM3Max48GiB. Medians65.51/67.70ms,p9581.37/83.77ms,construction1.805/1.200sec,peakwholeprocess1313.69/1321.72MiB. Docs appendedlocal-training.md runtime section androadmap; scopeexcludesdecode/serialization/transport, notconcurrent/mobile/productionperformance. Finalactualartifact review CLEARED:all144calls, exactprovenance, repeatedposteriorhashes, framecounts/RTF/percentiles/RSS/docrounding independentlyverified; WavLMavailableexportmatchesmeasuredposteriorhash. No performancererun. Reviewercomplete/available. No modeldownloads/dependencychanges/newtraining/clinicalfeedback. UIunchangedthisturn; previous8browserchecks/build remainvalid. GoalACTIVE, High.

## Previous goal turn — consent history and seed stability
Previous turn classified as progress (live overview + actual paired models, all reviewed). This turn also made progress:
- Root added components/consent-history.tsx; learnerdetail keeps current explicit latestConsent visible, older records in native details. Everyfield retained, pillsremoved, plaincopy. Fixture covers actualcomponent and keyboard/mobileexpandcollapse.8/8browserchecks,typecheck,lint,warning-freeproductionbuild pass; independentreviewcleared. Logs /tmp/cadence-consent-{a11y,build}.log; beforefiles/tmp/cadence-consent-before/. Docs updated.
- Browser tab3 connectedPreview restoredoverview andmarkedHandoff, devserver3211stillrunning. No provider-backed signed-in or native runtime verification claimed.
- speech_training_high now runs8NEWfixed trainingruns:headseeds17/29,bothencoders,200/800steps,global7. Existingseed7fourruns preserved as anchors. Recipe experiments/cmu-arctic-head-seed-stability-v1.json, replay script experiments/run_head_seed_stability.py; pre-runreviewclear. Actual live execution session78554 (agentowns polling; NEVERrestartdueobservationtimeout). ALL8newruns COMPLETE; outputs/cmu-arctic-head-seed-stability-v1.json saved and finalindependentreview CLEARED. All12runs+3seedmean/min/max/sampleSD, initializationvariabilityonly; no populationCI orselectedwinner. Testmeans: wav2vec20059.54%,80051.10%;WavLM20012.75%,80010.64%. WavLM800range10.03–11.35%. Reviewer independentlyverified all12artifacts/hashes/partitions, allaggregates and all6 curveprefixes. No newnoise/downloads/hyperparamtuning. Modeldocs updated. Rootindependentlychecked teststats/flags too. Allagentscomplete; canreuseHighagentsfornextboundedwork.
- Usage last97%used/3%remaining weekly; no resetredeemed. Goal staysACTIVE.

## Latest completed checkpoint (supersedes in-progress notes below)
- Live signed-in overview implemented and independently reviewed:3bulk authorized reads, current-consent assignment filtering, factual latest100 review evidence, direct learner link, explicit preview-only fixtures.53webtests/typecheck/lint pass; root productionbuild has no warnings and7/7browser checks pass. Provider-backed signed-in visual verification remains unavailable because Clerk/Postgres not provisioned. Docs updated. Root simplified loading/notfound/error copy and removed the unsupported assertion that an error means no mutation occurred.
- New controlled four-run experiment complete at outputs/cmu-arctic-paired-{wav2vec2,wavlm}-{200,800}-headseed7. All headseed7 and initialdigest73d9a5e2612b2b70401910eb5824832489db326f5baed45c72e559527cc90090, same216clipmanifest. Root saved outputs/cmu-arctic-paired-comparison-v2.json and checked same train partition too.54Python tests independently pass.
- Paired test automatic-label errors: wav2vec200232/379=61.21%,800196/379=51.72%; WavLM20050/379=13.19%,80040/379=10.55%. Calibration WavLM58/406=14.29% then61/406=15.02%; longer run has worse calibration and both heldout CTC losses, no blanket winner.
- Separate stress reports outputs/cmu-arctic-paired-{wav2vec2,wavlm}-stress-v2.json complete. WavLM test20dB14.78/14.78%,10dB21.11/23.75%;wav2vec20dB72.56/70.18%,10dB116.62/119.79%. Both use identical96transforms. Both WavLM127x46posterior exports normalized and retain license and falseflags.
- docs/model/local-training.md section432+ and roadmap contain actual outcomes/reproduction commands/limitations. Final actualartifact review CLEARED with no blockers: reviewer rebuilt comparison exactly, independently regenerated all96stresswaveform hashes for both encoders, verified metric/head/manifest linkage, both127x46exports, license evidence, falseflags, and documentation tables. No training rerun needed. All three High agents now completed/available for a new bounded task; do not restart original Ultra agents.
- Browser workingtab3 re-markedHandoff thisturn andserver3211staysrunning. Root buildlog/tmp/cadence-live-overview-build.log; browserlog/tmp/cadence-live-overview-a11y.log.

## Current agents and ownership
- speech_training_high: research/audio-head except root diagnostics/comparison; docs/model/local-training.md and model-development-roadmap.md. Implementing paired frozen wav2vec2/WavLM experiments below.
- offline_model_high: now owns signed-in overview integration (page.tsx, overview-workspace.tsx, projection lib/tests, two preview callers). Previously finished offline adapter, platform clock fixtures, narrow build tracing fix. No backend API/permissions changes planned.
- model_review_high: read-only; completed previous model/native/adapter/comparison reviews, available for forthcoming paired experiment and signed-in overview review.
- Root owns diagnostics.py/test_diagnostics.py, comparison.py/test_comparison.py, other UI integration and checks.

## Completed UI
Neutral compact flat shell/list/detail layout; connected development preview routes overview/learners/assignments/review/safety/privacy. Fictional data explicitly disclosed; local-only assignment form never posts. Mobile navigation/focus/empty/search/filter states work. Unknown preview views404; all preview paths404 in production even with audit flag. Corrected privacy/consent/link-code/safety copy. Native auto recorder completion, stale callbacks, late permissions and interrupted upload fixes independently reviewed. Native Unlink now explicit confirmation; completed practice offers refresh without unlinking. Swift format/parse pass; runtime/build tests blocked by unaccepted Xcode license (exit69), do not accept automatically.

Development preview server remains running3211 in exec session4226. CUA browser2 tab3 handle connectedPreview works, currently overview; markHandoff/Deliverable before ending. Old tabs1/2 have stuck data-URL network errors; avoid them. Playwright temporary config /tmp/cadence-a11y-running-preview.config.ts uses existing server, no downtime. Latest7/7 accessibility/browser checks pass.

Signed-in overview currently still demo-backed; agent now replacing with tenant-authorized bulk reads and pure factual projection. Preview receives explicit fixtures; no demo default in production. Agent must avoid clinical 'on track' inference and N+1 reads. Needs review/browser checks after completion.

## Completed model work
Pinned wav2vec2 frozen encoder +35,374parameter CTC head trained on synthetic tones then public CMU Arctic speech with AUTOMATIC phone alignments (not produced-phone ground truth). All artifacts research-only, uncalibrated, production/feedback flags false. Public source notices and lock hashes retained, decodedPCM duplicate/identity checks strict; households unknown, speaker-disjoint only.

Actual artifacts under research/audio-head/outputs (ignored):
- cmu-arctic-v1/manifest.json:56clips (32bdltrain,12rmscal,12slttest),6.49MB. cmu-arctic-verified-seed7:200steps lr.01; test267/379=70.45%token edits,0exact. Replay identical.
- cmu-arctic-four-speaker-v1/manifest.json:216clips (192train48eachbdl/awb/clb/jmk, exact same24holdouts),24.81MB.
- cmu-arctic-four-speaker-200-seed7:train39.13%,cal52.96%,test226/379=59.63%,26.57sec.
- cmu-arctic-four-speaker-800-seed7:train20.82%,cal50.25%,test189/379=49.87%,54.64sec; heldout CTCloss worse than200step;0exact. Both original recipes retained, no winner.
- cmu-arctic-comparison-v1.json:three ordered original runs, exact holdout identity/provenance validated. Root latest comparison now explicit --allow-encoder-comparison opt-in; default strict.6tests+review passed. Latest tiny addition exports optional headInitializationSeed/initialHeadSha256 (needs test once agent adds fields).
- cmu-arctic-stress-v1.json:same24holdouts×original/-6dB/20dBnoise/10dBnoise,96sharedencoder calls. Test edits baseline70.45/95.25/112.66%;200step59.63/77.57/118.47%;800step49.87/83.64/133.51% original/20/10. Gain unchanged. Independently reproduced waveform hashes/measurements. No clinical robustness claim.
-39/45nonblankphones observed intrain;test2zh unseen. Diagnostic observations only, no holdout-driven recipe tuning.

## Paired encoder work currently in progress
WavLM Base+ exact revision4c66d4806a428f2e922ccfa1a962776e232d487b;377,619,872bytes all3assets within400MB cap. Official processor do_normalize:false preserved. Exactcard links Microsoft UniSpeech CC BY-SA3.0, NOT separate MITcode license; retain fullcard/notices, sourcehashes, attribution and license identity inreport. Private engineering only/no production or redistribution claim. Full52Python tests/review pass before paired initialization extension. No WavLM weights fetched at last update.

Reviewer flagged ambiguous sourceLockSha256; corrected pre-run recipe should distinctly name corpusSourceLockSha256 and sourceNoticeLockSha256, retain earlierrecipe. Root identified avoidable head initialization confound: old global seed applied before encoder construction, which consumes randomstate differently. Agent asked to add optional headInitializationSeed (default preserves oldbehavior) applied immediately beforeheadcreation + initialHeadSha256. Run NEWpaired wav2vec andWavLM200/800step heads withsameheadseed7/same216clips, lr.01, preserve originals. Save all4reports, stress eachencoderpair separately (cannot sharefeaturesbetweenencoders). Root runs explicitcrossencodercomparison whenready and verifies matchinginitialdigests. Reviewer needed.

## Completed runtime and checks
Audio adapter verifies config/preprocessor/vocab/ONNX SHA+size, loads private verified snapshot entirelyoffline; corruptwarmcache failsclosed, no repair/download.22tests+typecheck pass. Actual network-denied synthetic inference49frames×392 zero fetches; retainedinventory evidence. Five narrow turbopackIgnore runtimepath annotations eliminate tracingwarnings and exclude unrelatedrepo files; warningfreewebbuild pass.

Platform authorization tests had stale July expiry fixtures; test-only relativeclock fix+boundarycoverage77pass, independently reviewed. Production expiry/auth unchanged.
Full pnpm test:js completed0 afterthosefixes:237tests total (contracts4,clinical30,audioscoring31,visual29,adapter22,platform77,web44). Log/tmp/cadence-full-js-final.log. Newoverview tests willchangewebcount; rerunfocusedchecksafteragent.
Latest web build/typecheck/lint pass before upcomingoverviewchange. Native runtime notverified dueXcodelicense. Root just corrected device eligibility copy to include assent not-applicable, matchingservice.

Last usage91%used/9%remaining weekly; no5amreset exposed. Weekly resetSep26 03:10CDT. No resetcredits consumed. Continue useful authorized increments; no artificial tokenburn or polling loops.
## Latest checkpoint — September 23, 2026, ~02:00 America/Chicago

User's latest priority is model training, while UI revision continues. Current task is GPT-6 Sol/High; goal remains ACTIVE until usage actually becomes unavailable or the user's 5am Chicago checkpoint. No reset credits, paid compute, patient recordings, clinical feedback, commits, or deployment authorized. Earlier sections below retain history and may describe older in-progress states.

- Downloaded official OpenSLR SLR101 SpeechOcean762 audio archive (520,810,923 bytes, SHA-256 `876c34b828c2ebcc35ba2ff1ba5947d50e6b0162fc4a4af91db0942422b3bdd5`) to ignored `research/audio-head/outputs/speechocean762-audio-v1`. Full archive extracted locally; all 1,525 selected exact-one-canonical-R WAVs verified against pinned archive members and pinned author metadata. Source archive is CC BY 4.0 per OpenSLR. The archive's score file differs from pinned author scores only in 1,877 selective note fields, not aggregate ratings/prompts.
- `research/audio-head/speechocean_r_probe.py` now implements a research-only frozen-wav2vec2 Base full-utterance mean-pool ridge rating probe, not a produced-phone CTC model. Author train/test: 766/759 clips, 124/125 disjoint speakers. Twenty-five training speakers /151 clips choose the ridge penalty; final head fits all766 training clips. Feature cache is bound to exact extracted WAV byte hashes, pinned archive, encoder identity, recipe, index and feature hash, with read-time WAV SHA verification. Fresh v2 extraction took100.86s, saved `outputs/speechocean-r-probe-v2/{report.json,provenance.json,rating-head.npz,feature-index.json,feature-progress.json,features.npy}`. Test audio ridge MAE/MSE .271251/.164728; train mean .273035/.166055; target-word .265806/.189093; constant-2 .146245/.184295. No meaningful MAE gain; 125/759 predictions >2. Known exploratory holdout, 81.29% labels at2, 11 shared prompts, all release/clinical flags false. Independent reviewer cleared v2 provenance, saved features/head and metrics. Root independently reran full Python suite78/78 pass after catching a transient test-fixture regression that agent corrected. `docs/model/local-training.md` and roadmap now report full methods, reproduction, limitations, next research question.
- Matched WavLM Base+ comparison is now complete and independently reviewed, using the predeclared `experiments/speechocean-r-wavlm-v1.json` and existing pinned local model cache offline. Fresh 1,525-clip feature extraction took108.48s; `outputs/speechocean-r-probe-wavlm-v1/report.json` has held-out MAE/MSE .258918/.164510 vs wav2vec .271251/.164728. Baselines match exactly, 163 WavLM predictions exceed2, and constant-2 MAE .146245 remains much better. No encoder winner or clinical claim. Root independently reran full Python suite80/80; reviewer recomputed fit/metrics and three WavLM feature vectors exactly. `docs/model/local-training.md` records this contrast. Do not tune on the already-inspected test results.
- UI agent fixed selected-learner continuity from overview to assignment form in preview and live, including query/tenant validation and ineligible-consent warning. Independent read-only reviewer found no blockers. Root browser-selected Jordan and confirmed `?learner=demo-learner-02#assignment-form`, selected combobox Jordan, heading Jordan. Root added explicit copy that the current /b/ exercise is the only assignable exercise so selected learners with other current targets are not misled. Then an Emil-skills-guided overview redesign replaced circular avatars/loose rows with a compact ruled numbered worklist, aligned last-practice values and a restrained selected rule. Root visually inspected the running browser; separate reviewer checked actual 1440/375px rendering, navigation and overflow from320–1024px, no blockers. Web typecheck, lint, 53 unit tests, 10/10 browser/a11y tests, and optimized production build all pass after final UI change. Production preview guard returned404 for overview and both valid/unknown assignment query even with audit flag. Temporary production3212 stopped; `127.0.0.1:3211` development preview still responds200. Browser tab1 now on overview; markHandoff before turn ends.
- Train-only canonical /R/ CTC alignment pilot is complete, source-pinned and independently reviewed. It selected20 deterministic distinct author-train speakers, mapped all766 train prompts to CTC vocabulary, verified pinned archive/selected WAVs/three WavLM-CMU-Arctic heads, and saved `outputs/speechocean-r-alignment-pilot-v1/report-v2.json`. Across60 head/clip diagnostics,9/20 clips had at least one support/stability flag and each head had zero exact full-prompt greedy matches. Reviewer independently replayed all60 and found no blockers. Forced canonical paths are model hypotheses, not verified intervals. Docs now say do not train a segment head on these as ground truth; need reviewed time/produced-phone annotations.
- Train-only nested speaker CV is now complete and independently reviewed. `experiments/speechocean-r-train-cv-v1.json` pinned two saved feature caches and five outer folds; inner speaker-only validation selected alpha/smoothing, then each fold refit on its outer training speakers. `outputs/speechocean-r-train-cv-v1/report.json` and `out-of-fold.json` cover all766 author-train clips, no author-test labels/metrics used. Pooled OOF MAE/MSE: wav2vec .294228/.200687, WavLM .294270/.202416, target-word .311897/.256113, constant2 .202350/.288512. Encoders essentially tied; WavLM lower in3/5 folds, no stable winner. 0 exact prompt overlaps observed per fold, not guaranteed by grouping. 130/193 audio predictions >2. Reviewer exactly replayed all766 predictions/inner choices/folds; root independently reran full Python suite90/90. Local-training docs and roadmap updated.
- Train-only exact-one-R label audit `speechocean_r_label_audit.py` is complete, independently reviewed, and documented. It parsed only2500 author-train score objects from pinned metadata, no test rating objects/audio, then rederived all3830 individual ratings for766 clips:611 unanimous2,29 unanimous0,0 unanimous1,126 mixed; spread0/1/2 counts640/20/106. Of155 below2,126 are mixed, so binary error labeling by mean<2 is weak. Reviewer reconstructed entire report, no blockers; root reran full Python suite96/96. A new planning draft `docs/model/r-target-annotation-plan.md` calls for qualified SLP review of a bounded train-only interval/production sample; separate reviewer cleared it as a draft. `rating_probe_sol` is now preparing a deterministic blinded40-clip train-only queue with age×score strata, source hashes, no patient data. No SLP annotation/feedback yet.
- Assignment UI received a second Emil-guided flat numbered learner→sole exercise→dose workflow in preview/live, with responsive no-overflow behavior. Root verified Jordan handoff and visually inspected preview. Reviewer found a live stale action-state bug: after success, changing learner could leave success text under the new learner. Root fixed via monotonic formRevision echoed by server, learner identity guard, hidden pending/stale states, controlled dose/retry fields, and cleared aria-invalid after edits. Reviewer rechecked race and found no blocker; last full web checks pass: typecheck/lint,53 unit,10 browser/a11y,optimized build. Actual signed-in provider UI still unavailable without clinic credentials.
- Repo still initially entirely untracked (`git status --short` top-level `??` paths); preserve. Reviewer of model v2 found no blockers. Native runtime remains unverified due unaccepted Xcode license; provider-backed signed-in runtime not configured. Avoid claiming either.
