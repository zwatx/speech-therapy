# Keep Stop visible when recording starts

Starting a first recording or retake now brings the active Stop control into
view. The presentation change anchors the existing Stop control and reveals it
when the session enters recording. It leaves recording ownership, recognition,
assessment submissions and saved participation unchanged.

The original largest-text ordinary-practice reproduction placed Stop 29 points
above the unobscured viewport. Its caption was still visible and hittable, so
this was partial clipping, not a completely unreachable control. Two normal-text
baseline journeys passed. The largest selected-practice baseline failed in its
word-selection helper before recording; that result does not establish a second
recording defect. All original failures and captures remain preserved.

The test setup now permits tapping the visible intersection of an oversized
word-selection row. Record and Stop still require their entire finite, enabled,
hittable frame to fit inside the measured usable viewport, with at least 44 points
in both dimensions. No visibility criterion was relaxed for the recording fix.

## Observed checks

Evidence is retained in `work/recording-transition-20261025`.

- Four generated Debug journeys passed: ordinary and selected practice, each at
  normal and largest text sizes on the owned iPhone SE simulator running iOS 26.2.
  Each covers a first recording and retake: all eight initial Stop observations
  were fully visible without corrective scrolling.
- Public Stop and Close actions verified retained-file counts and zero files
  kept after closing. Guided checks and history remained unchanged. Teardown
  termination is not the cleanup evidence.
- An independent reviewer inspected all 30 distinct generated screenshots,
  representing 34 image attachments, and checked all 34 geometry records.
  First and retake Stop placement matched within each configuration.
- Two existing ordinary Release navigation journeys passed against the current
  source, at normal and largest text. They cover word selection, current practice
  instructions, fresh-visit word positioning, disclosure position, next-word
  reset, fresh recheck and unchanged history on closing. They do not record.
- Independent Release review inspected all 47 distinct screenshots, representing
  57 image attachments, and all 46 geometry records. Four pre-gesture word entries
  and eight disclosure pairs retained the expected positions. Fourteen text traces
  covered their complete text, using overlapping scroll captures for long content.

Both successful suites had zero failures, skips, expected failures, runtime
warnings or restarts. Root personally observed generated test parent 19287,
export 32234 and verifier 5180 finish successfully, followed by Release test
parent 55844, export 12078 and verifier 59520. The Release worker completed normally
in 460.756 seconds with no signals, remaining worker processes or cleanup errors.
Both simulator states were confirmed shut down afterward.

The Release verification matched all 306 frozen inputs and all 28 prior build
inventories. Its fresh build inventory contains 1,134 files. `CANDIDATE.json`
records the exact Release app and every bundled file hash; `POSTCHECK.json` and
`DELIVERY.json`, when present, record final preservation. Previous candidates
remain unchanged. No copied build database was executed.

## Limits

The recording tests use generated capture held until Stop, silent media doubles
and a nil spoken-word provider. They do not establish actual microphone/camera
behavior, audible playback, automatic four-second stopping or model accuracy.
The observation is the first passive XCTest snapshot after Stop appears, not a
frame-by-frame guarantee of zero movement or transient clipping. Larger text can
still require scrolling to read surrounding paragraphs.

The ordinary Release checks qualify navigation on this source; they do not
exercise active Stop, timeout retry or real media in Release. No installed-bundle
byte comparison, physical-device, VoiceOver, contrast, whole-app release or
clinical qualification is claimed. Individual-sound feedback and diagnosis still
require supporting evidence. The broad product goal and external review remain
open.
