#if DEBUG && targetEnvironment(simulator)
  import CryptoKit
  import Foundation
  import SwiftUI

  enum HistoryGeneratedCase: String, CaseIterable {
    case historyfour, hundred, empty, unreadable, clearFailure
    var seedCount: Int {
      switch self {
      case .historyfour, .clearFailure: 4
      case .hundred: 100
      case .empty, .unreadable: 0
      }
    }
  }

  /// Metadata-only component host: never creates Root, shared history or media/recovery owners.
  @MainActor
  struct HistoryGeneratedHost: View {
    @StateObject private var resources: HistoryGeneratedResources
    @State private var showingHistory = false
    let testCase: HistoryGeneratedCase

    init(testCase: HistoryGeneratedCase, runID: UUID) {
      self.testCase = testCase
      _resources = StateObject(
        wrappedValue: HistoryGeneratedResources(testCase: testCase, runID: runID))
    }

    var body: some View {
      VStack(spacing: 0) {
        banner
        content.frame(maxWidth: .infinity, maxHeight: .infinity)
      }
    }

    private var content: some View {
      Group {
        if resources.initializationFailed {
          Text("Generated history initialization failed").accessibilityIdentifier(
            "cadence.generated-history.failed")
        } else if resources.finished {
          Text("Generated history check finished").accessibilityIdentifier(
            "cadence.generated-history.finished")
        } else if let history = resources.history {
          NavigationStack {
            ScrollView {
              PracticeParticipationHistorySection(history: history, allowsLiveRoutes: false)
                .padding(24).frame(maxWidth: 680).frame(maxWidth: .infinity)
            }
            .accessibilityIdentifier("cadence.generated-history.home")
            .background(DirectPracticeStyle.canvas.ignoresSafeArea())
            .foregroundStyle(DirectPracticeStyle.ink).tint(DirectPracticeStyle.ink)
            .navigationTitle("Generated history").navigationBarTitleDisplayMode(.inline)
            .navigationDestination(isPresented: $showingHistory) {
              PracticeParticipationHistoryView(history: history, allowsLiveRoutes: false)
            }
          }
          .onReceive(history.objectWillChange) { _ in
            // Published is willSet; read actual storage after synchronous delivery.
            Task { @MainActor in resources.refreshEvidence() }
          }
        }
      }
    }

    private var banner: some View {
      VStack(alignment: .leading, spacing: 2) {
        Text("Generated participation metadata — no media or shared history")
          .accessibilityIdentifier("cadence.generated-history.banner")
        Text(resources.statusLine)
          .accessibilityIdentifier("cadence.generated-history.receipt")
          .accessibilityValue(resources.receiptJSON)
        if !resources.finished {
          HStack {
            Button {
              resources.refreshEvidence()
            } label: {
              Text("Inspect generated file").frame(minHeight: 44).contentShape(Rectangle())
            }
            .accessibilityIdentifier("cadence.generated-history.inspect")
            Button {
              resources.finish()
            } label: {
              Text("Finish generated check").frame(minHeight: 44).contentShape(Rectangle())
            }
            .accessibilityIdentifier("cadence.generated-history.finish")
          }
          if testCase == .empty || testCase == .unreadable {
            Button {
              showingHistory = true
            } label: {
              Text("Open generated history state").frame(minHeight: 44).contentShape(Rectangle())
            }
            .accessibilityIdentifier("cadence.generated-history.open-state")
          }
          if testCase == .clearFailure {
            Button {
              resources.repairObstacle()
            } label: {
              Text("Repair generated file obstacle").frame(minHeight: 44).contentShape(Rectangle())
            }
            .accessibilityIdentifier("cadence.generated-history.repair")
          }
          if testCase == .historyfour {
            Button {
              resources.clearForObservation()
            } label: {
              Text("Clear generated store for observation").frame(minHeight: 44).contentShape(
                Rectangle())
            }
            .accessibilityIdentifier("cadence.generated-history.observe-clear")
          }
        }
      }
      .buttonStyle(.plain).font(.caption).padding(8)
      .environment(\.dynamicTypeSize, .large)
      .background(DirectPracticeStyle.canvas)
    }
  }

  struct HistoryGeneratedReceipt: Encodable {
    let schema = "HistoryGeneratedV1"
    var seedCount = 0, currentCount = 0, reopenedCount: Int?
    var seedOrderConfirmed = false, seedReadbackConfirmed = false, reopenedMatches = false
    var seedOrderSHA256 = "", currentOrderSHA256 = ""
    var seedFileSHA256 = "", currentFileSHA256: String?
    var bytesUnchanged = false, loadError = false, obstaclePresent = false
    var repairCount = 0, observationClearCount = 0
    var failed = false, cleanupConfirmed = false
    var ownedDirectoryCreated = false, cleanupAttempted = false
  }

  @MainActor
  final class HistoryGeneratedResources: ObservableObject {
    let history: PracticeParticipationStore?
    let directory: URL
    private let fileURL: URL
    private let testCase: HistoryGeneratedCase
    private let directoryName: String
    private(set) var initializationFailed = false
    @Published private(set) var receipt = HistoryGeneratedReceipt()
    @Published private(set) var finished = false

    var receiptJSON: String {
      guard let bytes = try? JSONEncoder().encode(receipt) else { return "encoding-failed" }
      return String(decoding: bytes, as: UTF8.self)
    }
    var statusLine: String {
      "Generated metadata: seeded \(receipt.seedCount), current \(receipt.currentCount), cleanup \(receipt.cleanupConfirmed ? "confirmed" : "pending")"
    }

    init(testCase: HistoryGeneratedCase, runID: UUID) {
      self.testCase = testCase
      directoryName = "generated-history-\(runID.uuidString)-\(UUID().uuidString)"
      directory = FileManager.default.temporaryDirectory.resolvingSymlinksInPath()
        .standardizedFileURL
        .appendingPathComponent(directoryName, isDirectory: true)
      fileURL = directory.appendingPathComponent("participation.json")
      var ownedStore: PracticeParticipationStore?
      var initial = HistoryGeneratedReceipt()
      do {
        guard runID != UUID(uuidString: "00000000-0000-0000-0000-000000000000") else {
          throw GeneratedFailure.invalidRun
        }
        try FileManager.default.createDirectory(
          at: directory, withIntermediateDirectories: false,
          attributes: [.posixPermissions: 0o700])
        initial.ownedDirectoryCreated = true
        if testCase == .unreadable {
          try Data("Generated unreadable history fixture".utf8).write(
            to: fileURL, options: .withoutOverwriting)
          try FileManager.default.setAttributes(
            [.posixPermissions: 0o600], ofItemAtPath: fileURL.path)
        }
        let store = PracticeParticipationStore(fileURL: fileURL)
        ownedStore = store
        if testCase != .unreadable {
          for index in 1..<(testCase.seedCount + 1) {
            try store.record(
              sessionID: Self.id(index), completedAt: Self.date(index),
              soundID: Self.sound(index), wordCount: 1 + (index - 1) % 3)
          }
        }
        initial.seedCount = store.entries.count
        if FileManager.default.fileExists(atPath: fileURL.path) {
          try FileManager.default.setAttributes(
            [.posixPermissions: 0o600], ofItemAtPath: fileURL.path)
        }
        initial.seedOrderConfirmed =
          store.entries.map(\.id) == (1..<(testCase.seedCount + 1)).map(Self.id)
        initial.seedOrderSHA256 = Self.orderDigest(store.entries)
        initial.seedFileSHA256 = (try? Data(contentsOf: fileURL)).map(Self.digest) ?? ""
        let reopened = PracticeParticipationStore(fileURL: fileURL)
        initial.seedReadbackConfirmed =
          reopened.entries == store.entries
          && (reopened.loadError != nil) == (testCase == .unreadable)
        guard initial.seedOrderConfirmed && initial.seedReadbackConfirmed else {
          throw GeneratedFailure.seed
        }
        if testCase == .clearFailure {
          try FileManager.default.removeItem(at: fileURL)
          try FileManager.default.createDirectory(
            at: fileURL, withIntermediateDirectories: false,
            attributes: [.posixPermissions: 0o700])
        }
      } catch {
        initializationFailed = true
        initial.failed = true
      }
      history = ownedStore
      receipt = initial
      refreshEvidence()
    }

    static func id(_ ordinal: Int) -> UUID {
      UUID(uuidString: String(format: "00000000-0000-0000-0000-%012d", ordinal))!
    }
    static func date(_ ordinal: Int) -> Date {
      Date(timeIntervalSince1970: 1_700_100_000 - Double(ordinal) * 60)
    }
    static func sound(_ ordinal: Int) -> String {
      ["voiced-th", "r", "b", "ch"][(ordinal - 1) % 4]
    }
    private static func digest(_ data: Data) -> String {
      SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    }
    private static func orderDigest(_ entries: [PracticeParticipation]) -> String {
      digest(Data(entries.map { $0.id.uuidString }.joined(separator: "\n").utf8))
    }
    private enum GeneratedFailure: Error { case invalidRun, seed, ownership, obstacle }

    func refreshEvidence() {
      guard !finished, let history else { return }
      var next = receipt
      next.currentCount = history.entries.count
      next.currentOrderSHA256 = Self.orderDigest(history.entries)
      next.loadError = history.loadError != nil
      next.currentFileSHA256 = (try? Data(contentsOf: fileURL)).map(Self.digest)
      next.bytesUnchanged =
        next.currentFileSHA256 == receipt.seedFileSHA256
        || (testCase == .empty && receipt.seedFileSHA256.isEmpty && next.currentFileSHA256 == nil)
      let reopened = PracticeParticipationStore(fileURL: fileURL)
      next.reopenedCount = reopened.loadError == nil ? reopened.entries.count : nil
      next.reopenedMatches =
        reopened.entries == history.entries
        && (reopened.loadError != nil) == (history.loadError != nil)
      let values = try? fileURL.resourceValues(forKeys: [.isDirectoryKey, .isSymbolicLinkKey])
      next.obstaclePresent = values?.isDirectory == true && values?.isSymbolicLink != true
      receipt = next
    }

    func repairObstacle() {
      guard testCase == .clearFailure, !finished, receipt.repairCount == 0 else { return }
      do {
        try requireOwnedDirectory()
        let values = try fileURL.resourceValues(forKeys: [.isDirectoryKey, .isSymbolicLinkKey])
        guard values.isDirectory == true && values.isSymbolicLink != true,
          try FileManager.default.contentsOfDirectory(atPath: fileURL.path).isEmpty
        else { throw GeneratedFailure.obstacle }
        try FileManager.default.removeItem(at: fileURL)
        receipt.repairCount += 1
      } catch { receipt.failed = true }
      refreshEvidence()
    }

    func clearForObservation() {
      guard testCase == .historyfour, !finished, let history else { return }
      do {
        try history.clear()
        receipt.observationClearCount += 1
      } catch { receipt.failed = true }
      refreshEvidence()
    }

    private func requireOwnedDirectory() throws {
      guard directory.lastPathComponent == directoryName,
        directory.deletingLastPathComponent().standardizedFileURL.path
          == FileManager.default.temporaryDirectory.resolvingSymlinksInPath().standardizedFileURL
          .path,
        directory.resolvingSymlinksInPath().path == directory.standardizedFileURL.path,
        receipt.ownedDirectoryCreated
      else { throw GeneratedFailure.ownership }
      let values = try directory.resourceValues(forKeys: [.isDirectoryKey, .isSymbolicLinkKey])
      guard values.isDirectory == true && values.isSymbolicLink != true else {
        throw GeneratedFailure.ownership
      }
    }

    func finish() {
      guard !finished else { return }
      refreshEvidence()
      guard receipt.ownedDirectoryCreated else {
        receipt.failed = true
        finished = true
        print("CADENCE_GENERATED_HISTORY_V1=" + receiptJSON)
        return
      }
      do {
        receipt.cleanupAttempted = true
        try requireOwnedDirectory()
        try FileManager.default.removeItem(at: directory)
        receipt.cleanupConfirmed = !FileManager.default.fileExists(atPath: directory.path)
      } catch {
        receipt.failed = true
        receipt.cleanupConfirmed = false
      }
      finished = true
      print("CADENCE_GENERATED_HISTORY_V1=" + receiptJSON)
    }
  }
#endif
