import XCTest

/// Generated capture and invented bound observations. No sensors, network, models or audio output.
@MainActor
final class ResearchGuidedPracticePlanUITests: XCTestCase {
  func testMixedSummaryChosenSequenceFinishSkipAndFullRecheck() throws {
    let app = launch("mixed")
    start(app)
    for index in 0..<4 {
      record(app)
      activate("guided-check", app)
      let next = app.buttons["guided-next"]
      let ready = XCTNSPredicateExpectation(
        predicate: NSPredicate(format: "enabled == YES"), object: next)
      XCTAssertEqual(XCTWaiter.wait(for: [ready], timeout: 5), .completed)
      if index < 3 { activate("guided-next", app) }
    }
    finishRound(app)
    let original = row("r-middle-bread", app).label
    activate("guided-plan-open", app)
    XCTAssertEqual(app.staticTexts["guided-plan-count"].label, "0 of 3 chosen")
    XCTAssertTrue(app.staticTexts["guided-plan-suggestions"].label.contains("bread"))
    XCTAssertFalse(app.staticTexts["guided-plan-suggestions"].label.contains("door"))
    XCTAssertFalse(app.buttons["guided-plan-start"].isEnabled)
    activate("guided-plan-row-r-middle-bread", app)
    activate("guided-plan-row-r-beginning-rabbit", app)
    attach(app, "generated-plan-choice-mixed")
    try app.performAccessibilityAudit()
    activate("guided-plan-start", app)
    XCTAssertEqual(app.staticTexts["guided-word"].label, "rabbit")
    XCTAssertEqual(app.staticTexts["guided-plan-position"].label, "Word 1 of 2")
    XCTAssertFalse(app.buttons["guided-finish-practice"].isEnabled)
    XCTAssertFalse(app.buttons["guided-plan-next"].exists)
    record(app)
    activate("guided-finish-practice", app)
    XCTAssertEqual(app.staticTexts["guided-practice-save-status"].label, "Saved to recent practice")
    activate("guided-plan-next", app)
    XCTAssertEqual(app.staticTexts["guided-word"].label, "bread")
    XCTAssertEqual(app.staticTexts["guided-plan-position"].label, "Word 2 of 2")
    XCTAssertFalse(app.buttons["guided-finish-practice"].isEnabled)
    activate("guided-plan-skip", app)
    XCTAssertTrue(app.staticTexts["guided-plan-results-title"].exists)
    XCTAssertTrue(planRow("r-beginning-rabbit", app).label.contains("Finished and saved"))
    XCTAssertTrue(planRow("r-middle-bread", app).label.contains("Skipped"))
    attach(app, "generated-plan-one-finished-one-skipped")
    activate("guided-plan-back-summary", app)
    XCTAssertEqual(row("r-middle-bread", app).label, original)
    activate("guided-start-recheck", app)
    XCTAssertEqual(app.staticTexts["guided-item-position"].label, "Word 1 of 13")
    XCTAssertEqual(app.staticTexts["guided-word"].label, "rabbit")
    finishRound(app)
    XCTAssertTrue(row("zh-middle-treasure", app).label.contains("Not reached"))
    app.buttons["guided-close"].tap()
  }

  func testLargestTextSelectionLimitAndSequenceRemainUsable() throws {
    let app = launch("mixed", large: true)
    start(app)
    finishRound(app)
    activate("guided-plan-open", app)
    XCTAssertTrue(app.staticTexts["guided-plan-suggestions"].label.contains("No word"))
    let ids = ["r-beginning-rabbit", "r-middle-bread", "r-end-door"]
    for id in ids { activate("guided-plan-row-" + id, app) }
    let fourthMatches = app.descendants(matching: .any)
      .matching(identifier: "guided-plan-row-b-beginning-baby")
    XCTAssertEqual(fourthMatches.count, 1)
    let fourth = fourthMatches.firstMatch
    scrollTo(fourth, app)
    XCTAssertFalse(fourth.isEnabled)
    activate("guided-plan-row-r-end-door", app)
    activate("guided-plan-row-b-beginning-baby", app)
    let firstMatches = app.descendants(matching: .any)
      .matching(identifier: "guided-plan-row-r-beginning-rabbit")
    XCTAssertEqual(firstMatches.count, 1)
    let first = firstMatches.firstMatch
    scrollTo(first, app)
    XCTAssertTrue(first.isHittable)
    XCTAssertGreaterThanOrEqual(first.frame.height, 44)
    attach(app, "generated-plan-largest-choice")
    try app.performAccessibilityAudit()
    activate("guided-plan-start", app)
    let skip = app.buttons["guided-plan-skip"]
    scrollTo(skip, app)
    XCTAssertTrue(skip.isHittable)
    XCTAssertGreaterThanOrEqual(skip.frame.height, 44)
    attach(app, "generated-plan-largest-sequence")
    try app.performAccessibilityAudit()
    activate("guided-plan-end", app)
    XCTAssertTrue(app.staticTexts["guided-plan-results-title"].exists)
    XCTAssertTrue(planRow("r-middle-bread", app).label.contains("Not started"))
    app.buttons["guided-close"].tap()
  }

  func testPlanSaveFailureRetainsRetryAndAdvancesAfterExplicitFinish() throws {
    let app = launch("historySaveFailure")
    start(app)
    finishRound(app)
    activate("guided-plan-open", app)
    activate("guided-plan-row-r-middle-bread", app)
    activate("guided-plan-start", app)
    record(app)
    activate("guided-finish-practice", app)
    XCTAssertEqual(app.staticTexts["guided-practice-save-status"].label, "Saving not confirmed")
    XCTAssertTrue(app.buttons["guided-retry-practice-save"].exists)
    XCTAssertTrue(app.buttons["guided-plan-next-unsaved"].exists)
    attach(app, "generated-plan-save-failure-retry")
    activate("guided-retry-practice-save", app)
    XCTAssertEqual(app.staticTexts["guided-practice-save-status"].label, "Saved to recent practice")
    activate("guided-plan-next", app)
    XCTAssertTrue(planRow("r-middle-bread", app).label.contains("Finished and saved"))
    app.buttons["guided-close"].tap()
  }

