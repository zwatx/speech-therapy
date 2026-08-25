#if DEBUG && targetEnvironment(simulator)
  import Combine
  import Foundation
  import SwiftUI

  enum DirectTryGeneratedCase: String, CaseIterable {
    case twoTry, finish, denied, failedStart, saveFailure, wordCheck, wordCheckCancel
    case twoTryAX, finishAX, deniedAX, failedStartAX, saveFailureAX, wordCheckAX, wordCheckCancelAX
    case wordCheckUnavailable, wordCheckUnavailableAX
    case wordCheckGuess, wordCheckGuessAX
    case wordCheckCompare, wordCheckCompareAX
    case wordCheckTimeout, wordCheckTimeoutAX
    case skip, skipAX

    var largeText: Bool { rawValue.hasSuffix("AX") }
    var holdsWordCheck: Bool {
      base == .wordCheck || base == .wordCheckCancel || base == .wordCheckUnavailable
        || base == .wordCheckGuess || base == .wordCheckCompare || base == .wordCheckTimeout
    }
    var base: DirectTryGeneratedCase {
      guard largeText else { return self }
      return DirectTryGeneratedCase(rawValue: String(rawValue.dropLast(2)))!
    }
  }

  /// Closed generated host for the two-try journeys. Every dependency is explicit: no system
  /// microphone, camera, audio output, shared history, network or model is constructed.
  struct DirectTryGeneratedHost: View {
    @StateObject private var resources: DirectTryGeneratedResources
    @State private var presented = true
    let testCase: DirectTryGeneratedCase

    init(testCase: DirectTryGeneratedCase, runID: UUID) {
      self.testCase = testCase
      _resources = StateObject(
        wrappedValue: DirectTryGeneratedResources(testCase: testCase, runID: runID))
    }

    var body: some View {
      Group {
        if presented {
          Color.clear
        } else {
          // Rendered only once the modal binding is actually false.
          VStack(spacing: 8) {
            Text("Generated check closed").accessibilityIdentifier(
              "cadence.generated-direct-closed")
            // Same producer-owned/on-disk count as the banner, read after the cover is gone.
            Text(resources.filesLine)
              .font(.caption2)
              .fixedSize(horizontal: false, vertical: true)
              .accessibilityIdentifier("cadence.generated-closed-files")
          }
        }
      }
      .fullScreenCover(isPresented: $presented) {
        DirectPracticePlayerView(session: resources.session)
          .environment(\.dynamicTypeSize, testCase.largeText ? .accessibility5 : .large)
          .safeAreaInset(edge: .top) { banner }
      }
    }

    /// Fixed, non-product setup strip. It sits above the practice scroll view and never
    /// overlaps product controls.
    private var banner: some View {
      VStack(alignment: .leading, spacing: 2) {
        Text("Generated check — no microphone, camera, audio output, network or models")
          .fixedSize(horizontal: false, vertical: true)
          .accessibilityIdentifier("cadence.generated-banner")
        Text(resources.filesLine)
          .fixedSize(horizontal: false, vertical: true)
          .accessibilityIdentifier("cadence.generated-files")
        Text(resources.playbackLine)
          .accessibilityIdentifier("cadence.generated-playback-file")
        if testCase.base == .saveFailure || testCase.base == .wordCheckUnavailable
          || testCase.base == .skip || testCase.base == .wordCheckTimeout
        {
          Text(resources.historyLine)
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityIdentifier("cadence.generated-history")
        }
        if testCase.holdsWordCheck {
          Text(resources.wordCheckLine)
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityIdentifier("cadence.generated-word-check")
          if testCase.base == .wordCheckTimeout {
            Text(resources.retryBindingLine)
              .fixedSize(horizontal: false, vertical: true)
              .accessibilityIdentifier("cadence.generated-retry-binding")
          }
          Button {
            resources.finishGeneratedWordCheck()
          } label: {
            Text("Release generated word check")
              .frame(minWidth: 44, minHeight: 44, alignment: .leading)
              .contentShape(Rectangle())
          }
          .buttonStyle(.plain)
          .disabled(!resources.canFinishWordCheck)
          .accessibilityIdentifier("cadence.generated-release-word-check")
        }
        if testCase.base == .saveFailure {
          // The label itself is the 44 pt hit and accessibility frame, as with product Close.
          Button {
            resources.restoreGeneratedSavePath()
          } label: {
            Text("Restore generated save path")
              .frame(minWidth: 44, minHeight: 44, alignment: .leading)
              .contentShape(Rectangle())
          }
          .buttonStyle(.plain)
          .disabled(!resources.canRestoreSavePath)
          .accessibilityIdentifier("cadence.generated-restore-save")
        }
      }
      .font(.caption2)
      .padding(8)
      .frame(maxWidth: .infinity, alignment: .leading)
      .background(DirectPracticeStyle.canvas)
      // The banner keeps the ambient size; only practice content uses the selected size.
      .environment(\.dynamicTypeSize, .large)
    }
  }

  @MainActor
  private final class DirectTryGeneratedResources: ObservableObject {
    let session: DirectPracticeSession
    @Published private(set) var filesLine = ""
    @Published private(set) var playbackLine = "Generated playback: none"
    @Published private(set) var historyLine = ""
    @Published private(set) var canRestoreSavePath = false
    @Published private(set) var wordCheckLine = ""
    @Published private(set) var retryBindingLine = "Generated retry binding: no retry"
    @Published private(set) var canFinishWordCheck = false
    private let wordRecognizer: DirectTryGeneratedWordRecognizer
    private let capture: DirectTryGeneratedCapture
    private let history: PracticeParticipationStore
    private var saveObstacle: URL?
    private var playbackStarts = 0
    private var lastPlayingID: UUID?
    private var subscriptions: Set<AnyCancellable> = []

    init(testCase: DirectTryGeneratedCase, runID: UUID) {
      precondition(runID != UUID(uuidString: "00000000-0000-0000-0000-000000000000"))
      let testCase = testCase.base
      let hardware = AudioHardwareOwnership()
      let files = ProcessAudioFileOwnership()
      let capture = DirectTryGeneratedCapture(
        hardware: hardware, files: files,
        denySecondPermission: testCase == .denied, failSecondStart: testCase == .failedStart)
      self.capture = capture
      // Inject for every old and new case: generated hosts never construct a system recognizer.
      let wordRecognizer = DirectTryGeneratedWordRecognizer(
        holdsResult: testCase.holdsWordCheck,
        result: testCase == .wordCheckTimeout ? .timedOut
          : testCase == .wordCheckUnavailable ? .unavailable
          : testCase == .wordCheckGuess ? .notMatched : .matched,
        followupResult: testCase == .wordCheckCompare ? .uncertain
          : testCase == .wordCheckTimeout ? .matched : nil)
      self.wordRecognizer = wordRecognizer
      let player = ResearchAcknowledgedPlaybackUITestFixture(
        completion: .explicitStop, ownership: hardware, fileOwnership: files)
      // Unsupported permission: Show publishes Unavailable and the factory is never reached.
      let recovery = ProcessPracticeMirrorRecovery()
      let runtime = PracticeMirrorRuntime(
        recovery: recovery, presentation: PracticeMirrorPresentation(),
        factory: { _ in DirectTryInertMirrorDriver() })
      let mirror = DirectPracticeMirror(
        permission: DirectTryUnsupportedMirrorPermission(), runtime: runtime, recovery: recovery)
      // Exclusively owned history file; never the shared store or Application Support.
      let directory = FileManager.default.temporaryDirectory.appendingPathComponent(
        "generated-direct-try-participation-\(runID)-\(UUID())", isDirectory: true)
      let fileURL = directory.appendingPathComponent("participation.json")
      // Constructed while the path is absent, so no existing file is read or overwritten.
      history = PracticeParticipationStore(fileURL: fileURL)
      if testCase == .saveFailure {
        // The store's own file path is an empty directory owned by this run: the first
        // write fails, and only the explicit generated restore removes this obstacle.
        do {
          try FileManager.default.createDirectory(at: fileURL, withIntermediateDirectories: true)
          saveObstacle = fileURL
        } catch {
          saveObstacle = nil
        }
      }
      let starter = PracticeLibrary.starterSound
      let prompts = Array(starter.prompts.prefix(testCase == .skip ? 3 : testCase == .finish ? 2 : 1))
      let sound = PracticeSound(
        id: starter.id, symbol: starter.symbol, name: starter.name, position: starter.position,
        prompts: prompts)
      session = DirectPracticeSession(
        sound: sound, capturer: capture, player: player, mirror: mirror, history: history,
        wordRecognizer: wordRecognizer,
        cleanupHardwareOwnership: hardware, cleanupFileOwnership: files)
      wordRecognizer.changed = { [weak self] in self?.refreshWordCheck() }
      session.$phase.sink { [weak self] _ in
        MainActor.assumeIsolated { self?.refreshWordCheck() }
      }.store(in: &subscriptions)
      refreshWordCheck()
      canRestoreSavePath = saveObstacle != nil
      capture.changed = { [weak self] in self?.refreshFiles() }
      capture.cleanupStatePublisher.sink { [weak self] _ in
        MainActor.assumeIsolated { self?.refreshFiles() }
      }.store(in: &subscriptions)
      // The event value, not a later getter, decides which generated file was requested.
      player.statePublisher.sink { [weak self] state in
        MainActor.assumeIsolated { self?.receivePlayback(state) }
      }.store(in: &subscriptions)
      history.$entries.sink { [weak self] entries in
        MainActor.assumeIsolated { self?.receiveHistory(entries) }
      }.store(in: &subscriptions)
      refreshFiles()
    }

    func finishGeneratedWordCheck() { wordRecognizer.finish() }

    private func refreshWordCheck() {
      let request = wordRecognizer.requests.last
      let file =
        request.flatMap { capture.returnedURLs.firstIndex(of: $0.fileURL) }
        .map { String($0 + 1) } ?? "none"
      let latest = request?.tryID == session.latestTry?.id && request != nil
      wordCheckLine =
        "Generated word checks: \(wordRecognizer.requests.count) · file \(file)"
        + " · latest \(latest ? "yes" : "no") · cancellations \(wordRecognizer.cancellations.count)"
        + " · pending \(wordRecognizer.isPending ? "yes" : "no")"
      if let first = wordRecognizer.requests.first, wordRecognizer.requests.count >= 2,
        let retry = wordRecognizer.requests.last {
        let same = first.tryID == retry.tryID && first.fileURL == retry.fileURL
          && first.expectedWord == retry.expectedWord
        retryBindingLine = "Generated retry binding: same take \(same ? "yes" : "no")"
          + " · new operation \(first.operationID != retry.operationID ? "yes" : "no")"
      }
      canFinishWordCheck = wordRecognizer.isPending
    }

    private func receivePlayback(_ state: PracticePlaybackRuntimeState) {
      guard case .playing(let operation) = state,
        let index = capture.returnedURLs.firstIndex(of: operation.url)
      else {
        playbackLine = "Generated playback: none"
        refreshFiles()
        return
      }
      if lastPlayingID != operation.id {
        lastPlayingID = operation.id
        playbackStarts += 1
      }
      playbackLine = "Generated playback file \(index + 1)"
      refreshFiles()
    }

    private func receiveHistory(_ entries: [PracticeParticipation]) {
      guard let entry = entries.first else {
        historyLine = "Generated history: 0 entries"
        return
      }
      historyLine =
        "Generated history: \(entries.count) \(entries.count == 1 ? "entry" : "entries"), "
        + "\(entry.soundID), \(entry.wordCount) \(entry.wordCount == 1 ? "word" : "words")"
    }

    private func refreshFiles() {
      // A file counts as removed only when the producer released it and it is gone on disk.
      let kept = capture.createdURLs.filter {
        capture.isOwned($0) || FileManager.default.fileExists(atPath: $0.path)
      }.count
      filesLine =
        "Generated files: made \(capture.createdURLs.count), kept \(kept)"
        + " · microphone requests \(capture.permissionRequests)"
        + " · playback starts \(playbackStarts)"
    }

    func restoreGeneratedSavePath() {
      guard let obstacle = saveObstacle else { return }
      var isDirectory: ObjCBool = false
      // Only this run's own empty obstacle is removed; anything else is left untouched.
      guard FileManager.default.fileExists(atPath: obstacle.path, isDirectory: &isDirectory),
        isDirectory.boolValue,
        (try? FileManager.default.contentsOfDirectory(atPath: obstacle.path))?.isEmpty == true,
        (try? FileManager.default.removeItem(at: obstacle)) != nil
      else { return }
      saveObstacle = nil
      canRestoreSavePath = false
    }
  }

  /// A held protocol fake, never an audio decoder or speech framework. Cancel records
  /// intent but cannot produce a cleanup receipt until the generated release is tapped.
  @MainActor
  private final class DirectTryGeneratedWordRecognizer: LocalWordRecognizing {
    private let holdsResult: Bool
    private let result: LocalWordRecognitionStatus
    private let followupResult: LocalWordRecognitionStatus?
    private var pending:
      (
        request: LocalWordRecognitionRequest,
        continuation: CheckedContinuation<LocalWordRecognitionReceipt, Never>
      )?
    private(set) var requests: [LocalWordRecognitionRequest] = []
    private(set) var cancellations: Set<UUID> = []
    var changed: (() -> Void)?
    var isPending: Bool { pending != nil }

    init(
      holdsResult: Bool, result: LocalWordRecognitionStatus,
      followupResult: LocalWordRecognitionStatus? = nil
    ) {
      self.holdsResult = holdsResult
      self.result = result
      self.followupResult = followupResult
    }

    func check(request: LocalWordRecognitionRequest) async -> LocalWordRecognitionReceipt {
      guard pending == nil else {
        return .init(request: request, status: .unavailable, cleanupConfirmed: true)
      }
      requests.append(request)
      guard holdsResult else {
        changed?()
        return .init(request: request, status: .unavailable, cleanupConfirmed: true)
      }
      return await withCheckedContinuation { continuation in
        pending = (request, continuation)
        changed?()
      }
    }

    func cancel(operationID: UUID) {
      guard pending?.request.operationID == operationID else { return }
      cancellations.insert(operationID)
      changed?()
    }

    func finish() {
      guard let pending else { return }
      self.pending = nil
      changed?()
      pending.continuation.resume(
        returning: .init(
          request: pending.request,
          status: cancellations.contains(pending.request.operationID) ? .cancelled : result,
          cleanupConfirmed: true,
          wordGuess: result == .notMatched
            ? LocalWordGuess(completedText: "wall", expectedWord: pending.request.expectedWord) : nil))
    }
  }

  @MainActor
  private final class DirectTryUnsupportedMirrorPermission: PracticeMirrorPermissionProviding {
    var isSupported: Bool { false }
    var status: PracticeMirrorPermission { .denied }
    func requestPermission(completion: @escaping @MainActor (Bool) -> Void) {
      completion(false)  // The OS has no involvement.
    }
  }

  /// Unreachable while permission is unsupported; it still refuses rather than start anything.
  private final class DirectTryInertMirrorDriver: PracticeMirrorDriver, @unchecked Sendable {
    func configure() throws { throw Unavailable.generated }
    func start() throws { throw Unavailable.generated }
    var previewSource: PracticeMirrorPreviewSource? { nil }
    func stopAndReleasePreviewResources() throws {}
    private enum Unavailable: Error { case generated }
  }

  /// Fake permission and generated private WAV files through the reviewed exact producer.
  @MainActor
  private final class DirectTryGeneratedCapture: AudioCapturing {
    private static let durations: [TimeInterval] = [0.2, 0.35, 0.5]
    private let ownership: ResearchGeneratedCaptureFileOwnership
    private let denySecondPermission: Bool
    private let failSecondStart: Bool
    private var active: URL?
    private var starts = 0
    private(set) var permissionRequests = 0
    /// Every file this producer wrote, including a cancelled partial start.
    private(set) var createdURLs: [URL] = []
    /// Completed takes in return order; playback markers map to these exact URLs.
    private(set) var returnedURLs: [URL] = []
    var changed: (() -> Void)?

    init(
      hardware: AudioHardwareOwnership, files: ProcessAudioFileOwnership,
      denySecondPermission: Bool, failSecondStart: Bool
    ) {
      ownership = ResearchGeneratedCaptureFileOwnership(hardware: hardware, files: files)
      self.denySecondPermission = denySecondPermission
      self.failSecondStart = failSecondStart
    }

    func isOwned(_ url: URL) -> Bool { ownership.owner(of: url) != nil }
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
      return !(denySecondPermission && permissionRequests >= 2)
    }
    func start(onFinish: @escaping @MainActor (Bool) async -> Void) throws {
      guard active == nil else { throw AudioCaptureError.couldNotStart }
      defer { changed?() }
      starts += 1
      let url = ownership.directory.appendingPathComponent("direct-try-\(UUID()).wav")
      try ownership.begin(url)
      let failing = failSecondStart && starts == 2
      let duration = Self.durations[returnedURLs.count % Self.durations.count]
      // A failing start leaves only a partial header, then cancels its own exact operation.
      let bytes = Self.wav(samples: failing ? 0 : Int((duration * 16000).rounded()))
      do { try (failing ? bytes.prefix(12) : bytes).write(to: url) } catch {
        try? ownership.cancel(url)
        throw error
      }
      createdURLs.append(url)
      if failing {
        try ownership.cancel(url)
        throw AudioCaptureError.couldNotStart
      }
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
