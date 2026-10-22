import Foundation
import XCTest

@testable import CadenceLearner

private actor WordHeldGate {
  private var opened = false
  private var waiters: [CheckedContinuation<Void, Never>] = []

  func wait() async {
    if opened { return }
    await withCheckedContinuation { waiters.append($0) }
  }

  func open() {
    opened = true
    let pending = waiters
    waiters.removeAll()
    for waiter in pending { waiter.resume() }
  }
}

private struct WordCancellableControl: Sendable {
  private let channel = AsyncStream<LocalWordRecognitionControl>.makeStream(
    bufferingPolicy: .bufferingNewest(1))
  func wait() async -> LocalWordRecognitionControl {
    var iterator = channel.stream.makeAsyncIterator()
    return await iterator.next() ?? .cancellation
  }
}

private actor WordCompletionEvidence {
  private(set) var cancelCalls = 0
  private(set) var finished = false
  func cancelling() { cancelCalls += 1 }
  func complete() { finished = true }
}

@MainActor
final class LocalWordRecognitionSupervisorTests: XCTestCase {
  func testConsumerFailureCancelsBeforeHeldAnalysisJoinAndBorrowRelease() async {
    executionTimeAllowance = 10
    let analysisEntered = WordHeldGate()
    let analysisRelease = WordHeldGate()
    let cancelEntered = WordHeldGate()
    let cancelRelease = WordHeldGate()
    let cancelReturned = WordHeldGate()
    let evidence = WordCompletionEvidence()
    let control = WordCancellableControl()
    let ownership = ProcessAudioFileOwnership()
    let operationID = UUID()
    let owner = UUID()
    let url = URL(fileURLWithPath: "/generated/\(UUID()).wav")
    ownership.retain(url, owner: owner)
    XCTAssertTrue(ownership.borrow(url, operation: operationID))
    let completion = await withTaskGroup(of: LocalWordWorkerCompletion.self) { group in
      group.addTask {
        let result = await LocalWordRecognitionSupervisor.run(
          analysis: {
            await analysisEntered.open()
            await analysisRelease.wait()
            return false
          },
          consumer: {
            await analysisEntered.wait()
            return .init(succeeded: false, status: .uncertain)
          },
          cancel: {
            await evidence.cancelling()
            await cancelEntered.open()
            await cancelRelease.wait()
            await cancelReturned.open()
            return true
          },
          deadline: { await control.wait() }, cancellation: { await control.wait() })
        await evidence.complete()
        return result
      }
      await cancelEntered.wait()
      let finishedDuringCancel = await evidence.finished
      XCTAssertFalse(finishedDuringCancel)
      XCTAssertFalse(ownership.canRemove(url, owner: owner))
      await cancelRelease.open()
      await cancelReturned.wait()
      let finishedDuringJoin = await evidence.finished
      XCTAssertFalse(finishedDuringJoin)
      XCTAssertFalse(ownership.canRemove(url, owner: owner))
      await analysisRelease.open()
      return await group.next()!
    }
    XCTAssertEqual(completion.status, .uncertain)
    XCTAssertTrue(completion.cleanupConfirmed)
    let calls = await evidence.cancelCalls
    XCTAssertEqual(calls, 1)
    XCTAssertFalse(ownership.canRemove(url, owner: owner))
    ownership.finishBorrowing(operation: operationID)
    XCTAssertTrue(ownership.canRemove(url, owner: owner))
  }

  func testHeldCancelCannotBeAcknowledgedEvenWhenBothWorkersReturn() async {
    executionTimeAllowance = 10
    let cancelEntered = WordHeldGate()
    let cancelRelease = WordHeldGate()
    let workersReturned = WordHeldGate()
    let control = WordCancellableControl()
    let evidence = WordCompletionEvidence()
    let completion = await withTaskGroup(of: LocalWordWorkerCompletion.self) { group in
      group.addTask {
        let result = await LocalWordRecognitionSupervisor.run(
          analysis: {
            await cancelEntered.wait()
            await workersReturned.open()
            return true
          },
          consumer: { .init(succeeded: false, status: .uncertain) },
          cancel: {
            await cancelEntered.open()
            await cancelRelease.wait()
            return true
          }, deadline: { await control.wait() }, cancellation: { await control.wait() })
        await evidence.complete()
        return result
      }
      await workersReturned.wait()
      let finished = await evidence.finished
      XCTAssertFalse(finished)
      await cancelRelease.open()
      return await group.next()!
    }
    XCTAssertTrue(completion.cleanupConfirmed)
  }

