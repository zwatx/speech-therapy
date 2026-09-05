import Combine
import Foundation
import SwiftUI
import UIKit
import XCTest

@testable import CadenceLearner

@MainActor
final class CACDemoTests: XCTestCase {
  // MARK: Script

  func testSoundCheckUsesExactCanonicalEntriesAndScriptedOutcomes() throws {
    let words = CACScript.soundCheck
    XCTAssertEqual(words.map(\.word), ["boat", "rabbit", "sun"])
    XCTAssertEqual(words.map(\.outcome), [.clear, .needsPractice, .clear])
    XCTAssertEqual(words.map(\.sound.id), ["b", "r", "s"])
    for word in words {
      XCTAssertEqual(word.sound.position, .beginning)
      XCTAssertEqual(word.sound.prompts.count, 1)
      let entry = try XCTUnwrap(
        PracticeLibrary.entries(soundID: word.sound.id, position: .beginning)
          .first(where: { $0.id == word.entryID }))
      XCTAssertEqual(entry.prompt, word.prompt, "\(word.word) must keep its canonical phonetics")
      XCTAssertTrue(word.word.hasPrefix(word.grapheme))
    }
    // R keeps the library's own symbol rather than the default starter sound.
    XCTAssertEqual(words[1].sound.symbol, "ɹ")
  }

  func testPlanFollowsTheSubmittedMissNotAFixedSound() throws {
    let words = CACScript.soundCheck
    func results(_ outcomes: [CACScriptedOutcome]) -> [CACScriptedResult] {
      zip(words, outcomes).map {
        CACScriptedResult(
          source: .scripted, wordID: $0.id, entryID: $0.entryID, takeID: UUID(), outcome: $1)
      }
    }
    let r = try XCTUnwrap(
      CACScript.plan(after: results([.clear, .needsPractice, .clear]), in: words))
    XCTAssertEqual(r.focus.entryID, words[1].entryID)
    XCTAssertEqual(r.recheck.entryID, words[1].entryID)
    XCTAssertEqual(r.recheck.part, .recheck)
    XCTAssertFalse(r.practice.isEmpty)
    let rEntries = PracticeLibrary.entries(soundID: "r", position: .beginning)
    for word in r.practice {
      XCTAssertEqual(word.sound.id, "r")
      XCTAssertNotEqual(word.entryID, words[1].entryID)
      XCTAssertTrue(rEntries.contains(where: { $0.id == word.entryID && $0.prompt == word.prompt }))
    }

    let b = try XCTUnwrap(
      CACScript.plan(after: results([.needsPractice, .clear, .clear]), in: words))
    XCTAssertEqual(b.letter, "B")
    XCTAssertTrue(b.practice.allSatisfy { $0.sound.id == "b" })
    XCTAssertNil(CACScript.plan(after: results([.clear, .clear, .clear]), in: words))
  }

  func testOutOfOrderActionsDoNothingWithoutMedia() async {
    let coordinator = CACDemoCoordinator(makeSession: { _ in
      preconditionFailure("No media session is expected")
    })
    coordinator.check()
    await coordinator.next()
    await coordinator.startPractice()
    await coordinator.practiceAgain()
    await coordinator.record()
    XCTAssertEqual(coordinator.stage, .welcome)
    XCTAssertNil(coordinator.session)
    XCTAssertTrue(coordinator.submitted.isEmpty)
  }

  // MARK: Result binding

  func testCheckNeedsAStoppedAcceptableTakeAndIsFrozenPerTake() async throws {
    let fixture = try CACDemoMediaFixture()
    defer { fixture.removeDirectory() }
    let coordinator = fixture.coordinator()
    await coordinator.start()
    let owner = try XCTUnwrap(coordinator.session)
    XCTAssertEqual(owner.sound.prompts.map(\.word), ["boat"])
    XCTAssertEqual(fixture.driver.recordings, 0, "Entering a word never starts media")

    coordinator.check()
    XCTAssertNil(coordinator.result)
    await coordinator.record()
    XCTAssertEqual(owner.phase, .recording)
    coordinator.check()
    XCTAssertNil(coordinator.result, "A recording in progress cannot be checked")
    owner.stopRecording()

    coordinator.check()
    let first = try XCTUnwrap(coordinator.currentResult)
    XCTAssertEqual(first.source, .scripted)
    XCTAssertEqual(first.takeID, owner.latestTry?.id)
    XCTAssertEqual(first.entryID, CACScript.soundCheck[0].entryID)
    XCTAssertEqual(first.outcome, .clear)
    coordinator.check()
    coordinator.check()
    XCTAssertEqual(coordinator.currentResult, first, "The same take keeps the same result")

    await coordinator.recordAgain()
    XCTAssertNil(coordinator.currentResult, "A retake clears the old result")
    XCTAssertEqual(owner.phase, .recording)
    await coordinator.next()
    XCTAssertTrue(coordinator.session === owner, "No result means no advance")
    owner.stopRecording()
    XCTAssertNil(coordinator.currentResult, "A new take needs its own check")
    coordinator.check()
    let second = try XCTUnwrap(coordinator.currentResult)
    XCTAssertNotEqual(second.takeID, first.takeID)
    XCTAssertEqual(second.takeID, owner.latestTry?.id)
    await coordinator.close()
  }

