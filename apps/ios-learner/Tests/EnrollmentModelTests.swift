import CadenceContracts
@preconcurrency import Combine
import Foundation
import XCTest

@testable import CadenceLearner

@MainActor
final class EnrollmentModelTests: XCTestCase {
  func testHardwareBlockedDisconnectRetainsSessionCredentialAndExactProducer() async throws {
    let sessions = try EnrollmentCaptureSessions()
    defer { sessions.dispose() }
    let store = InMemoryEnrollmentStore()
    let client = FakePracticeClient(assignment: .localPreview)
    let model = EnrollmentModel(store: store, practiceSessionFactory: sessions.makeSession) { _ in
      client
    }
    model.serverAddress = "https://practice.example.test"
    model.deviceToken = String(repeating: "x", count: 43)
    await model.connect()
    let original = try XCTUnwrap(model.practiceSession)
    let originalData = store.data
    let driver = try XCTUnwrap(sessions.drivers.last)
    await original.startRecording()
    driver.failDeactivate = true
    await original.stopRecording()
    let id = try XCTUnwrap(original.captureCleanupState.hardwareBlockedOperationID)

    XCTAssertFalse(model.disconnect())
    XCTAssertFalse(model.disconnect())
    XCTAssertTrue(model.practiceSession === original)
    XCTAssertEqual(store.data, originalData)
    XCTAssertEqual(store.removals, 0)
    XCTAssertEqual(store.saves, 1)
    XCTAssertEqual(sessions.hardware.currentLease?.operationID, id)
    XCTAssertTrue(FileManager.default.fileExists(atPath: try XCTUnwrap(driver.url).path))
    XCTAssertEqual(model.errorMessage, original.captureCleanupDetail)
    original.retryCaptureCleanup(operationID: UUID())
    XCTAssertEqual(driver.deactivations, 1)
    driver.failDeactivate = false
    original.retryCaptureCleanup(operationID: id)
    XCTAssertTrue(model.disconnect())
    XCTAssertNil(model.practiceSession)
    XCTAssertNil(store.data)
    XCTAssertEqual(store.removals, 1)
    XCTAssertNil(sessions.hardware.currentLease)
    XCTAssertTrue(sessions.files.protectedURLs.isEmpty)
  }

  func testRetryLoadCannotFetchOrExpireCredentialsWhileHardwareIsBlocked() async throws {
    let sessions = try EnrollmentCaptureSessions()
    defer { sessions.dispose() }
    let store = InMemoryEnrollmentStore()
    let client = FakePracticeClient(assignment: .localPreview)
    let model = EnrollmentModel(store: store, practiceSessionFactory: sessions.makeSession) { _ in
      client
    }
    model.serverAddress = "https://practice.example.test"
    model.deviceToken = String(repeating: "x", count: 43)
    await model.connect()
    let original = try XCTUnwrap(model.practiceSession)
    let data = store.data
    let driver = try XCTUnwrap(sessions.drivers.last)
    await original.startRecording()
    driver.failDeactivate = true
    await original.stopRecording()
    let id = try XCTUnwrap(original.captureCleanupRetryIDs.first)
    await client.setError(.sessionExpired)
    await model.retryAssignmentLoad()
    await model.retryAssignmentLoad()
    let blockedFetches = await client.fetchCount()
    XCTAssertEqual(blockedFetches, 1)
    XCTAssertEqual(store.data, data)
    XCTAssertEqual(store.removals, 0)
    XCTAssertTrue(model.practiceSession === original)
    XCTAssertEqual(sessions.captures.count, 1)

    driver.failDeactivate = false
    original.retryCaptureCleanup(operationID: id)
    await model.retryAssignmentLoad()
    let finalFetches = await client.fetchCount()
    XCTAssertEqual(finalFetches, 2)
    XCTAssertEqual(model.phase, .disconnected)
    XCTAssertNil(store.data)
    XCTAssertEqual(store.removals, 1)
    XCTAssertNil(model.practiceSession)
  }

