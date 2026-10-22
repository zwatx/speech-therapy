import Combine
import XCTest

@testable import CadenceLearner

@MainActor
final class RecordingAdviceSessionTests: XCTestCase {
  private func record(_ fixture: RecordingAdviceGeneratedFixture, another: Bool = false) async {
    if another {
      await fixture.session.recordAnotherTry()
    } else {
      await fixture.session.startRecording()
    }
    XCTAssertEqual(fixture.session.phase, .recording)
    fixture.session.stopRecording()
  }

  private func advice(_ take: DirectPracticeTry) -> DirectPracticeRecordingAdvice? {
    DirectPracticeRecordingAdvice.observation(summary: take.summary, assessment: take.assessment)
  }

  func testDistinctTakeBindingsThirdTryEvictionAndReadingAdviceAreInert() async throws {
    let fixture = try RecordingAdviceGeneratedFixture()
    await record(fixture)
    let first = try XCTUnwrap(fixture.session.latestTry)
    XCTAssertEqual(advice(first)?.title, "No sound was saved in this try")
    await record(fixture, another: true)
    let second = try XCTUnwrap(fixture.session.latestTry)
    XCTAssertNotEqual(first.id, second.id)
    XCTAssertEqual(fixture.session.earlierTry, first)
    XCTAssertEqual(advice(second)?.title, "Recording reached its volume limit")
    XCTAssertEqual(advice(try XCTUnwrap(fixture.session.earlierTry)), advice(first))
    for _ in 0..<3 { _ = fixture.session.tries.map(advice) }
    XCTAssertEqual(fixture.capture.startCount, 2)
    XCTAssertEqual(fixture.capture.permissionCount, 2)
    XCTAssertEqual(fixture.player.playCount, 0)
    XCTAssertEqual(fixture.recognizer.checkCount, 0)
    XCTAssertTrue(fixture.history.entries.isEmpty)
    await record(fixture, another: true)
    let third = try XCTUnwrap(fixture.session.latestTry)
    XCTAssertEqual(fixture.session.earlierTry, second)
    XCTAssertNotEqual(third.id, second.id)
    XCTAssertNil(advice(third))
    XCTAssertNil(third.summary.pcm16Signal)
    XCTAssertFalse(
      DirectPracticeRecordingAdvice.suppressesQuietTip(
        summary: third.summary, assessment: third.assessment))
    XCTAssertFalse(FileManager.default.fileExists(atPath: fixture.capture.recordings[0].url.path))
    XCTAssertEqual(fixture.capture.discardCount, 1)
    XCTAssertEqual(fixture.session.tries.count, 2)
    let finished = try await fixture.finish()
    XCTAssertTrue(finished)
    XCTAssertTrue(fixture.session.tries.isEmpty)
  }

  func testDeniedAndFailedReplacementRetainExactPriorAdviceUntilExplicitReturn() async throws {
    let fixture = try RecordingAdviceGeneratedFixture()
    await record(fixture)
    let kept = try XCTUnwrap(fixture.session.latestTry)
    fixture.capture.permissionGranted = false
    await fixture.session.recordAnotherTry()
    XCTAssertEqual(fixture.session.phase, .permissionDenied)
    XCTAssertEqual(fixture.session.latestTry, kept)
    fixture.session.returnToReview()
    XCTAssertEqual(advice(try XCTUnwrap(fixture.session.latestTry)), advice(kept))
    fixture.capture.permissionGranted = true
    fixture.capture.failStart = true
    await fixture.session.recordAnotherTry()
    guard case .failed = fixture.session.phase else {
      return XCTFail("Expected failed replacement")
    }
    XCTAssertEqual(fixture.session.latestTry, kept)
    fixture.session.returnToReview()
    XCTAssertEqual(fixture.capture.startCount, 1)
    XCTAssertEqual(fixture.player.playCount, 0)
    XCTAssertEqual(fixture.recognizer.checkCount, 0)
    XCTAssertTrue(fixture.history.entries.isEmpty)
    let finished = try await fixture.finish()
    XCTAssertTrue(finished)
  }

