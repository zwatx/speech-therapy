#if DEBUG && targetEnvironment(simulator)
  import XCTest
  @testable import CadenceLearner

  @MainActor
  final class ControlledUITestHostTests: XCTestCase {
    private let runID = UUID(uuidString: "7A8F4123-34EF-4967-9012-89ABCDEF0123")!
    private let optIn = ["CADENCE_CONTROLLED_UI_HOST": "1"]

    private func arguments(
      _ mode: String = "Sound", _ caseFlag: String = "Sound", _ value: String = "br"
    ) -> [String] {
      [
        "CadenceLearner", "-Cadence\(mode)Mode", "-Cadence\(caseFlag)UITestCase", value,
        "-CadenceControlledUIRunID", runID.uuidString,
      ]
    }
    private func selection(
      _ arguments: [String], environment: [String: String]? = nil,
      runtime: Bool = false
    ) -> ControlledAppLaunch.Selection {
      ControlledAppLaunch.select(
        arguments: arguments, environment: environment ?? optIn,
        hasXCTestRuntime: runtime)
    }

    func testCompleteMatchingGeneratedModesOverrideAutomaticXCTestHost() {
      let cases: [(String, String, String, ControlledUIConfiguration.Fixture)] = [
        ("Sound", "Sound", "br", .sound(.br)),
        ("Feedback", "UnifiedFeedback", "freeCompletion", .feedback(.freeCompletion)),
        ("GuidedWord", "GuidedWord", "mixed", .guided(.mixed)),
      ]
      for (mode, flag, value, fixture) in cases {
        var environment = optIn
        environment["XCTestConfigurationFilePath"] = "generated-test-configuration"
        environment["CADENCE_UI_TEST_FIXTURE"] = "1"
        XCTAssertEqual(
          selection(arguments(mode, flag, value), environment: environment, runtime: true),
          .generated(.init(fixture: fixture, runID: runID)))
      }
    }

    func testMirrorAdmissionIsExplicitClosedAndHasNoHomeOrHistoryRoutes() {
      for testCase in PracticeMirrorGeneratedCase.allCases {
        let args = arguments("Mirror", "Mirror", testCase.rawValue)
        XCTAssertEqual(selection(args), .generated(.init(fixture: .mirror(testCase), runID: runID)))
        XCTAssertEqual(selection(args, environment: [:]), .inert)
        XCTAssertEqual(selection(args + ["-CadenceFeedbackMode"]), .inert)
        XCTAssertEqual(selection(args + ["-CadenceClinicalMode"]), .inert)
        XCTAssertEqual(selection(arguments("Mirror", "Sound", "br")), .inert)
        let configuration = ControlledUIConfiguration(fixture: .mirror(testCase), runID: runID)
        for destination in ControlledUIConfiguration.Destination.allCases {
          XCTAssertEqual(configuration.admits(destination), destination == .mirror)
        }
      }
      XCTAssertEqual(selection(arguments("Mirror", "Mirror", "unknown")), .inert)
      XCTAssertEqual(selection(Array(arguments("Mirror", "Mirror", "sample").dropLast(2))), .inert)
      XCTAssertEqual(
        selection(
          arguments("Mirror", "Mirror", "sample"),
          environment: ["CADENCE_CONTROLLED_UI_HOST": "1", "CADENCE_CONTROLLED_UNIT_HOST": "1"]),
        .inert)
    }

    func testRawAndRunnerPrefixedUIOptInAreAccepted() {
      for environment in [
        optIn, ["TEST_RUNNER_CADENCE_CONTROLLED_UI_HOST": "1"],
        ["CADENCE_CONTROLLED_UI_HOST": "1", "TEST_RUNNER_CADENCE_CONTROLLED_UI_HOST": "1"],
      ] {
        XCTAssertEqual(
          selection(arguments(), environment: environment),
          .generated(.init(fixture: .sound(.br), runID: runID)))
      }
      XCTAssertEqual(
        selection(arguments() + ["-AppleLanguages", "(en)", "-AppleLocale", "en_US"]),
        .generated(.init(fixture: .sound(.br), runID: runID)))
      var lower = arguments()
      lower[lower.count - 1] = runID.uuidString.lowercased()
      XCTAssertEqual(selection(lower), .generated(.init(fixture: .sound(.br), runID: runID)))
    }

    func testExplicitUnitFlagAlwaysWinsAgainstCompleteUIAdmission() {
      for key in ["CADENCE_CONTROLLED_UNIT_HOST", "TEST_RUNNER_CADENCE_CONTROLLED_UNIT_HOST"] {
        var environment = optIn
        environment[key] = "1"
        XCTAssertEqual(selection(arguments(), environment: environment), .inert)
        XCTAssertEqual(selection(arguments(), environment: environment, runtime: true), .inert)
      }
    }

    func testInvalidOrConflictingUIOptInStaysInert() {
      for environment in [
        ["CADENCE_CONTROLLED_UI_HOST": "0"], ["CADENCE_CONTROLLED_UI_HOST": "true"],
        ["TEST_RUNNER_CADENCE_CONTROLLED_UI_HOST": ""],
        ["CADENCE_CONTROLLED_UI_HOST": "1", "TEST_RUNNER_CADENCE_CONTROLLED_UI_HOST": "0"],
        ["CADENCE_CONTROLLED_UI_HOST": "0", "TEST_RUNNER_CADENCE_CONTROLLED_UI_HOST": "1"],
      ] {
        XCTAssertEqual(selection(arguments(), environment: environment), .inert)
      }
    }

    func testAutomaticAndIncompleteTestLaunchesStayInert() {
      XCTAssertEqual(selection(["CadenceLearner"], environment: [:], runtime: true), .inert)
      for key in [
        "XCTestConfigurationFilePath", "XCTestBundlePath", "XCInjectBundleInto",
        "CADENCE_UI_TEST_FIXTURE", "TEST_RUNNER_CADENCE_UI_TEST_FIXTURE",
      ] {
        XCTAssertEqual(selection(["CadenceLearner"], environment: [key: ""]), .inert)
      }
      XCTAssertEqual(selection(arguments(), environment: [:]), .inert)
      XCTAssertEqual(
        selection(["CadenceLearner", "-CadenceUnknownUITestCase", "unknown"], environment: [:]),
        .inert)
      XCTAssertEqual(
        selection(
          ["CadenceLearner", "-CadenceControlledUIRunID", runID.uuidString], environment: [:]),
        .inert)
      XCTAssertEqual(selection(["CadenceLearner"]), .inert)
    }

    func testRunIDMustBeSingleValidNonzeroUUID() {
      for value in [
        "", "not-a-uuid", "00000000-0000-0000-0000-000000000000", runID.uuidString + " ",
      ] {
        var args = arguments()
        args[args.count - 1] = value
        XCTAssertEqual(selection(args), .inert, value)
      }
      XCTAssertEqual(selection(Array(arguments().dropLast(2))), .inert)
      XCTAssertEqual(selection(Array(arguments().dropLast())), .inert)
      XCTAssertEqual(
        selection(arguments() + ["-CadenceControlledUIRunID", UUID().uuidString]), .inert)
    }

    func testExactlyOneMatchingKnownModeAndCaseAreRequired() {
      let invalid: [[String]] = [
        arguments("Sound", "UnifiedFeedback", "combined"),
        arguments("Feedback", "GuidedWord", "mixed"),
        arguments("GuidedWord", "Sound", "br"),
        arguments("Sound", "Sound", "unknown"),
        arguments("Feedback", "UnifiedFeedback", "unknown"),
        arguments("GuidedWord", "GuidedWord", "unknown"),
        arguments() + ["-CadenceFeedbackMode"],
        arguments() + ["-CadenceSoundMode"],
        arguments() + ["-CadenceSoundUITestCase", "br"],
        arguments() + ["-CadenceUnifiedFeedbackUITestCase", "combined"],
        ["CadenceLearner", "-CadenceSoundMode", "-CadenceControlledUIRunID", runID.uuidString],
        [
          "CadenceLearner", "-CadenceSoundUITestCase", "br", "-CadenceControlledUIRunID",
          runID.uuidString,
        ],
      ]
      for args in invalid { XCTAssertEqual(selection(args), .inert, args.joined(separator: " ")) }
    }

    func testUnselectedLiveOrUnknownCadenceRoutesCannotEnterControlledRoot() {
      for flag in [
        "-CadenceClinicalMode", "-CadenceAssessmentMode", "-CadenceUnknownMode",
        "-CadenceSomethingElse", "-accessibility-practice-preview",
      ] {
        XCTAssertEqual(selection(arguments() + [flag]), .inert, flag)
      }
    }

    func testOrdinaryDevelopmentRoutingRemainsAvailableWithoutTestIntent() {
      for args in [
        ["CadenceLearner"], ["CadenceLearner", "-CadenceClinicalMode"],
        ["CadenceLearner", "-CadenceSoundMode"], ["CadenceLearner", "-CadenceAssessmentMode"],
        ["CadenceLearner", "-accessibility-practice-preview"],
      ] {
        XCTAssertEqual(selection(args, environment: [:]), .development)
      }
      XCTAssertEqual(
        selection(["CadenceLearner"], environment: ["CADENCE_CONTROLLED_UNIT_HOST": "0"]),
        .development)
    }

    func testGeneratedRootMembershipAllowsOnlySafeHomeAndSelectedResearchMode() {
      let cases: [(ControlledUIConfiguration.Fixture, ControlledUIConfiguration.Destination)] = [
        (.sound(.br), .sound), (.feedback(.combined), .feedback), (.guided(.mixed), .guided),
      ]
      for (fixture, selected) in cases {
        let configuration = ControlledUIConfiguration(fixture: fixture, runID: runID)
        for destination in ControlledUIConfiguration.Destination.allCases {
          let safeHome: [ControlledUIConfiguration.Destination] = [
            .home, .about, .historyRead, .historyClear,
          ]
          XCTAssertEqual(
            configuration.admits(destination),
            safeHome.contains(destination) || destination == selected)
        }
      }
    }
  }