  func testRealParentCancellationCancelsBeforeHeldWorkersAndJoinsThem() async {
    executionTimeAllowance = 10
    let entered = WordHeldGate()
    let release = WordHeldGate()
    let cancelEntered = WordHeldGate()
    let control = WordCancellableControl()
    let evidence = WordCompletionEvidence()
    let completion = await withTaskGroup(of: LocalWordWorkerCompletion.self) { group in
      group.addTask {
        let result = await LocalWordRecognitionSupervisor.run(
          analysis: {
            await entered.open()
            await release.wait()
            return true
          },
          consumer: {
            await release.wait()
            return .init(succeeded: true, status: .matched)
          },
          cancel: {
            await evidence.cancelling()
            await cancelEntered.open()
            return true
          },
          deadline: { await control.wait() }, cancellation: { await control.wait() })
        await evidence.complete()
        return result
      }
      await entered.wait()
      group.cancelAll()
      await cancelEntered.wait()
      let finished = await evidence.finished
      XCTAssertFalse(finished)
      await release.open()
      return await group.next()!
    }
    XCTAssertEqual(completion.status, .cancelled)
    XCTAssertTrue(completion.cleanupConfirmed)
    let calls = await evidence.cancelCalls
    XCTAssertEqual(calls, 1)
  }

  func testExplicitCancellationAndDeadlineKeepResultConservative() async {
    for trigger in [LocalWordRecognitionControl.cancellation, .deadline] {
      let entered = WordHeldGate()
      let release = WordHeldGate()
      let control = WordCancellableControl()
      let completion = await LocalWordRecognitionSupervisor.run(
        analysis: {
          await entered.open()
          await release.wait()
          return true
        },
        consumer: {
          await release.wait()
          return .init(succeeded: true, status: .matched)
        },
        cancel: {
          await release.open()
          return true
        },
        deadline: {
          await entered.wait()
          return trigger
        }, cancellation: { await control.wait() })
      XCTAssertEqual(completion.status, trigger == .cancellation ? .cancelled : .timedOut)
      XCTAssertTrue(completion.cleanupConfirmed)
    }
  }

  func testNormalCompletionDoesNotCallCancel() async {
    let control = WordCancellableControl()
    let evidence = WordCompletionEvidence()
    let completion = await LocalWordRecognitionSupervisor.run(
      analysis: { true }, consumer: { .init(succeeded: true, status: .notMatched) },
      cancel: {
        await evidence.cancelling()
        return true
      },
      deadline: { await control.wait() }, cancellation: { await control.wait() })
    XCTAssertEqual(completion.status, .notMatched)
    XCTAssertTrue(completion.cleanupConfirmed)
    let calls = await evidence.cancelCalls
    XCTAssertEqual(calls, 0)
  }

  func testUnconfirmedCancelCannotProduceCleanupReceipt() async {
    let release = WordHeldGate()
    let control = WordCancellableControl()
    let completion = await LocalWordRecognitionSupervisor.run(
      analysis: { false },
      consumer: {
        await release.wait()
        return .init(succeeded: false, status: .uncertain)
      },
      cancel: {
        await release.open()
        return false
      },
      deadline: { await control.wait() }, cancellation: { await control.wait() })
    XCTAssertFalse(completion.cleanupConfirmed)
    XCTAssertEqual(completion.status, .uncertain)
  }
}

