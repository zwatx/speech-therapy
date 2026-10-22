import XCTest

/// Explicit free completion through Home, with generated PCM and an isolated real history store.
/// Controlled fixtures establish UI/participation behavior, not audible or clinical outcomes.
@MainActor
final class ResearchFreePracticeCompletionUITests: XCTestCase {
  func testTwoRecordedTriesFinishOneWordAndClearRealHistory() throws {
    try finishTwoTriesAndClear(large: false)
  }

  func testLargestTextCompletionAndHistoryControlsAreVisibleAndAccessible() throws {
    try finishTwoTriesAndClear(large: true)
  }

  func testPracticeAgainRequiresAnotherRecordingAndCompletesANewVisit() {
    let app = launch()
    recordStop("feedback-record", app)
    activate("feedback-finish-practice", app)
    XCTAssertTrue(element("feedback-practice-saved", app).waitForExistence(timeout: 5))
    activate("feedback-practice-again", app)
    XCTAssertTrue(app.staticTexts["feedback-state-ready"].waitForExistence(timeout: 5))
    XCTAssertFalse(element("feedback-practice-saved", app).exists)
    XCTAssertFalse(element("feedback-finish-practice", app).exists)
    XCTAssertFalse(app.buttons["feedback-replay"].exists)
    XCTAssertFalse(app.buttons["feedback-stop"].exists)
    recordStop("feedback-record", app)
    activate("feedback-finish-practice", app)
    XCTAssertTrue(element("feedback-practice-saved", app).waitForExistence(timeout: 5))
    closeHome(app)
    let rows = historyRows(app)
    XCTAssertEqual(rows.count, 2)
    XCTAssertNotEqual(rows.element(boundBy: 0).identifier, rows.element(boundBy: 1).identifier)
    XCTAssertTrue(rows.element(boundBy: 0).label.contains("1 word"))
    XCTAssertTrue(rows.element(boundBy: 1).label.contains("1 word"))
  }

  func testFailedSaveExplicitRetryProducesOneHistoryEntry() {
    let app = launch("freeSaveFailure")
    recordStop("feedback-record", app)
    activate("feedback-finish-practice", app)
    XCTAssertTrue(element("feedback-practice-not-saved", app).waitForExistence(timeout: 5))
    XCTAssertFalse(element("feedback-practice-saved", app).exists)
    visibleControl("feedback-retry-saving", app)
    attach(app, "free-completion-save-unconfirmed-retry")
    activate("feedback-retry-saving", app)
    XCTAssertTrue(element("feedback-practice-saved", app).waitForExistence(timeout: 5))
    XCTAssertFalse(element("feedback-retry-saving", app).exists)
    closeHome(app)
    XCTAssertEqual(historyRows(app).count, 1)
    attach(app, "free-completion-retry-one-real-history-row")
  }

  func testDeniedReplacementCanFinishRetainedPriorRecording() {
    let app = launch("freeDeniedReplacement")
    recordStop("feedback-record", app)
    activate("feedback-record-another", app)
    XCTAssertTrue(app.staticTexts["feedback-state-denied"].waitForExistence(timeout: 5))
    XCTAssertFalse(app.buttons["feedback-stop"].exists)
    XCTAssertTrue(app.buttons["feedback-replay"].exists)
    XCTAssertFalse(app.buttons["feedback-check"].exists)
    activate("feedback-finish-practice", app)
    XCTAssertTrue(element("feedback-practice-saved", app).waitForExistence(timeout: 5))
    closeHome(app)
    XCTAssertEqual(historyRows(app).count, 1)
  }

