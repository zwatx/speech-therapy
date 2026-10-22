import XCTest

/// History continuation stops at the library; its default player/capturer is never presented.
@MainActor
final class RecentPracticeContinuationUITests: XCTestCase {
  func testFreeCompletionContinuesChosenGroupWithoutRestoringWordOrWritingHistory() {
    let app = launch("freeCompletion")
    activate("cadence.feedback.start", app)
    XCTAssertTrue(app.staticTexts["feedback-state-ready"].waitForExistence(timeout: 5))
    activate("feedback-record", app)
    XCTAssertTrue(app.buttons["feedback-stop"].waitForExistence(timeout: 5))
    activate("feedback-stop", app)
    XCTAssertTrue(app.staticTexts["feedback-state-review"].waitForExistence(timeout: 5))
    activate("feedback-finish-practice", app)
    XCTAssertTrue(element("feedback-practice-saved", app).waitForExistence(timeout: 5))
    app.buttons["feedback-close"].tap()
    XCTAssertTrue(app.buttons["cadence.feedback.start"].waitForExistence(timeout: 5))
    XCTAssertEqual(historyRows(app).count, 1)
    let rowID = historyRows(app).firstMatch.identifier
    let uuid = String(rowID.dropFirst("cadence.history.entry-".count))
    let actionID = "cadence.history.practice-" + uuid
    visibleControl(actionID, app)
    attach(app, "history-free-completion-continuation")
    activate(actionID, app)
    assertLibrary(app, name: "R sound", position: "beginning", wordID: "r-beginning-rabbit")
    XCTAssertFalse(app.buttons["cadence.library.r-middle-bread"].exists)
    attach(app, "history-free-completion-r-default-library")
    backHome(app)
    XCTAssertEqual(historyRows(app).count, 1)
    XCTAssertEqual(historyRows(app).firstMatch.identifier, rowID)
    XCTAssertTrue(element(actionID, app).exists)
    clearHistory(app)
  }

  func testGuidedCreatedHistoryContinuesGroupWithoutRestoringPriorPractice() {
    continueAfterFailure = false
    let app = XCUIApplication()
    app.launchArguments = ["-CadenceGuidedWordUITestCase", "mixed"]
    app.launch()
    XCTAssertTrue(app.buttons["cadence.guided-word.start"].waitForExistence(timeout: 5))
    activate("cadence.guided-word.start", app)
    XCTAssertTrue(app.staticTexts["guided-title"].waitForExistence(timeout: 5))
    XCTAssertFalse(app.buttons["guided-start"].isEnabled)
    XCTAssertFalse(app.buttons["guided-stop"].exists)
    activate("guided-age-picker", app)
    XCTAssertTrue(app.buttons["9 years"].waitForExistence(timeout: 3))
    app.buttons["9 years"].tap()
    activate("guided-check-optin", app)
    activate("guided-start", app)
    activate("guided-finish-early", app)
    XCTAssertTrue(app.alerts.firstMatch.waitForExistence(timeout: 3))
    app.alerts.firstMatch.buttons["Finish round"].tap()
    XCTAssertTrue(app.staticTexts["guided-summary-title"].waitForExistence(timeout: 5))
    activate("guided-practice-word-r-middle-bread", app)
    XCTAssertFalse(app.buttons["guided-finish-practice"].isEnabled)
    activate("guided-record", app)
    activate("guided-stop", app)
    activate("guided-finish-practice", app)
    XCTAssertEqual(app.staticTexts["guided-practice-save-status"].label, "Saved to recent practice")
    app.buttons["guided-close"].tap()
    XCTAssertTrue(app.buttons["cadence.guided-word.start"].waitForExistence(timeout: 5))
    XCTAssertEqual(historyRows(app).count, 1)
    let rowID = historyRows(app).firstMatch.identifier
    let actionID =
      "cadence.history.practice-" + String(rowID.dropFirst("cadence.history.entry-".count))
    activate(actionID, app)
    assertLibrary(app, name: "R sound", position: "beginning", wordID: "r-beginning-rabbit")
    attach(app, "history-guided-created-r-default-library")
    backHome(app)
    XCTAssertEqual(historyRows(app).count, 1)
    XCTAssertEqual(historyRows(app).firstMatch.identifier, rowID)
    clearHistory(app)
  }

  func testAccessibilityXLSeededHistoryActionsOpenMatchingLibrariesWithoutCapture() throws {
    try seededContinuation(contentSize: "UICTContentSizeCategoryAccessibilityXL", tag: "ax3")
  }

  func testAccessibilityXXXLSeededHistoryActionsOpenMatchingLibrariesWithoutCapture() throws {
    try seededContinuation(contentSize: "UICTContentSizeCategoryAccessibilityXXXL", tag: "ax5")
  }