extension LocalWordRecognitionSupervisorTests {
  func testDiagnosticControlObservationCannotReplaceDeadlineStatusOrExactJoin() async {
    let workersReleased = WordHeldGate()
    let operationID = UUID()
    let tryID = UUID()
    let recorder = LocalWordDiagnosticRecorder(operationID: operationID, tryID: tryID)
    let completion = await LocalWordRecognitionSupervisor.run(
      analysis: {
        await workersReleased.wait()
        return true
      },
      consumer: {
        await workersReleased.wait()
        return .init(succeeded: true, status: .matched)
      },
      cancel: {
        await workersReleased.open()
        return true
      },
      deadline: { .deadline },
      cancellation: {
        await workersReleased.wait()
        return .stopped
      },
      observeControl: { control in
        if control == .deadline {
          recorder.record(operationID: operationID, tryID: tryID, reason: .deadline)
        }
      })
    XCTAssertEqual(completion.status, .timedOut)
    XCTAssertTrue(completion.cleanupConfirmed)
    XCTAssertEqual(recorder.snapshot().reasons, [.deadline])
  }
}

extension LocalWordRecognitionSupervisorTests {
  func testDiagnosticPrimaryFailureSurvivesOppositeWorkerTeardownFailure() async {
    for analysisFirst in [false, true] {
      let released = WordHeldGate()
      let operationID = UUID()
      let tryID = UUID()
      let recorder = LocalWordDiagnosticRecorder(operationID: operationID, tryID: tryID)
      let result = await LocalWordRecognitionSupervisor.run(
        analysis: {
          if !analysisFirst { await released.wait() }
          recorder.record(operationID: operationID, tryID: tryID, reason: .analysisFailed)
          return false
        },
        consumer: {
          if analysisFirst { await released.wait() }
          recorder.record(operationID: operationID, tryID: tryID, reason: .resultStreamFailed)
          return .init(succeeded: false, status: .uncertain)
        },
        cancel: {
          await released.open()
          return true
        },
        deadline: {
          await released.wait()
          return .stopped
        },
        cancellation: {
          await released.wait()
          return .stopped
        },
        observeTerminal: { trigger in
          recorder.record(operationID: operationID, tryID: tryID, terminalTrigger: trigger)
        })
      XCTAssertEqual(result.status, .uncertain)
      XCTAssertTrue(result.cleanupConfirmed)
      XCTAssertEqual(
        recorder.snapshot().terminalTrigger,
        analysisFirst ? .analysisFailure : .consumerFailure)
      XCTAssertEqual(recorder.snapshot().reasons, [.analysisFailed, .resultStreamFailed])
    }
  }

  func testDiagnosticParentCancellationOverrideIsRecordedWithoutControlEvent() async {
    let operationID = UUID()
    let tryID = UUID()
    let recorder = LocalWordDiagnosticRecorder(operationID: operationID, tryID: tryID)
    let task = Task {
      withUnsafeCurrentTask { $0?.cancel() }
      return await LocalWordRecognitionSupervisor.run(
        analysis: { true }, consumer: { .init(succeeded: true, status: .matched) },
        cancel: { true }, deadline: { .stopped }, cancellation: { .stopped },
        observeTerminal: { trigger in
          recorder.record(operationID: operationID, tryID: tryID, terminalTrigger: trigger)
        })
    }
    let result = await task.value
    XCTAssertEqual(result.status, .cancelled)
    XCTAssertTrue(result.cleanupConfirmed)
    XCTAssertEqual(recorder.snapshot().terminalTrigger, .parentCancellation)
  }
}

@MainActor
private final class WordExplicitCancellationFlag {
  var requested = false
}