  func testLeavingRecordedPracticeWithoutFinishDoesNotSave() {
    let app = launch()
    recordStop("feedback-record", app)
    XCTAssertTrue(element("feedback-finish-practice", app).exists)
    closeHome(app)
    XCTAssertEqual(historyRows(app).count, 0)
    activate("cadence.feedback.start", app)
    XCTAssertTrue(app.staticTexts["feedback-state-ready"].waitForExistence(timeout: 5))
    XCTAssertFalse(element("feedback-practice-saved", app).exists)
    XCTAssertFalse(app.buttons["feedback-replay"].exists)
    closeHome(app)
    XCTAssertEqual(historyRows(app).count, 0)
  }

  func testPrivateCleanupFailureCannotAcknowledgeOrSaveCompletion() {
    let app = launch("freeCleanup")
    recordStop("feedback-record", app)
    recordStop("feedback-record-another", app)
    activate("feedback-finish-practice", app)
    XCTAssertTrue(app.staticTexts["feedback-state-cleanup"].waitForExistence(timeout: 5))
    XCTAssertFalse(element("feedback-practice-saved", app).exists)
    XCTAssertFalse(element("feedback-practice-not-saved", app).exists)
    XCTAssertFalse(element("feedback-retry-saving", app).exists)
    XCTAssertFalse(app.buttons["feedback-stop"].exists)
    attach(app, "free-completion-private-cleanup-no-save")
    closeHome(app)
    XCTAssertEqual(historyRows(app).count, 0)
  }

  private func finishTwoTriesAndClear(large: Bool) throws {
    let app = launch(large: large)
    let context = element("feedback-context", app)
    XCTAssertTrue(
      context.label.contains("Not set") || (context.value as? String)?.contains("Not set") == true)
    XCTAssertEqual(element("feedback-opt-in", app).value as? String, "Off")
    recordStop("feedback-record", app)
    recordStop("feedback-record-another", app)
    visibleControl("feedback-finish-practice", app)
    attach(app, large ? "free-completion-largest-finish" : "free-completion-compact-finish")
    activate("feedback-finish-practice", app)
    XCTAssertTrue(element("feedback-practice-saved", app).waitForExistence(timeout: 5))
    XCTAssertFalse(app.buttons["feedback-replay"].exists)
    XCTAssertFalse(app.buttons["feedback-replay-earlier"].exists)
    XCTAssertFalse(app.buttons["feedback-record"].exists)
    XCTAssertFalse(app.buttons["feedback-check"].exists)
    visibleControl("feedback-practice-again", app)
    scrollTo(element("feedback-practice-saved", app), app)
    attach(app, large ? "free-completion-largest-saved" : "free-completion-compact-saved")
    try app.performAccessibilityAudit()
    closeHome(app)
    XCTAssertEqual(historyRows(app).count, 1)
    let row = historyRows(app).firstMatch
    scrollTo(row, app)
    XCTAssertTrue(row.label.contains("1 word"))
    attach(app, large ? "free-completion-largest-history" : "free-completion-compact-history")
    visibleControl("cadence.history.clear", app)
    activate("cadence.history.clear", app)
    let confirm = app.sheets.buttons["Clear recent practice"].firstMatch
    XCTAssertTrue(confirm.waitForExistence(timeout: 3))
    confirm.tap()
    let cleared = XCTNSPredicateExpectation(
      predicate: NSPredicate(format: "count == 0"), object: historyRows(app))
    XCTAssertEqual(XCTWaiter.wait(for: [cleared], timeout: 3), .completed)
    try app.performAccessibilityAudit()
  }

  private func launch(_ fixture: String = "freeCompletion", large: Bool = false) -> XCUIApplication
  {
    continueAfterFailure = false
    let app = XCUIApplication()
    app.launchArguments = [
      "-UIPreferredContentSizeCategoryName",
      large ? "UICTContentSizeCategoryAccessibilityXXXL" : "UICTContentSizeCategoryL",
      "-CadenceUnifiedFeedbackUITestCase", fixture,
    ]
    app.launch()
    XCTAssertTrue(app.buttons["cadence.feedback.start"].waitForExistence(timeout: 5))
    XCTAssertFalse(app.staticTexts["feedback-title"].exists)
    XCTAssertEqual(historyRows(app).count, 0)
    activate("cadence.feedback.start", app)
    XCTAssertTrue(app.staticTexts["feedback-state-ready"].waitForExistence(timeout: 5))
    XCTAssertFalse(app.buttons["feedback-stop"].exists)
    XCTAssertFalse(element("feedback-finish-practice", app).exists)
    return app
  }