  func testBlockedConnectCannotOverwritePendingCredentialForLaterRetry() async throws {
    let sessions = try EnrollmentCaptureSessions()
    defer { sessions.dispose() }
    let store = InMemoryEnrollmentStore()
    let client = FakePracticeClient(assignment: .localPreview)
    var requestedURLs: [URL] = []
    let model = EnrollmentModel(store: store, practiceSessionFactory: sessions.makeSession) {
      requestedURLs.append($0)
      return client
    }
    model.serverAddress = "https://practice.example.test"
    model.deviceToken = String(repeating: "x", count: 43)
    await model.connect()
    let original = try XCTUnwrap(model.practiceSession)
    let saved = store.data
    let driver = try XCTUnwrap(sessions.drivers.last)
    await original.startRecording()
    driver.failDeactivate = true
    await original.stopRecording()
    model.serverAddress = "https://replacement.example.test"
    model.deviceToken = String(repeating: "y", count: 43)
    await model.connect()
    XCTAssertEqual(requestedURLs.map(\.absoluteString), ["https://practice.example.test"])
    XCTAssertEqual(store.data, saved)
    XCTAssertTrue(model.practiceSession === original)
    driver.failDeactivate = false
    original.retryCaptureCleanup(operationID: try XCTUnwrap(original.captureCleanupRetryIDs.first))
    await model.retryAssignmentLoad()
    let tokens = await client.fetchedTokens()
    XCTAssertEqual(tokens, [String(repeating: "x", count: 43), String(repeating: "x", count: 43)])
    XCTAssertEqual(
      requestedURLs.map(\.absoluteString),
      ["https://practice.example.test", "https://practice.example.test"])
    XCTAssertEqual(store.data, saved)
    XCTAssertEqual(store.saves, 1)
    XCTAssertFalse(model.practiceSession === original)
    XCTAssertEqual(sessions.captures.count, 2)
  }

  func testFileOnlyWarningPermitsOnlySecondExplicitDepartureNeverReplacementRetry() async throws {
    let sessions = try EnrollmentCaptureSessions()
    defer { sessions.dispose() }
    let store = InMemoryEnrollmentStore()
    let client = FakePracticeClient(assignment: .localPreview)
    let model = EnrollmentModel(store: store, practiceSessionFactory: sessions.makeSession) { _ in
      client
    }
    model.serverAddress = "https://practice.example.test"
    model.deviceToken = String(repeating: "x", count: 43)
    await model.connect()
    var original: PracticeSessionModel? = try XCTUnwrap(model.practiceSession)
    let saved = store.data
    let control = try XCTUnwrap(sessions.controls.last)
    let driver = try XCTUnwrap(sessions.drivers.last)
    await original!.startRecording()
    control.failRemoval = true
    await original!.stopRecording()
    let id = try XCTUnwrap(original!.captureCleanupState.fileBlockedOwnerIDs.first)
    let url = try XCTUnwrap(driver.url)
    XCTAssertNil(sessions.hardware.currentLease)
    XCTAssertTrue(sessions.files.pendingCleanupOwners.contains(id))
    await model.retryAssignmentLoad()
    await model.retryAssignmentLoad()
    model.serverAddress = "https://replacement.example.test"
    model.deviceToken = String(repeating: "y", count: 43)
    await model.connect()
    let fetches = await client.fetchCount()
    XCTAssertEqual(fetches, 1)
    XCTAssertEqual(control.removals, 1)
    XCTAssertEqual(store.data, saved)
    XCTAssertTrue(model.practiceSession === original)
    XCTAssertFalse(model.disconnect())
    XCTAssertEqual(store.removals, 0)
    XCTAssertTrue(model.disconnect())
    XCTAssertEqual(store.removals, 1)
    XCTAssertNil(model.practiceSession)
    XCTAssertTrue(FileManager.default.fileExists(atPath: url.path))
    weak var oldVisit = original
    original = nil
    XCTAssertNil(oldVisit)
    control.failRemoval = false
    XCTAssertTrue(sessions.files.retryCleanup(owner: id))
    XCTAssertFalse(FileManager.default.fileExists(atPath: url.path))
    XCTAssertTrue(sessions.files.protectedURLs.isEmpty)
  }