  func testDeniedMicrophoneNeverProducesAResult() async throws {
    let fixture = try CACDemoMediaFixture()
    defer { fixture.removeDirectory() }
    fixture.permissionGranted = false
    let coordinator = fixture.coordinator()
    await coordinator.start()
    let owner = try XCTUnwrap(coordinator.session)
    await coordinator.record()
    XCTAssertEqual(owner.phase, .permissionDenied)
    coordinator.check()
    await coordinator.next()
    XCTAssertNil(coordinator.currentResult)
    XCTAssertTrue(coordinator.session === owner)
    XCTAssertEqual(coordinator.current?.id, CACScript.soundCheck[0].id)
    XCTAssertEqual(fixture.driver.recordings, 0)
    await coordinator.close()
  }

  func testShortTakeCannotBeChecked() async throws {
    let fixture = try CACDemoMediaFixture()
    defer { fixture.removeDirectory() }
    fixture.summary = CaptureSummary(duration: 0.1, averagePower: -70)
    let coordinator = fixture.coordinator()
    await coordinator.start()
    let owner = try XCTUnwrap(coordinator.session)
    await coordinator.record()
    owner.stopRecording()
    guard case .review(_, .retry) = owner.phase else {
      return XCTFail("Expected a retry assessment, got \(owner.phase)")
    }
    coordinator.check()
    XCTAssertNil(coordinator.result)
    await coordinator.close()
  }

  func testQuietTakeCanBeCheckedAndAdvanceWithoutChangingCaptureAssessment() async throws {
    let fixture = try CACDemoMediaFixture()
    defer { fixture.removeDirectory() }
    var signal = PCM16SignalMeasurements.Accumulator()
    signal.append(1)
    fixture.summary = CaptureSummary(
      duration: 1, averagePower: -70, pcm16Signal: signal.measurements())
    let coordinator = fixture.coordinator()
    await coordinator.start()
    let owner = try XCTUnwrap(coordinator.session)
    await coordinator.record()
    owner.stopRecording()
    XCTAssertEqual(owner.latestTry?.assessment, .retry(CaptureQualityAssessor.quietCoaching))
    XCTAssertTrue(coordinator.currentRecordingCanBeChecked)
    coordinator.check()
    let result = try XCTUnwrap(coordinator.currentResult)
    XCTAssertEqual(result.takeID, owner.latestTry?.id)
    coordinator.check()
    XCTAssertEqual(coordinator.currentResult, result)
    await coordinator.next()
    XCTAssertEqual(coordinator.current?.word, "rabbit")
    XCTAssertEqual(coordinator.submitted.count, 1)
    await coordinator.close()
  }

  func testCapturedAllZeroAudioCannotProduceAResult() async throws {
    let fixture = try CACDemoMediaFixture()
    defer { fixture.removeDirectory() }
    var signal = PCM16SignalMeasurements.Accumulator()
    signal.append(0)
    fixture.summary = CaptureSummary(
      duration: 1, averagePower: -70, pcm16Signal: signal.measurements())
    let coordinator = fixture.coordinator()
    await coordinator.start()
    let owner = try XCTUnwrap(coordinator.session)
    await coordinator.record()
    owner.stopRecording()
    XCTAssertFalse(coordinator.currentRecordingCanBeChecked)
    coordinator.check()
    XCTAssertNil(coordinator.currentResult)
    await coordinator.next()
    XCTAssertTrue(coordinator.session === owner)
    await coordinator.close()
  }

  func testBackgroundAndInterruptionInvalidateTheUnsubmittedResult() async throws {
    let fixture = try CACDemoMediaFixture()
    defer { fixture.removeDirectory() }
    let coordinator = fixture.coordinator()
    await coordinator.start()
    let owner = try XCTUnwrap(coordinator.session)
    try await recordAndCheck(coordinator)
    XCTAssertNotNil(coordinator.currentResult)

    coordinator.forwardScene(.background)
    XCTAssertNil(coordinator.result)
    await waitUntil { owner.phase == .ready && owner.tries.isEmpty }
    coordinator.forwardScene(.active)
    XCTAssertEqual(owner.phase, .ready, "Returning never resumes media")
    XCTAssertEqual(fixture.driver.recordings, 1)
    await coordinator.next()
    XCTAssertTrue(coordinator.session === owner)

    try await recordAndCheck(coordinator)
    coordinator.audioWasInterrupted()
    XCTAssertNil(coordinator.currentResult)
    await waitUntil { owner.phase == .ready }
    await coordinator.next()
    XCTAssertTrue(coordinator.session === owner)
    await coordinator.close()
  }

  // MARK: Journey

