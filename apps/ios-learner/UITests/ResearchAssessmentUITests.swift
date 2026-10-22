import XCTest

@MainActor
final class ResearchAssessmentUITests: XCTestCase {
  func testLabRequiresExplanationAndExplicitAgeWordAndProcessingChoice() throws {
    let app = launch()
    XCTAssertTrue(app.staticTexts["cadence.lab.state.consent"].waitForExistence(timeout: 5))
    XCTAssertFalse(app.buttons["cadence.lab.record"].exists)
    app.buttons["cadence.lab.consent.accept"].tap()
    XCTAssertTrue(app.staticTexts["cadence.lab.state.setup"].waitForExistence(timeout: 3))
    XCTAssertTrue(app.buttons["cadence.lab.age"].label.contains("Choose"))
    XCTAssertEqual(app.switches["cadence.lab.optin"].value as? String, "0")
    scrollTo(app.buttons["cadence.lab.continue"], in: app)
    XCTAssertFalse(app.buttons["cadence.lab.continue"].isEnabled)
    attach(app, name: "lab-setup")
    app.buttons["cadence.lab.close"].tap()
    XCTAssertTrue(app.buttons["cadence.start"].waitForExistence(timeout: 3))
  }

  func testUnsupportedSoundExplainsUnavailableWithoutRecording() throws {
    let app = launch()
    app.buttons["cadence.lab.consent.accept"].tap()
    app.buttons["cadence.lab.age"].tap()
    app.buttons["6"].tap()
    app.switches["cadence.lab.optin"].tap()
    let word = app.buttons["cadence.lab.word.zh-middle-treasure"]
    scrollTo(word, in: app)
    word.tap()
    scrollTo(app.buttons["cadence.lab.continue"], in: app)
    XCTAssertTrue(app.buttons["cadence.lab.continue"].isEnabled)
    app.buttons["cadence.lab.continue"].tap()
    XCTAssertTrue(app.staticTexts["cadence.lab.state.unavailable"].waitForExistence(timeout: 3))
    XCTAssertFalse(app.buttons["cadence.lab.record"].exists)
    XCTAssertTrue(app.buttons["cadence.lab.practice"].exists)
    attach(app, name: "lab-unavailable")
    app.buttons["cadence.lab.change-word"].tap()
    XCTAssertTrue(app.staticTexts["cadence.lab.state.setup"].waitForExistence(timeout: 3))
    XCTAssertEqual(app.switches["cadence.lab.optin"].value as? String, "0")
  }

  func testLargeTextLabExplanationAccessibility() throws {
    let app = launch(extra: [
      "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL",
    ])
    try app.performAccessibilityAudit()
    scrollTo(app.buttons["cadence.lab.consent.accept"], in: app)
    XCTAssertTrue(app.buttons["cadence.lab.consent.accept"].isHittable)
    attach(app, name: "lab-large-text")
  }

  private func launch(extra: [String] = []) -> XCUIApplication {
    continueAfterFailure = false
    let app = XCUIApplication()
    app.launchArguments =
      ["-CadenceAssessmentMode"]
      + (extra.isEmpty
        ? ["-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryL"] : extra)
    app.launch()
    return app
  }
  private func scrollTo(_ element: XCUIElement, in app: XCUIApplication) {
    for _ in 0..<12 {
      if element.isHittable { return }
      app.scrollViews.firstMatch.swipeUp()
    }
  }
  private func attach(_ app: XCUIApplication, name: String) {
    let attachment = XCTAttachment(screenshot: app.screenshot())
    attachment.name = name
    attachment.lifetime = .keepAlways
    add(attachment)
  }
}