  func testResolvedFileCleanupAllowsFreshFetchWithoutRevivingPreviousVisit() async throws {
    let sessions = try EnrollmentCaptureSessions()
    defer { sessions.dispose() }
    let store = InMemoryEnrollmentStore()
    let client = FakePracticeClient(assignment: .localPreview)
    let model = EnrollmentModel(store: store, practiceSessionFactory: sessions.makeSession) { _ in
      client
    }
    model.serverAddress = "https://practice.example.test"
    model.deviceToken = String(repeating: "x", count: 43)
    await model.connect()
    let original = try XCTUnwrap(model.practiceSession)
    let control = try XCTUnwrap(sessions.controls.last)
    await original.startRecording()
    control.failRemoval = true
    await original.stopRecording()
    let id = try XCTUnwrap(original.captureCleanupRetryIDs.first)
    await model.retryAssignmentLoad()
    XCTAssertTrue(model.practiceSession === original)
    control.failRemoval = false
    XCTAssertTrue(sessions.files.retryCleanup(owner: id))
    await model.retryAssignmentLoad()
    let fetches = await client.fetchCount()
    XCTAssertEqual(fetches, 2)
    XCTAssertFalse(model.practiceSession === original)
    XCTAssertEqual(model.phase, .ready)
    XCTAssertEqual(sessions.captures.count, 2)
    XCTAssertTrue(original.captureDisabledForVisit)
    original.tryAgain()
    await original.startRecording()
    XCTAssertEqual(control.factoryCalls, 1)
    XCTAssertEqual(original.currentRepetition, 1)
  }

  func testDisconnectRevokesPendingPermissionWithoutStartingItsProducer() async throws {
    let sessions = try EnrollmentCaptureSessions()
    defer { sessions.dispose() }
    let store = InMemoryEnrollmentStore()
    let client = FakePracticeClient(assignment: .localPreview)
    let model = EnrollmentModel(store: store, practiceSessionFactory: sessions.makeSession) { _ in
      client
    }
    model.serverAddress = "https://practice.example.test"
    model.deviceToken = String(repeating: "x", count: 43)
    await model.connect()
    let original = try XCTUnwrap(model.practiceSession)
    let capture = try XCTUnwrap(sessions.captures.last)
    let control = try XCTUnwrap(sessions.controls.last)
    capture.holdsPermission = true
    let starting = Task { await original.startRecording() }
    await waitForEnrollmentState { capture.permission != nil }
    XCTAssertTrue(model.disconnect())
    capture.grantPermission()
    await starting.value
    XCTAssertEqual(control.factoryCalls, 0)
    XCTAssertNil(model.practiceSession)
    XCTAssertEqual(model.phase, .disconnected)
    XCTAssertNil(store.data)
    XCTAssertNil(sessions.hardware.currentLease)
  }

  func testLateFetchCannotReplaceNewerBlockedCaptureOrSaveItsOldCredential() async throws {
    let sessions = try EnrollmentCaptureSessions()
    defer { sessions.dispose() }
    let store = InMemoryEnrollmentStore()
    let client = FakePracticeClient(assignment: .localPreview)
    let model = EnrollmentModel(store: store, practiceSessionFactory: sessions.makeSession) { _ in
      client
    }
    model.serverAddress = "https://practice.example.test"
    model.deviceToken = String(repeating: "x", count: 43)
    await model.connect()
    await client.holdNextFetch()
    let oldFetch = Task { await model.retryAssignmentLoad() }
    await waitForHeldEnrollmentFetch(client)
    model.serverAddress = "https://replacement.example.test"
    model.deviceToken = String(repeating: "y", count: 43)
    await model.connect()
    let newer = try XCTUnwrap(model.practiceSession)
    let saved = store.data
    let driver = try XCTUnwrap(sessions.drivers.last)
    await newer.startRecording()
    driver.failDeactivate = true
    await newer.stopRecording()
    XCTAssertFalse(model.disconnect())
    await client.finishHeldFetch(.success(.localPreview))
    await oldFetch.value
    XCTAssertTrue(model.practiceSession === newer)
    XCTAssertEqual(store.data, saved)
    XCTAssertEqual(store.saves, 2)
    XCTAssertEqual(store.removals, 0)
    XCTAssertEqual(sessions.captures.count, 2)
    let decoded = try JSONDecoder().decode(
      EnrollmentTestStoredRecord.self, from: XCTUnwrap(store.data))
    XCTAssertEqual(decoded.deviceToken, String(repeating: "y", count: 43))
    XCTAssertEqual(decoded.baseURL.absoluteString, "https://replacement.example.test")
  }

