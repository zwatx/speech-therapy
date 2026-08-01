import SwiftUI

@main
@MainActor
struct CadenceLearnerApp: App {
  init() {
    #if DEBUG && targetEnvironment(simulator)
      ControlledUnitTestHost.recordAppInitialization()
    #endif
  }

  var body: some Scene {
    WindowGroup {
      #if DEBUG
        #if targetEnvironment(simulator)
          switch ControlledUnitTestHost.launchSelection {
          case .inert: Color.clear
          case .generated(let configuration):
            if case .mirror(let testCase) = configuration.fixture {
              PracticeMirrorGeneratedHost(testCase: testCase)
            } else if case .directTry(let testCase) = configuration.fixture {
              // Isolated host only: no shared root, history store or recovery host.
              DirectTryGeneratedHost(testCase: testCase, runID: configuration.runID)
            } else if case .localGuided(let testCase) = configuration.fixture {
              LocalGuidedGeneratedHost(testCase: testCase, runID: configuration.runID)
            } else if case .history(let testCase) = configuration.fixture {
              HistoryGeneratedHost(testCase: testCase, runID: configuration.runID)
            } else if case .sound = configuration.fixture {
              let resources = ResearchSoundUITestFixtures.resources(runID: configuration.runID)
              AudioCleanupRecoveryHost(ownership: resources.hardware, files: resources.files) {
                DirectPracticeRootView(
                  controlledUI: configuration, controlledSoundResources: resources)
              }
            } else {
              DirectPracticeRootView(controlledUI: configuration)
            }
          case .development: AudioCleanupRecoveryHost { developmentRoot }
          }
        #else
          AudioCleanupRecoveryHost { developmentRoot }
        #endif
      #else
        // Ordinary launch opens the sound-check journey directly.
        AudioCleanupRecoveryHost { CACDemoView(placement: .root) }
      #endif
    }
  }

  #if DEBUG
    @ViewBuilder private var developmentRoot: some View {
      let arguments = ProcessInfo.processInfo.arguments
      if arguments.contains("-CadenceClinicalMode")
        || arguments.contains(where: { $0.hasPrefix("-accessibility-") })
      {
        ClinicalPracticeRootView()
      } else {
        DirectPracticeRootView()
      }
    }
  #endif
}

#if DEBUG && targetEnvironment(simulator)
  /// Unit-host startup must not construct production roots, stores or sensor owners.
  /// Only indicator presence is inspected; no test configuration or history file is opened.
  @MainActor
  enum ControlledUnitTestHost {
    static let launchSelection = ControlledAppLaunch.select(
      arguments: ProcessInfo.processInfo.arguments,
      environment: ProcessInfo.processInfo.environment,
      hasXCTestRuntime: NSClassFromString("XCTestCase") != nil)
    static var isEnabled: Bool { launchSelection == .inert }
    private(set) static var appInitializedWithInertRoot = false

    static func recordAppInitialization() {
      appInitializedWithInertRoot = isEnabled
    }

    static func selectsInertRoot(
      environment: [String: String], hasXCTestRuntime: Bool
    ) -> Bool {
      environment["CADENCE_CONTROLLED_UNIT_HOST"] == "1"
        || environment["TEST_RUNNER_CADENCE_CONTROLLED_UNIT_HOST"] == "1"
        || environment["XCTestConfigurationFilePath"] != nil
        || hasXCTestRuntime
    }
  }
#endif