extension LocalWordRecognitionSupervisorTests {
  func testFinalReceiptOverrideAfterPrimaryDecisionKeepsTriggerAndExactCleanup() async {
    for parentCancellation in [false, true] {
      for cleanupAcknowledged in [false, true] {
        let teardownEntered = WordHeldGate()
        let teardownReleased = WordHeldGate()
        let workersReleased = WordHeldGate()
        let explicit = WordExplicitCancellationFlag()
        let operationID = UUID()
        let tryID = UUID()
        let recorder = LocalWordDiagnosticRecorder(operationID: operationID, tryID: tryID)
        let task = Task {
          let completion = await LocalWordRecognitionSupervisor.run(
            analysis: { false },
            consumer: {
              await workersReleased.wait()
              recorder.record(operationID: operationID, tryID: tryID, reason: .cancellation)
              return .init(succeeded: false, status: .uncertain)
            },
            cancel: {
              await teardownEntered.open()
              await teardownReleased.wait()
              await workersReleased.open()
              return cleanupAcknowledged
            },
            deadline: {
              await workersReleased.wait()
              return .stopped
            },
            cancellation: {
              await workersReleased.wait()
              return .stopped
            },
            observeTerminal: { trigger in
              recorder.record(operationID: operationID, tryID: tryID, terminalTrigger: trigger)
            })
          return LocalWordReceiptFinalization.complete(
            completion, parentCancelled: Task.isCancelled,
            cancellationRequested: explicit.requested,
            operationID: operationID, tryID: tryID, diagnostic: recorder)
        }
        await teardownEntered.wait()
        XCTAssertEqual(recorder.snapshot().terminalTrigger, .analysisFailure)
        XCTAssertNil(recorder.snapshot().receiptOverride)
        if parentCancellation {
          // Exercise both true predicates too: parent cancellation retains precedence.
          explicit.requested = true
          task.cancel()
        } else {
          explicit.requested = true
        }
        await teardownReleased.open()
        let final = await task.value
        XCTAssertEqual(final.status, .cancelled)
        XCTAssertEqual(final.cleanupConfirmed, cleanupAcknowledged)
        XCTAssertEqual(recorder.snapshot().terminalTrigger, .analysisFailure)
        XCTAssertEqual(
          recorder.snapshot().receiptOverride,
          parentCancellation ? .parentCancellation : .explicitCancellation)
        XCTAssertEqual(recorder.snapshot().reasons, [.cancellation])
      }
    }
  }

  func testFinalReceiptWithoutOverridePreservesStatusCleanupAndPrimaryDecision() {
    let operationID = UUID()
    let tryID = UUID()
    let recorder = LocalWordDiagnosticRecorder(operationID: operationID, tryID: tryID)
    recorder.record(operationID: operationID, tryID: tryID, terminalTrigger: .consumerFailure)
    let final = LocalWordReceiptFinalization.complete(
      .init(status: .uncertain, cleanupConfirmed: false), parentCancelled: false,
      cancellationRequested: false, operationID: operationID, tryID: tryID, diagnostic: recorder)
    XCTAssertEqual(final.status, .uncertain)
    XCTAssertFalse(final.cleanupConfirmed)
    XCTAssertEqual(recorder.snapshot().terminalTrigger, .consumerFailure)
    XCTAssertNil(recorder.snapshot().receiptOverride)
  }

  func testTimedOutFinalReceiptKeepsCleanupAndCancellationPriority() {
    for cleanup in [false, true] {
      for parentCancelled in [false, true] {
        for cancellationRequested in [false, true] {
          let operationID = UUID()
          let tryID = UUID()
          let recorder = LocalWordDiagnosticRecorder(operationID: operationID, tryID: tryID)
          recorder.record(
            operationID: operationID, tryID: tryID, reason: .deadline, terminalTrigger: .deadline)
          let final = LocalWordReceiptFinalization.complete(
            .init(status: .timedOut, cleanupConfirmed: cleanup), parentCancelled: parentCancelled,
            cancellationRequested: cancellationRequested, operationID: operationID,
            tryID: tryID, diagnostic: recorder)
          XCTAssertEqual(
            final.status, parentCancelled || cancellationRequested ? .cancelled : .timedOut)
          XCTAssertEqual(final.cleanupConfirmed, cleanup)
          XCTAssertEqual(recorder.snapshot().terminalTrigger, .deadline)
          XCTAssertEqual(
            recorder.snapshot().receiptOverride,
            parentCancelled ? .parentCancellation : cancellationRequested ? .explicitCancellation : nil)
        }
      }
    }
  }
}