  func testLateExpiredFetchAfterDisconnectCannotRemoveCredentialsAgainOrSetError() async throws {
    let sessions = try EnrollmentCaptureSessions()
    defer { sessions.dispose() }
    let store = InMemoryEnrollmentStore()
    let client = FakePracticeClient(assignment: .localPreview)
    let model = EnrollmentModel(store: store, practiceSessionFactory: sessions.makeSession) { _ in
      client
    }
    model.serverAddress = "https://practice.example.test"
    model.deviceToken = String(repeating: "x", count: 43)
    await model.connect()
    await client.holdNextFetch()
    let oldFetch = Task { await model.retryAssignmentLoad() }
    await waitForHeldEnrollmentFetch(client)
    XCTAssertTrue(model.disconnect())
    await client.finishHeldFetch(.failure(LearnerAttemptAPIError.sessionExpired))
    await oldFetch.value
    XCTAssertEqual(model.phase, .disconnected)
    XCTAssertNil(model.practiceSession)
    XCTAssertNil(model.errorMessage)
    XCTAssertEqual(store.removals, 1)
    XCTAssertEqual(store.saves, 1)
  }

  func testCredentialRemovalFailureKeepsAuthorizedClosedSessionUntilExplicitRetry() async throws {
    let sessions = try EnrollmentCaptureSessions()
    defer { sessions.dispose() }
    let store = InMemoryEnrollmentStore()
    let client = FakePracticeClient(assignment: .localPreview)
    let model = EnrollmentModel(store: store, practiceSessionFactory: sessions.makeSession) { _ in
      client
    }
    model.serverAddress = "https://practice.example.test"
    model.deviceToken = String(repeating: "x", count: 43)
    await model.connect()
    let original = try XCTUnwrap(model.practiceSession)
    let saved = store.data
    store.failRemove = true
    XCTAssertFalse(model.disconnect())
    XCTAssertTrue(model.practiceSession === original)
    XCTAssertEqual(store.data, saved)
    XCTAssertNotNil(model.errorMessage)
    XCTAssertEqual(model.departureError, model.errorMessage)
    XCTAssertNotNil(model.departureError)
    await original.startRecording()
    XCTAssertEqual(sessions.controls[0].factoryCalls, 0)
    XCTAssertEqual(store.removals, 1)
    store.failRemove = false
    XCTAssertTrue(model.disconnect())
    XCTAssertNil(model.practiceSession)
    XCTAssertNil(store.data)
    XCTAssertNil(model.departureError)
    XCTAssertEqual(store.removals, 2)
  }

  func testFailedAuthenticatedPersistenceKeepsRetryPendingWithoutConstructingSession() async throws
  {
    let sessions = try EnrollmentCaptureSessions()
    defer { sessions.dispose() }
    let store = InMemoryEnrollmentStore()
    store.failSave = true
    let client = FakePracticeClient(assignment: .localPreview)
    let model = EnrollmentModel(store: store, practiceSessionFactory: sessions.makeSession) { _ in
      client
    }
    model.serverAddress = "https://practice.example.test"
    model.deviceToken = String(repeating: "x", count: 43)
    await model.connect()
    XCTAssertNil(store.data)
    XCTAssertNil(model.practiceSession)
    XCTAssertTrue(sessions.captures.isEmpty)
    XCTAssertNotNil(model.errorMessage)
    store.failSave = false
    await model.retryAssignmentLoad()
    let fetches = await client.fetchCount()
    XCTAssertEqual(fetches, 2)
    XCTAssertEqual(store.saves, 2)
    XCTAssertNotNil(store.data)
    XCTAssertEqual(model.phase, .ready)
    XCTAssertEqual(sessions.captures.count, 1)
  }

  #if DEBUG
    func testAccessibilityPreviewCannotDropHardwareBlockedSessionOrCredential() async throws {
      let sessions = try EnrollmentCaptureSessions()
      defer { sessions.dispose() }
      let store = InMemoryEnrollmentStore()
      let client = FakePracticeClient(assignment: .localPreview)
      let model = EnrollmentModel(store: store, practiceSessionFactory: sessions.makeSession) { _ in
        client
      }
      model.serverAddress = "https://practice.example.test"
      model.deviceToken = String(repeating: "x", count: 43)
      await model.connect()
      let original = try XCTUnwrap(model.practiceSession)
      let saved = store.data
      let driver = try XCTUnwrap(sessions.drivers.last)
      await original.startRecording()
      driver.failDeactivate = true
      await original.stopRecording()
      let id = try XCTUnwrap(original.captureCleanupRetryIDs.first)
      XCTAssertFalse(model.configureAccessibilityPreview(.noAssignment))
      XCTAssertTrue(model.practiceSession === original)
      XCTAssertEqual(store.data, saved)
      XCTAssertEqual(store.removals, 0)
      driver.failDeactivate = false
      original.retryCaptureCleanup(operationID: id)
      XCTAssertTrue(model.configureAccessibilityPreview(.noAssignment))
      XCTAssertNil(model.practiceSession)
      XCTAssertEqual(model.phase, .noAssignment)
      XCTAssertEqual(store.data, saved)
      XCTAssertEqual(store.removals, 0)
    }