  private func launch(_ fixture: String, large: Bool = false) -> XCUIApplication {
    continueAfterFailure = false
    let app = XCUIApplication()
    app.launchArguments = [
      "-CadenceGuidedWordMode", "-CadenceGuidedWordUITestCase", fixture,
      "-UIPreferredContentSizeCategoryName",
      large ? "UICTContentSizeCategoryAccessibilityXXXL" : "UICTContentSizeCategoryL",
    ]
    app.launch()
    XCTAssertTrue(app.staticTexts["guided-ui-test-banner"].waitForExistence(timeout: 5))
    XCTAssertEqual(app.staticTexts["guided-ui-test-banner"].label, "Generated test")
    let note = app.staticTexts["guided-ui-test-fixture-note"]
    XCTAssertTrue(note.exists)
    XCTAssertTrue(note.label.contains("No sensors, network or models"))
    XCTAssertTrue(note.label.contains("Request start is simulated"))
    return app
  }
  private func start(_ app: XCUIApplication) {
    activate("guided-age-picker", app)
    XCTAssertTrue(app.buttons["9 years"].waitForExistence(timeout: 3))
    app.buttons["9 years"].tap()
    activate("guided-check-optin", app)
    activate("guided-start", app)
  }
  private func record(_ app: XCUIApplication) {
    activate("guided-record", app)
    XCTAssertTrue(app.buttons["guided-stop"].waitForExistence(timeout: 5))
    activate("guided-stop", app)
    XCTAssertTrue(app.buttons["guided-replay"].waitForExistence(timeout: 5))
  }
  private func finishRound(_ app: XCUIApplication) {
    activate("guided-finish-early", app)
    let alert = app.alerts.firstMatch
    if alert.waitForExistence(timeout: 1) { alert.buttons["Finish round"].tap() }
    XCTAssertTrue(app.staticTexts["guided-summary-title"].waitForExistence(timeout: 5))
  }
  private func row(_ id: String, _ app: XCUIApplication) -> XCUIElement {
    app.descendants(matching: .any).matching(identifier: "guided-row-" + id).firstMatch
  }
  private func planRow(_ id: String, _ app: XCUIApplication) -> XCUIElement {
    app.descendants(matching: .any).matching(identifier: "guided-plan-result-" + id).firstMatch
  }
  private func activate(_ id: String, _ app: XCUIApplication) {
    let target = app.descendants(matching: .any).matching(identifier: id).firstMatch
    scrollTo(target, app)
    XCTAssertTrue(target.isHittable, id)
    XCTAssertTrue(target.isEnabled, id)
    target.tap()
  }
  private func scrollTo(_ target: XCUIElement, _ app: XCUIApplication) {
    let scroll = app.scrollViews.firstMatch
    for iteration in 0..<40 {
      let viewport = scroll.frame
      let banner = app.staticTexts["guided-ui-test-banner"]
      let close = app.buttons["guided-close"]
      let top = max(viewport.minY, banner.frame.maxY, close.frame.maxY) + 8
      let bottom = viewport.maxY - 8
      let frame = target.frame
      let height = bottom - top
      print(
        "plan-scroll \(iteration) target=\(target.identifier) frame=\(frame) top=\(top) bottom=\(bottom) hittable=\(target.isHittable)"
      )
      XCTAssertGreaterThan(height, 44, "No usable scroll viewport")
      guard frame.height <= height else {
        attach(app, "generated-plan-control-too-tall")
        XCTFail("Control is taller than the usable scroll viewport: \(target.identifier)")
        return
      }
      if target.isHittable && frame.minY >= top && frame.maxY <= bottom { return }
      // Match the existing word-guess helper: aim inside the fitting range and
      // hold fine corrections before releasing so inertia cannot overshoot it.
      let fittingTop = (top + bottom - frame.height) / 2
      let adjustment = fittingTop - frame.minY
      let towardTop = adjustment > 0
      let available = height - 48
      let distance = min(available * 0.9, max(6, abs(adjustment) * 0.8))
      let startY = towardTop ? top + 24 : bottom - 24
      let start = scroll.coordinate(
        withNormalizedOffset: CGVector(dx: 0.96, dy: (startY - viewport.minY) / viewport.height))
      let end = scroll.coordinate(
        withNormalizedOffset: CGVector(
          dx: 0.96,
          dy: (startY + (towardTop ? distance : -distance) - viewport.minY) / viewport.height))
      if abs(adjustment) > available * 1.5 {
        start.press(forDuration: 0.01, thenDragTo: end)
      } else {
        start.press(
          forDuration: 0.1, thenDragTo: end, withVelocity: .slow, thenHoldForDuration: 0.2)
      }
    }
    attach(app, "generated-plan-failed-scroll-geometry")
    XCTFail("Control did not fit fully within the scroll viewport: \(target.identifier)")
  }
  private func attach(_ app: XCUIApplication, _ name: String) {
    let image = XCTAttachment(screenshot: app.screenshot())
    image.name = name
    image.lifetime = .keepAlways
    add(image)
    let tree = XCTAttachment(string: app.debugDescription)
    tree.name = name + "-accessibility"
    tree.lifetime = .keepAlways
    add(tree)
  }
}
