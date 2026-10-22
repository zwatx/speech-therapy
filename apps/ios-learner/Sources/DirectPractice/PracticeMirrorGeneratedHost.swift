#if DEBUG && targetEnvironment(simulator)
  import Combine
  import Foundation
  import SwiftUI

  enum PracticeMirrorGeneratedCase: String, CaseIterable {
    case sample, sampleAX, pending, unavailable, denied, failedStop, heldStop
    case pendingAX, unavailableAX, deniedAX, failedStopAX, heldStopAX

    var largeText: Bool { rawValue.hasSuffix("AX") }
    var base: PracticeMirrorGeneratedCase {
      guard largeText else { return self }
      return PracticeMirrorGeneratedCase(rawValue: String(rawValue.dropLast(2)))!
    }
  }

  /// Closed generated host. Every dependency is explicit: no system permission, sensor,
  /// framework player, shared history or production root is constructed.
  struct PracticeMirrorGeneratedHost: View {
    @StateObject private var resources: PracticeMirrorGeneratedResources
    @State private var presented = true
    let testCase: PracticeMirrorGeneratedCase

    init(testCase: PracticeMirrorGeneratedCase) {
      self.testCase = testCase
      _resources = StateObject(wrappedValue: PracticeMirrorGeneratedResources(testCase: testCase))
    }

    var body: some View {
      Group {
        if presented {
          Color.clear
        } else {
          Text("Generated check closed").accessibilityIdentifier("mirror-generated.closed")
        }
      }
      .fullScreenCover(isPresented: $presented) {
        DirectPracticePlayerView(session: resources.session)
          .environment(\.dynamicTypeSize, testCase.largeText ? .accessibility5 : .large)
          .safeAreaInset(edge: .top) {
            VStack(spacing: 4) {
              Text("Generated check — no camera or microphone")
                .font(.footnote).fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier("mirror-generated.banner")
              if testCase.base == .heldStop {
                Button("Release generated camera stop") { resources.driver.releaseStop() }
                  .frame(minHeight: 44)
                  .accessibilityIdentifier("mirror-generated.release-stop")
              }
            }.padding(8).frame(maxWidth: .infinity).background(DirectPracticeStyle.canvas)
          }
      }
    }
  }

  @MainActor
  private final class PracticeMirrorGeneratedResources: ObservableObject {
    let session: DirectPracticeSession
    let driver: PracticeMirrorGeneratedDriver

    init(testCase: PracticeMirrorGeneratedCase) {
      let testCase = testCase.base
      let hardware = AudioHardwareOwnership()
      let files = ProcessAudioFileOwnership()
      let recovery = ProcessPracticeMirrorRecovery()
      let driver = PracticeMirrorGeneratedDriver(
        failFirstStop: testCase == .failedStop, holdStop: testCase == .heldStop)
      self.driver = driver
      let runtime = PracticeMirrorRuntime(
        recovery: recovery, presentation: PracticeMirrorPresentation(), factory: { _ in driver })
      let mirror = DirectPracticeMirror(
        permission: PracticeMirrorGeneratedPermission(testCase: testCase),
        runtime: runtime, recovery: recovery)
      let prompt = PracticeLibrary.starterSound.prompts[0]
      let sound = PracticeSound(
        id: PracticeLibrary.starterSound.id, symbol: PracticeLibrary.starterSound.symbol,
        name: PracticeLibrary.starterSound.name, position: PracticeLibrary.starterSound.position,
        prompts: [prompt])
      session = DirectPracticeSession(
        sound: sound,
        capturer: PracticeMirrorGeneratedCapture(hardware: hardware, files: files),
        player: ResearchAcknowledgedPlaybackUITestFixture(
          completion: .explicitStop, ownership: hardware, fileOwnership: files),
        mirror: mirror, cleanupHardwareOwnership: hardware, cleanupFileOwnership: files)
    }
  }

  @MainActor
  private final class PracticeMirrorGeneratedPermission: PracticeMirrorPermissionProviding {
    let testCase: PracticeMirrorGeneratedCase
    init(testCase: PracticeMirrorGeneratedCase) { self.testCase = testCase.base }
    var isSupported: Bool { testCase != .unavailable }
    var status: PracticeMirrorPermission {
      switch testCase {
      case .pending: .notDetermined
      case .denied: .denied
      default: .authorized
      }
    }
    func requestPermission(completion: @escaping @MainActor (Bool) -> Void) {
      // The OS has no involvement. Cancel must settle even without a generated grant.
    }
  }

  private final class PracticeMirrorGeneratedDriver: PracticeMirrorDriver, @unchecked Sendable {
    private let condition = NSCondition()
    private var failFirstStop: Bool
    private var holdStop: Bool
    init(failFirstStop: Bool, holdStop: Bool) {
      self.failFirstStop = failFirstStop
      self.holdStop = holdStop
    }
    func configure() throws {}
    func start() throws {}
    var previewSource: PracticeMirrorPreviewSource? { .sample }
    func releaseStop() {
      condition.lock()
      holdStop = false
      condition.broadcast()
      condition.unlock()
    }
    func stopAndReleasePreviewResources() throws {
      condition.lock()
      defer { condition.unlock() }
      let deadline = Date().addingTimeInterval(20)
      while holdStop {
        guard condition.wait(until: deadline) else { throw GeneratedFailure.stopUnconfirmed }
      }
      if failFirstStop {
        failFirstStop = false
        throw GeneratedFailure.stopUnconfirmed
      }
    }
    private enum GeneratedFailure: Error { case stopUnconfirmed }
  }

  @MainActor
  private final class PracticeMirrorGeneratedCapture: AudioCapturing {
    private let ownership: ResearchGeneratedCaptureFileOwnership
    private var active: URL?
    init(hardware: AudioHardwareOwnership, files: ProcessAudioFileOwnership) {
      ownership = ResearchGeneratedCaptureFileOwnership(hardware: hardware, files: files)
    }
    var cleanupState: CaptureCleanupState { ownership.cleanupState }
    var cleanupStatePublisher: AnyPublisher<CaptureCleanupState, Never> {
      ownership.cleanupStatePublisher
    }
    func retryCleanup(operationID: UUID) -> CaptureCleanupReceipt {
      ownership.retryCleanup(operationID: operationID)
    }
    func completedFileCleanup(operationID: UUID) -> CaptureCleanupReceipt? {
      ownership.completedFileCleanup(operationID: operationID)
    }
    func requestPermission() async -> Bool { true }
    func start(onFinish: @escaping @MainActor (Bool) async -> Void) throws {
      guard active == nil else { throw AudioCaptureError.couldNotStart }
      let url = ownership.directory.appendingPathComponent("sample-\(UUID()).wav")
      try ownership.begin(url)
      var bytes = Data()
      func text(_ value: String) { bytes.append(contentsOf: value.utf8) }
      func word(_ value: Int, _ count: Int) {
        for offset in 0..<count { bytes.append(UInt8((value >> (offset * 8)) & 255)) }
      }
      text("RIFF")
      word(6436, 4)
      text("WAVEfmt ")
      word(16, 4)
      word(1, 2)
      word(1, 2)
      word(16000, 4)
      word(32000, 4)
      word(2, 2)
      word(16, 2)
      text("data")
      word(6400, 4)
      for _ in 0..<3200 { word(8192, 2) }
      do { try bytes.write(to: url) } catch {
        try? ownership.cancel(url)
        throw error
      }
      active = url
    }
    func stop() throws -> CapturedRecording {
      guard let url = active else { throw AudioCaptureError.couldNotReadRecording }
      let owner = try ownership.stop(url)
      active = nil
      return .init(
        url: url, summary: .init(duration: 0.2, averagePower: -12), cleanupOwnerID: owner)
    }
    func cancel() throws {
      guard let url = active else { return }
      try ownership.cancel(url)
      active = nil
    }
    func discard(_ recording: CapturedRecording) throws { try ownership.remove(recording.url) }
  }
#endif
