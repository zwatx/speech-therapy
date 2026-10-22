#if DEBUG && targetEnvironment(simulator)
  import XCTest
  @testable import CadenceLearner

  @MainActor
  final class ResearchSoundPresentationTests: XCTestCase {
    func testAllFourModelStatesCarryLimitationAndSpokenBoundary() {
      let cases: [(ResearchSoundObservation.Preference?, String)] = [
        (.rPath, "result-br"), (.wPath, "result-bw"), (.otherPath, "result-other"),
        (nil, "result-no-clear-pick"),
      ]
      for (preference, id) in cases {
        let observation = ResearchSoundObservation(
          status: preference == nil ? .inconclusive : .observedModelPreference,
          reason: preference == nil ? "uncovered_mass_dominates" : "model_preferred_candidate",
          preference: preference)
        let result = ResearchSoundPresentation.make(
          phase: .observation(observation), paused: false, canCheck: false)
        XCTAssertEqual(result.id, id)
        XCTAssertTrue(result.modelResult)
        XCTAssertTrue(result.announcement.contains("doesn't show whether bread was said correctly"))
        if preference == .rPath { XCTAssertTrue(result.spokenTitle.contains("B R version")) }
        if preference == .wPath { XCTAssertTrue(result.spokenTitle.contains("B W version")) }
      }
      XCTAssertTrue(ResearchSoundPresentation.limitation.contains("whole recording"))
      XCTAssertTrue(ResearchSoundPresentation.limitation.contains("independently confirmed"))
      XCTAssertTrue(ResearchSoundPresentation.limitation.contains("isn't validated for children"))
    }
    func testFailureAndPauseNeverBestFitAndSeparate8782Unchanged() {
      for reason in ResearchSoundContract.unavailable {
        let result = ResearchSoundPresentation.make(
          phase: .observation(.init(status: .unavailable, reason: reason, preference: nil)),
          paused: false, canCheck: false)
        XCTAssertFalse(result.modelResult)
        XCTAssertFalse(result.title.contains("best fit"))
      }
      let pause = ResearchSoundPresentation.make(
        phase: .review, paused: true, canCheck: false)
      XCTAssertEqual(pause.id, "paused")
      XCTAssertFalse(pause.modelResult)
      XCTAssertFalse(pause.title.contains("word"))
      XCTAssertFalse(pause.detail.contains("8782"))
      XCTAssertEqual(
        ResearchSoundPresentation.make(
          phase: .recording, paused: true, canCheck: false
        ).id, "recording")
      let cleanup = ResearchSoundPresentation.make(
        phase: .localCleanupBlocked, paused: true, canCheck: false)
      XCTAssertEqual(cleanup.id, "cleanup")
      XCTAssertTrue(cleanup.detail.contains("could not be confirmed removed"))
      XCTAssertFalse(cleanup.detail.contains("restart"))
    }
    func testReadyCopyReflectsActualSelections() {
      let off = ResearchSoundPresentation.make(
        phase: .ready, paused: false, canCheck: false, setupEnabled: false)
      let on = ResearchSoundPresentation.make(
        phase: .ready, paused: false, canCheck: false, setupEnabled: true)
      XCTAssertTrue(off.detail.contains("turn on both options"))
      XCTAssertFalse(on.detail.contains("turn on both options"))
      XCTAssertTrue(on.detail.contains("Tap Record"))
    }
    func testCapacityAndAlreadyCheckedCopyDoesNotPromiseRecovery() {
      for reason in [
        "attempt_limit", "context_limit", "capture_already_checked", "attempt_already_checked",
      ] {
        let result = ResearchSoundPresentation.make(
          phase: .observation(.init(status: .unavailable, reason: reason, preference: nil)),
          paused: false, canCheck: false)
        XCTAssertFalse(result.modelResult)
        XCTAssertFalse(result.detail.contains("restart"))
        if reason.hasSuffix("_limit") {
          XCTAssertEqual(result.id, "error-limit")
          XCTAssertTrue(result.detail.contains("cannot accept more checks"))
        } else {
          XCTAssertEqual(result.id, "error-already-checked")
          XCTAssertTrue(result.detail.contains("fresh take"))
        }
      }
      let limit = ResearchSoundPresentation.make(
        phase: .ready, paused: false, canCheck: false, captureLimitReached: true)
      XCTAssertEqual(limit.id, "recording-limit")
      XCTAssertTrue(limit.detail.contains("cannot start more recordings"))
      XCTAssertFalse(limit.detail.contains("reset"))
    }
    func testClosedFixtureSelectionOnlyAndNormalDefaultHasNoFixture() {
      XCTAssertNil(ResearchSoundUITestFixtures.selected([]))
      XCTAssertNil(ResearchSoundUITestFixtures.selected(["-CadenceSoundUITestCase"]))
      XCTAssertNil(ResearchSoundUITestFixtures.selected(["-CadenceSoundUITestCase", "unknown"]))
      XCTAssertEqual(ResearchSoundUITestFixtures.selected(["-CadenceSoundUITestCase", "bw"]), .bw)
    }
  }
#endif