  func testCompleteJourneyChoosesRPracticeAndRechecksRabbit() async throws {
    let fixture = try CACDemoMediaFixture()
    defer { fixture.removeDirectory() }
    let coordinator = fixture.coordinator()
    await coordinator.start()
    var owners: [DirectPracticeSession] = []

    for expected in CACScript.soundCheck {
      XCTAssertEqual(coordinator.current?.id, expected.id)
      owners.append(try XCTUnwrap(coordinator.session))
      try await recordAndCheck(coordinator)
      XCTAssertEqual(coordinator.currentResult?.outcome, expected.outcome)
      await coordinator.next()
    }
    XCTAssertEqual(coordinator.stage, .plan)
    XCTAssertNil(coordinator.session)
    let plan = try XCTUnwrap(coordinator.plan)
    XCTAssertEqual(plan.letter, "R")
    XCTAssertEqual(plan.focus.word, "rabbit")
    XCTAssertEqual(plan.practice.map(\.word), ["rain", "ring"])

    await coordinator.startPractice()
    for expected in plan.practice + [plan.recheck] {
      XCTAssertEqual(coordinator.stage, .word)
      XCTAssertEqual(coordinator.current?.id, expected.id)
      let owner = try XCTUnwrap(coordinator.session)
      XCTAssertEqual(owner.sound.id, "r")
      XCTAssertEqual(owner.sound.prompts, [expected.prompt])
      owners.append(owner)
      try await recordAndCheck(coordinator)
      XCTAssertEqual(coordinator.currentResult?.outcome, .clear)
      await coordinator.next()
    }
    XCTAssertEqual(coordinator.stage, .recap)
    XCTAssertEqual(
      coordinator.submitted.map(\.outcome),
      [.clear, .needsPractice, .clear, .clear, .clear, .clear])
    XCTAssertTrue(coordinator.submitted.allSatisfy { $0.source == .scripted })
    XCTAssertEqual(coordinator.submittedResult(for: plan.focus)?.outcome, .needsPractice)
    XCTAssertEqual(coordinator.submittedResult(for: plan.recheck)?.outcome, .clear)
    XCTAssertEqual(fixture.sessionsCreated, 6)
    XCTAssertEqual(fixture.driver.recordings, 6)
    XCTAssertTrue(owners.allSatisfy { $0.hasFullyEndedCleanup })
    XCTAssertTrue(fixture.files.protectedURLs.isEmpty)

    await coordinator.practiceAgain()
    XCTAssertEqual(coordinator.current?.id, plan.practice[0].id)
    XCTAssertEqual(coordinator.submitted.count, 3, "Practice again keeps only the sound check")
    await coordinator.close()
    XCTAssertEqual(coordinator.stage, .plan, "Ending practice keeps the sound check and plan")
    XCTAssertNil(coordinator.session)
    XCTAssertEqual(coordinator.submitted.count, 3)
    XCTAssertEqual(coordinator.plan, plan)
    XCTAssertFalse(coordinator.finished, "Root exit returns home")

    await coordinator.start()
    XCTAssertEqual(coordinator.current?.id, CACScript.soundCheck[0].id)
    XCTAssertTrue(coordinator.submitted.isEmpty, "A new sound check replaces earlier results")
    XCTAssertNil(coordinator.plan)
    await coordinator.close()
    XCTAssertEqual(coordinator.stage, .welcome)
    XCTAssertNil(coordinator.session)
    XCTAssertTrue(coordinator.submitted.isEmpty)
    XCTAssertEqual(fixture.driver.recordings, 6, "The home starts no media")
  }

  func testModalCloseFinishesWithoutMedia() async {
    let coordinator = CACDemoCoordinator(
      placement: .modal,
      makeSession: { _ in
        preconditionFailure("No media session is expected")
      })
    await coordinator.close()
    XCTAssertTrue(coordinator.finished)
    await coordinator.start()
    XCTAssertNil(coordinator.session)
  }

  // MARK: Ownership

  func testHeldCleanupKeepsOwnerAndRepeatedNextCannotLeaveFiles() async throws {
    let fixture = try CACDemoMediaFixture()
    defer { fixture.removeDirectory() }
    let coordinator = fixture.coordinator()
    await coordinator.start()
    let owner = try XCTUnwrap(coordinator.session)
    try await recordAndCheck(coordinator)
    let result = try XCTUnwrap(coordinator.currentResult)
    fixture.failRemoval = true

    await coordinator.next()
    XCTAssertTrue(coordinator.session === owner)
    XCTAssertEqual(coordinator.pendingDeparture, .advance(result))
    XCTAssertFalse(owner.hasFullyEndedCleanup)
    XCTAssertFalse(fixture.files.pendingCleanupOwners.isEmpty)
    let attempts = fixture.removalAttempts
    await coordinator.next()
    XCTAssertEqual(fixture.removalAttempts, attempts, "Repeated Next never re-ends the owner")
    // Explicit recovery that still fails keeps the exact owner and its held departure.
    await coordinator.retryHeldDeparture()
    XCTAssertNotEqual(owner.phase, .ended)
    XCTAssertTrue(coordinator.session === owner)
    XCTAssertEqual(coordinator.pendingDeparture, .advance(result))
    XCTAssertEqual(fixture.sessionsCreated, 1)

    fixture.failRemoval = false
    await coordinator.retryHeldDeparture()
    XCTAssertTrue(owner.hasFullyEndedCleanup)
    XCTAssertTrue(fixture.files.pendingCleanupOwners.isEmpty)
    XCTAssertEqual(fixture.sessionsCreated, 2)
    XCTAssertEqual(coordinator.current?.id, CACScript.soundCheck[1].id)
    XCTAssertEqual(coordinator.submitted, [result])
    await coordinator.close()
  }

