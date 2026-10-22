import AVFoundation
import CoreMedia
import Foundation
import Speech

@MainActor
final class SystemLocalWordRecognizer: LocalWordRecognizing {
  private final class Operation {
    let request: LocalWordRecognitionRequest
    let control = AsyncStream<Void>.makeStream(bufferingPolicy: .bufferingNewest(1))
    var cancellationRequested = false
    var retainedAdmissionHandle: FileHandle?
    let diagnostic: LocalWordDiagnosticRecorder

    init(request: LocalWordRecognitionRequest) {
      self.request = request
      diagnostic = .init(operationID: request.operationID, tryID: request.tryID)
    }
  }

  private let ownership: ProcessAudioFileOwnership
  private var operation: Operation?
  private(set) var lastDiagnostic: LocalWordRecognitionDiagnostic?
  private let fixtureDiagnosticSink: (@MainActor (LocalWordRecognitionDiagnostic) -> Void)?

  /// Deliberately inert: constructing the provider does not query Speech or open files.
  init(
    ownership: ProcessAudioFileOwnership = .shared,
    fixtureDiagnosticSink: (@MainActor (LocalWordRecognitionDiagnostic) -> Void)? = nil
  ) {
    self.ownership = ownership
    self.fixtureDiagnosticSink = fixtureDiagnosticSink
  }

  func cancel(operationID: UUID) {
    guard let operation, operation.request.operationID == operationID else { return }
    operation.cancellationRequested = true
    operation.control.continuation.yield(())
  }

  func check(request: LocalWordRecognitionRequest) async -> LocalWordRecognitionReceipt {
    guard operation == nil else {
      // No new operation may bypass a live operation or a retained cleanup failure.
      return .init(request: request, status: .unavailable, cleanupConfirmed: false)
    }
    let current = Operation(request: request)
    operation = current
    lastDiagnostic = nil
    func finish(_ status: LocalWordRecognitionStatus, cleanup: Bool = true)
      -> LocalWordRecognitionReceipt
    {
      if cleanup {
        current.control.continuation.finish()
        operation = nil
      }
      if status == .cancelled {
        current.diagnostic.record(
          operationID: request.operationID, tryID: request.tryID, reason: .cancellation)
      }
      let diagnostic = current.diagnostic.snapshot()
      lastDiagnostic = diagnostic
      fixtureDiagnosticSink?(diagnostic)
      return .init(request: request, status: status, cleanupConfirmed: cleanup)
    }
    func cancelled() -> Bool { Task.isCancelled || current.cancellationRequested }
    func unavailable(_ reason: LocalWordRecognitionDiagnostic.Reason, cleanup: Bool = true)
      -> LocalWordRecognitionReceipt
    {
      current.diagnostic.record(
        operationID: request.operationID, tryID: request.tryID, reason: reason)
      return finish(.unavailable, cleanup: cleanup)
    }
    guard !cancelled() else { return finish(.cancelled) }
    guard #available(iOS 26, *) else { return unavailable(.unsupportedPlatform) }
    guard LocalWordComparison.singleWord(request.expectedWord) != nil, request.fileURL.isFileURL
    else {
      return unavailable(.invalidRequest)
    }

    let locale = await DictationTranscriber.supportedLocale(
      equivalentTo: Locale(identifier: "en-US"))
    guard !cancelled() else { return finish(.cancelled) }
    guard let locale, locale.language.languageCode == .english else {
      return unavailable(.unsupportedLocale)
    }
    // Expected word never enters the Speech configuration or analysis context.
    let transcriber = DictationTranscriber(
      locale: locale, contentHints: [], transcriptionOptions: [], reportingOptions: [],
      attributeOptions: [])
    let assets = await AssetInventory.status(forModules: [transcriber])
    guard !cancelled() else { return finish(.cancelled) }
    guard assets == .installed else { return unavailable(.assetsNotInstalled) }
    guard ownership.borrow(request.fileURL, operation: request.operationID) else {
      return unavailable(.ownershipUnavailable)
    }

    // Admission reads at most the bounded WAV bytes, after fresh installed-asset readiness.
    let duration: Double
    do {
      let admission = try LocalWordWAVGate.read(fileURL: request.fileURL)
      guard admission.cleanupConfirmed else {
        current.retainedAdmissionHandle = admission.retainedHandle
        return unavailable(.admissionCleanupUnconfirmed, cleanup: false)
      }
      guard let admitted = admission.duration else {
        current.diagnostic.record(
          operationID: request.operationID, tryID: request.tryID, reason: .admissionRejected)
        ownership.finishBorrowing(operation: request.operationID)
        return finish(.unavailable)
      }
      duration = admitted
      current.diagnostic.record(
        operationID: request.operationID, tryID: request.tryID, stage: .admitted)
    } catch {
      ownership.finishBorrowing(operation: request.operationID)
      return unavailable(.admissionReadFailed)
    }
    guard !cancelled() else {
      ownership.finishBorrowing(operation: request.operationID)
      return finish(.cancelled)
    }

    let completion = await Self.runInstalled(
      request: request, duration: duration, transcriber: transcriber,
      cancellation: current.control.stream, diagnostic: current.diagnostic)
    // runInstalled and the whole supervisor group have exited. If framework cleanup was
    // unconfirmed, keep both this operation and its exact process borrow indefinitely.
    if completion.cleanupConfirmed {
      ownership.finishBorrowing(operation: request.operationID)
    }
    let final = LocalWordReceiptFinalization.complete(
      completion, parentCancelled: Task.isCancelled,
      cancellationRequested: current.cancellationRequested,
      operationID: request.operationID, tryID: request.tryID, diagnostic: current.diagnostic)
    return finish(final.status, cleanup: final.cleanupConfirmed)
  }

