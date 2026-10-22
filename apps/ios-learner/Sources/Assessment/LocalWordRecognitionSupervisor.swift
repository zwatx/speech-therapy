import Foundation

enum LocalWordRecognitionControl: Equatable, Sendable {
  case cancellation
  case deadline
  case stopped
}

struct LocalWordConsumerCompletion: Sendable {
  let succeeded: Bool
  let status: LocalWordRecognitionStatus
}

struct LocalWordWorkerCompletion: Sendable {
  let status: LocalWordRecognitionStatus
  let cleanupConfirmed: Bool
}

/// Handles failure inside the group before scope exit can wait on held work.
enum LocalWordRecognitionSupervisor {
  private enum Event: Sendable {
    case analysis(Bool)
    case consumer(LocalWordConsumerCompletion)
    case control(LocalWordRecognitionControl)
  }

  static func run(
    analysis: @escaping @Sendable () async -> Bool,
    consumer: @escaping @Sendable () async -> LocalWordConsumerCompletion,
    cancel: @escaping @Sendable () async -> Bool,
    deadline: @escaping @Sendable () async -> LocalWordRecognitionControl,
    cancellation: @escaping @Sendable () async -> LocalWordRecognitionControl,
    observeControl: (@Sendable (LocalWordRecognitionControl) -> Void)? = nil,
    observeTerminal: (@Sendable (LocalWordRecognitionDiagnostic.TerminalTrigger) -> Void)? = nil
  ) async -> LocalWordWorkerCompletion {
    let completion = await withTaskGroup(of: Event.self, returning: LocalWordWorkerCompletion.self)
    { group in
      group.addTask { .consumer(await consumer()) }
      group.addTask { .analysis(await analysis()) }
      group.addTask { .control(await deadline()) }
      group.addTask { .control(await cancellation()) }
      var analysisSucceeded: Bool?
      var consumerCompletion: LocalWordConsumerCompletion?
      var interrupted: LocalWordRecognitionStatus?
      var terminalTrigger: LocalWordRecognitionDiagnostic.TerminalTrigger = .normal
      while let event = await group.next() {
        if case .control(let control) = event { observeControl?(control) }
        switch event {
        case .analysis(let success):
          analysisSucceeded = success
          if !success {
            interrupted = .uncertain
            terminalTrigger = .analysisFailure
          }
        case .consumer(let report):
          consumerCompletion = report
          if !report.succeeded {
            interrupted = .uncertain
            terminalTrigger = .consumerFailure
          }
        case .control(.cancellation):
          interrupted = .cancelled
          terminalTrigger = .explicitCancellation
        case .control(.deadline):
          interrupted = .timedOut
          terminalTrigger = .deadline
        case .control(.stopped): break
        }
        if interrupted != nil || (analysisSucceeded != nil && consumerCompletion != nil) { break }
      }
      // Parent cancellation must also win when already queued worker reports arrive first.
      if Task.isCancelled {
        interrupted = .cancelled
        terminalTrigger = .parentCancellation
      }
      observeTerminal?(terminalTrigger)
      let cancelNeeded = interrupted != nil
      var cancelAcknowledged = false
      if cancelNeeded {
        // No cleanup deadline: neither task cancellation nor elapsed time releases a borrow.
        cancelAcknowledged = await cancel()
      }
      group.cancelAll()
      while let event = await group.next() {
        switch event {
        case .analysis(let success): analysisSucceeded = success
        case .consumer(let report): consumerCompletion = report
        case .control: break
        }
      }
      let normal = analysisSucceeded == true && consumerCompletion?.succeeded == true
      let joined = analysisSucceeded != nil && consumerCompletion != nil
      return LocalWordWorkerCompletion(
        status: interrupted ?? consumerCompletion?.status ?? .uncertain,
        cleanupConfirmed: joined && (cancelNeeded ? cancelAcknowledged : normal))
    }
    // The completion crosses this boundary only after every structured child has joined.
    return completion
  }
}