  func testFailedCleanupRetryDoesNotAuthorizeAnotherClose() async throws {
    let fixture = try CACDemoMediaFixture()
    defer { fixture.removeDirectory() }
    let coordinator = fixture.coordinator()
    await coordinator.start()
    let owner = try XCTUnwrap(coordinator.session)
    try await recordAndCheck(coordinator)
    fixture.failRemoval = true

    await coordinator.close()
    XCTAssertTrue(coordinator.session === owner)
    XCTAssertEqual(coordinator.pendingDeparture, .close)
    await coordinator.retryHeldDeparture()
    XCTAssertTrue(coordinator.session === owner, "Retry must not become a second Close")
    XCTAssertNotEqual(owner.phase, .ended)
    XCTAssertEqual(coordinator.pendingDeparture, .close)
    XCTAssertEqual(fixture.sessionsCreated, 1)

    // A separate, explicit Exit may use the session's existing file-recovery escape.
    await coordinator.close()
    XCTAssertEqual(coordinator.stage, .welcome)
    XCTAssertNil(coordinator.session)
    XCTAssertFalse(fixture.files.pendingCleanupOwners.isEmpty)
    fixture.failRemoval = false
    for id in fixture.files.pendingCleanupOwners {
      XCTAssertTrue(fixture.files.retryCleanup(owner: id))
    }
  }

  func testExitMayLeaveProcessRecoveryButNeverOpensASuccessorOverIt() async throws {
    let fixture = try CACDemoMediaFixture()
    defer { fixture.removeDirectory() }
    let coordinator = fixture.coordinator()
    await coordinator.start()
    let owner = try XCTUnwrap(coordinator.session)
    try await recordAndCheck(coordinator)
    fixture.failRemoval = true
    await coordinator.next()
    XCTAssertNotNil(coordinator.pendingDeparture)
    await coordinator.close()
    XCTAssertEqual(coordinator.stage, .welcome)
    XCTAssertNil(coordinator.session)
    XCTAssertTrue(coordinator.submitted.isEmpty, "A held result is never submitted on exit")
    XCTAssertFalse(owner.hasFullyEndedCleanup)
    XCTAssertFalse(fixture.files.pendingCleanupOwners.isEmpty)

    await coordinator.start()
    XCTAssertTrue(coordinator.startBlocked)
    XCTAssertNil(coordinator.session)
    XCTAssertEqual(fixture.sessionsCreated, 1)

    fixture.failRemoval = false
    for id in fixture.files.pendingCleanupOwners {
      XCTAssertTrue(fixture.files.retryCleanup(owner: id))
    }
    XCTAssertTrue(fixture.files.protectedURLs.isEmpty)
    await coordinator.start()
    XCTAssertFalse(coordinator.startBlocked)
    XCTAssertEqual(fixture.sessionsCreated, 2)
    XCTAssertEqual(coordinator.current?.id, CACScript.soundCheck[0].id)
    await coordinator.close()
  }

  func testEndingPracticeOverProcessRecoveryNeverRestartsPractice() async throws {
    let fixture = try CACDemoMediaFixture()
    defer { fixture.removeDirectory() }
    let coordinator = fixture.coordinator()
    await coordinator.start()
    for _ in CACScript.soundCheck {
      try await recordAndCheck(coordinator)
      await coordinator.next()
    }
    await coordinator.startPractice()
    try await recordAndCheck(coordinator)
    fixture.failRemoval = true
    await coordinator.next()
    XCTAssertNotNil(coordinator.pendingDeparture)
    await coordinator.close()
    XCTAssertEqual(coordinator.stage, .plan)
    XCTAssertNil(coordinator.session)
    XCTAssertFalse(fixture.files.pendingCleanupOwners.isEmpty)
    let created = fixture.sessionsCreated

    await coordinator.startPractice()
    XCTAssertTrue(coordinator.startBlocked)
    XCTAssertNil(coordinator.session)
    XCTAssertEqual(fixture.sessionsCreated, created)

    fixture.failRemoval = false
    for id in fixture.files.pendingCleanupOwners {
      XCTAssertTrue(fixture.files.retryCleanup(owner: id))
    }
    await coordinator.startPractice()
    XCTAssertFalse(coordinator.startBlocked)
    XCTAssertEqual(fixture.sessionsCreated, created + 1)
    XCTAssertEqual(coordinator.current?.part, .practice)
    await coordinator.close()
  }

  func testCloseDuringHeldEndWinsOverAdvance() async throws {
    let fixture = try CACDemoMediaFixture()
    defer { fixture.removeDirectory() }
    let recognizer = CACDemoHeldRuntime()
    let coordinator = fixture.coordinator(recognizer: recognizer)
    await coordinator.start()
    try await recordAndCheck(coordinator)
    let leaving = Task { await coordinator.next() }
    await recognizer.waitForRelease()
    XCTAssertTrue(coordinator.isLeaving)
    await coordinator.close()
    XCTAssertEqual(coordinator.pendingDeparture, .close, "Close is latched, not dropped")
    recognizer.finishRelease()
    await leaving.value
    XCTAssertEqual(coordinator.stage, .welcome)
    XCTAssertNil(coordinator.session)
    XCTAssertNil(coordinator.pendingDeparture)
    XCTAssertTrue(coordinator.submitted.isEmpty)
    XCTAssertEqual(fixture.sessionsCreated, 1, "No successor opens once Close wins")
    XCTAssertEqual(fixture.driver.recordings, 1)
  }

  // MARK: Inline face preview (generated camera; real audio ownership)