    func testAccessibilityPreviewFileDepartureRequiresItsOwnSecondWarning() async throws {
      let sessions = try EnrollmentCaptureSessions()
      defer { sessions.dispose() }
      let store = InMemoryEnrollmentStore()
      let client = FakePracticeClient(assignment: .localPreview)
      let model = EnrollmentModel(store: store, practiceSessionFactory: sessions.makeSession) { _ in
        client
      }
      model.serverAddress = "https://practice.example.test"
      model.deviceToken = String(repeating: "x", count: 43)
      await model.connect()
      let original = try XCTUnwrap(model.practiceSession)
      let control = try XCTUnwrap(sessions.controls.last)
      await original.startRecording()
      control.failRemoval = true
      await original.stopRecording()
      await model.retryAssignmentLoad()
      XCTAssertFalse(model.configureAccessibilityPreview(.noAssignment))
      XCTAssertTrue(model.practiceSession === original)
      XCTAssertTrue(model.configureAccessibilityPreview(.noAssignment))
      XCTAssertNil(model.practiceSession)
      XCTAssertEqual(model.phase, .noAssignment)
      XCTAssertFalse(sessions.files.pendingCleanupOwners.isEmpty)
      XCTAssertEqual(store.removals, 0)
      XCTAssertEqual(control.removals, 1)
    }
  #endif

  func testConnectAuthenticatesBeforePersistingAndBuildsAssignedSession() async throws {
    let sessions = try EnrollmentCaptureSessions()
    defer { sessions.dispose() }
    let store = InMemoryEnrollmentStore()
    let client = FakePracticeClient(assignment: .localPreview)
    let model = EnrollmentModel(store: store, practiceSessionFactory: sessions.makeSession) { _ in
      client
    }
    model.serverAddress = "https://practice.example.test"
    model.deviceToken = String(repeating: "x", count: 43)

    await model.connect()

    XCTAssertEqual(model.phase, .ready)
    XCTAssertEqual(model.practiceSession?.promptWord, "ball")
    XCTAssertEqual(model.practiceSession?.assignmentProgress, "1 of 5")
    XCTAssertEqual(
      sessions.contexts.first?.assignmentID, LearnerPracticeAssignment.localPreview.assignmentID)
    XCTAssertEqual(
      sessions.contexts.first?.exerciseID, LearnerPracticeAssignment.localPreview.exerciseID)
    XCTAssertEqual(sessions.contexts.first?.deviceToken, String(repeating: "x", count: 43))
    XCTAssertNotNil(store.data)
    XCTAssertNil(model.errorMessage)
    XCTAssertEqual(model.deviceToken, "")
  }

  func testNoAssignmentPersistsAuthenticatedCredentialAndCanRetry() async throws {
    let sessions = try EnrollmentCaptureSessions()
    defer { sessions.dispose() }
    let store = InMemoryEnrollmentStore()
    let client = FakePracticeClient(assignment: nil)
    let model = EnrollmentModel(store: store, practiceSessionFactory: sessions.makeSession) { _ in
      client
    }
    model.serverAddress = "https://practice.example.test"
    model.deviceToken = String(repeating: "x", count: 43)

    await model.connect()

    XCTAssertEqual(model.phase, .noAssignment)
    XCTAssertNil(model.practiceSession)
    XCTAssertNotNil(store.data)

    await client.setAssignment(.localPreview)
    await model.retryAssignmentLoad()
    XCTAssertEqual(model.phase, .ready)
    XCTAssertNotNil(model.practiceSession)
  }