  private func historyRows(_ app: XCUIApplication) -> XCUIElementQuery {
    app.descendants(matching: .any).matching(
      NSPredicate(format: "identifier BEGINSWITH %@", "cadence.history.entry-"))
  }

  private func recordStop(_ id: String, _ app: XCUIApplication) {
    activate(id, app)
    XCTAssertTrue(app.buttons["feedback-stop"].waitForExistence(timeout: 5))
    activate("feedback-stop", app)
    XCTAssertTrue(app.staticTexts["feedback-state-review"].waitForExistence(timeout: 5))
  }

  private func closeHome(_ app: XCUIApplication) {
    app.buttons["feedback-close"].tap()
    XCTAssertTrue(app.buttons["cadence.feedback.start"].waitForExistence(timeout: 5))
    XCTAssertFalse(app.staticTexts["feedback-title"].exists)
  }

  private func visibleControl(_ id: String, _ app: XCUIApplication) {
    let control = element(id, app)
    scrollTo(control, app)
    XCTAssertTrue(control.isHittable, id)
    XCTAssertGreaterThanOrEqual(control.frame.height, 44, id)
  }

  private func element(_ id: String, _ app: XCUIApplication) -> XCUIElement {
    app.descendants(matching: .any).matching(identifier: id).firstMatch
  }

  private func activate(_ id: String, _ app: XCUIApplication) {
    let target = element(id, app)
    scrollTo(target, app)
    XCTAssertTrue(target.isHittable, id)
    XCTAssertTrue(target.isEnabled, id)
    target.tap()
  }

  private func scrollTo(_ target: XCUIElement, _ app: XCUIApplication) {
    XCTAssertTrue(target.waitForExistence(timeout: 5), target.identifier)
    let scroll = app.scrollViews.firstMatch
    for _ in 0..<40 {
      let viewport = scroll.frame
      var top = viewport.minY
      for id in [
        "feedback-close", "feedback-close-note", "feedback-ui-test-banner",
      ] {
        let fixed = element(id, app)
        if fixed.exists && fixed.isHittable { top = max(top, fixed.frame.maxY) }
      }
      let frame = target.frame
      if target.isHittable && frame.minY >= top + 8 && frame.maxY <= viewport.maxY - 8 { return }
      // Small final corrections avoid oscillating past a large control that fits the viewport.
      let towardTop = frame.minY < top + 8
      let overflow = towardTop ? top + 8 - frame.minY : frame.maxY - (viewport.maxY - 8)
      let distance = min(0.2, max(0.04, overflow / viewport.height * 0.45))
      let start = scroll.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5))
      let end = scroll.coordinate(
        withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5 + (towardTop ? distance : -distance)))
      start.press(forDuration: 0.01, thenDragTo: end)
    }
    let geometry = XCTAttachment(
      string: "target=\(target.identifier) frame=\(target.frame) viewport=\(scroll.frame)")
    geometry.name = "failed-scroll-control-geometry"
    geometry.lifetime = .keepAlways
    add(geometry)
    XCTFail("Control did not become fully visible: \(target.identifier)")
  }

  private func attach(_ app: XCUIApplication, _ name: String) {
    let screenshot = XCTAttachment(screenshot: app.screenshot())
    screenshot.name = name
    screenshot.lifetime = .keepAlways
    add(screenshot)
    let tree = XCTAttachment(string: app.debugDescription)
    tree.name = name + "-accessibility-tree"
    tree.lifetime = .keepAlways
    add(tree)
  }
}