  func testPreviewIsLiveDuringCaptureAndReviewAndKeepsOwnerAcrossWords() async throws {
    let fixture = try CACDemoMediaFixture()
    defer { fixture.removeDirectory() }
    fixture.faceHardware.isSupported = true
    let coordinator = fixture.coordinator()
    XCTAssertTrue(fixture.faceHardware.drivers.isEmpty, "Construction is inert")
    await coordinator.start()
    let cameraOwner = try XCTUnwrap(fixture.cameraLease.owner)
    for _ in 0..<2 {
      let audio = try XCTUnwrap(coordinator.session)
      await coordinator.record()
      XCTAssertEqual(audio.phase, .recording)
      XCTAssertTrue(coordinator.facePreview.hasCameraOwner)
      XCTAssertEqual(fixture.cameraLease.owner, cameraOwner)
      audio.stopRecording()
      XCTAssertTrue(coordinator.facePreview.hasCameraOwner)
      coordinator.check()
      await coordinator.next()
      XCTAssertEqual(fixture.cameraLease.owner, cameraOwner)
    }
    XCTAssertEqual(fixture.faceHardware.drivers.count, 1)
    try await recordAndCheck(coordinator)
    await coordinator.next()
    XCTAssertEqual(coordinator.stage, .plan)
    XCTAssertNil(fixture.cameraLease.owner)
    XCTAssertNil(coordinator.session)
    await coordinator.startPractice()
    XCTAssertEqual(fixture.faceHardware.drivers.count, 2)
    let practiceCamera = try XCTUnwrap(fixture.cameraLease.owner)
    for index in 0..<3 {
      try await recordAndCheck(coordinator)
      XCTAssertEqual(fixture.cameraLease.owner, practiceCamera)
      await coordinator.next()
      if index < 2 { XCTAssertEqual(fixture.cameraLease.owner, practiceCamera) }
    }
    XCTAssertEqual(coordinator.stage, .recap)
    XCTAssertNil(fixture.cameraLease.owner)
    await coordinator.practiceAgain()
    let audio = try XCTUnwrap(coordinator.session)
    await coordinator.record()
    await coordinator.close()
    XCTAssertEqual(audio.phase, .ended)
    XCTAssertNil(fixture.cameraLease.owner)
    XCTAssertEqual(coordinator.stage, .plan, "Ending practice mid-recording returns to the plan")
  }

  func testCameraPermissionPreservesReadyAudioAndBlocksRecordingUntilResolved() async throws {
    let fixture = try CACDemoMediaFixture()
    defer { fixture.removeDirectory() }
    fixture.faceHardware.isSupported = true
    fixture.faceHardware.permission = .notDetermined
    let coordinator = fixture.coordinator()
    await coordinator.start()
    let owner = try XCTUnwrap(coordinator.session)
    XCTAssertTrue(coordinator.recordingControlsBlockedForCamera)
    coordinator.forwardScene(.inactive)
    XCTAssertEqual(owner.phase, .ready)
    await coordinator.record()
    XCTAssertEqual(fixture.driver.recordings, 0)
    fixture.faceHardware.completePermission(true)
    XCTAssertEqual(coordinator.facePreview.phase, .awaitingActive)
    coordinator.forwardScene(.active)
    await coordinator.record()
    XCTAssertEqual(owner.phase, .recording)
    XCTAssertTrue(coordinator.facePreview.hasCameraOwner)
    await coordinator.close()
  }

  func testHideCancelsCameraPermissionAndDeniedCameraAllowsAudioOnly() async throws {
    for denied in [false, true] {
      let fixture = try CACDemoMediaFixture()
      defer { fixture.removeDirectory() }
      fixture.faceHardware.isSupported = true
      fixture.faceHardware.permission = .notDetermined
      let coordinator = fixture.coordinator()
      await coordinator.start()
      if denied {
        fixture.faceHardware.completePermission(false)
      } else {
        coordinator.hideFacePreview()
        fixture.faceHardware.completePermission(true)
        XCTAssertFalse(coordinator.facePreviewEnabled)
      }
      XCTAssertFalse(coordinator.recordingControlsBlockedForCamera)
      await coordinator.record()
      XCTAssertEqual(coordinator.session?.phase, .recording)
      XCTAssertTrue(fixture.faceHardware.drivers.isEmpty)
      await coordinator.close()
    }
  }

  func testMicrophonePermissionRestoresPreviewOnlyForSameExplicitRecording() async throws {
    for (background, activeBeforeGrant) in [(false, false), (false, true), (true, false)] {
      let fixture = try CACDemoMediaFixture()
      defer { fixture.removeDirectory() }
      fixture.faceHardware.isSupported = true
      let coordinator = fixture.coordinator()
      await coordinator.start()
      let entered = expectation(description: "Microphone permission requested")
      var grant: CheckedContinuation<Bool, Never>?
      fixture.microphonePermission = {
        coordinator.forwardScene(.inactive)
        return await withCheckedContinuation {
          grant = $0
          entered.fulfill()
        }
      }
      let record = Task { await coordinator.record() }
      let wait = await XCTWaiter.fulfillment(of: [entered], timeout: 2)
      XCTAssertEqual(wait, .completed)
      XCTAssertNil(fixture.cameraLease.owner)
      if background { coordinator.forwardScene(.background) }
      if activeBeforeGrant { coordinator.forwardScene(.active) }
      grant?.resume(returning: true)
      await record.value
      coordinator.forwardScene(.active)
      if background {
        XCTAssertNotEqual(coordinator.session?.phase, .recording)
        XCTAssertNil(fixture.cameraLease.owner)
        XCTAssertEqual(fixture.faceHardware.drivers.count, 1)
      } else {
        XCTAssertEqual(coordinator.session?.phase, .recording)
        XCTAssertNotNil(fixture.cameraLease.owner)
        XCTAssertEqual(fixture.faceHardware.drivers.count, 2)
      }
      await coordinator.close()
    }
  }