  func testCompletedServerProgressRestoresCompletedPractice() async throws {
    let sessions = try EnrollmentCaptureSessions()
    defer { sessions.dispose() }
    let store = InMemoryEnrollmentStore()
    let completed = LearnerPracticeAssignment(
      assignmentID: "assignment-completed",
      version: 1,
      exerciseRegistryVersion: "foundation-exercises-v1",
      exerciseDefinitionSHA256: String(repeating: "a", count: 64),
      exerciseID: "foundation-ball-initial-b-v1",
      protocolID: "bilabial-closure-v1",
      prompt: "ball",
      targetLabel: "Beginning /b/",
      attemptTarget: 1,
      retryLimit: 1,
      progress: .completed(acceptedRepetitions: 1)
    )
    let client = FakePracticeClient(assignment: completed)
    let model = EnrollmentModel(store: store, practiceSessionFactory: sessions.makeSession) { _ in
      client
    }
    model.serverAddress = "https://practice.example.test"
    model.deviceToken = String(repeating: "x", count: 43)

    await model.connect()

    XCTAssertEqual(model.phase, .ready)
    XCTAssertEqual(model.practiceSession?.phase, .completed)
  }

  func testStoredEnrollmentRefreshesAssignmentAndDisconnectRemovesIt() async throws {
    let sessions = try EnrollmentCaptureSessions()
    defer { sessions.dispose() }
    let store = InMemoryEnrollmentStore()
    let firstClient = FakePracticeClient(assignment: .localPreview)
    let first = EnrollmentModel(store: store, practiceSessionFactory: sessions.makeSession) { _ in
      firstClient
    }
    first.serverAddress = "https://practice.example.test"
    first.deviceToken = String(repeating: "x", count: 43)
    await first.connect()

    let refreshedAssignment = LearnerPracticeAssignment(
      assignmentID: "assignment-refreshed",
      version: 2,
      exerciseRegistryVersion: "foundation-exercises-v1",
      exerciseDefinitionSHA256: String(repeating: "a", count: 64),
      exerciseID: "foundation-ball-initial-b-v1",
      protocolID: "bilabial-closure-v1",
      prompt: "ball again",
      targetLabel: "Beginning /b/",
      attemptTarget: 3,
      retryLimit: 1,
      progress: .ready(
        acceptedRepetitions: 1,
        repetitionIndex: 2,
        retryIndex: 1
      )
    )
    let refreshClient = FakePracticeClient(assignment: refreshedAssignment)
    let restored = EnrollmentModel(store: store, practiceSessionFactory: sessions.makeSession) {
      _ in refreshClient
    }
    XCTAssertEqual(restored.phase, .loading)

    await restored.loadStoredAssignment()

    XCTAssertEqual(restored.practiceSession?.promptWord, "ball again")
    XCTAssertEqual(restored.practiceSession?.assignmentProgress, "2 of 3")
    XCTAssertEqual(restored.practiceSession?.currentRetry, 1)
    restored.disconnect()
    XCTAssertNil(restored.practiceSession)
    XCTAssertNil(store.data)
    XCTAssertEqual(restored.phase, .disconnected)
  }

  func testExpiredStoredEnrollmentIsRemoved() async throws {
    let sessions = try EnrollmentCaptureSessions()
    defer { sessions.dispose() }
    let store = InMemoryEnrollmentStore()
    let firstClient = FakePracticeClient(assignment: .localPreview)
    let first = EnrollmentModel(store: store, practiceSessionFactory: sessions.makeSession) { _ in
      firstClient
    }
    first.serverAddress = "https://practice.example.test"
    first.deviceToken = String(repeating: "x", count: 43)
    await first.connect()

    let expiredClient = FakePracticeClient(
      assignment: nil,
      error: .sessionExpired
    )
    let restored = EnrollmentModel(store: store, practiceSessionFactory: sessions.makeSession) {
      _ in expiredClient
    }
    await restored.loadStoredAssignment()

    XCTAssertEqual(restored.phase, .disconnected)
    XCTAssertNil(store.data)
    XCTAssertNotNil(restored.errorMessage)
  }

  func testTransientFirstLoadDoesNotPersistUntilAuthenticatedRetry() async throws {
    let sessions = try EnrollmentCaptureSessions()
    defer { sessions.dispose() }
    let store = InMemoryEnrollmentStore()
    let client = FakePracticeClient(
      assignment: nil,
      error: .rejected(status: 503)
    )
    let model = EnrollmentModel(store: store, practiceSessionFactory: sessions.makeSession) { _ in
      client
    }
    model.serverAddress = "https://practice.example.test"
    model.deviceToken = String(repeating: "x", count: 43)

    await model.connect()

    XCTAssertEqual(
      model.phase,
      .failed("The practice service could not complete this request (503).")
    )
    XCTAssertNil(store.data)

    await client.setAssignment(.localPreview)
    await model.retryAssignmentLoad()

    XCTAssertEqual(model.phase, .ready)
    XCTAssertNotNil(store.data)
  }

