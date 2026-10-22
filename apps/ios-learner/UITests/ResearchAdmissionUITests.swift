import XCTest

@MainActor
final class ResearchAdmissionUITests: XCTestCase {
  func testAdmissionLabRemainsOptionalAndRequiresExplicitProcessing() throws {
    let app = launch(large: false)
    XCTAssertTrue(app.staticTexts["cadence.lab.state.consent"].waitForExistence(timeout: 5))
    attach(app, "admission-consent")
    scrollTo(app.buttons["cadence.lab.consent.accept"], app)
    app.buttons["cadence.lab.consent.accept"].tap()
    XCTAssertTrue(app.staticTexts["cadence.lab.state.setup"].waitForExistence(timeout: 3))
    XCTAssertEqual(app.switches["cadence.lab.optin"].value as? String, "0")
    XCTAssertFalse(app.buttons["cadence.lab.record"].exists)
    attach(app, "admission-setup")
    app.buttons["cadence.lab.close"].tap()
    XCTAssertTrue(app.buttons["cadence.start"].waitForExistence(timeout: 3))
  }

  func testAdmissionExplanationLargeTextWithoutSensorActivation() throws {
    let app = launch(large: true)
    XCTAssertTrue(app.staticTexts["cadence.lab.state.consent"].waitForExistence(timeout: 5))
    try app.performAccessibilityAudit()
    attach(app, "admission-large-text-top")
    scrollTo(app.buttons["cadence.lab.consent.accept"], app)
    XCTAssertTrue(app.buttons["cadence.lab.consent.accept"].isHittable)
    attach(app, "admission-large-text-action")
  }

  func testAboutKeepsOldLabAndExposesAdmissionAsSeparateOptionalEntry() throws {
    continueAfterFailure = false
    let app = XCUIApplication()
    app.launch()
    XCTAssertTrue(app.buttons["cadence.start"].waitForExistence(timeout: 5))
    app.buttons["About practice and privacy"].tap()
    let admission = app.buttons["cadence.admission-lab.open"]
    scrollTo(admission, app)
    XCTAssertTrue(app.buttons["cadence.lab.open"].exists)
    XCTAssertTrue(admission.isHittable)
    attach(app, "admission-about-entries")
    admission.tap()
    XCTAssertTrue(app.staticTexts["cadence.lab.state.consent"].waitForExistence(timeout: 3))
    XCTAssertTrue(app.staticTexts["Speech admission lab"].exists)
    XCTAssertFalse(app.buttons["cadence.lab.record"].exists)
    attach(app, "admission-opened-from-about")
  }

  private func launch(large: Bool) -> XCUIApplication {
    continueAfterFailure = false
    let app = XCUIApplication()
    app.launchArguments = [
      "-CadenceAssessmentMode", "-CadenceAdmissionMode", "-UIPreferredContentSizeCategoryName",
      large ? "UICTContentSizeCategoryAccessibilityXXXL" : "UICTContentSizeCategoryL",
    ]
    app.launch()
    return app
  }
  private func scrollTo(_ element: XCUIElement, _ app: XCUIApplication) {
    for _ in 0..<12 {
      if element.isHittable { return }
      app.scrollViews.firstMatch.swipeUp()
    }
  }
  private func attach(_ app: XCUIApplication, _ name: String) {
    let attachment = XCTAttachment(screenshot: app.screenshot())
    attachment.name = name
    attachment.lifetime = .keepAlways
    add(attachment)
  }
}