#endif

#if DEBUG && targetEnvironment(simulator)
  // Root append: place after the closing brace of ControlledUITestHostTests and before the
  // file's final `#endif`. The original 11 tests stay byte-identical. Pure admission only:
  // no host, store, capturer, player or driver is constructed.
  extension ControlledUITestHostTests {
    private var directTryRunID: UUID { UUID(uuidString: "3C1D9E57-0B4A-4F62-8E13-5A7B9C2D4E61")! }

    private func directTryArguments(
      _ mode: String = "DirectTry", _ caseFlag: String = "DirectTry", value: String = "twoTry"
    ) -> [String] {
      [
        "CadenceLearner", "-Cadence\(mode)Mode", "-Cadence\(caseFlag)UITestCase", value,
        "-CadenceControlledUIRunID", directTryRunID.uuidString,
      ]
    }

    private func directTrySelection(
      _ arguments: [String],
      environment: [String: String] = ["CADENCE_CONTROLLED_UI_HOST": "1"],
      runtime: Bool = false
    ) -> ControlledAppLaunch.Selection {
      ControlledAppLaunch.select(
        arguments: arguments, environment: environment, hasXCTestRuntime: runtime)
    }

    func testDirectTryCasesAreClosedNormalAndLargestTextPairs() {
      let bases: [DirectTryGeneratedCase] = [
        .twoTry, .finish, .denied, .failedStart, .saveFailure, .wordCheck, .wordCheckCancel,
        .wordCheckUnavailable, .wordCheckGuess, .wordCheckCompare, .wordCheckTimeout, .skip,
      ]
      XCTAssertEqual(DirectTryGeneratedCase.allCases.count, bases.count * 2)
      for base in bases {
        XCTAssertFalse(base.largeText)
        XCTAssertEqual(base.base, base)
        let large = DirectTryGeneratedCase(rawValue: base.rawValue + "AX")
        XCTAssertEqual(large?.largeText, true)
        XCTAssertEqual(large?.base, base)
      }
      for value in ["", "twotry", "TwoTry", "twoTryAXAX", "sample", "unknown"] {
        XCTAssertNil(DirectTryGeneratedCase(rawValue: value), value)
      }
    }

    func testDirectTryAdmissionIsExplicitClosedAndHasNoHomeOrHistoryRoutes() {
      for testCase in DirectTryGeneratedCase.allCases {
        let args = directTryArguments(value: testCase.rawValue)
        let expected = ControlledAppLaunch.Selection.generated(
          .init(fixture: .directTry(testCase), runID: directTryRunID))
        for environment in [
          ["CADENCE_CONTROLLED_UI_HOST": "1"], ["TEST_RUNNER_CADENCE_CONTROLLED_UI_HOST": "1"],
          ["CADENCE_CONTROLLED_UI_HOST": "1", "TEST_RUNNER_CADENCE_CONTROLLED_UI_HOST": "1"],
        ] {
          XCTAssertEqual(directTrySelection(args, environment: environment), expected)
          XCTAssertEqual(
            directTrySelection(args, environment: environment, runtime: true), expected)
        }
        var lower = args
        lower[lower.count - 1] = directTryRunID.uuidString.lowercased()
        XCTAssertEqual(directTrySelection(lower), expected)
        let configuration = ControlledUIConfiguration(
          fixture: .directTry(testCase), runID: directTryRunID)
        for destination in ControlledUIConfiguration.Destination.allCases {
          XCTAssertEqual(configuration.admits(destination), destination == .directTry)
        }
      }
    }

    func testDirectTryUnitHostFlagAlwaysWins() {
      for key in ["CADENCE_CONTROLLED_UNIT_HOST", "TEST_RUNNER_CADENCE_CONTROLLED_UNIT_HOST"] {
        let environment = ["CADENCE_CONTROLLED_UI_HOST": "1", key: "1"]
        for testCase in DirectTryGeneratedCase.allCases {
          let args = directTryArguments(value: testCase.rawValue)
          XCTAssertEqual(directTrySelection(args, environment: environment), .inert)
          XCTAssertEqual(
            directTrySelection(args, environment: environment, runtime: true), .inert)
        }
      }
    }

    func testDirectTryUnknownConflictingMismatchedOrLiveArgumentsStayInert() {
      let args = directTryArguments()
      let invalid: [[String]] = [
        directTryArguments(value: "unknown"),
        directTryArguments(value: "sample"),
        directTryArguments("DirectTry", "Mirror", value: "twoTry"),
        directTryArguments("Mirror", "DirectTry", value: "sample"),
        directTryArguments("Mirror", "DirectTry", value: "twoTry"),
        directTryArguments("Sound", "DirectTry", value: "twoTry"),
        directTryArguments("DirectTry", "Sound", value: "br"),
        args + ["-CadenceMirrorMode"],
        args + ["-CadenceDirectTryMode"],
        args + ["-CadenceDirectTryUITestCase", "finish"],
        args + ["-CadenceMirrorUITestCase", "sample"],
        args + ["-CadenceClinicalMode"],
        args + ["-CadenceAssessmentMode"],
        args + ["-CadenceUnknownMode"],
        args + ["-accessibility-practice-preview"],
        args + ["-CadenceControlledUIRunID", UUID().uuidString],
        Array(args.dropLast(2)),
        Array(args.dropLast()),
        [
          "CadenceLearner", "-CadenceDirectTryMode", "-CadenceControlledUIRunID",
          directTryRunID.uuidString,
        ],
      ]
      for arguments in invalid {
        XCTAssertEqual(directTrySelection(arguments), .inert, arguments.joined(separator: " "))
      }
      for value in ["", "not-a-uuid", "00000000-0000-0000-0000-000000000000"] {
        var zero = args
        zero[zero.count - 1] = value
        XCTAssertEqual(directTrySelection(zero), .inert, value)
      }
    }

    func testDirectTryWithoutValidOptInStaysInertAndNeverDevelopment() {
      let args = directTryArguments()
      for environment in [
        [:], ["CADENCE_CONTROLLED_UI_HOST": "0"], ["CADENCE_CONTROLLED_UI_HOST": "true"],
        ["CADENCE_CONTROLLED_UI_HOST": "1", "TEST_RUNNER_CADENCE_CONTROLLED_UI_HOST": "0"],
      ] {
        XCTAssertEqual(directTrySelection(args, environment: environment), .inert)
      }
      XCTAssertEqual(directTrySelection(args, environment: [:], runtime: true), .inert)
    }

    func testExistingFixturesNeverAdmitDirectTryAndKeepTheirRoutes() {
      let cases: [(ControlledUIConfiguration.Fixture, ControlledUIConfiguration.Destination)] = [
        (.sound(.br), .sound), (.feedback(.combined), .feedback), (.guided(.mixed), .guided),
        (.mirror(.sample), .mirror),
      ]
      for (fixture, selected) in cases {
        let configuration = ControlledUIConfiguration(fixture: fixture, runID: directTryRunID)
        XCTAssertFalse(configuration.admits(.directTry))
        XCTAssertTrue(configuration.admits(selected))
      }
      // Existing mirror admission is unchanged by the new mode/case flags.
      XCTAssertEqual(
        directTrySelection(directTryArguments("Mirror", "Mirror", value: "sample")),
        .generated(.init(fixture: .mirror(.sample), runID: directTryRunID)))
    }
  }

