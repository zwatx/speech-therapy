# Canonical reminder before a deliberate retake

Selected practice now offers a collapsed **Practice reminder** immediately before
Record another try. Opening it shows the same canonical instruction used before
the first recording, including P in Pig and R in the BR of Bread. It is general
practice guidance; the recording's word-check outcome does not select its text.

The reminder requires a retained take in the exact prepared selected-practice
visit. It closes for a new take, new practice visit or departure from review.
Replay/check state alone does not reset it. Opening or closing the reminder changes
only presentation state. Existing action, cleanup, assessment and participation
rules remain unchanged. About retains its other content and Sources; only its
identical main detail is omitted while the reminder is open, then restored on
collapse. Ready Try this remains unchanged.

## Observed verification

Evidence is retained in `work/feedback-continuation-20261025`:

- Seven existing canonical-instruction tests passed, covering default targets,
  exact R/BR selection, neutral unsupported-target fallback, mismatched/forged
  context, review exclusion and changing words.
- Two generated Debug UI journeys passed at normal and largest text on the owned
  iPhone SE simulator with iOS 26.2. Each records first-review Ball, finishes that
  review, selects Pig and Bread, opens the Pig reminder, retakes Pig, changes to
  Bread, records and stops a fresh take, opens its BR reminder, skips Bread and
  enters a fresh recheck.
- Each journey proves explicit public Close with four generated files made and
  zero retained, zero word checks/playback starts, one exact Pig participation
  receipt and unchanged history after Bread skip. Reminder interactions themselves
  leave those counters unchanged. First-review and fresh-recheck screens have no
  reminder; a new take returns with it collapsed.
- Independent review inspected all 48 distinct generated screenshots, 76 image
  members and 76 raw geometry records. Six reminder and two restored-About text
  traces cover each complete paragraph. Largest text uses overlapping scroll
  captures, with minimum overlap 211 points. No font reduction was used.
- Eight recording screenshots and their accessibility trees, captured before
  helper reveal, show Stop fully inside the usable viewport, including the retake
  entered with an expanded reminder. The test's Stop helper may reveal it before
  tapping; these snapshots are not a new passive visibility assertion gate.
- Two ordinary Release navigation journeys passed on the same frozen source.
  They cover normal/largest selected-word entry, current ready instruction,
  disclosure/source access, next-word reset, fresh recheck and closing with
  unchanged visible history. They never start recording. Their export contains
  47 distinct screenshots, 58 image members and 48 geometry records.
- Independent Release review inspected those 47 screenshots and checked all 58
  members and 48 geometry records. Four word entries, eight disclosure pairs and
  14 complete text traces preserve the expected positions and readability.

All three suites had zero failures, skips, expected failures, runtime warnings or
runner restarts. Root personally observed original unit parent 28105, direct unit
export return 64071f and verifier 14563 finish successfully; generated UI parent
93137, export 29473 and verifier 58162; Release parent 50323, export 89474 and
verifier 51691. The Release worker completed normally in 463.615 seconds with no
signals, remaining worker processes or cleanup errors. Both simulator states were
confirmed shut down afterward.

All 307 frozen input pins matched. Release verification preserved 31 earlier
build inventories and recorded 1,136 files in the fresh current build. The exact
26-file, 310,277,151-byte Release app is identified in CANDIDATE.json. POSTCHECK and
DELIVERY, when present, record final preservation of the earlier candidate and
current bindings. No copied build database was executed.

## Limits

Generated recordings are held synthetic captures with fake permission, silent
media providers and no spoken-word provider. They establish no real microphone,
audible playback, automatic four-second timing, model accuracy or clinical benefit.
Ordinary Release evidence qualifies navigation, not reminder interaction after
recording or timeout retry. Active playback/check continuity, ordinary reminder
exclusion and permission/error recovery are source-reviewed rather than newly
runtime-qualified here. Full R alternatives, VoiceOver, contrast, installed-bundle
byte equality, physical-device and whole-app release qualification remain outside
this increment. Individual-sound assessment and diagnosis remain unvalidated; the
broad product goal and external review remain open.