  func testInvalidOrUnauthenticatedEnrollmentNeverPersists() async throws {
    let sessions = try EnrollmentCaptureSessions()
    defer { sessions.dispose() }
    let store = InMemoryEnrollmentStore()
    let client = FakePracticeClient(
      assignment: nil,
      error: .rejected(status: 503)
    )
    let model = EnrollmentModel(store: store, practiceSessionFactory: sessions.makeSession) { _ in
      client
    }
    model.serverAddress = "http://not-secure.example.test"
    model.deviceToken = "short"

    await model.connect()

    XCTAssertNil(model.practiceSession)
    XCTAssertNil(store.data)
    XCTAssertNotNil(model.errorMessage)
    let fetchCount = await client.fetchCount()
    XCTAssertEqual(fetchCount, 0)
  }
}

private final class InMemoryEnrollmentStore: EnrollmentCredentialStoring {
  var data: Data?
  private(set) var saves = 0
  private(set) var removals = 0
  var failSave = false
  var failRemove = false

  func load() throws -> Data? { data }
  func save(_ data: Data) throws {
    saves += 1
    if failSave { throw EnrollmentTestFailure.controlled }
    self.data = data
  }
  func remove() throws {
    removals += 1
    if failRemove { throw EnrollmentTestFailure.controlled }
    data = nil
  }
}

private actor FakePracticeClient: LearnerPracticeServicing {
  private var assignment: LearnerPracticeAssignment?
  private var fetchError: LearnerAttemptAPIError?
  private var fetches = 0
  private var tokens: [String] = []
  private var holdsNextFetch = false
  private var heldFetch: CheckedContinuation<LearnerPracticeAssignment?, Error>?
  func holdNextFetch() { holdsNextFetch = true }
  func isHoldingFetch() -> Bool { heldFetch != nil }
  func finishHeldFetch(_ result: Result<LearnerPracticeAssignment?, Error>) {
    heldFetch?.resume(with: result)
    heldFetch = nil
  }
  func fetchedTokens() -> [String] { tokens }

  init(
    assignment: LearnerPracticeAssignment?,
    error: LearnerAttemptAPIError? = nil
  ) {
    self.assignment = assignment
    fetchError = error
  }

  func setError(_ error: LearnerAttemptAPIError?) { fetchError = error }

  func setAssignment(_ assignment: LearnerPracticeAssignment?) {
    self.assignment = assignment
    fetchError = nil
  }

  func fetchCount() -> Int { fetches }

  func fetchCurrentAssignment(
    deviceToken: String
  ) async throws -> LearnerPracticeAssignment? {
    fetches += 1
    tokens.append(deviceToken)
    if holdsNextFetch {
      holdsNextFetch = false
      return try await withCheckedThrowingContinuation { heldFetch = $0 }
    }
    if let fetchError { throw fetchError }
    return assignment
  }

  func submit(
    recording: CapturedRecording,
    attemptID: String,
    context: LearnerAttemptContext
  ) async throws -> LearnerAttemptReceipt {
    LearnerAttemptReceipt(
      attemptId: attemptID,
      status: .acceptedSilent,
      feedbackAvailable: false,
      mediaRetained: false,
      reasonCodes: []
    )
  }
}

private enum EnrollmentTestFailure: Error { case controlled }

/// Every test-created session uses a fresh producer namespace and controlled driver.
/// No production AV permission/session or shared capture startup scan is invoked.
@MainActor
private final class EnrollmentCaptureSessions {
  let directory: URL
  let hardware = AudioHardwareOwnership()
  let files = ProcessAudioFileOwnership()
  private(set) var captures: [EnrollmentPermissionCapture] = []
  private(set) var drivers: [EnrollmentCaptureDriver] = []
  private(set) var controls: [EnrollmentCaptureControl] = []
  private(set) var contexts: [LearnerAttemptContext] = []

  init() throws {
    directory = FileManager.default.temporaryDirectory.appendingPathComponent(
      "enrollment-capture-\(UUID())")
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
  }