  @available(iOS 26, *)
  private nonisolated static func runInstalled(
    request: LocalWordRecognitionRequest, duration: Double,
    transcriber: DictationTranscriber, cancellation: AsyncStream<Void>,
    diagnostic: LocalWordDiagnosticRecorder
  ) async -> LocalWordWorkerCompletion {
    @Sendable func record(
      _ stage: LocalWordRecognitionDiagnostic.Stage? = nil,
      reason: LocalWordRecognitionDiagnostic.Reason? = nil,
      error: (any Error)? = nil
    ) {
      diagnostic.record(
        operationID: request.operationID, tryID: request.tryID, stage: stage, reason: reason,
        speechFailure: error.flatMap {
          $0 is CancellationError ? nil : LocalWordSpeechDiagnostic.category($0)
        })
    }
    let analyzer = SpeechAnalyzer(modules: [transcriber])
    let registered = AsyncStream<Void>.makeStream(bufferingPolicy: .bufferingNewest(1))
    let results = transcriber.results
    let completion = await LocalWordRecognitionSupervisor.run(
      analysis: {
        var failure: LocalWordRecognitionDiagnostic.Reason = .analysisFailed
        do {
          var registration = registered.stream.makeAsyncIterator()
          guard await registration.next() != nil else { return false }
          try Task.checkCancellation()
          // AVAudioFile is confined to the exact worker until its terminal return.
          record(.fileOpenReached)
          failure = .fileOpenFailed
          let file = try AVAudioFile(forReading: request.fileURL)
          defer { file.close() }
          record(.fileOpened)
          failure = .analysisFailed
          guard file.fileFormat.sampleRate == 16_000, file.fileFormat.channelCount == 1,
            file.length >= 1_600, file.length <= 64_000,
            Double(file.length) / 16_000 == duration
          else {
            record(reason: .formatRejected)
            return false
          }
          record(.formatValidated)
          try Task.checkCancellation()
          record(.formatSelectionReached)
          guard
            let inputFormat = await SpeechAnalyzer.bestAvailableAudioFormat(
              compatibleWith: [transcriber], considering: file.processingFormat)
          else {
            record(reason: .formatUnavailable)
            return false
          }
          try Task.checkCancellation()
          record(.formatSelected)
          failure = .conversionFailed
          record(.conversionReached)
          let source = try LocalWordAudioInput.read(file, admittedDuration: duration)
          let converted = try LocalWordAudioInput.convert(source, to: inputFormat)
          let inputs = try converted.inputSequence()
          record(.conversionReturned)
          try Task.checkCancellation()
          failure = .analysisFailed
          record(.analyzeReached)
          _ = try await analyzer.analyzeSequence(inputs)
          record(.analyzeReturned)
          try Task.checkCancellation()
          record(.finalizeReached)
          failure = .finalizationFailed
          try await analyzer.finalizeAndFinishThroughEndOfInput()
          record(.finalizeReturned)
          return true
        } catch {
          record(reason: error is CancellationError ? .cancellation : failure, error: error)
          return false
        }
      },
      consumer: {
        var iterator = results.makeAsyncIterator()
        registered.continuation.yield(())
        registered.continuation.finish()
        var finals: [LocalWordFinalSegment] = []
        var resultCount = 0
        var characterCount = 0
        do {
          while let result = try await iterator.next() {
            resultCount += 1
            characterCount += result.text.characters.count
            guard resultCount <= 64, characterCount <= 1024 else {
              record(reason: .boundedLimit)
              return .init(succeeded: false, status: .uncertain)
            }
            guard result.isFinal else { continue }
            let start = result.range.start
            let length = result.range.duration
            guard start.isNumeric, length.isNumeric, start.epoch == 0, length.epoch == 0 else {
              record(reason: .timing)
              return .init(succeeded: false, status: .uncertain)
            }
            finals.append(
              .init(
                text: String(result.text.characters), start: start.seconds, duration: length.seconds
              ))
          }
          record(.resultStreamFinished)
          try Task.checkCancellation()
          record(.comparisonReached)
          let comparison = LocalWordComparison.diagnose(
            finals: finals, expectedWord: request.expectedWord, audioDuration: duration)
          record(reason: comparison.reason)
          return .init(succeeded: true, status: comparison.status)
        } catch {
          record(
            reason: error is CancellationError ? .cancellation : .resultStreamFailed, error: error)
          return .init(succeeded: false, status: .uncertain)
        }
      },
      cancel: {
        await analyzer.cancelAndFinishNow()
        return true
      },
      deadline: {
        do {
          try await Task.sleep(for: .seconds(15))
          return .deadline
        } catch { return .cancellation }
      },
      cancellation: {
        var iterator = cancellation.makeAsyncIterator()
        return await iterator.next() == nil ? .stopped : .cancellation
      },
      observeControl: { control in
        switch control {
        case .deadline: record(reason: .deadline)
        case .cancellation: record(reason: .cancellation)
        case .stopped: break
        }
      },
      observeTerminal: { trigger in
        diagnostic.record(
          operationID: request.operationID, tryID: request.tryID, terminalTrigger: trigger)
      })
    record(.joined)
    return completion
  }
}
