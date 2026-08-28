#if DEBUG && targetEnvironment(simulator)
  import Combine
  import Foundation
  import SwiftUI

  enum LocalGuidedGeneratedCase: String, CaseIterable {
    case setup, practice, recheck, heldFinish, heldClose, timeout, wordGuess, retake, practiceQuality
    case setupAX, practiceAX, recheckAX, heldFinishAX, heldCloseAX, timeoutAX, wordGuessAX, retakeAX, practiceQualityAX
    case researchDetails, researchDetailsAX
    case practiceTimeoutRetry, practiceTimeoutRetryAX
    var largeText: Bool { rawValue.hasSuffix("AX") }
    var base: Self {
      largeText ? Self(rawValue: String(rawValue.dropLast(2)))! : self
    }
    var holdsCheck: Bool {
      base == .heldFinish || base == .heldClose || base == .practiceTimeoutRetry
    }
  }

  /// Closed DEBUG/simulator fixture. The product view has one injected managed owner.
  /// Seeds are generated coordinator actions, never edits to ledger or presentation state.
  struct LocalGuidedGeneratedHost: View {
    @StateObject private var resources: LocalGuidedGeneratedResources
    @State private var presented = true
    let testCase: LocalGuidedGeneratedCase

    init(testCase: LocalGuidedGeneratedCase, runID: UUID) {
      self.testCase = testCase
      _resources = StateObject(
        wrappedValue: LocalGuidedGeneratedResources(testCase: testCase, runID: runID))
    }

    var body: some View {
      Group {
        if presented {
          Color.clear
        } else {
          VStack(spacing: 8) {
            Text("Generated guided check closed")
              .accessibilityIdentifier("cadence.generated-guided.closed")
            Text(resources.filesLine)
              .accessibilityIdentifier("cadence.generated-guided.closed-files")
            Text(resources.historyLine)
              .accessibilityIdentifier("cadence.generated-guided.closed-history")
          }
        }
      }
      .fullScreenCover(isPresented: $presented) {
        Group {
          switch resources.seedState {
          case .ready:
            LocalGuidedReviewView(session: resources.session)
          case .preparing:
            Text("Preparing generated stage")
          case .failed:
            // Fail closed: no replacement owner, production root or model fallback.
            Text("Generated stage setup failed")
              .accessibilityIdentifier("cadence.generated-guided.failed")
          }
        }
        .environment(\.dynamicTypeSize, testCase.largeText ? .accessibility5 : .large)
        .safeAreaInset(edge: .top) { banner }
        .task { await resources.prepareSeed() }
      }
    }

    private var banner: some View {
      VStack(alignment: .leading, spacing: 2) {
        Text("Generated guided fixture — no sensors, audio output, network or models")
          .accessibilityIdentifier("cadence.generated-guided.banner")
        Text(resources.seedLine).accessibilityIdentifier("cadence.generated-guided.seed")
        Text(resources.filesLine)
          .monospacedDigit()
          .accessibilityIdentifier("cadence.generated-guided.files")
        Text(resources.checkLine).accessibilityIdentifier("cadence.generated-guided.checks")
        Text(resources.historyLine).accessibilityIdentifier("cadence.generated-guided.history")
        Text(resources.receiptLine).accessibilityIdentifier("cadence.generated-guided.receipts")
        if testCase.base == .researchDetails {
          Text(resources.modelLine).accessibilityIdentifier("cadence.generated-guided.model-calls")
        }
        if testCase.base == .practiceTimeoutRetry {
          Text(resources.retryBindingLine)
            .accessibilityIdentifier("cadence.generated-guided.retry-binding")
        }
        if testCase.holdsCheck {
          Button {
            resources.recognizer.finish()
          } label: {
            Text("Release generated exact check receipt")
              .frame(minWidth: 44, minHeight: 44, alignment: .leading)
              .contentShape(Rectangle())
          }
          .buttonStyle(.plain)
          .disabled(!resources.recognizer.isPending)
          .accessibilityIdentifier("cadence.generated-guided.release")
        }
      }
      .font(.caption2)
      .fixedSize(horizontal: false, vertical: true)
      .environment(\.dynamicTypeSize, .large)
      .frame(maxWidth: .infinity, alignment: .leading)
      .padding(8)
      .background(.thinMaterial)
    }
  }

  @MainActor
  final class LocalGuidedGeneratedResources: ObservableObject {
    enum SeedState { case preparing, ready, failed }
    let session: LocalGuidedReviewSession
    let capture: LocalGuidedGeneratedCapture
    let recognizer: LocalGuidedGeneratedRecognizer
    let history: PracticeParticipationStore
    let files: ProcessAudioFileOwnership
    private let researchProcessor: LocalGuidedGeneratedResearchProcessor?
    @Published private(set) var seedState: SeedState = .preparing
    @Published private(set) var seedLine = "Generated stage: preparing"
    @Published private(set) var filesLine = ""
    @Published private(set) var checkLine = ""
    @Published private(set) var retryBindingLine = "Generated retry binding: no retry"
    @Published private(set) var historyLine = ""
    @Published private(set) var receiptLine = "Generated practice receipts: 0 exact"
    @Published private(set) var modelLine = "Generated model calls: 0"
    private let testCase: LocalGuidedGeneratedCase
    private var seedStarted = false
    private var subscriptions: Set<AnyCancellable> = []
    private var playbackIDs: Set<UUID> = []

    init(testCase: LocalGuidedGeneratedCase, runID: UUID) {
      precondition(runID != UUID(uuidString: "00000000-0000-0000-0000-000000000000"))
      self.testCase = testCase.base
      let hardware = AudioHardwareOwnership()
      let files = ProcessAudioFileOwnership()
      self.files = files
      capture = LocalGuidedGeneratedCapture(
        hardware: hardware, files: files,
        durations: testCase.base == .practiceQuality ? [0.6, 0.8, 1.0, 0.6, 0.8, 0.2, 0.8]
          : testCase.base == .retake ? [0.2, 0.8] : [0.6, 0.8, 1.0])
      recognizer = LocalGuidedGeneratedRecognizer(
        files: files, holdsResult: testCase.holdsCheck,
        returnedStatus: testCase.base == .timeout ? .timedOut
          : testCase.base == .wordGuess ? .notMatched : .matched,
        alternatives: testCase.base == .wordGuess ? ["wall", "call", "fall", "tall"] : [],
        heldAfterRequestCount: testCase.base == .practiceTimeoutRetry ? 5 : 0,
        timeoutRequestNumber: testCase.base == .practiceTimeoutRetry ? 6 : nil)
      let processor = testCase.base == .researchDetails ? LocalGuidedGeneratedResearchProcessor() : nil
      researchProcessor = processor
      let researchModel: GuidedResearchModelRecognizer?
      if let processor {
        researchModel = GuidedResearchModelRecognizer(
          wordRecognizer: recognizer, processor: processor, ownership: files,
          availability: GuidedResearchModelAvailability())
      } else {
        researchModel = nil
      }
      let wordChecker: any LocalWordRecognizing = if let researchModel { researchModel } else { recognizer }
      let player = ResearchAcknowledgedPlaybackUITestFixture(
        completion: .explicitStop, ownership: hardware, fileOwnership: files)
      let recovery = ProcessPracticeMirrorRecovery()
      let runtime = PracticeMirrorRuntime(
        recovery: recovery, presentation: PracticeMirrorPresentation(),
        factory: { _ in LocalGuidedInertMirrorDriver() })
      let mirror = DirectPracticeMirror(
        permission: LocalGuidedUnsupportedMirrorPermission(), runtime: runtime, recovery: recovery)
      let directory = FileManager.default.temporaryDirectory.appendingPathComponent(
        "generated-local-guided-history-\(runID)-\(UUID())", isDirectory: true)
      history = PracticeParticipationStore(
        fileURL: directory.appendingPathComponent("participation.json"))
      let starter = PracticeLibrary.starterSound
      let sound = PracticeSound(
        id: starter.id, symbol: starter.symbol, name: starter.name, position: starter.position,
        prompts: [starter.prompts[0]])
      let media = DirectPracticeSession(
        sound: sound, capturer: capture, player: player, mirror: mirror, history: history,
        managedForGuided: true, wordRecognizer: wordChecker,
        cleanupHardwareOwnership: hardware, cleanupFileOwnership: files)
      if let researchModel {
        session = LocalGuidedReviewSession(history: history, media: media, researchModel: researchModel)
        precondition(session.configureResearchModel(enabled: true, ageYears: 9))
      } else {
        session = LocalGuidedReviewSession(history: history, media: media)
      }
      processor?.changed = { [weak self] in self?.refresh() }
      capture.changed = { [weak self] in self?.refresh() }
      recognizer.changed = { [weak self] in self?.refresh() }
      capture.cleanupStatePublisher.sink { [weak self] _ in
        MainActor.assumeIsolated { self?.refresh() }
      }.store(in: &subscriptions)
      history.$entries.sink { [weak self] entries in
        MainActor.assumeIsolated { self?.receiveHistory(entries) }
      }.store(in: &subscriptions)
      player.statePublisher.sink { [weak self] state in
        MainActor.assumeIsolated {
          guard let self else { return }
          if case .playing(let operation) = state { self.playbackIDs.insert(operation.id) }
          self.refresh()
        }
      }.store(in: &subscriptions)
      session.$ledger.sink { [weak self] ledger in
        MainActor.assumeIsolated { self?.receiveLedger(ledger) }
      }.store(in: &subscriptions)
      refresh()
    }

    func prepareSeed() async {
      guard !seedStarted else { return }
      seedStarted = true
      guard testCase == .practice || testCase == .practiceQuality || testCase == .recheck
        || testCase == .researchDetails || testCase == .practiceTimeoutRetry else {
        seedLine = "Generated stage: unseeded setup"
        seedState = .ready
        return
      }
      await session.startInitialReview()
      for index in 0..<5 {
        guard session.ledger?.stage == .initialReview,
          session.media.currentPrompt.id == session.setupEntries[index].id,
          await recordGeneratedTake()
        else {
          failSeed()
          return
        }
        await session.checkCurrentWord()
        guard session.ledger?.initialRound.rows[index].state == .finished(.matched) else {
          failSeed()
          return
        }
        await session.advanceVisit()
      }
      guard session.ledger?.stage == .choosingPractice, history.entries.isEmpty,
        capture.retainedCount == 0, recognizer.requests.count == 5
      else {
        failSeed()
        return
      }
      if testCase == .practice || testCase == .practiceQuality || testCase == .researchDetails
        || testCase == .practiceTimeoutRetry {
        seedLine = "Generated stage: five settled first checks; no choices preselected"
        seedState = .ready
        return
      }
      let pig = session.setupEntries[1].id
      session.togglePracticeSelection(entryID: pig)
      await session.startPractice()
      guard session.media.currentPrompt.id == pig, await recordGeneratedTake() else {
        failSeed()
        return
      }
      await session.advanceVisit()
      guard session.ledger?.stage == .readyToRecheck,
        history.entries.count == 1, history.entries[0].soundID == "p",
        history.entries[0].wordCount == 1, capture.retainedCount == 0,
        session.ledger?.practiceRows.first?.visit?.visitID == history.entries[0].id
      else {
        failSeed()
        return
      }
      seedLine = "Generated stage: five settled first checks; one fresh pig practice saved"
      seedState = .ready
    }

    private func recordGeneratedTake() async -> Bool {
      await session.media.startRecording()
      guard session.media.phase == .recording else { return false }
      session.media.stopRecording()
      return session.media.latestTry != nil && session.media.canCheckWordsInLatestTry
        || session.ledger?.stage == .practice && session.media.latestTry != nil
    }
    private func failSeed() {
      seedLine = "Generated stage: failed closed"
      seedState = .failed
      // Preserve owner and resource evidence. No speculative discard or fallback.
    }
    private func receiveHistory(_ entries: [PracticeParticipation]) {
      let rows = entries.map { "\($0.soundID):\($0.wordCount)" }.sorted().joined(separator: ",")
      historyLine = "Generated history: \(entries.count) rows [\(rows)]"
    }
    private func receiveLedger(_ ledger: LocalGuidedReviewLedger?) {
      let exact =
        ledger?.practiceRows.filter { row in
          guard row.state == .finished(.finished), let visit = row.visit,
            row.freshTryID != nil
          else { return false }
          return history.entries.contains {
            $0.id == visit.visitID && $0.soundID == row.entry.soundID && $0.wordCount == 1
          }
        }.count ?? 0
      receiptLine = "Generated practice receipts: \(exact) exact"
    }
    private func refresh() {
      filesLine =
        "Generated files: made \(capture.createdURLs.count), kept \(capture.retainedCount)"
        + " · permission requests \(capture.permissionRequests) · playback starts \(playbackIDs.count)"
      checkLine =
        "Generated checks: \(recognizer.requests.count), pending \(recognizer.isPending ? 1 : 0)"
        + ", cancelled \(recognizer.cancellations.count), borrowed \(recognizer.borrowCount)"
      if testCase == .practiceTimeoutRetry, recognizer.requests.count >= 7,
        let retry = recognizer.requests.last {
        let first = recognizer.requests[5]
        let same = first.tryID == retry.tryID && first.fileURL == retry.fileURL
          && first.expectedWord == retry.expectedWord
        let latest = retry.tryID == session.media.latestTry?.id
        retryBindingLine = "Generated retry binding: same take \(same ? "yes" : "no")"
          + " · new operation \(first.operationID != retry.operationID ? "yes" : "no")"
          + " · latest \(latest ? "yes" : "no")"
      }
      modelLine = "Generated model calls: \(researchProcessor?.calls ?? 0)"
    }
  }

  /// Generated UI evidence only. Reads only this host's synthetic take; never runs a model.
  @MainActor
  private final class LocalGuidedGeneratedResearchProcessor: ResearchAssessmentProcessing {
    private(set) var calls = 0
    var changed: (() -> Void)?

    func process(
      attemptId: UUID, recording: CapturedRecording, entry: PracticeLibraryEntry, ageYears: Int
    ) async throws -> ResearchAssessmentOutcome {
      calls += 1
      changed?()
      let prompt = try ResearchAssessmentClient.prompt(for: entry)
      let context = try ResearchAssessmentClient.context(
        attemptId: attemptId, audio: Data(contentsOf: recording.url), entry: entry, ageYears: ageYears)
      let probabilities = calls <= 5 ? [0.2, 0.3, 0.5] : [0.5, 0.25, 0.25]
      return .processedResearch(.init(
        context: context,
        model: .init(id: "ages-6-12-research-mixture", manifestSha256: ResearchAssessmentClient.manifest),
        targets: prompt.targets.map {
          .init(id: $0.id, wordIndex: $0.wordIndex, phoneIndex: $0.phoneIndex,
            targetPhone: $0.targetPhone, subjectiveCorpusRatingProbabilities: probabilities)
        }, timingMilliseconds: .init(total: 1, inference: 0.5)))
    }
  }

  /// Protocol receipt fake; never decodes generated bytes or queries Speech. The exact
  /// borrowed source remains protected until finish explicitly releases its operation.
  @MainActor
  final class LocalGuidedGeneratedRecognizer: LocalWordRecognizing {
    private let files: ProcessAudioFileOwnership
    private var acceptsGeneratedChecks = true
    private let holdsResult: Bool
    private let returnedStatus: LocalWordRecognitionStatus
    private let heldAfterRequestCount: Int
    private let timeoutRequestNumber: Int?
    private let alternatives: [String]
    private var pending:
      (
        LocalWordRecognitionRequest, CheckedContinuation<LocalWordRecognitionReceipt, Never>
      )?
    private(set) var requests: [LocalWordRecognitionRequest] = []
    private(set) var cancellations: Set<UUID> = []
    var changed: (() -> Void)?
    var isPending: Bool { pending != nil }
    var borrowCount: Int { isPending ? 1 : 0 }
    init(
      files: ProcessAudioFileOwnership, holdsResult: Bool,
      returnedStatus: LocalWordRecognitionStatus = .matched, alternatives: [String] = [],
      heldAfterRequestCount: Int = 0, timeoutRequestNumber: Int? = nil
    ) {
      self.files = files
      self.holdsResult = holdsResult
      self.returnedStatus = returnedStatus
    }
    func check(request: LocalWordRecognitionRequest) async -> LocalWordRecognitionReceipt {
      guard !Task.isCancelled else {
        return .init(request: request, status: .cancelled, cleanupConfirmed: true)
      }
      guard pending == nil, files.borrow(request.fileURL, operation: request.operationID) else {
        return .init(request: request, status: .unavailable, cleanupConfirmed: true)
      }
      requests.append(request)
      if !holdsResult {
        files.finishBorrowing(operation: request.operationID)
        changed?()
        return .init(request: request, status: returnedStatus, cleanupConfirmed: true)
      }
      return await withCheckedContinuation { continuation in
        pending = (request, continuation)
        changed?()
      }
    }
    func cancel(operationID: UUID) {
      guard pending?.0.operationID == operationID else { return }
      cancellations.insert(operationID)
      changed?()
    }
    func finish() {
      guard let (request, continuation) = pending else { return }
      files.finishBorrowing(operation: request.operationID)
      pending = nil
      changed?()
      continuation.resume(
        returning: .init(
          request: request,
          status: cancellations.contains(request.operationID) ? .cancelled : returnedStatus,
          cleanupConfirmed: true))
    }
  }

  @MainActor
  private final class LocalGuidedUnsupportedMirrorPermission: PracticeMirrorPermissionProviding {
    var isSupported: Bool { false }
    var status: PracticeMirrorPermission { .denied }
    func requestPermission(completion: @escaping @MainActor (Bool) -> Void) { completion(false) }
  }
  private final class LocalGuidedInertMirrorDriver: PracticeMirrorDriver, @unchecked Sendable {
    private enum Unavailable: Error { case generated }
    func configure() throws { throw Unavailable.generated }
    func start() throws { throw Unavailable.generated }
    var previewSource: PracticeMirrorPreviewSource? { nil }
    func stopAndReleasePreviewResources() throws {}
  }
  /// Fake permission and generated private WAV files through the reviewed exact producer.
  @MainActor
  final class LocalGuidedGeneratedCapture: AudioCapturing {
    private static let durations: [TimeInterval] = [0.6, 0.8, 1.0]
    private let ownership: ResearchGeneratedCaptureFileOwnership
    private var active: URL?
    private(set) var permissionRequests = 0
    /// Every file this producer wrote, including a cancelled partial start.
    private(set) var createdURLs: [URL] = []
    /// Completed takes in return order; playback markers map to these exact URLs.
    private(set) var returnedURLs: [URL] = []
    var changed: (() -> Void)?

    /// Explicit synthetic level for generated UI checks; never reads a microphone.
    var generatedInputPower: Float?
    func currentRecordingPower() -> Float? { active == nil ? nil : generatedInputPower }

    init(
      hardware: AudioHardwareOwnership, files: ProcessAudioFileOwnership
    ) {
      ownership = ResearchGeneratedCaptureFileOwnership(hardware: hardware, files: files)
    }

    func isOwned(_ url: URL) -> Bool { ownership.owner(of: url) != nil }
    var retainedCount: Int {
      createdURLs.filter { isOwned($0) || FileManager.default.fileExists(atPath: $0.path) }.count
    }
    var cleanupState: CaptureCleanupState { ownership.cleanupState }
    var cleanupStatePublisher: AnyPublisher<CaptureCleanupState, Never> {
      ownership.cleanupStatePublisher
    }
    func retryCleanup(operationID: UUID) -> CaptureCleanupReceipt {
      defer { changed?() }
      return ownership.retryCleanup(operationID: operationID)
    }
    func completedFileCleanup(operationID: UUID) -> CaptureCleanupReceipt? {
      ownership.completedFileCleanup(operationID: operationID)
    }
    func requestPermission() async -> Bool {
      permissionRequests += 1
      changed?()
      return true
    }
    func start(onFinish: @escaping @MainActor (Bool) async -> Void) throws {
      guard active == nil else { throw AudioCaptureError.couldNotStart }
      defer { changed?() }
      let url = ownership.directory.appendingPathComponent("local-guided-\(UUID()).wav")
      try ownership.begin(url)
      let duration = Self.durations[returnedURLs.count % Self.durations.count]
      let bytes = Self.wav(samples: Int((duration * 16000).rounded()))
      do { try bytes.write(to: url) } catch {
        try? ownership.cancel(url)
        throw error
      }
      createdURLs.append(url)
      active = url
    }
    func stop() throws -> CapturedRecording {
      guard let url = active else { throw AudioCaptureError.couldNotReadRecording }
      defer { changed?() }
      let owner = try ownership.stop(url)
      active = nil
      let duration = Self.durations[returnedURLs.count % Self.durations.count]
      returnedURLs.append(url)
      return .init(
        url: url, summary: .init(duration: duration, averagePower: -12), cleanupOwnerID: owner)
    }
    func cancel() throws {
      guard let url = active else { return }
      defer { changed?() }
      try ownership.cancel(url)
      active = nil
    }
    func discard(_ recording: CapturedRecording) throws {
      defer { changed?() }
      try ownership.remove(recording.url)
    }

    private static func wav(samples: Int) -> Data {
      var bytes = Data()
      func text(_ value: String) { bytes.append(contentsOf: value.utf8) }
      func word(_ value: Int, _ count: Int) {
        for offset in 0..<count { bytes.append(UInt8((value >> (offset * 8)) & 255)) }
      }
      text("RIFF")
      word(36 + samples * 2, 4)
      text("WAVEfmt ")
      word(16, 4)
      word(1, 2)
      word(1, 2)
      word(16000, 4)
      word(32000, 4)
      word(2, 2)
      word(16, 2)
      text("data")
      word(samples * 2, 4)
      for _ in 0..<samples { word(8192, 2) }
      return bytes
    }
  }
#endif