  func makeSession(
    assignment: LearnerPracticeAssignment, client: any LearnerPracticeServicing,
    context: LearnerAttemptContext
  ) throws -> PracticeSessionModel {
    let visit = directory.appendingPathComponent(UUID().uuidString)
    try FileManager.default.createDirectory(at: visit, withIntermediateDirectories: true)
    let store = TemporaryRecordingStore(directory: visit)
    let driver = EnrollmentCaptureDriver()
    let control = EnrollmentCaptureControl()
    let capture = EnrollmentPermissionCapture(
      SystemAudioCapturer(
        recordingStore: store, fileOwnership: files, hardwareOwnership: hardware,
        driverFactory: {
          control.factoryCalls += 1
          return driver
        },
        summaryReader: { _ in .init(duration: 1, averagePower: -20) },
        removeFile: { url in
          control.removals += 1
          if control.failRemoval { throw EnrollmentTestFailure.controlled }
          try store.removeRecordingIfPresent(at: url)
        }))
    captures.append(capture)
    drivers.append(driver)
    controls.append(control)
    contexts.append(context)
    return PracticeSessionModel(
      assignment: assignment, capturer: capture, submitter: client, attemptContext: context,
      visualConfiguration: .disabled, hardwareOwnership: hardware, fileOwnership: files)
  }

  func dispose() {
    for driver in drivers { driver.failDeactivate = false }
    for control in controls { control.failRemoval = false }
    for capture in captures { try? capture.cancel() }
    if let id = hardware.blockedCaptureOperationID {
      _ = hardware.retryCaptureCleanup(operationID: id)
    }
    for id in files.pendingCleanupOwners { _ = files.retryCleanup(owner: id) }
    try? FileManager.default.removeItem(at: directory)
  }
}

@MainActor
private final class EnrollmentPermissionCapture: AudioCapturing {
  let concrete: SystemAudioCapturer
  var holdsPermission = false
  var permission: CheckedContinuation<Bool, Never>?
  init(_ concrete: SystemAudioCapturer) { self.concrete = concrete }
  var cleanupState: CaptureCleanupState { concrete.cleanupState }
  var cleanupStatePublisher: AnyPublisher<CaptureCleanupState, Never> {
    concrete.cleanupStatePublisher
  }
  func completedFileCleanup(operationID: UUID) -> CaptureCleanupReceipt? {
    concrete.completedFileCleanup(operationID: operationID)
  }
  func requestPermission() async -> Bool {
    if holdsPermission { return await withCheckedContinuation { permission = $0 } }
    return true
  }
  func grantPermission() {
    permission?.resume(returning: true)
    permission = nil
  }
  func start(onFinish: @escaping @MainActor (Bool) async -> Void) throws {
    try concrete.start(onFinish: onFinish)
  }
  func stop() throws -> CapturedRecording { try concrete.stop() }
  func cancel() throws { try concrete.cancel() }
  func discard(_ recording: CapturedRecording) throws { try concrete.discard(recording) }
  func retryCleanup(operationID: UUID) -> CaptureCleanupReceipt {
    concrete.retryCleanup(operationID: operationID)
  }
}

@MainActor
private final class EnrollmentCaptureControl {
  var factoryCalls = 0
  var removals = 0
  var failRemoval = false
}

@MainActor
private final class EnrollmentCaptureDriver: CaptureHardwareDriver {
  var failDeactivate = false
  var deactivations = 0
  var url: URL?
  func configureActivate() throws {}
  func createRecorder(
    url: URL, recorderID: UUID, onFinish: @escaping @MainActor @Sendable (UUID, Bool) -> Void
  ) throws {
    self.url = url
    // Generated bytes and controlled summary; no claim that this is captured audio.
    try Data([1, 2, 3]).write(to: url)
  }
  func prepare() throws -> Bool { true }
  func record() throws -> Bool { true }
  func stop() throws {}
  func detachRelease() throws {}
  func deactivate() throws {
    deactivations += 1
    if failDeactivate { throw EnrollmentTestFailure.controlled }
  }
}

@MainActor
private func waitForEnrollmentState(_ predicate: @MainActor () -> Bool) async {
  let deadline = ContinuousClock.now + .seconds(2)
  while !predicate(), ContinuousClock.now < deadline { await Task.yield() }
  XCTAssertTrue(predicate(), "Expected controlled state was not reached")
}

private func waitForHeldEnrollmentFetch(_ client: FakePracticeClient) async {
  let deadline = ContinuousClock.now + .seconds(2)
  while !(await client.isHoldingFetch()), ContinuousClock.now < deadline { await Task.yield() }
  let held = await client.isHoldingFetch()
  XCTAssertTrue(held, "Expected controlled fetch was not reached")
}

private struct EnrollmentTestStoredRecord: Decodable {
  let baseURL: URL
  let deviceToken: String
}
