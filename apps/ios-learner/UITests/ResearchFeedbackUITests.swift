import XCTest

/// Actual simulator rendering/navigation only. Never taps Record, Replay or Check.
@MainActor
final class ResearchFeedbackUITests: XCTestCase {
  func testWordMenuPreservesAllCanonicalChoicesAndSelectsBanana() throws {
    let app = launchFeedback(large: false)
    let menu = app.buttons["feedback-word-picker"]
    scrollTo(menu, app)
    XCTAssertTrue(menu.isHittable)
    menu.tap()
    let labels = [
      "rabbit · r sound", "bread · r sound", "door · r sound",
      "baby · first b sound", "baby · second b sound", "banana · first n sound",
      "backpack · first k sound", "backpack · second k sound", "sky · s sound",
      "vase · v sound", "yo-yo · first y sound", "thumb · th sound",
      "feather · voiced th sound", "ring · ng sound", "treasure · zh sound",
    ]
    let banana = app.buttons["banana · first n sound"]
    XCTAssertTrue(banana.waitForExistence(timeout: 3))
    let inventory = XCTAttachment(string: app.debugDescription)
    inventory.name = "feedback-word-menu-canonical-inventory"
    inventory.lifetime = .keepAlways
    add(inventory)
    attach(app, "feedback-word-menu-options")
    XCTAssertEqual(app.buttons.matching(NSPredicate(format: "label IN %@", labels)).count, 15)
    for label in labels {
      XCTAssertEqual(
        app.buttons.matching(NSPredicate(format: "label == %@", label)).count, 1, label)
    }
    XCTAssertTrue(
      banana.isHittable, "Selection requires the observed menu option, not guessed coordinates.")
    banana.tap()
    XCTAssertEqual(menu.value as? String, "banana · first n sound")
    attach(app, "feedback-word-menu-selected-banana-setup")
    let word = app.staticTexts["feedback-word"]
    scrollTo(word, app)
    XCTAssertTrue(word.isHittable)
    let changedWord = XCTNSPredicateExpectation(
      predicate: NSPredicate(format: "label == %@", "banana"), object: word)
    XCTAssertEqual(XCTWaiter.wait(for: [changedWord], timeout: 5), .completed)
    XCTAssertEqual(word.label, "banana")
    assertNoRecordingOrProcessing(app)
    attach(app, "feedback-word-menu-selected-banana-word")
  }

  func testDefaultAllowsLocalRecordingWithoutAgeOrProcessingAndCloseReturnsPractice() throws {
    let app = launchFeedback(large: false)
    XCTAssertTrue(app.staticTexts["feedback-state-ready"].waitForExistence(timeout: 5))
    XCTAssertTrue(
      app.buttons["feedback-record"].isHittable, "Record must be available before scrolling.")
    let geometry = XCTAttachment(
      string:
        "viewport=\(app.windows.firstMatch.frame)\nRecord.frame=\(app.buttons["feedback-record"].frame)\n"
        + "dynamicType=UICTContentSizeCategoryL\nactual XCTest simulator bounds")
    geometry.name = "feedback-default-record-viewport"
    geometry.lifetime = .keepAlways
    add(geometry)
    attach(app, "feedback-default-top")
    let age = element("feedback-context", app)
    let optIn = element("feedback-opt-in", app)
    scrollTo(age, app)
    XCTAssertTrue(
      age.label.contains("Not set") || (age.value as? String)?.contains("Not set") == true)
    XCTAssertEqual(optIn.value as? String, "Off")
    scrollTo(app.buttons["feedback-record"], app)
    XCTAssertTrue(app.buttons["feedback-record"].isHittable)
    assertNoRecordingOrProcessing(app)
    attach(app, "feedback-default-record-controls")
    let privacyNote = app.staticTexts["feedback-note"]
    scrollTo(privacyNote, app)
    XCTAssertTrue(privacyNote.isHittable)
    attach(app, "feedback-default-privacy-footer")
    app.buttons["feedback-close"].tap()
    XCTAssertTrue(app.buttons["cadence.start"].waitForExistence(timeout: 5))
  }

  func testExplicitAgeOptInAndNextWordStaySensorFreeUntilSeparateActions() throws {
    let app = launchFeedback(large: false)
    let age = element("feedback-context", app)
    scrollTo(age, app)
    age.tap()
    XCTAssertTrue(app.buttons["Child, age 9"].waitForExistence(timeout: 3))
    app.buttons["Child, age 9"].tap()
    XCTAssertTrue(age.label.contains("9") || (age.value as? String)?.contains("9") == true)
    let optIn = element("feedback-opt-in", app)
    scrollTo(optIn, app)
    optIn.tap()
    XCTAssertEqual(optIn.value as? String, "On")
    let next = app.buttons["feedback-next"]
    scrollTo(next, app)
    XCTAssertTrue(next.isEnabled)
    XCTAssertTrue(next.isHittable)
    next.tap()
    attach(app, "feedback-after-next-controls")
    let word = app.staticTexts["feedback-word"]
    scrollTo(word, app)
    XCTAssertTrue(word.isHittable)
    attach(app, "feedback-after-next-visible-word")
    let changedWord = XCTNSPredicateExpectation(
      predicate: NSPredicate(format: "label == %@", "bread"), object: word)
    let nextWordResult = XCTWaiter.wait(for: [changedWord], timeout: 5)
    if nextWordResult != .completed { capturePracticeFailure(app) }
    XCTAssertEqual(nextWordResult, .completed)
    XCTAssertEqual(word.label, "bread")
    XCTAssertTrue(app.staticTexts["feedback-state-ready"].exists)
    assertNoRecordingOrProcessing(app)
    attach(app, "feedback-context-nine-opt-in-next-word")
    app.buttons["feedback-close"].tap()
    XCTAssertTrue(app.buttons["cadence.start"].waitForExistence(timeout: 5))
  }

