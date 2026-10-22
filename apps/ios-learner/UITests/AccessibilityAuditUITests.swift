import XCTest

final class AccessibilityAuditUITests: XCTestCase {
  @MainActor
  func testEnrollmentScreenPassesPlatformAccessibilityAudit() throws {
    let app = XCUIApplication()
    app.launchArguments = ["-CadenceClinicalMode"]
    app.launch()

    XCTAssertTrue(app.staticTexts["Connect this device"].waitForExistence(timeout: 5))
    XCTAssertTrue(app.staticTexts["Practice server address"].exists)
    XCTAssertTrue(app.staticTexts["Practice link code"].exists)
    XCTAssertTrue(app.buttons["Connect for practice"].isHittable)

    try app.performAccessibilityAudit()
  }

  @MainActor
  func testReadyPracticeScreenPassesPlatformAccessibilityAudit() throws {
    let app = XCUIApplication()
    app.launchArguments = ["-accessibility-practice-preview"]
    app.launch()

    XCTAssertTrue(app.buttons["Record"].waitForExistence(timeout: 5))
    XCTAssertTrue(app.buttons["Record"].isHittable)

    try app.performAccessibilityAudit()
  }

  @MainActor
  func testAssignmentLoadingScreenPassesPlatformAccessibilityAudit() throws {
    let app = XCUIApplication()
    app.launchArguments = ["-accessibility-assignment-loading-preview"]
    app.launch()

    XCTAssertTrue(
      app.staticTexts["Loading practice assignment"].waitForExistence(timeout: 5)
    )
    try app.performAccessibilityAudit()
  }

  @MainActor
  func testNoAssignmentScreenPassesPlatformAccessibilityAudit() throws {
    let app = XCUIApplication()
    app.launchArguments = ["-accessibility-no-assignment-preview"]
    app.launch()

    XCTAssertTrue(app.staticTexts["No practice assignment yet"].waitForExistence(timeout: 5))
    XCTAssertTrue(app.buttons["Check again"].isHittable)
    XCTAssertTrue(app.buttons["Unlink this device"].isHittable)
    try app.performAccessibilityAudit()
  }

  @MainActor
  func testAssignmentErrorScreenPassesPlatformAccessibilityAudit() throws {
    let app = XCUIApplication()
    app.launchArguments = ["-accessibility-assignment-error-preview"]
    app.launch()

    XCTAssertTrue(app.staticTexts["Practice could not load"].waitForExistence(timeout: 5))
    XCTAssertTrue(app.buttons["Check again"].isHittable)
    XCTAssertTrue(app.buttons["Unlink this device"].isHittable)
    try app.performAccessibilityAudit()
  }

  @MainActor
  func testUnlinkRequiresAnExplicitChoice() throws {
    let app = XCUIApplication()
    app.launchArguments = ["-accessibility-no-assignment-preview"]
    app.launch()

    let unlink = app.buttons["Unlink this device"]
    XCTAssertTrue(unlink.waitForExistence(timeout: 5))
    unlink.tap()
    XCTAssertTrue(app.buttons["Keep device linked"].waitForExistence(timeout: 2))
    app.buttons["Keep device linked"].tap()
    XCTAssertTrue(app.buttons["Check again"].isHittable)

    unlink.tap()
    app.buttons["Unlink device"].tap()
    XCTAssertTrue(app.buttons["Connect for practice"].waitForExistence(timeout: 2))
  }
}