#if DEBUG && targetEnvironment(simulator)
  /// Pure admission: case validation reads enum values, never constructs a fixture/store.
  @MainActor
  enum ControlledAppLaunch {
    enum Selection: Equatable {
      case development, inert
      case generated(ControlledUIConfiguration)
    }

    static func select(
      arguments: [String], environment: [String: String], hasXCTestRuntime: Bool
    ) -> Selection {
      let unitKeys = ["CADENCE_CONTROLLED_UNIT_HOST", "TEST_RUNNER_CADENCE_CONTROLLED_UNIT_HOST"]
      if unitKeys.contains(where: { environment[$0] == "1" }) { return .inert }
      let uiKeys = ["CADENCE_CONTROLLED_UI_HOST", "TEST_RUNNER_CADENCE_CONTROLLED_UI_HOST"]
      let optedIn = uiKeys.contains(where: { environment[$0] == "1" })
      let testEnvironmentKeys = [
        "XCTestConfigurationFilePath", "XCTestBundlePath", "XCInjectBundleInto",
        "CADENCE_UI_TEST_FIXTURE", "TEST_RUNNER_CADENCE_UI_TEST_FIXTURE",
      ]
      let testIntent =
        hasXCTestRuntime
        || arguments.contains("-CadenceHistoryMode")
        || testEnvironmentKeys.contains(where: { environment[$0] != nil })
        || uiKeys.contains(where: { environment[$0] != nil })
        || arguments.contains(where: {
          $0.contains("CadenceControlledUI") || ($0.hasPrefix("-Cadence") && $0.contains("UITest"))
        })
      guard optedIn else { return testIntent ? .inert : .development }
      guard uiKeys.allSatisfy({ environment[$0] == nil || environment[$0] == "1" }) else {
        return .inert
      }
      let modeFlags = [
        "-CadenceSoundMode", "-CadenceFeedbackMode", "-CadenceGuidedWordMode", "-CadenceMirrorMode",
        "-CadenceDirectTryMode", "-CadenceLocalGuidedMode", "-CadenceHistoryMode",
      ]
      let caseFlags = [
        "-CadenceSoundUITestCase", "-CadenceUnifiedFeedbackUITestCase",
        "-CadenceGuidedWordUITestCase",
        "-CadenceMirrorUITestCase", "-CadenceDirectTryUITestCase", "-CadenceLocalGuidedUITestCase",
        "-CadenceHistoryUITestCase",
      ]
      let allowedFlags = Set(modeFlags + caseFlags + ["-CadenceControlledUIRunID"])
      guard arguments.filter({ modeFlags.contains($0) }).count == 1,
        arguments.filter({ caseFlags.contains($0) }).count == 1,
        arguments.filter({ $0.hasPrefix("-Cadence") }).allSatisfy({ allowedFlags.contains($0) }),
        !arguments.contains(where: { $0.hasPrefix("-accessibility-") }),
        let runValue = singleValue("-CadenceControlledUIRunID", in: arguments),
        let runID = UUID(uuidString: runValue),
        runID.uuidString.lowercased() == runValue.lowercased(),
        runID.uuidString != "00000000-0000-0000-0000-000000000000"
      else { return .inert }
      let fixture: ControlledUIConfiguration.Fixture
      if arguments.contains("-CadenceSoundMode"),
        let value = singleValue("-CadenceSoundUITestCase", in: arguments),
        let testCase = ResearchSoundUITestFixtures.Case(rawValue: value)
      {
        fixture = .sound(testCase)
      } else if arguments.contains("-CadenceFeedbackMode"),
        let value = singleValue("-CadenceUnifiedFeedbackUITestCase", in: arguments),
        let testCase = ResearchUnifiedFeedbackUITestFixtures.Case(rawValue: value)
      {
        fixture = .feedback(testCase)
      } else if arguments.contains("-CadenceGuidedWordMode"),
        let value = singleValue("-CadenceGuidedWordUITestCase", in: arguments),
        let testCase = ResearchGuidedWordUITestFixtures.Case(rawValue: value)
      {
        fixture = .guided(testCase)
      } else if arguments.contains("-CadenceMirrorMode"),
        let value = singleValue("-CadenceMirrorUITestCase", in: arguments),
        let testCase = PracticeMirrorGeneratedCase(rawValue: value)
      {
        fixture = .mirror(testCase)
      } else if arguments.contains("-CadenceDirectTryMode"),
        let value = singleValue("-CadenceDirectTryUITestCase", in: arguments),
        let testCase = DirectTryGeneratedCase(rawValue: value)
      {
        fixture = .directTry(testCase)
      } else if arguments.contains("-CadenceLocalGuidedMode"),
        let value = singleValue("-CadenceLocalGuidedUITestCase", in: arguments),
        let testCase = LocalGuidedGeneratedCase(rawValue: value)
      {
        fixture = .localGuided(testCase)
      } else if arguments.contains("-CadenceHistoryMode"),
        let value = singleValue("-CadenceHistoryUITestCase", in: arguments),
        let testCase = HistoryGeneratedCase(rawValue: value)
      {
        fixture = .history(testCase)
      } else {
        return .inert
      }
      return .generated(.init(fixture: fixture, runID: runID))
    }

    private static func singleValue(_ flag: String, in arguments: [String]) -> String? {
      guard arguments.filter({ $0 == flag }).count == 1,
        let index = arguments.firstIndex(of: flag), arguments.indices.contains(index + 1)
      else { return nil }
      return arguments[index + 1]
    }
  }

  struct ControlledUIConfiguration: Equatable {
    enum Fixture: Equatable {
      case sound(ResearchSoundUITestFixtures.Case)
      case feedback(ResearchUnifiedFeedbackUITestFixtures.Case)
      case guided(ResearchGuidedWordUITestFixtures.Case)
      case mirror(PracticeMirrorGeneratedCase)
      case directTry(DirectTryGeneratedCase)
      case localGuided(LocalGuidedGeneratedCase)
      case history(HistoryGeneratedCase)
    }
    enum Destination: CaseIterable {
      case home, about, historyRead, historyClear
      case sound, feedback, guided, mirror, directTry, localGuided
      case directPractice, search, soundLibrary, assessment, clinical
    }
    let fixture: Fixture
    let runID: UUID

    func admits(_ destination: Destination) -> Bool {
      if case .mirror = fixture { return destination == .mirror }
      if case .directTry = fixture { return destination == .directTry }
      if case .localGuided = fixture { return destination == .localGuided }
      if case .history = fixture {
        return destination == .home || destination == .historyRead || destination == .historyClear
      }
      return switch destination {
      case .home, .about, .historyRead, .historyClear: true
      case .sound: if case .sound = fixture { true } else { false }
      case .feedback: if case .feedback = fixture { true } else { false }
      case .guided: if case .guided = fixture { true } else { false }
      case .mirror, .directTry, .localGuided: false
      case .directPractice, .search, .soundLibrary, .assessment, .clinical: false
      }
    }
  }
