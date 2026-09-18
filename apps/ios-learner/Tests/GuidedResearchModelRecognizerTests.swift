#if DEBUG && targetEnvironment(simulator)
  import Combine
  import Foundation
  import XCTest

  @testable import CadenceLearner

  @MainActor
  enum ResearchAssessmentFixtures {
    static func result(attemptId: UUID, recording: CapturedRecording,
      entry: PracticeLibraryEntry, ageYears: Int, milliseconds: Double = 12)
      throws -> ResearchAssessmentResult
    {
      let context = try ResearchAssessmentClient.context(attemptId: attemptId,
        audio: Data(contentsOf: recording.url), entry: entry, ageYears: ageYears)
      let prompt = try ResearchAssessmentClient.prompt(for: entry)
      return .init(context: context,
        model: .init(id: "ages-6-12-research-mixture", manifestSha256: ResearchAssessmentClient.manifest),
        targets: prompt.targets.enumerated().map { index, target in .init(id: target.id, wordIndex: target.wordIndex,
          phoneIndex: target.phoneIndex, targetPhone: target.targetPhone,
          subjectiveCorpusRatingProbabilities: index.isMultiple(of: 2) ? [0.1, 0.2, 0.7] : [0.7, 0.2, 0.1]) },
        timingMilliseconds: .init(total: milliseconds, inference: milliseconds))
    }
  }

  @MainActor
  final class GuidedResearchModelRecognizerTests: XCTestCase {
    func testTimeoutRetryCapabilityIsAlwaysExcludedByActualResearchComposition() {
      for innerAllowsRetry in [false, true] {
        let word = WordDouble()
        let inner: any LocalWordRecognizing = innerAllowsRetry
          ? word : TimeoutRetryExcludedWordDouble(base: word)
        XCTAssertEqual(inner.allowsTimedOutRetry, innerAllowsRetry)
        let model = ModelDouble()
        let files = ProcessAudioFileOwnership()
        let availability = GuidedResearchModelAvailability()
        let adapter = GuidedResearchModelRecognizer(wordRecognizer: inner, processor: model,
          ownership: files, availability: availability)
        let provider: any LocalWordRecognizing = adapter
        XCTAssertFalse(provider.allowsTimedOutRetry)
        for enabled in [false, true, false] {
          XCTAssertTrue(adapter.configure(ageYears: enabled ? 9 : nil, enabled: enabled))
          XCTAssertFalse(provider.allowsTimedOutRetry)
        }
        availability.pauseForUnknownCleanup()
        XCTAssertFalse(provider.allowsTimedOutRetry)
        XCTAssertTrue(word.requests.isEmpty)
        XCTAssertTrue(word.cancelled.isEmpty)
        XCTAssertTrue(model.calls.isEmpty)
        XCTAssertEqual(model.readinessCalls, 0)
        XCTAssertEqual(adapter.processingState, .idle)
        XCTAssertTrue(adapter.observations.isEmpty)
        XCTAssertTrue(files.protectedURLs.isEmpty)
      }
    }

    private final class TimeoutRetryExcludedWordDouble: LocalWordRecognizing {
      let base: WordDouble
      var allowsTimedOutRetry: Bool { false }
      init(base: WordDouble) { self.base = base }
      func check(request: LocalWordRecognitionRequest) async -> LocalWordRecognitionReceipt {
        await base.check(request: request)
      }
      func cancel(operationID: UUID) { base.cancel(operationID: operationID) }
    }

    private final class WordDouble: LocalWordRecognizing {
      var status: LocalWordRecognitionStatus = .matched
      var cleanupConfirmed = true
      var siblingReceipt = false
      var requests: [LocalWordRecognitionRequest] = []
      var cancelled: [UUID] = []
      var hold = false
      var started: (() -> Void)?
      var continuation: CheckedContinuation<Void, Never>?
      var ownership: ProcessAudioFileOwnership?

      func check(request: LocalWordRecognitionRequest) async -> LocalWordRecognitionReceipt {
        ownership?.borrow(request.fileURL, operation: request.operationID)
        defer { ownership?.finishBorrowing(operation: request.operationID) }
        requests.append(request)
        if hold {
          await withCheckedContinuation { continuation in
            self.continuation = continuation
            started?()
          }
        }
        let returned =
          siblingReceipt
          ? LocalWordRecognitionRequest(
            operationID: UUID(), tryID: request.tryID, fileURL: request.fileURL,
            expectedWord: request.expectedWord)
          : request
        return .init(request: returned, status: status, cleanupConfirmed: cleanupConfirmed)
      }
      func cancel(operationID: UUID) { cancelled.append(operationID) }
      func release() {
        continuation?.resume()
        continuation = nil
      }
    }

    private final class ModelDouble: ResearchAssessmentReadinessChecking {
      struct Call {
        let operationID: UUID
        let recording: CapturedRecording
        let entry: PracticeLibraryEntry
        let age: Int
      }
      var calls: [Call] = []
      var result: ResearchAssessmentOutcome?
      var transform: ((ResearchAssessmentResult) -> ResearchAssessmentResult)?
      var error: Error?
      var hold = false
      var started: (() -> Void)?
      var continuation: CheckedContinuation<Void, Never>?
      var cancellationSeen = false
      var ready = true
      var readinessCalls = 0
      var holdReadiness = false
      var readinessStarted: (() -> Void)?
      var readinessContinuation: CheckedContinuation<Void, Never>?
      var readinessCancellationSeen = false
      func checkReadiness() async -> Bool {
        readinessCalls += 1
        if holdReadiness {
          await withCheckedContinuation { continuation in
            readinessContinuation = continuation
            readinessStarted?()
          }
        }
        readinessCancellationSeen = Task.isCancelled
        return ready
      }
      func releaseReadiness() {
        readinessContinuation?.resume()
        readinessContinuation = nil
      }
      func process(
        attemptId: UUID, recording: CapturedRecording, entry: PracticeLibraryEntry, ageYears: Int
      ) async throws -> ResearchAssessmentOutcome {
        calls.append(
          .init(operationID: attemptId, recording: recording, entry: entry, age: ageYears))
        if hold {
          await withCheckedContinuation { continuation in
            self.continuation = continuation
            started?()
          }
        }
        cancellationSeen = Task.isCancelled
        if let error { throw error }
        if let result { return result }
        let research = try ResearchAssessmentFixtures.result(attemptId: attemptId,
          recording: recording, entry: entry, ageYears: ageYears)
        return .processedResearch(transform?(research) ?? research)
      }
      func release() {
        continuation?.resume()
        continuation = nil
      }
    }

    private final class LegacyModelDouble: ResearchAssessmentProcessing {
      var calls = 0
      func process(
        attemptId: UUID, recording: CapturedRecording, entry: PracticeLibraryEntry, ageYears: Int
      ) async throws -> ResearchAssessmentOutcome {
        calls += 1
        return .processedResearch(try ResearchAssessmentFixtures.result(attemptId: attemptId,
          recording: recording, entry: entry, ageYears: ageYears, milliseconds: 7))
      }
    }

    private var entry: PracticeLibraryEntry {
      PracticeLibrary.entries().first { $0.soundID == "b" && $0.prompt.word == "ball" }!
    }

    private var cleanupSafeRejections:
      [(code: String, reason: GuidedResearchModelOutcome.Reason, note: String)]
    {
      [
        (
          "silence", .silentRecording,
          "No signal was recorded in this take. Check the microphone input before making another recording."
        ),
        (
          "clipping", .recordingAtDigitalLimit,
          "This take reached the recording’s digital level limit. Try moving a little farther from the microphone for another recording."
        ),
        (
          "invalid_audio", .invalidRecording,
          "The research model could not read this recording. Make another recording for a later check."
        ),
        (
          "audio_too_long", .recordingTooLong,
          "This recording exceeds the research model’s length limit. Say the displayed word once, then tap Stop."
        ),
        (
          "unsupported_target", .unsupportedTarget,
          "This target is unavailable for the research model. You can continue manual practice."
        ),
        (
          "model_unavailable", .modelUnavailable,
          "The research model is unavailable on this Mac. You can continue manual practice."
        ),
        (
          "busy", .busy,
          "The research model is busy. You can continue manual practice and check a later recording."
        ),
        (
          "invalid_request", .requestRejected,
          "The research model could not accept this check. You can continue manual practice."
        ),
        (
          "age_out_of_range", .ageRejected,
          "The research model did not accept the declared age. This take received no sound assessment."
        ),
      ]
    }

    private func request(word: String = "ball", url: URL? = nil) -> LocalWordRecognitionRequest {
      .init(
        operationID: UUID(), tryID: UUID(),
        fileURL: url ?? URL(fileURLWithPath: "/generated/unused.wav"), expectedWord: word)
    }

    func testOffUndeclaredAndOutOfRangeAgeNeverAccessModelOrFile() async {
      for (age, enabled, reason) in [
        (Optional<Int>.none, false, GuidedResearchModelOutcome.Reason.disabled),
        (nil, true, .ageNotDeclared), (5, true, .unsupportedAge), (13, true, .unsupportedAge),
      ] {
        let word = WordDouble()
        let model = ModelDouble()
        let recognizer = makeRecognizer(
          wordRecognizer: word, processor: model, availability: GuidedResearchModelAvailability())
        XCTAssertTrue(recognizer.configure(ageYears: age, enabled: enabled))
        XCTAssertTrue(self.prepare(recognizer, entry: entry))
        let input = request()
        let receipt = await self.check(recognizer, request: input)
        XCTAssertEqual(receipt, .init(request: input, status: .matched, cleanupConfirmed: true))
        XCTAssertTrue(model.calls.isEmpty)
        XCTAssertEqual(model.readinessCalls, 0)
        XCTAssertEqual(recognizer.observations[input.operationID]?.outcome, .notRun(reason))
      }
    }

    func testAlreadyCancelledCheckStartsNoWordModelOrBorrow() async {
      let word = WordDouble()
      let model = ModelDouble()
      let ownership = ProcessAudioFileOwnership()
      let recognizer = makeRecognizer(
        wordRecognizer: word, processor: model, ownership: ownership,
        availability: GuidedResearchModelAvailability())
      recognizer.configure(ageYears: 8, enabled: true)
      self.prepare(recognizer, entry: entry)
      let input = request()
      let task = Task { await self.check(recognizer, request: input) }
      task.cancel()
      let receipt = await task.value
      XCTAssertEqual(receipt, .init(request: input, status: .cancelled, cleanupConfirmed: true))
      XCTAssertTrue(word.requests.isEmpty)
      XCTAssertTrue(model.calls.isEmpty)
      XCTAssertEqual(model.readinessCalls, 0)
      XCTAssertTrue(ownership.protectedURLs.isEmpty)
    }

    func testCanonicalEntryAndExactWordAreRequiredAndZHIsUnsupported() async {
      let word = WordDouble()
      let model = ModelDouble()
      let recognizer = makeRecognizer(
        wordRecognizer: word, processor: model, availability: GuidedResearchModelAvailability())
      recognizer.configure(ageYears: 8, enabled: true)
      let altered = PracticeLibraryEntry(
        soundID: entry.soundID, position: entry.position,
        prompt: .init(id: entry.id, word: "ball", systemImage: "wrong"))
      XCTAssertFalse(self.prepare(recognizer, entry: altered))
      let missing = request()
      _ = await self.check(recognizer, request: missing)
      XCTAssertEqual(recognizer.observations[missing.operationID]?.outcome, .notRun(.missingEntry))
      XCTAssertTrue(self.prepare(recognizer, entry: entry))
      let wrong = request(word: "BALL")
      _ = await self.check(recognizer, request: wrong)
      XCTAssertEqual(recognizer.observations[wrong.operationID]?.outcome, .notRun(.wrongEntry))
      let zh = PracticeLibrary.entries(soundID: "zh").first!
      XCTAssertTrue(self.prepare(recognizer, entry: zh))
      let unsupported = request(word: zh.prompt.word)
      _ = await self.check(recognizer, request: unsupported)
      XCTAssertEqual(
        recognizer.observations[unsupported.operationID]?.outcome, .notRun(.unsupportedPrompt))
      XCTAssertTrue(model.calls.isEmpty)
      XCTAssertEqual(model.readinessCalls, 0)
    }

    func testWordNonmatchesAndUncertainResultsStayUnchangedAndSkipModel() async {
      for (status, reason) in [
        (LocalWordRecognitionStatus.notMatched, GuidedResearchModelOutcome.Reason.wordNotMatched),
        (.uncertain, .wordUncertain), (.timedOut, .wordUnavailable), (.unavailable, .wordUnavailable),
      ] {
        let word = WordDouble()
        let model = ModelDouble()
        word.status = status
        let recognizer = makeRecognizer(
          wordRecognizer: word, processor: model, availability: GuidedResearchModelAvailability())
        recognizer.configure(ageYears: 8, enabled: true)
        self.prepare(recognizer, entry: entry)
        let input = request()
        let result = await self.check(recognizer, request: input)
        XCTAssertEqual(result.request, input)
        XCTAssertEqual(result.status, status)
        XCTAssertEqual(recognizer.observations[input.operationID]?.outcome, .notRun(reason))
        XCTAssertTrue(model.calls.isEmpty)
        XCTAssertEqual(model.readinessCalls, 0)
      }
    }

    func testSiblingReceiptAndFalseCleanupCannotRunModel() async {
      for sibling in [false, true] {
        let word = WordDouble()
        let model = ModelDouble()
        word.siblingReceipt = sibling
        word.cleanupConfirmed = sibling
        let recognizer = makeRecognizer(
          wordRecognizer: word, processor: model, availability: GuidedResearchModelAvailability())
        recognizer.configure(ageYears: 8, enabled: true)
        self.prepare(recognizer, entry: entry)
        let input = request()
        let receipt = await self.check(recognizer, request: input)
        XCTAssertEqual(receipt.request, input)
        XCTAssertFalse(receipt.cleanupConfirmed)
        XCTAssertEqual(
          recognizer.observations[input.operationID]?.outcome,
          .unavailable(sibling ? .wrongReceipt : .wordCleanupUnconfirmed))
        XCTAssertTrue(model.calls.isEmpty)
        XCTAssertEqual(model.readinessCalls, 0)
      }
    }

    func testFrozenRequestAgeEntryAndSeparateInitialRecheckObservations() async throws {
      let url = try generatedWAV()
      defer { try? FileManager.default.removeItem(at: url) }
      let word = WordDouble()
      let model = ModelDouble()
      let ownership = ProcessAudioFileOwnership()
      let recognizer = makeRecognizer(
        wordRecognizer: word, processor: model, ownership: ownership,
        availability: GuidedResearchModelAvailability())
      recognizer.configure(ageYears: 9, enabled: true)
      self.prepare(recognizer, entry: entry)
      for _ in 0..<2 {
        let input = request(url: url)
        let receipt = await self.check(recognizer, request: input)
        XCTAssertEqual(receipt.request, input)
        XCTAssertEqual(receipt.status, .matched)
        XCTAssertEqual(model.calls.last?.operationID, input.operationID)
        XCTAssertEqual(model.calls.last?.recording.url, input.fileURL)
        XCTAssertEqual(model.calls.last?.entry, entry)
        XCTAssertEqual(model.calls.last?.age, 9)
        XCTAssertEqual(recognizer.observations[input.operationID]?.request, input)
        XCTAssertEqual(recognizer.observations[input.operationID]?.entryID, entry.id)
        let retained = try XCTUnwrap(recognizer.observations[input.operationID]?.researchResult)
        XCTAssertEqual(retained.context.operationID, input.operationID)
        XCTAssertEqual(retained.context.ageYears, 9)
        XCTAssertEqual(retained.targets.first?.subjectiveCorpusRatingProbabilities, [0.1, 0.2, 0.7])
        XCTAssertEqual(
          recognizer.observations[input.operationID]?.outcome,
          .processedUnverified(milliseconds: 12))
      }
      XCTAssertEqual(recognizer.observations.count, 2)
      XCTAssertEqual(model.calls.count, 2)
      XCTAssertTrue(ownership.protectedURLs.isEmpty)
    }

    func testCancellationDuringWordHoldsBorrowAndFreezesConfigurationUntilActualReturn() async {
      let word = WordDouble()
      let model = ModelDouble()
      let ownership = ProcessAudioFileOwnership()
      word.hold = true
      let recognizer = makeRecognizer(
        wordRecognizer: word, processor: model, ownership: ownership,
        availability: GuidedResearchModelAvailability())
      recognizer.configure(ageYears: 8, enabled: true)
      self.prepare(recognizer, entry: entry)
      let started = expectation(description: "word started")
      word.started = { started.fulfill() }
      let input = request()
      let owner = UUID()
      retainFixture(input.fileURL, owner: owner, ownership: ownership)
      let task = Task { await self.check(recognizer, request: input) }
      let wordStarted = await XCTWaiter.fulfillment(of: [started], timeout: 2)
      XCTAssertEqual(wordStarted, .completed)
      XCTAssertFalse(recognizer.configure(ageYears: 10, enabled: false))
      XCTAssertFalse(self.prepare(recognizer, entry: entry))
      let sibling = await self.check(recognizer, request: request())
      XCTAssertEqual(sibling.status, .unavailable)
      XCTAssertEqual(word.requests.count, 1)
      recognizer.cancel(operationID: UUID())
      XCTAssertTrue(word.cancelled.isEmpty)
      recognizer.cancel(operationID: input.operationID)
      XCTAssertEqual(word.cancelled, [input.operationID])
      XCTAssertFalse(ownership.canRemove(input.fileURL, owner: owner))
      XCTAssertNil(recognizer.observations[input.operationID])
      word.release()
      let receipt = await task.value
      XCTAssertEqual(receipt.status, .cancelled)
      XCTAssertEqual(recognizer.observations[input.operationID]?.outcome, .cancelled)
      XCTAssertTrue(model.calls.isEmpty)
      XCTAssertEqual(model.readinessCalls, 0)
      XCTAssertTrue(ownership.canRemove(input.fileURL, owner: owner))
    }

    func testCancellationDuringModelWaitsForActualReturnAndNeverRecordsSuccess() async throws {
      let url = try generatedWAV()
      defer { try? FileManager.default.removeItem(at: url) }
      let word = WordDouble()
      let model = ModelDouble()
      let ownership = ProcessAudioFileOwnership()
      word.ownership = ownership
      model.hold = true
      let recognizer = makeRecognizer(
        wordRecognizer: word, processor: model, ownership: ownership,
        availability: GuidedResearchModelAvailability())
      recognizer.configure(ageYears: 8, enabled: true)
      self.prepare(recognizer, entry: entry)
      let started = expectation(description: "model started")
      model.started = { started.fulfill() }
      let input = request(url: url)
      let owner = UUID()
      retainFixture(url, owner: owner, ownership: ownership)
      let task = Task { await self.check(recognizer, request: input) }
      let modelStarted = await XCTWaiter.fulfillment(of: [started], timeout: 2)
      XCTAssertEqual(modelStarted, .completed)
      // Exercise caller cancellation, in addition to the explicit coordinator route.
      task.cancel()
      XCTAssertFalse(ownership.canRemove(url, owner: owner))
      XCTAssertNil(recognizer.observations[input.operationID])
      XCTAssertFalse(recognizer.configure(ageYears: nil, enabled: false))
      model.release()
      let receipt = await task.value
      XCTAssertEqual(receipt.status, .cancelled)
      XCTAssertEqual(recognizer.observations[input.operationID]?.outcome, .cancelled)
      XCTAssertFalse(model.cancellationSeen)
      XCTAssertNil(recognizer.observations[input.operationID]?.researchResult)
      XCTAssertTrue(ownership.canRemove(url, owner: owner))
      XCTAssertEqual(recognizer.processingState, .idle)
      // A same-take retry has a new operation; current display must use that
      // operation rather than an arbitrary dictionary entry for this take.
      model.hold = false
      let retry = LocalWordRecognitionRequest(
        operationID: UUID(), tryID: input.tryID, fileURL: input.fileURL,
        expectedWord: input.expectedWord)
      let retried = await self.check(recognizer, request: retry)
      XCTAssertEqual(retried.status, .matched)
      XCTAssertEqual(recognizer.latestObservationOperationID, retry.operationID)
      XCTAssertEqual(recognizer.observations[input.operationID]?.outcome, .cancelled)
      XCTAssertEqual(
        recognizer.observations[retry.operationID]?.outcome, .processedUnverified(milliseconds: 12))
    }

    func testModelFailureKeepsWordStatusAndPausesAcrossOptOutAndBackIn() async throws {
      let url = try generatedWAV()
      defer { try? FileManager.default.removeItem(at: url) }
      let word = WordDouble()
      let model = ModelDouble()
      model.error = ResearchAssessmentError.timeout
      let recognizer = makeRecognizer(
        wordRecognizer: word, processor: model, availability: GuidedResearchModelAvailability())
      recognizer.configure(ageYears: 8, enabled: true)
      self.prepare(recognizer, entry: entry)
      let first = request(url: url)
      let receipt = await self.check(recognizer, request: first)
      XCTAssertEqual(receipt.status, .matched)
      XCTAssertTrue(receipt.cleanupConfirmed)
      XCTAssertTrue(recognizer.modelCallsPaused)
      XCTAssertEqual(
        recognizer.observations[first.operationID]?.outcome, .unavailable(.serverCleanupUnknown))
      recognizer.configure(ageYears: nil, enabled: false)
      recognizer.configure(ageYears: 8, enabled: true)
      let second = request(url: url)
      let secondReceipt = await self.check(recognizer, request: second)
      XCTAssertEqual(secondReceipt.status, .matched)
      XCTAssertEqual(word.requests.count, 2)
      XCTAssertEqual(model.calls.count, 1)
      XCTAssertEqual(recognizer.observations[second.operationID]?.outcome, .notRun(.paused))
    }

    func testAdmissionOnlyResponseIsNotFullModelSuccess() async throws {
      let url = try generatedWAV()
      defer { try? FileManager.default.removeItem(at: url) }
      let word = WordDouble()
      let model = ModelDouble()
      model.result = .admissionProcessed(milliseconds: 3)
      let recognizer = makeRecognizer(
        wordRecognizer: word, processor: model, availability: GuidedResearchModelAvailability())
      recognizer.configure(ageYears: 8, enabled: true)
      self.prepare(recognizer, entry: entry)
      let input = request(url: url)
      let receipt = await self.check(recognizer, request: input)
      XCTAssertEqual(receipt.status, .matched)
      XCTAssertTrue(recognizer.modelCallsPaused)
      XCTAssertEqual(
        recognizer.observations[input.operationID]?.outcome, .unavailable(.serverCleanupUnknown))
    }

    func testSynchronousObservationCancellationRevokesTerminalSuccess() async throws {
      let url = try generatedWAV()
      defer { try? FileManager.default.removeItem(at: url) }
      let word = WordDouble()
      let model = ModelDouble()
      let recognizer = makeRecognizer(
        wordRecognizer: word, processor: model, availability: GuidedResearchModelAvailability())
      recognizer.configure(ageYears: 8, enabled: true)
      self.prepare(recognizer, entry: entry)
      let input = request(url: url)
      let subscription = recognizer.$observations.sink { observations in
        if let outcome = observations[input.operationID]?.outcome,
          case .processedUnverified = outcome
        {
          recognizer.cancel(operationID: input.operationID)
        }
      }
      let receipt = await self.check(recognizer, request: input)
      XCTAssertEqual(receipt.status, .cancelled)
      XCTAssertEqual(recognizer.observations[input.operationID]?.outcome, .cancelled)
      XCTAssertNil(recognizer.observations[input.operationID]?.researchResult)
      withExtendedLifetime(subscription) {}
    }

    func testUnavailableTimeoutInferenceFailureAndUnknownReasonPauseEndpoint() async throws {
      let url = try generatedWAV()
      defer { try? FileManager.default.removeItem(at: url) }
      for reason in [
        "timeout", "inference_failed", "unrecognized_future_reason", "SILENCE", "silence ",
        "clipping_future", "",
      ] {
        let word = WordDouble()
        let model = ModelDouble()
        let availability = GuidedResearchModelAvailability()
        model.result = .unavailable(reason: reason)
        let recognizer = makeRecognizer(
          wordRecognizer: word, processor: model, availability: availability)
        recognizer.configure(ageYears: 8, enabled: true)
        self.prepare(recognizer, entry: entry)
        let input = request(url: url)
        let receipt = await self.check(recognizer, request: input)
        XCTAssertEqual(receipt.status, .matched)
        XCTAssertTrue(receipt.cleanupConfirmed)
        XCTAssertTrue(availability.modelCallsPaused)
        XCTAssertEqual(
          recognizer.observations[input.operationID]?.outcome, .unavailable(.serverCleanupUnknown))
      }
    }

    func testPreflightUnavailableDoesNotPauseEndpoint() async throws {
      let url = try generatedWAV()
      defer { try? FileManager.default.removeItem(at: url) }
      let word = WordDouble()
      let model = ModelDouble()
      let availability = GuidedResearchModelAvailability()
      model.result = .unavailable(reason: "busy")
      let recognizer = makeRecognizer(
        wordRecognizer: word, processor: model, availability: availability)
      recognizer.configure(ageYears: 8, enabled: true)
      self.prepare(recognizer, entry: entry)
      let input = request(url: url)
      let receipt = await self.check(recognizer, request: input)
      XCTAssertEqual(receipt.status, .matched)
      XCTAssertFalse(availability.modelCallsPaused)
      XCTAssertEqual(
        recognizer.observations[input.operationID]?.outcome, .unavailable(.busy))
      model.result = nil
      let second = request(url: url)
      _ = await self.check(recognizer, request: second)
      XCTAssertEqual(model.calls.count, 2)
      XCTAssertEqual(
        recognizer.observations[second.operationID]?.outcome, .processedUnverified(milliseconds: 12)
      )
    }

    func testLegacyTimingOnlyResultsNeverAdmitResearchScores() async throws {
      let url = try generatedWAV()
      defer { try? FileManager.default.removeItem(at: url) }
      for milliseconds in [Double.nan, .infinity, -.infinity, -1, 12] {
        let word = WordDouble()
        let model = ModelDouble()
        let availability = GuidedResearchModelAvailability()
        model.result = .processedUnverified(milliseconds: milliseconds)
        let recognizer = makeRecognizer(
          wordRecognizer: word, processor: model, availability: availability)
        recognizer.configure(ageYears: 8, enabled: true)
        self.prepare(recognizer, entry: entry)
        let input = request(url: url)
        let receipt = await self.check(recognizer, request: input)
        XCTAssertEqual(receipt, .init(request: input, status: .matched, cleanupConfirmed: true))
        XCTAssertTrue(availability.modelCallsPaused)
        XCTAssertEqual(
          recognizer.observations[input.operationID]?.outcome, .unavailable(.serverCleanupUnknown))
      }
    }

    func testRepeatedTargetDistributionsRetainedAndMalformedTypedTargetsRejected() async throws {
      let repeated = try XCTUnwrap(PracticeLibrary.entries().first { $0.id == "n-middle-banana" })
      let url = try generatedWAV()
      defer { try? FileManager.default.removeItem(at: url) }
      for variant in ["valid", "missing", "reordered", "negative", "aboveOne", "nonfinite", "nonfiniteTiming"] {
        let model = ModelDouble()
        model.transform = { value in
          var targets = value.targets
          if variant == "missing" { targets.removeLast() }
          if variant == "reordered" { targets.reverse() }
          if ["negative", "aboveOne", "nonfinite"].contains(variant) {
            let first = targets[0]
            let probabilities: [Double] = variant == "negative" ? [-0.1, 0.2, 0.9]
              : variant == "aboveOne" ? [1.1, 0, 0] : [.nan, 0.2, 0.8]
            targets[0] = .init(id: first.id, wordIndex: first.wordIndex, phoneIndex: first.phoneIndex,
              targetPhone: first.targetPhone, subjectiveCorpusRatingProbabilities: probabilities)
          }
          return .init(context: value.context, model: value.model, targets: targets,
            timingMilliseconds: variant == "nonfiniteTiming" ? .init(total: .nan, inference: 0) : value.timingMilliseconds)
        }
        let recognizer = makeRecognizer(wordRecognizer: WordDouble(), processor: model,
          availability: GuidedResearchModelAvailability())
        recognizer.configure(ageYears: 8, enabled: true)
        self.prepare(recognizer, entry: repeated)
        let input = request(word: repeated.prompt.word, url: url)
        let receipt = await self.check(recognizer, request: input)
        XCTAssertEqual(receipt.status, .matched)
        let observation = try XCTUnwrap(recognizer.observations[input.operationID])
        if variant == "valid" {
          let result = try XCTUnwrap(observation.researchResult)
          XCTAssertEqual(result.targets.map(\.subjectiveCorpusRatingProbabilities), [[0.1, 0.2, 0.7], [0.7, 0.2, 0.1]])
          XCTAssertEqual(result.targets.map(\.id), try ResearchAssessmentClient.prompt(for: repeated).targets.map(\.id))
        } else {
          XCTAssertNil(observation.researchResult, variant)
          XCTAssertEqual(observation.outcome, .unavailable(.serverCleanupUnknown), variant)
          XCTAssertTrue(recognizer.modelCallsPaused, variant)
        }
      }
    }

    func testRejectsTypedResultForWrongTakeAudioPromptRequestAgeEntryOrModel() async throws {
      let url = try generatedWAV()
      defer { try? FileManager.default.removeItem(at: url) }
      for field in ["operation", "audio", "prompt", "request", "age", "entry", "model"] {
        let model = ModelDouble()
        model.transform = { value in
          let c = value.context
          return .init(context: .init(
            operationID: field == "operation" ? UUID() : c.operationID,
            entryID: field == "entry" ? "another-entry" : c.entryID,
            ageYears: field == "age" ? 12 : c.ageYears,
            requestSHA256: field == "request" ? String(repeating: "0", count: 64) : c.requestSHA256,
            audioSHA256: field == "audio" ? String(repeating: "0", count: 64) : c.audioSHA256,
            promptSHA256: field == "prompt" ? String(repeating: "0", count: 64) : c.promptSHA256),
            model: .init(id: value.model.id,
              manifestSha256: field == "model" ? "wrong-manifest" : value.model.manifestSha256),
            targets: value.targets, timingMilliseconds: value.timingMilliseconds)
        }
        let recognizer = makeRecognizer(wordRecognizer: WordDouble(), processor: model,
          availability: GuidedResearchModelAvailability())
        recognizer.configure(ageYears: 8, enabled: true)
        self.prepare(recognizer, entry: entry)
        let input = request(url: url)
        _ = await self.check(recognizer, request: input)
        XCTAssertEqual(recognizer.observations[input.operationID]?.outcome,
          .unavailable(.serverCleanupUnknown), field)
        XCTAssertNil(recognizer.observations[input.operationID]?.researchResult, field)
        XCTAssertTrue(recognizer.modelCallsPaused, field)
      }
    }

    func testExactNineCleanupSafeRejectionsKeepDistinctFrozenNotesAndAllowLaterOperations()
      async throws
    {
      let cases = cleanupSafeRejections
      XCTAssertEqual(cases.count, 9)
      XCTAssertEqual(
        Set(cases.map(\.code)),
        Set([
          "silence", "clipping", "invalid_audio", "audio_too_long", "unsupported_target",
          "model_unavailable", "busy", "invalid_request", "age_out_of_range",
        ]))
      XCTAssertEqual(Set(cases.map(\.note)).count, 9)
      for index in cases.indices {
        for previous in cases[..<index] {
          XCTAssertNotEqual(cases[index].reason, previous.reason)
        }
      }
      let url = try generatedWAV()
      defer { try? FileManager.default.removeItem(at: url) }
      for rejection in cases {
        let word = WordDouble()
        let model = ModelDouble()
        let ownership = ProcessAudioFileOwnership()
        let availability = GuidedResearchModelAvailability()
        word.ownership = ownership
        model.result = .unavailable(reason: rejection.code)
        let recognizer = makeRecognizer(
          wordRecognizer: word, processor: model, ownership: ownership, availability: availability)
        recognizer.configure(ageYears: 9, enabled: true)
        self.prepare(recognizer, entry: entry)
        XCTAssertTrue(model.calls.isEmpty)
        XCTAssertEqual(model.readinessCalls, 0)
        let input = request(url: url)
        let receipt = await self.check(recognizer, request: input)
        XCTAssertEqual(receipt, .init(request: input, status: .matched, cleanupConfirmed: true))
        let first = try XCTUnwrap(recognizer.observations[input.operationID])
        XCTAssertEqual(first.request, input)
        XCTAssertEqual(first.entryID, entry.id)
        XCTAssertEqual(first.outcome, .unavailable(rejection.reason))
        XCTAssertEqual(first.note, rejection.note)
        XCTAssertEqual(word.requests, [input])
        XCTAssertEqual(model.calls.count, 1)
        XCTAssertEqual(model.calls[0].operationID, input.operationID)
        XCTAssertEqual(model.calls[0].recording.url, input.fileURL)
        XCTAssertEqual(model.calls[0].entry, entry)
        XCTAssertEqual(model.calls[0].age, 9)
        XCTAssertFalse(availability.modelCallsPaused)
        XCTAssertTrue(ownership.protectedURLs.isEmpty)
        let repeated = await self.check(recognizer, request: input)
        XCTAssertEqual(repeated.status, .unavailable)
        XCTAssertEqual(word.requests.count, 1)
        XCTAssertEqual(model.calls.count, 1)
        XCTAssertEqual(recognizer.observations[input.operationID], first)

        model.result = nil
        let later = request(url: url)
        let laterReceipt = await self.check(recognizer, request: later)
        XCTAssertNotEqual(later.operationID, input.operationID)
        XCTAssertNotEqual(later.tryID, input.tryID)
        XCTAssertEqual(
          laterReceipt, .init(request: later, status: .matched, cleanupConfirmed: true))
        XCTAssertEqual(word.requests, [input, later])
        XCTAssertEqual(model.calls.count, 2)
        XCTAssertEqual(
          recognizer.observations[later.operationID]?.outcome,
          .processedUnverified(milliseconds: 12))
        XCTAssertEqual(recognizer.observations[input.operationID], first)
        XCTAssertFalse(availability.modelCallsPaused)
        XCTAssertTrue(ownership.protectedURLs.isEmpty)
      }
    }

    func testCancellationDuringCleanupSafeRejectionWaitsForActualModelReturn() async throws {
      let url = try generatedWAV()
      defer { try? FileManager.default.removeItem(at: url) }
      let word = WordDouble()
      let model = ModelDouble()
      let ownership = ProcessAudioFileOwnership()
      let availability = GuidedResearchModelAvailability()
      model.result = .unavailable(reason: "clipping")
      model.hold = true
      let recognizer = makeRecognizer(
        wordRecognizer: word, processor: model, ownership: ownership, availability: availability)
      recognizer.configure(ageYears: 8, enabled: true)
      self.prepare(recognizer, entry: entry)
      let started = expectation(description: "model rejection held")
      model.started = { started.fulfill() }
      let input = request(url: url)
      let owner = UUID()
      retainFixture(url, owner: owner, ownership: ownership)
      let task = Task { await self.check(recognizer, request: input) }
      let modelStarted = await XCTWaiter.fulfillment(of: [started], timeout: 2)
      XCTAssertEqual(modelStarted, .completed)
      recognizer.cancel(operationID: input.operationID)
      XCTAssertEqual(recognizer.processingState, .cancelling(operationID: input.operationID))
      XCTAssertNil(recognizer.observations[input.operationID])
      XCTAssertFalse(ownership.canRemove(url, owner: owner))
      XCTAssertFalse(recognizer.configure(ageYears: nil, enabled: false))
      model.release()
      let receipt = await task.value
      XCTAssertEqual(receipt, .init(request: input, status: .cancelled, cleanupConfirmed: true))
      XCTAssertEqual(recognizer.observations[input.operationID]?.outcome, .cancelled)
      XCTAssertFalse(model.cancellationSeen)
      XCTAssertFalse(availability.modelCallsPaused)
      XCTAssertTrue(ownership.canRemove(url, owner: owner))
      XCTAssertEqual(model.calls.count, 1)
      XCTAssertEqual(recognizer.processingState, .idle)
    }

    func testSynchronousObservationCancellationRevokesEverySpecificRejection() async throws {
      let url = try generatedWAV()
      defer { try? FileManager.default.removeItem(at: url) }
      for rejection in cleanupSafeRejections {
        let word = WordDouble()
        let model = ModelDouble()
        let ownership = ProcessAudioFileOwnership()
        let availability = GuidedResearchModelAvailability()
        model.result = .unavailable(reason: rejection.code)
        let recognizer = makeRecognizer(
          wordRecognizer: word, processor: model, ownership: ownership, availability: availability)
        recognizer.configure(ageYears: 8, enabled: true)
        self.prepare(recognizer, entry: entry)
        let input = request(url: url)
        var specificObservationSeen = false
        let subscription = recognizer.$observations.sink { observations in
          if observations[input.operationID]?.outcome == .unavailable(rejection.reason) {
            specificObservationSeen = true
            recognizer.cancel(operationID: input.operationID)
          }
        }
        let receipt = await self.check(recognizer, request: input)
        XCTAssertTrue(specificObservationSeen)
        XCTAssertEqual(receipt, .init(request: input, status: .cancelled, cleanupConfirmed: true))
        XCTAssertEqual(recognizer.observations[input.operationID]?.outcome, .cancelled)
        XCTAssertEqual(word.cancelled, [input.operationID])
        XCTAssertEqual(model.calls.count, 1)
        XCTAssertFalse(availability.modelCallsPaused)
        XCTAssertTrue(ownership.protectedURLs.isEmpty)
        withExtendedLifetime(subscription) {}
      }
    }

    func testUnknownCleanupSurvivesRecognizerReconstructionWithSameEndpointAvailability()
      async throws
    {
      let url = try generatedWAV()
      defer { try? FileManager.default.removeItem(at: url) }
      let availability = GuidedResearchModelAvailability()
      do {
        let word = WordDouble()
        let model = ModelDouble()
        model.error = ResearchAssessmentError.serviceUnavailable
        let original = makeRecognizer(
          wordRecognizer: word, processor: model, availability: availability)
        original.configure(ageYears: 8, enabled: true)
        self.prepare(original, entry: entry)
        _ = await self.check(original, request: request(url: url))
        XCTAssertTrue(original.modelCallsPaused)
      }
      let nextWord = WordDouble()
      let nextModel = ModelDouble()
      let reconstructed = makeRecognizer(
        wordRecognizer: nextWord, processor: nextModel, availability: availability)
      XCTAssertTrue(reconstructed.modelCallsPaused)
      reconstructed.configure(ageYears: nil, enabled: false)
      reconstructed.configure(ageYears: 9, enabled: true)
      self.prepare(reconstructed, entry: entry)
      let input = request(url: url)
      let receipt = await self.check(reconstructed, request: input)
      XCTAssertEqual(receipt.status, .matched)
      XCTAssertEqual(nextWord.requests.count, 1)
      XCTAssertTrue(nextModel.calls.isEmpty)
      XCTAssertEqual(reconstructed.observations[input.operationID]?.outcome, .notRun(.paused))
    }

    func testReadinessFailureAllowsFreshOperationWithoutRewritingFirstObservation() async throws {
      let url = try generatedWAV()
      defer { try? FileManager.default.removeItem(at: url) }
      let word = WordDouble()
      let model = ModelDouble()
      let ownership = ProcessAudioFileOwnership()
      let availability = GuidedResearchModelAvailability()
      model.ready = false
      let recognizer = preparedRecognizer(
        word: word, model: model, ownership: ownership, availability: availability)
      let input = request(url: url)
      let receipt = await self.check(recognizer, request: input)
      let first = try XCTUnwrap(recognizer.observations[input.operationID])
      XCTAssertEqual(receipt, .init(request: input, status: .matched, cleanupConfirmed: true))
      XCTAssertEqual(first.request, input)
      XCTAssertEqual(first.entryID, entry.id)
      XCTAssertEqual(first.outcome, .unavailable(.serviceNotReady))
      XCTAssertEqual(
        first.note,
        "The local research service could not be reached or confirmed. Start the service on this Mac before checking a later recording. You can continue manual practice."
      )
      XCTAssertEqual(model.readinessCalls, 1)
      XCTAssertTrue(model.calls.isEmpty)
      XCTAssertFalse(availability.modelCallsPaused)
      XCTAssertTrue(ownership.protectedURLs.isEmpty)
      model.ready = true
      let later = request(url: url)
      let laterReceipt = await self.check(recognizer, request: later)
      XCTAssertEqual(laterReceipt, .init(request: later, status: .matched, cleanupConfirmed: true))
      XCTAssertEqual(model.readinessCalls, 2)
      XCTAssertEqual(model.calls.count, 1)
      XCTAssertEqual(model.calls.first?.operationID, later.operationID)
      XCTAssertEqual(recognizer.observations[input.operationID], first)
      XCTAssertEqual(
        recognizer.observations[later.operationID]?.outcome,
        .processedUnverified(milliseconds: 12))
      XCTAssertTrue(ownership.protectedURLs.isEmpty)
    }

    func testCancellationDuringReadinessRetainsBorrowUntilActualReturn() async throws {
      let url = try generatedWAV()
      defer { try? FileManager.default.removeItem(at: url) }
      let word = WordDouble()
      let model = ModelDouble()
      let ownership = ProcessAudioFileOwnership()
      let availability = GuidedResearchModelAvailability()
      model.holdReadiness = true
      let recognizer = preparedRecognizer(
        word: word, model: model, ownership: ownership, availability: availability)
      let input = request(url: url)
      let owner = UUID()
      ownership.retain(url, owner: owner)
      let started = expectation(description: "readiness started")
      model.readinessStarted = { started.fulfill() }
      let task = Task { await recognizer.check(request: input) }
      let reached = await XCTWaiter.fulfillment(of: [started], timeout: 2)
      XCTAssertEqual(reached, .completed)
      XCTAssertEqual(recognizer.processingState, .checkingService(operationID: input.operationID))
      XCTAssertEqual(
        recognizer.statusNote,
        "Checking whether the local research service is available…")
      task.cancel()
      XCTAssertFalse(ownership.canRemove(url, owner: owner))
      XCTAssertNil(recognizer.observations[input.operationID])
      XCTAssertFalse(recognizer.configure(ageYears: nil, enabled: false))
      XCTAssertTrue(model.calls.isEmpty)
      model.releaseReadiness()
      let receipt = await task.value
      XCTAssertEqual(receipt, .init(request: input, status: .cancelled, cleanupConfirmed: true))
      XCTAssertEqual(recognizer.observations[input.operationID]?.outcome, .cancelled)
      XCTAssertEqual(model.readinessCalls, 1)
      XCTAssertFalse(model.readinessCancellationSeen)
      XCTAssertTrue(model.calls.isEmpty)
      XCTAssertFalse(availability.modelCallsPaused)
      XCTAssertTrue(ownership.canRemove(url, owner: owner))
      XCTAssertEqual(recognizer.processingState, .idle)
    }

    func testSynchronousCheckingServiceCancellationStartsNeitherReadinessNorModel() async throws {
      let url = try generatedWAV()
      defer { try? FileManager.default.removeItem(at: url) }
      let word = WordDouble()
      let model = ModelDouble()
      let ownership = ProcessAudioFileOwnership()
      let availability = GuidedResearchModelAvailability()
      let recognizer = preparedRecognizer(
        word: word, model: model, ownership: ownership, availability: availability)
      let input = request(url: url)
      let subscription = recognizer.$processingState.sink { state in
        if state == .checkingService(operationID: input.operationID) {
          recognizer.cancel(operationID: input.operationID)
        }
      }
      let receipt = await recognizer.check(request: input)
      XCTAssertEqual(receipt.status, .cancelled)
      XCTAssertEqual(recognizer.observations[input.operationID]?.outcome, .cancelled)
      XCTAssertEqual(model.readinessCalls, 0)
      XCTAssertTrue(model.calls.isEmpty)
      XCTAssertFalse(availability.modelCallsPaused)
      XCTAssertTrue(ownership.protectedURLs.isEmpty)
      withExtendedLifetime(subscription) {}
    }

    func testSynchronousServiceNotReadyObservationCancellationRevokesResult() async throws {
      let url = try generatedWAV()
      defer { try? FileManager.default.removeItem(at: url) }
      let word = WordDouble()
      let model = ModelDouble()
      let ownership = ProcessAudioFileOwnership()
      let availability = GuidedResearchModelAvailability()
      model.ready = false
      let recognizer = preparedRecognizer(
        word: word, model: model, ownership: ownership, availability: availability)
      let input = request(url: url)
      let subscription = recognizer.$observations.sink { observations in
        if observations[input.operationID]?.outcome == .unavailable(.serviceNotReady) {
          recognizer.cancel(operationID: input.operationID)
        }
      }
      let receipt = await recognizer.check(request: input)
      XCTAssertEqual(receipt.status, .cancelled)
      XCTAssertEqual(recognizer.observations[input.operationID]?.outcome, .cancelled)
      XCTAssertEqual(model.readinessCalls, 1)
      XCTAssertTrue(model.calls.isEmpty)
      XCTAssertFalse(availability.modelCallsPaused)
      XCTAssertTrue(ownership.protectedURLs.isEmpty)
      withExtendedLifetime(subscription) {}
    }

    func testSharedPauseDuringReadinessPreventsModelAndRemainsPaused() async throws {
      let url = try generatedWAV()
      defer { try? FileManager.default.removeItem(at: url) }
      let word = WordDouble()
      let model = ModelDouble()
      let ownership = ProcessAudioFileOwnership()
      let availability = GuidedResearchModelAvailability()
      model.holdReadiness = true
      let recognizer = preparedRecognizer(
        word: word, model: model, ownership: ownership, availability: availability)
      let input = request(url: url)
      let started = expectation(description: "readiness waiting for shared pause")
      model.readinessStarted = { started.fulfill() }
      let task = Task { await recognizer.check(request: input) }
      let reached = await XCTWaiter.fulfillment(of: [started], timeout: 2)
      XCTAssertEqual(reached, .completed)
      availability.pauseForUnknownCleanup()
      model.releaseReadiness()
      let receipt = await task.value
      XCTAssertEqual(receipt, .init(request: input, status: .matched, cleanupConfirmed: true))
      XCTAssertEqual(recognizer.observations[input.operationID]?.outcome, .notRun(.paused))
      XCTAssertTrue(model.calls.isEmpty)
      XCTAssertEqual(model.readinessCalls, 1)
      XCTAssertTrue(availability.modelCallsPaused)
      XCTAssertTrue(ownership.protectedURLs.isEmpty)
      _ = await recognizer.check(request: request(url: url))
      XCTAssertEqual(model.readinessCalls, 1)
      XCTAssertTrue(model.calls.isEmpty)
    }

    func testSynchronousProcessingPublicationPauseOrCancellationPreventsModel() async throws {
      let url = try generatedWAV()
      defer { try? FileManager.default.removeItem(at: url) }
      for cancel in [false, true] {
        let word = WordDouble()
        let model = ModelDouble()
        let ownership = ProcessAudioFileOwnership()
        let availability = GuidedResearchModelAvailability()
        let recognizer = preparedRecognizer(
          word: word, model: model, ownership: ownership, availability: availability)
        let input = request(url: url)
        let subscription = recognizer.$processingState.sink { state in
          if state == .processingModel(operationID: input.operationID) {
            if cancel {
              recognizer.cancel(operationID: input.operationID)
            } else {
              availability.pauseForUnknownCleanup()
            }
          }
        }
        let receipt = await recognizer.check(request: input)
        XCTAssertEqual(receipt.status, cancel ? .cancelled : .matched)
        XCTAssertEqual(
          recognizer.observations[input.operationID]?.outcome,
          cancel ? .cancelled : .notRun(.paused))
        XCTAssertEqual(model.readinessCalls, 1)
        XCTAssertTrue(model.calls.isEmpty)
        XCTAssertEqual(availability.modelCallsPaused, !cancel)
        XCTAssertTrue(ownership.protectedURLs.isEmpty)
        withExtendedLifetime(subscription) {}
      }
    }

    func testInvalidRecordingAndAlreadyPausedEndpointSkipReadiness() async {
      let word = WordDouble()
      let model = ModelDouble()
      let ownership = ProcessAudioFileOwnership()
      let availability = GuidedResearchModelAvailability()
      let recognizer = preparedRecognizer(
        word: word, model: model, ownership: ownership, availability: availability)
      let invalid = request()
      _ = await recognizer.check(request: invalid)
      XCTAssertEqual(
        recognizer.observations[invalid.operationID]?.outcome,
        .unavailable(.invalidRecording))
      availability.pauseForUnknownCleanup()
      let paused = request()
      _ = await recognizer.check(request: paused)
      XCTAssertEqual(recognizer.observations[paused.operationID]?.outcome, .notRun(.paused))
      XCTAssertEqual(model.readinessCalls, 0)
      XCTAssertTrue(model.calls.isEmpty)
      XCTAssertTrue(ownership.protectedURLs.isEmpty)
    }

    func testReadinessSuccessThenProcessingErrorStillPausesWithoutFutureReadiness() async throws {
      let url = try generatedWAV()
      defer { try? FileManager.default.removeItem(at: url) }
      let word = WordDouble()
      let model = ModelDouble()
      let ownership = ProcessAudioFileOwnership()
      let availability = GuidedResearchModelAvailability()
      model.error = ResearchAssessmentError.timeout
      let recognizer = preparedRecognizer(
        word: word, model: model, ownership: ownership, availability: availability)
      let input = request(url: url)
      let receipt = await recognizer.check(request: input)
      XCTAssertEqual(receipt.status, .matched)
      XCTAssertEqual(
        recognizer.observations[input.operationID]?.outcome,
        .unavailable(.serverCleanupUnknown))
      XCTAssertTrue(availability.modelCallsPaused)
      _ = await recognizer.check(request: request(url: url))
      XCTAssertEqual(model.readinessCalls, 1)
      XCTAssertEqual(model.calls.count, 1)
      XCTAssertTrue(ownership.protectedURLs.isEmpty)
    }

    func testLegacyProcessorWithoutReadinessCapabilityRetainsExistingBehavior() async throws {
      let url = try generatedWAV()
      defer { try? FileManager.default.removeItem(at: url) }
      let model = LegacyModelDouble()
      let ownership = ProcessAudioFileOwnership()
      let recognizer = preparedRecognizer(
        word: WordDouble(), model: model, ownership: ownership,
        availability: GuidedResearchModelAvailability())
      let input = request(url: url)
      let receipt = await recognizer.check(request: input)
      XCTAssertEqual(receipt.status, .matched)
      XCTAssertEqual(model.calls, 1)
      XCTAssertEqual(
        recognizer.observations[input.operationID]?.outcome,
        .processedUnverified(milliseconds: 7))
      XCTAssertTrue(ownership.protectedURLs.isEmpty)
    }

    private func preparedRecognizer(
      word: WordDouble, model: any ResearchAssessmentProcessing,
      ownership: ProcessAudioFileOwnership, availability: GuidedResearchModelAvailability
    ) -> GuidedResearchModelRecognizer {
      let recognizer = GuidedResearchModelRecognizer(
        wordRecognizer: word, processor: model,
        ownership: ownership, availability: availability)
      XCTAssertTrue(recognizer.configure(ageYears: 9, enabled: true))
      XCTAssertTrue(recognizer.prepare(entry: entry))
      return recognizer
    }

    private func generatedWAV() throws -> URL {
      var data = Data()
      func text(_ value: String) { data.append(contentsOf: value.utf8) }
      func little(_ value: Int, _ count: Int) {
        for index in 0..<count { data.append(UInt8((value >> (index * 8)) & 255)) }
      }
      text("RIFF")
      little(36 + 3200, 4)
      text("WAVEfmt ")
      little(16, 4)
      little(1, 2)
      little(1, 2)
      little(16_000, 4)
      little(32_000, 4)
      little(2, 2)
      little(16, 2)
      text("data")
      little(3200, 4)
      data.append(Data(repeating: 0, count: 3200))
      let url = FileManager.default.temporaryDirectory.appendingPathComponent(
        "generated-\(UUID()).wav")
      try data.write(to: url)
      return url
    }
  }
#endif