  func testAboutKeepsBothExistingLabsAndHomeOpensSeparateFeedback() throws {
    continueAfterFailure = false
    let app = XCUIApplication()
    app.launch()
    XCTAssertTrue(app.buttons["cadence.start"].waitForExistence(timeout: 5))
    app.buttons["About practice and privacy"].tap()
    let lab = app.buttons["cadence.lab.open"]
    scrollTo(lab, app)
    XCTAssertTrue(lab.isHittable)
    XCTAssertTrue(app.buttons["cadence.admission-lab.open"].exists)
    XCTAssertFalse(app.buttons["cadence.feedback.open"].exists)
    attach(app, "feedback-about-existing-labs")
    app.buttons["Done"].tap()
    let feedback = app.buttons["cadence.feedback.start"]
    scrollTo(feedback, app)
    XCTAssertTrue(feedback.isHittable)
    feedback.tap()
    XCTAssertTrue(app.staticTexts["feedback-title"].waitForExistence(timeout: 5))
    XCTAssertTrue(app.staticTexts["feedback-state-ready"].exists)
    assertNoRecordingOrProcessing(app)
    attach(app, "feedback-opened-from-home")
    app.buttons["feedback-close"].tap()
    XCTAssertTrue(app.buttons["cadence.start"].waitForExistence(timeout: 5))
  }

  func testLargeDynamicTypeAccessibilityAndHittableMinimumControls() throws {
    let app = launchFeedback(large: true)
    XCTAssertTrue(app.staticTexts["feedback-title"].waitForExistence(timeout: 5))
    attach(app, "feedback-large-text-top")
    for identifier in [
      "feedback-close", "feedback-word-picker", "feedback-context", "feedback-opt-in",
      "feedback-record", "feedback-next",
    ] {
      let control = element(identifier, app)
      scrollTo(control, app)
      XCTAssertTrue(control.isHittable, identifier)
      XCTAssertGreaterThanOrEqual(control.frame.height, 44, identifier)
      XCTAssertGreaterThanOrEqual(control.frame.width, 44, identifier)
      if identifier == "feedback-word-picker" || identifier == "feedback-context" {
        attach(app, "feedback-large-text-setup-\(identifier)")
      }
    }
    assertNoRecordingOrProcessing(app)
    attach(app, "feedback-large-text-controls")
    try app.performAccessibilityAudit()
  }

  private func launchFeedback(large: Bool) -> XCUIApplication {
    continueAfterFailure = false
    let app = XCUIApplication()
    app.launchArguments = [
      "-CadenceFeedbackMode", "-UIPreferredContentSizeCategoryName",
      large ? "UICTContentSizeCategoryAccessibilityXXXL" : "UICTContentSizeCategoryL",
    ]
    app.launch()
    return app
  }
  private func element(_ id: String, _ app: XCUIApplication) -> XCUIElement {
    app.descendants(matching: .any).matching(identifier: id).firstMatch
  }
  private func scrollTo(_ target: XCUIElement, _ app: XCUIApplication) {
    let window = app.windows.firstMatch.frame
    // Close belongs to the fixed inset, outside the scrolling content.
    if target.identifier == "feedback-close" {
      XCTAssertTrue(window.contains(target.frame) && target.isEnabled && target.isHittable)
      return
    }
    // The underlying Today ScrollView can coexist with the presented Feedback view.
    // Select the actual target's scroll ancestor, never the app's first ScrollView.
    let scroll = app.scrollViews.containing(.any, identifier: target.identifier).firstMatch
    guard !target.identifier.isEmpty, scroll.exists else {
      XCTFail("No scroll ancestor contains \(target.identifier)")
      return
    }
    let viewport = scroll.frame.intersection(window)
    var top = viewport.minY + 8
    for identifier in ["feedback-close", "feedback-close-note", "feedback-ui-test-banner"] {
      let inset = element(identifier, app)
      if inset.exists { top = max(top, inset.frame.maxY + 8) }
    }
    let bottom = viewport.maxY - 8
    let visibleHeight = bottom - top
    guard visibleHeight > 0 else {
      XCTFail("No unobscured Feedback viewport is available")
      return
    }
  }
  private func assertNoRecordingOrProcessing(_ app: XCUIApplication) {
    for id in [
      "feedback-stop", "feedback-check", "feedback-replay", "feedback-permission-progress",
      "feedback-checking-progress",
    ] { XCTAssertFalse(element(id, app).exists, id) }
  }
  private func attach(_ app: XCUIApplication, _ name: String) {
    let attachment = XCTAttachment(screenshot: app.screenshot())
    attachment.name = name
    attachment.lifetime = .keepAlways
    add(attachment)
  }
}
