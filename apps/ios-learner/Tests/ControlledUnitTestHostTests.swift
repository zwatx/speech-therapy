#if DEBUG && targetEnvironment(simulator)
  import XCTest

  @testable import CadenceLearner

  @MainActor
  final class ControlledUnitTestHostTests: XCTestCase {
    func testActualApplicationInitializationSelectedInertUnitHost() {
      XCTAssertTrue(ControlledUnitTestHost.isEnabled)
      XCTAssertTrue(ControlledUnitTestHost.appInitializedWithInertRoot)
    }

    func testRecognizedUnitHostIndicatorsSelectInertRoot() {
      for environment in [
        ["CADENCE_CONTROLLED_UNIT_HOST": "1"],
        ["TEST_RUNNER_CADENCE_CONTROLLED_UNIT_HOST": "1"],
        ["XCTestConfigurationFilePath": "generated-test-configuration"],
      ] {
        XCTAssertTrue(
          ControlledUnitTestHost.selectsInertRoot(environment: environment, hasXCTestRuntime: false)
        )
      }
      XCTAssertTrue(
        ControlledUnitTestHost.selectsInertRoot(environment: [:], hasXCTestRuntime: true))
    }

    func testOrdinaryDevelopmentLaunchDoesNotSelectUnitHost() {
      for environment in [
        [:], ["CADENCE_CONTROLLED_UNIT_HOST": "0"],
        ["TEST_RUNNER_CADENCE_CONTROLLED_UNIT_HOST": "0"],
        ["CADENCE_UI_TEST_FIXTURE": "1"],
      ] {
        XCTAssertFalse(
          ControlledUnitTestHost.selectsInertRoot(environment: environment, hasXCTestRuntime: false)
        )
      }
    }
  }

#endif