  private func seededContinuation(contentSize: String, tag: String) throws {
    let app = launch("historyContinuation", contentSize: contentSize)
    let rows = [
      ("00000000-0000-4000-8000-000000000301", "R sound", "beginning", "r-beginning-rabbit"),
      (
        "00000000-0000-4000-8000-000000000302", "TH · feather", "middle", "voiced-th-middle-feather"
      ),
      ("00000000-0000-4000-8000-000000000303", "ZH · treasure", "middle", "zh-middle-treasure"),
    ]
    let expectedIDs = Set(rows.map { "cadence.history.entry-" + $0.0 })
    XCTAssertEqual(historyIDs(app), expectedIDs)
    XCTAssertEqual(historyActions(app).count, 3)
    for (uuid, name, position, wordID) in rows {
      let metadata = element("cadence.history.entry-" + uuid, app)
      scrollTo(metadata, app)
      XCTAssertTrue(metadata.label.contains(name))
      XCTAssertTrue(metadata.label.contains("1 word"))
      attach(app, "history-" + tag + "-metadata-" + uuid)
      let actionID = "cadence.history.practice-" + uuid
      visibleControl(actionID, app)
      XCTAssertTrue(element(actionID, app).label.contains(name))
      attach(app, "history-" + tag + "-action-" + uuid)
      try app.performAccessibilityAudit()
      activate(actionID, app)
      assertLibrary(app, name: name, position: position, wordID: wordID)
      visibleControl("cadence.library.start", app)
      attach(app, "history-" + tag + "-library-" + uuid)
      try app.performAccessibilityAudit()
      backHome(app)
      XCTAssertEqual(historyIDs(app), expectedIDs)
      XCTAssertEqual(historyActions(app).count, 3)
    }
    clearHistory(app)
  }

  private func launch(_ fixture: String, contentSize: String = "UICTContentSizeCategoryL")
    -> XCUIApplication
  {
    continueAfterFailure = false
    let app = XCUIApplication()
    app.launchArguments = [
      "-UIPreferredContentSizeCategoryName", contentSize,
      "-CadenceUnifiedFeedbackUITestCase", fixture,
    ]
    app.launch()
    XCTAssertTrue(app.buttons["cadence.feedback.start"].waitForExistence(timeout: 5))
    XCTAssertFalse(app.staticTexts["feedback-title"].exists)
    assertNoPlayer(app)
    return app
  }

  private func assertLibrary(_ app: XCUIApplication, name: String, position: String, wordID: String)
  {
    XCTAssertTrue(app.navigationBars["Words to practice"].waitForExistence(timeout: 5))
    XCTAssertTrue(app.staticTexts[name].exists)
    XCTAssertTrue(app.buttons["cadence.position." + position].exists)
    XCTAssertTrue(app.buttons["cadence.position." + position].isSelected)
    XCTAssertTrue(app.buttons["cadence.library." + wordID].exists)
    XCTAssertTrue(app.buttons["cadence.library.start"].exists)
    assertNoPlayer(app)
  }

  private func assertNoPlayer(_ app: XCUIApplication) {
    XCTAssertFalse(app.buttons["cadence.record"].exists)
    XCTAssertFalse(app.buttons["cadence.stop"].exists)
    XCTAssertFalse(app.buttons["feedback-record"].exists)
    XCTAssertFalse(app.buttons["feedback-stop"].exists)
    XCTAssertFalse(element("cadence.word", app).exists)
  }

  private func backHome(_ app: XCUIApplication) {
    let bar = app.navigationBars["Words to practice"]
    XCTAssertTrue(bar.exists)
    let back = bar.buttons.firstMatch
    XCTAssertTrue(back.isHittable)
    back.tap()
    XCTAssertTrue(app.buttons["cadence.feedback.start"].waitForExistence(timeout: 5))
    XCTAssertFalse(app.navigationBars["Words to practice"].exists)
    assertNoPlayer(app)
  }

  private func historyRows(_ app: XCUIApplication) -> XCUIElementQuery {
    app.descendants(matching: .any).matching(
      NSPredicate(format: "identifier BEGINSWITH %@", "cadence.history.entry-"))
  }

  private func historyActions(_ app: XCUIApplication) -> XCUIElementQuery {
    app.descendants(matching: .any).matching(
      NSPredicate(format: "identifier BEGINSWITH %@", "cadence.history.practice-"))
  }

  private func historyIDs(_ app: XCUIApplication) -> Set<String> {
    Set(historyRows(app).allElementsBoundByIndex.map { $0.identifier })
  }

  private func clearHistory(_ app: XCUIApplication) {
    activate("cadence.history.clear", app)
    let confirm = app.sheets.buttons["Clear recent practice"].firstMatch
    XCTAssertTrue(confirm.waitForExistence(timeout: 3))
    confirm.tap()
    let empty = XCTNSPredicateExpectation(
      predicate: NSPredicate { _, _ in
        self.historyRows(app).count == 0 && self.historyActions(app).count == 0
      }, object: app)
    XCTAssertEqual(XCTWaiter.wait(for: [empty], timeout: 3), .completed)
    XCTAssertEqual(historyRows(app).count, 0)
    XCTAssertEqual(historyActions(app).count, 0)
  }

  private func visibleControl(_ id: String, _ app: XCUIApplication) {
    let control = element(id, app)
    scrollTo(control, app)
    XCTAssertTrue(control.isHittable, id)
    XCTAssertGreaterThanOrEqual(control.frame.height, 44, id)
    XCTAssertGreaterThanOrEqual(control.frame.width, 44, id)
    let viewport = app.scrollViews.firstMatch.frame
    XCTAssertGreaterThanOrEqual(control.frame.minY, viewport.minY, id)
    XCTAssertLessThanOrEqual(control.frame.maxY, viewport.maxY, id)
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
        "guided-close", "guided-close-note", "guided-ui-test-banner",
        "feedback-close", "feedback-close-note", "feedback-ui-test-banner",
        "cadence.home.ui-test-banner",
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