  func testCloseDuringStopAndReviewPublicationCannotRetainStaleMetadata() async throws {
    for publication in [false, true] {
      let fixture = try RecordingAdviceGeneratedFixture()
      await record(fixture)
      await fixture.session.recordAnotherTry()
      let session = fixture.session
      var observation: AnyCancellable?
      var revoked = false
      if publication {
        observation = session.$phase.sink { phase in
          MainActor.assumeIsolated {
            guard !revoked, case .review(let summary, _) = phase,
              summary.pcm16Signal?.railSampleCount == 2
            else { return }
            revoked = true
            session.viewDidDisappear()
          }
        }
      } else {
        fixture.capture.duringStop = {
          revoked = true
          session.viewDidDisappear()
        }
      }
      session.stopRecording()
      XCTAssertTrue(revoked)
      let finished = try await fixture.finish()
      XCTAssertTrue(finished)
      XCTAssertTrue(session.tries.isEmpty)
      XCTAssertEqual(session.attemptCount, 1)
      XCTAssertEqual(session.completedWords, 0)
      XCTAssertTrue(fixture.history.entries.isEmpty)
      observation?.cancel()
      fixture.capture.duringStop = nil
    }
  }

  func testBackgroundAndNextRemoveAdviceWithExactOwnedTakesWithoutAutoRecognition() async throws {
    for background in [false, true] {
      let fixture = try RecordingAdviceGeneratedFixture()
      await record(fixture)
      await record(fixture, another: true)
      if background {
        fixture.session.appDidEnterBackground()
      } else {
        await fixture.session.continuePractice()
        XCTAssertEqual(fixture.session.currentIndex, 1)
      }
      // end joins background's exact pending transition; no arbitrary settling delay.
      let finished = try await fixture.finish()
      XCTAssertTrue(finished)
      XCTAssertTrue(fixture.session.tries.isEmpty)
      XCTAssertEqual(fixture.capture.discardCount, 2)
      XCTAssertEqual(fixture.player.playCount, 0)
      XCTAssertEqual(fixture.recognizer.checkCount, 0)
      XCTAssertTrue(fixture.history.entries.isEmpty)
    }
  }

  func testGuidedNextStillRequiresLatestQualityAndRailEvidenceNeverStartsCheck() async throws {
    let cases: [[Int16]?] = [[-32768, 32767], [1, -1], nil]
    for samples in cases {
      let fixture = try RecordingAdviceGeneratedFixture(managedForGuided: true)
      fixture.capture.summaries = [
        RecordingAdviceGeneratedFixture.summary(samples, duration: 0.1),
        RecordingAdviceGeneratedFixture.summary(samples),
      ]
      let entry = try XCTUnwrap(PracticeLibrary.entries(soundID: "b", position: .beginning).first)
      let visit = LocalGuidedPracticeVisit(
        workflowID: UUID(), practiceID: UUID(),
        visitID: UUID(), entryID: entry.id)
      let prepared = await fixture.session.prepareGuidedVisit(entry: entry, visit: .practice(visit))
      XCTAssertTrue(prepared)
      await record(fixture)
      let rejected = await fixture.session.finishGuidedPractice(visit)
      XCTAssertNil(rejected.completionID)
      XCTAssertTrue(fixture.history.entries.isEmpty)
      await record(fixture, another: true)
      let fresh = try XCTUnwrap(fixture.session.latestTry)
      XCTAssertEqual(fresh.assessment, .acceptable)
      let completed = await fixture.session.finishGuidedPractice(visit)
      XCTAssertEqual(completed.freshTryID, fresh.id)
      XCTAssertEqual(completed.completionID, visit.visitID)
      XCTAssertTrue(completed.cleanupConfirmed && completed.saveConfirmed)
      XCTAssertEqual(fixture.history.entries.count, 1)
      XCTAssertEqual(fixture.recognizer.checkCount, 0)
      XCTAssertEqual(fixture.player.playCount, 0)
      XCTAssertEqual(fixture.capture.startCount, 2)
      let finished = try await fixture.finish()
      XCTAssertTrue(finished)
    }
  }
}