  func testFailedCameraTeardownHoldsDepartureButStillEndsAudioUntilExplicitRetry() async throws {
    for closing in [false, true] {
      let fixture = try CACDemoMediaFixture()
      defer { fixture.removeDirectory() }
      fixture.faceHardware.isSupported = true
      let coordinator = fixture.coordinator()
      await coordinator.start()
      let audio = try XCTUnwrap(coordinator.session)
      let camera = try XCTUnwrap(fixture.faceHardware.drivers.first)
      if closing {
        await coordinator.record()
        camera.stopFailures = 1
        await coordinator.close()
      } else {
        try await recordAndCheck(coordinator)
        camera.stopFailures = 1
        coordinator.hideFacePreview()
        await coordinator.next()
      }
      XCTAssertEqual(audio.phase, .ended)
      XCTAssertNotNil(coordinator.pendingDeparture)
      XCTAssertTrue(coordinator.cameraRecoveryBlocked)
      XCTAssertNotNil(fixture.cameraLease.owner)
      XCTAssertEqual(camera.stops, 1)
      if closing { await coordinator.close() } else { await coordinator.next() }
      XCTAssertEqual(camera.stops, 1, "Ordinary repeated actions never retry camera cleanup")
      await coordinator.retryHeldDeparture()
      XCTAssertNil(coordinator.pendingDeparture)
      XCTAssertNil(fixture.cameraLease.owner)
      XCTAssertEqual(camera.stops, 2)
      XCTAssertEqual(coordinator.stage, closing ? .welcome : .word)
      await coordinator.close()
    }
  }

  func testCameraPermissionCloseAndLateCallbackCannotOpenSuccessor() async throws {
    let fixture = try CACDemoMediaFixture()
    defer { fixture.removeDirectory() }
    fixture.faceHardware.isSupported = true
    fixture.faceHardware.permission = .notDetermined
    let coordinator = fixture.coordinator()
    await coordinator.start()
    let owner = try XCTUnwrap(coordinator.session)
    await coordinator.close()
    fixture.faceHardware.completePermission(true)
    coordinator.forwardScene(.active)
    XCTAssertEqual(coordinator.stage, .welcome)
    XCTAssertEqual(owner.phase, .ended)
    XCTAssertTrue(fixture.faceHardware.drivers.isEmpty)
    XCTAssertNil(fixture.cameraLease.owner)
  }

  func testPreviewReentrantHideDuringRecordRestartPreventsStaleCameraIntent() async throws {
    let fixture = try CACDemoMediaFixture()
    defer { fixture.removeDirectory() }
    fixture.faceHardware.isSupported = true
    let coordinator = fixture.coordinator()
    await coordinator.start()
    XCTAssertTrue(coordinator.facePreview.stopForPracticeTransition())
    let subscription = coordinator.facePreview.statePublisher.dropFirst().sink { state in
      if case .live = state.phase { coordinator.hideFacePreview() }
    }
    await coordinator.record()
    XCTAssertNil(fixture.cameraLease.owner)
    XCTAssertFalse(coordinator.facePreviewEnabled)
    XCTAssertEqual(fixture.driver.recordings, 0, "Hide revoked this in-flight Record handoff")
    await coordinator.close()
    withExtendedLifetime(subscription) {}
  }

  func testQueuedCloseDuringAudioReleaseAlsoStopsCameraAndWinsOverNext() async throws {
    let fixture = try CACDemoMediaFixture()
    defer { fixture.removeDirectory() }
    fixture.faceHardware.isSupported = true
    let recognizer = CACDemoHeldRuntime()
    let coordinator = fixture.coordinator(recognizer: recognizer)
    await coordinator.start()
    try await recordAndCheck(coordinator)
    let leaving = Task { await coordinator.next() }
    await recognizer.waitForRelease()
    XCTAssertNotNil(fixture.cameraLease.owner)
    await coordinator.close()
    XCTAssertNil(fixture.cameraLease.owner)
    recognizer.finishRelease()
    await leaving.value
    XCTAssertEqual(coordinator.stage, .welcome)
    XCTAssertNil(coordinator.session)
    XCTAssertEqual(fixture.sessionsCreated, 1)
    XCTAssertTrue(coordinator.submitted.isEmpty)
  }

  func testMicrophoneGrantAfterExitCannotRestoreCameraOrRecord() async throws {
    let fixture = try CACDemoMediaFixture()
    defer { fixture.removeDirectory() }
    fixture.faceHardware.isSupported = true
    let coordinator = fixture.coordinator()
    await coordinator.start()
    let entered = expectation(description: "Pending microphone grant")
    var grant: CheckedContinuation<Bool, Never>?
    fixture.microphonePermission = {
      coordinator.forwardScene(.inactive)
      return await withCheckedContinuation {
        grant = $0
        entered.fulfill()
      }
    }
    let record = Task { await coordinator.record() }
    let wait = await XCTWaiter.fulfillment(of: [entered], timeout: 2)
    XCTAssertEqual(wait, .completed)
    await coordinator.close()
    grant?.resume(returning: true)
    await record.value
    coordinator.forwardScene(.active)
    XCTAssertEqual(coordinator.stage, .welcome)
    XCTAssertEqual(fixture.driver.recordings, 0)
    XCTAssertEqual(fixture.faceHardware.drivers.count, 1)
    XCTAssertNil(fixture.cameraLease.owner)
  }