#endif

// The existing linked-device flow remains available to development audits.
// The direct-practice demo never creates an enrollment model or loads credentials.
private struct ClinicalPracticeRootView: View {
  @StateObject private var enrollment = EnrollmentModel()
  #if DEBUG
    @StateObject private var accessibilityPreviewSession = PracticeSessionModel(
      assignment: .localPreview
    )
  #endif
  @Environment(\.scenePhase) private var scenePhase
  @Environment(\.refreshAudioCleanupRecovery) private var refreshCleanupRecovery

  var body: some View {
    Group {
      Group {
        #if DEBUG
          if ProcessInfo.processInfo.arguments.contains("-accessibility-practice-preview") {
            PracticeView(session: accessibilityPreviewSession)
          } else if ProcessInfo.processInfo.arguments.contains(
            "-accessibility-assignment-loading-preview"
          ) {
            EnrollmentView(model: enrollment)
              .onAppear { enrollment.configureAccessibilityPreview(.loading) }
          } else if ProcessInfo.processInfo.arguments.contains(
            "-accessibility-no-assignment-preview"
          ) {
            EnrollmentView(model: enrollment)
              .onAppear { enrollment.configureAccessibilityPreview(.noAssignment) }
          } else if ProcessInfo.processInfo.arguments.contains(
            "-accessibility-assignment-error-preview"
          ) {
            EnrollmentView(model: enrollment)
              .onAppear {
                enrollment.configureAccessibilityPreview(
                  .failed("The practice service is temporarily unavailable.")
                )
              }
          } else if let session = enrollment.practiceSession {
            PracticeView(
              session: session,
              onDisconnect: { enrollment.disconnect() },
              onRefreshAssignment: {
                Task { await enrollment.retryAssignmentLoad() }
              },
              departureError: enrollment.departureError
            )
          } else {
            EnrollmentView(model: enrollment)
          }
        #else
          if let session = enrollment.practiceSession {
            PracticeView(
              session: session,
              onDisconnect: { enrollment.disconnect() },
              onRefreshAssignment: {
                Task { await enrollment.retryAssignmentLoad() }
              },
              departureError: enrollment.departureError
            )
          } else {
            EnrollmentView(model: enrollment)
          }
        #endif
      }
      .task { await enrollment.loadStoredAssignment() }
      .onChange(of: scenePhase) { _, newPhase in
        if newPhase == .active {
          Task { await enrollment.practiceSession?.resumeVisualCaptureIfActivated() }
        } else {
          enrollment.practiceSession?.appDidBecomeInactive()
        }
      }
      // Passive reads only; a departed session's retained cleanup becomes visible here.
      .onAppear { refreshCleanupRecovery() }
      .onChange(of: enrollment.phase) { _, _ in refreshCleanupRecovery() }
      .onChange(of: enrollment.practiceSession.map(ObjectIdentifier.init)) { _, _ in
        refreshCleanupRecovery()
      }
    }
  }
}