#endif

#if DEBUG && targetEnvironment(simulator)
  extension ControlledUITestHostTests {
    func testLocalGuidedAdmissionRequiresExactExplicitClosedConfiguration() {
      for testCase in LocalGuidedGeneratedCase.allCases {
        let args = arguments("LocalGuided", "LocalGuided", testCase.rawValue)
        XCTAssertEqual(
          selection(args, runtime: true),
          .generated(.init(fixture: .localGuided(testCase), runID: runID)))
        XCTAssertEqual(selection(args, environment: [:]), .inert)
        for destination in ControlledUIConfiguration.Destination.allCases {
          let configuration = ControlledUIConfiguration(
            fixture: .localGuided(testCase), runID: runID)
          XCTAssertEqual(configuration.admits(destination), destination == .localGuided)
        }
      }
    }
    func testLocalGuidedMalformedMixedAndDuplicateRequestsFailClosed() {
      let args = arguments("LocalGuided", "LocalGuided", "setup")
      for rejected in [
        arguments("LocalGuided", "GuidedWord", "mixed"),
        arguments("GuidedWord", "LocalGuided", "setup"),
        arguments("LocalGuided", "LocalGuided", "live"),
        arguments("LocalGuided", "LocalGuided", "unknown"),
        args + ["-CadenceLocalGuidedUITestCase", "practice"],
        args + ["-CadenceDirectTryMode"], args + ["-CadenceClinicalMode"],
        args + ["-accessibility-practice-preview"],
        args + ["-CadenceControlledUIRunID", runID.uuidString],
        Array(args.dropLast(2)),
      ] { XCTAssertEqual(selection(rejected), .inert) }
      var zeroID = args
      zeroID[zeroID.count - 1] = "00000000-0000-0000-0000-000000000000"
      XCTAssertEqual(selection(zeroID), .inert)
    }
    func testLocalGuidedUnitOverrideAndConflictingOptInCannotConstructHost() {
      let args = arguments("LocalGuided", "LocalGuided", "recheckAX")
      for key in ["CADENCE_CONTROLLED_UNIT_HOST", "TEST_RUNNER_CADENCE_CONTROLLED_UNIT_HOST"] {
        XCTAssertEqual(
          selection(args, environment: optIn.merging([key: "1"]) { _, new in new }), .inert)
      }
      XCTAssertEqual(
        selection(
          args,
          environment: [
            "CADENCE_CONTROLLED_UI_HOST": "1", "TEST_RUNNER_CADENCE_CONTROLLED_UI_HOST": "0",
          ]), .inert)
      XCTAssertEqual(
        selection(args, environment: ["TEST_RUNNER_CADENCE_CONTROLLED_UI_HOST": "1"]),
        .generated(.init(fixture: .localGuided(.recheckAX), runID: runID)))
    }
    func testLocalGuidedCompactAndLargestCasesHaveOneToOnePairs() {
      let compact = LocalGuidedGeneratedCase.allCases.filter { !$0.largeText }
      XCTAssertEqual(compact.count, 6)
      XCTAssertEqual(LocalGuidedGeneratedCase.allCases.count, 12)
      for testCase in compact {
        let large = LocalGuidedGeneratedCase(rawValue: testCase.rawValue + "AX")
        XCTAssertEqual(large?.base, testCase)
        XCTAssertEqual(large?.holdsCheck, testCase.holdsCheck)
      }
      for testCase in DirectTryGeneratedCase.allCases {
        XCTAssertFalse(
          ControlledUIConfiguration(fixture: .directTry(testCase), runID: runID).admits(
            .localGuided))
      }
    }
  }
#endif