  func testCameraCleanupFailureDuringMicrophoneAlertRevokesCapture() async throws {
    let fixture = try CACDemoMediaFixture()
    defer { fixture.removeDirectory() }
    fixture.faceHardware.isSupported = true
    let coordinator = fixture.coordinator()
    await coordinator.start()
    let camera = try XCTUnwrap(fixture.faceHardware.drivers.first)
    camera.stopFailures = 1
    fixture.microphonePermission = {
      coordinator.forwardScene(.inactive)
      return true
    }
    await coordinator.record()
    coordinator.forwardScene(.active)
    XCTAssertEqual(fixture.driver.recordings, 0)
    XCTAssertTrue(coordinator.cameraRecoveryBlocked)
    XCTAssertEqual(camera.stops, 1)
    coordinator.retryFacePreviewCleanup()
    XCTAssertNil(fixture.cameraLease.owner)
    await coordinator.close()
  }

  func testUnexpectedDisappearanceKeepsReachableCameraRecovery() async throws {
    let fixture = try CACDemoMediaFixture()
    defer { fixture.removeDirectory() }
    fixture.faceHardware.isSupported = true
    let coordinator = fixture.coordinator()
    await coordinator.start()
    fixture.faceHardware.drivers.first?.stopFailures = 1
    coordinator.viewDisappeared()
    XCTAssertTrue(coordinator.cameraRecoveryBlocked)
    coordinator.retryFacePreviewCleanup()
    XCTAssertFalse(coordinator.cameraRecoveryBlocked)
    XCTAssertNil(fixture.cameraLease.owner)
    await coordinator.close()
  }

  func testHideDuringRecordingLeavesMicrophoneRunningAndShowCannotPromptOverTake() async throws {
    let fixture = try CACDemoMediaFixture()
    defer { fixture.removeDirectory() }
    fixture.faceHardware.isSupported = true
    let coordinator = fixture.coordinator()
    await coordinator.start()
    let audio = try XCTUnwrap(coordinator.session)
    await coordinator.record()
    coordinator.hideFacePreview()
    XCTAssertEqual(audio.phase, .recording)
    XCTAssertNil(fixture.cameraLease.owner)
    XCTAssertFalse(coordinator.canShowFacePreview)
    fixture.faceHardware.permission = .notDetermined
    coordinator.showFacePreview()
    XCTAssertEqual(fixture.faceHardware.permissionRequests, 0)
    audio.stopRecording()
    XCTAssertFalse(coordinator.canShowFacePreview)
    coordinator.showFacePreview()
    XCTAssertEqual(fixture.faceHardware.permissionRequests, 0)
    coordinator.check()
    await coordinator.next()
    XCTAssertFalse(coordinator.facePreviewEnabled, "Hide persists across word changes")
    XCTAssertTrue(coordinator.canShowFacePreview)
    coordinator.showFacePreview()
    XCTAssertEqual(fixture.faceHardware.permissionRequests, 1)
    await coordinator.close()
  }

  // MARK: Helpers

  private func recordAndCheck(_ coordinator: CACDemoCoordinator) async throws {
    let owner = try XCTUnwrap(coordinator.session)
    await coordinator.record()
    XCTAssertEqual(owner.phase, .recording)
    owner.stopRecording()
    coordinator.check()
    XCTAssertNotNil(coordinator.currentResult)
  }

  private func waitUntil(_ condition: () -> Bool) async {
    for _ in 0..<200 where !condition() { await Task.yield() }
    XCTAssertTrue(condition())
  }
}

@MainActor
private final class CACDemoMediaFixture {
  enum Failure: Error { case removal }
  let directory: URL
  let files = ProcessAudioFileOwnership()
  let hardware = AudioHardwareOwnership()
  let driver = CACDemoCaptureDriver()
  var failRemoval = false
  var permissionGranted = true
  var summary = CaptureSummary(duration: 1, averagePower: -20)
  var removalAttempts = 0
  var sessionsCreated = 0
  let cameraLease = ProcessCameraLease()
  let faceHardware = CACInlineFaceHardware()
  lazy var faceModel = FaceGuideModel(
    hardware: faceHardware, recovery: FaceGuideRecovery(cameraLease: cameraLease))
  var microphonePermission: (@MainActor () async -> Bool)?

  init() throws {
    directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
  }
  func removeDirectory() { try? FileManager.default.removeItem(at: directory) }

  func coordinator(recognizer: (any LocalWordRecognizing)? = nil) -> CACDemoCoordinator {
    CACDemoCoordinator(
      placement: .root, files: files, facePreview: faceModel,
      makeSession: {
        self.makeSession($0, recognizer: recognizer)
      })
  }

  func makeSession(_ sound: PracticeSound, recognizer: (any LocalWordRecognizing)? = nil)
    -> DirectPracticeSession
  {
    sessionsCreated += 1
    let store = TemporaryRecordingStore(directory: directory)
    let capturer = SystemAudioCapturer(
      recordingStore: store, fileOwnership: files, hardwareOwnership: hardware,
      driverFactory: { self.driver },
      summaryReader: { _ in self.summary },
      removeFile: { url in
        self.removalAttempts += 1
        if self.failRemoval { throw Failure.removal }
        try store.removeRecordingIfPresent(at: url)
      })
    return DirectPracticeSession(
      sound: sound, capturer: CACDemoPermissionCapturer(capturer, fixture: self),
      player: CACDemoIdlePlayer(), wordRecognizer: recognizer ?? CACDemoNoWordCheck(),
      cleanupHardwareOwnership: hardware, cleanupFileOwnership: files)
  }
}

/// Permission and hardware stay inert; production capture ownership/removal remain real.
@MainActor
private final class CACDemoPermissionCapturer: AudioCapturing {
  let underlying: SystemAudioCapturer
  unowned let fixture: CACDemoMediaFixture
  init(_ underlying: SystemAudioCapturer, fixture: CACDemoMediaFixture) {
    self.underlying = underlying
    self.fixture = fixture
  }
  var cleanupState: CaptureCleanupState { underlying.cleanupState }
  var cleanupStatePublisher: AnyPublisher<CaptureCleanupState, Never> {
    underlying.cleanupStatePublisher
  }
  func requestPermission() async -> Bool {
    if let permission = fixture.microphonePermission { return await permission() }
    return fixture.permissionGranted
  }
  func start(onFinish: @escaping @MainActor (Bool) async -> Void) throws {
    try underlying.start(onFinish: onFinish)
  }
  func stop() throws -> CapturedRecording { try underlying.stop() }
  func cancel() throws { try underlying.cancel() }
  func discard(_ recording: CapturedRecording) throws { try underlying.discard(recording) }
  func retryCleanup(operationID: UUID) -> CaptureCleanupReceipt {
    underlying.retryCleanup(operationID: operationID)
  }
  func completedFileCleanup(operationID: UUID) -> CaptureCleanupReceipt? {
    underlying.completedFileCleanup(operationID: operationID)
  }
}

@MainActor
private final class CACDemoCaptureDriver: CaptureHardwareDriver {
  var recordings = 0
  var stops = 0
  func configureActivate() throws {}
  func createRecorder(
    url: URL, recorderID: UUID,
    onFinish: @escaping @MainActor @Sendable (UUID, Bool) -> Void
  ) throws {
    try Data([1, 2, 3]).write(to: url)
  }
  func prepare() throws -> Bool { true }
  func record() throws -> Bool {
    recordings += 1
    return true
  }
  func stop() throws { stops += 1 }
  func detachRelease() throws {}
  func deactivate() throws {}
}

@MainActor
private final class CACDemoIdlePlayer: AcknowledgedPracticeAudioPlaying {
  var state: PracticePlaybackRuntimeState { .idle }
  var statePublisher: AnyPublisher<PracticePlaybackRuntimeState, Never> {
    Just(.idle).eraseToAnyPublisher()
  }
  func play(
    id: UUID, url: URL,
    onFinish: @escaping @MainActor (PracticePlaybackOperation, Bool) -> Void
  ) async throws {
    XCTFail("These coordinator tests never request playback")
  }
  func requestStop(id: UUID) -> PracticePlaybackCleanup? { nil }
  func retryCleanup(id: UUID) -> PracticePlaybackCleanup? { nil }
}

@MainActor
private final class CACDemoHeldRuntime: LocalWordRecognizing, LocalWordRuntimeReleasing {
  private var release: CheckedContinuation<Bool, Never>?
  private var started: CheckedContinuation<Void, Never>?
  func check(request: LocalWordRecognitionRequest) async -> LocalWordRecognitionReceipt {
    .init(request: request, status: .unavailable, cleanupConfirmed: true)
  }
  func cancel(operationID: UUID) {}
  func releaseWordRuntime() async -> Bool {
    await withCheckedContinuation { continuation in
      release = continuation
      started?.resume()
      started = nil
    }
  }
  func waitForRelease() async {
    if release != nil { return }
    await withCheckedContinuation { started = $0 }
  }
  func finishRelease() {
    release?.resume(returning: true)
    release = nil
  }
}

/// Camera-free face service. Only the capture fixture writes a temporary audio ownership file.
@MainActor
private final class CACInlineFaceHardware: FaceGuideHardware {
  var isSupported = false
  var permission: FaceGuidePermission = .authorized
  var permissionRequests = 0
  var drivers: [CACInlineFaceDriver] = []
  private var completion: (@MainActor (Bool) -> Void)?
  func requestPermission(completion: @escaping @MainActor (Bool) -> Void) {
    permissionRequests += 1
    self.completion = completion
  }
  func completePermission(_ granted: Bool) {
    permission = granted ? .authorized : .denied
    completion?(granted)
  }
  func makeDriver() -> any FaceGuideDriver {
    let driver = CACInlineFaceDriver()
    drivers.append(driver)
    return driver
  }
}

@MainActor
private final class CACInlineFaceDriver: FaceGuideDriver {
  private enum Failure: Error { case stop }
  var surface: UIView? { nil }
  var stopFailures = 0
  var stops = 0
  func start(events: @escaping @MainActor (FaceGuideEvent) -> Void) throws {}
  func stop() throws {
    stops += 1
    if stopFailures > 0 {
      stopFailures -= 1
      throw Failure.stop
    }
  }
}
