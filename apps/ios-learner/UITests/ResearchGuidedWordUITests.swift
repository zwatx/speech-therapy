import XCTest

/// Generated PCM and invented bound replies; no microphone, socket or model.
@MainActor
final class ResearchGuidedWordUITests: XCTestCase {
  func testFullFirstRoundManualPracticeAndFreshPartialRecheck() throws {
    let app = launch("mixed")
    start(app, age: 9)
    for index in 0..<13 {
      XCTAssertEqual(app.staticTexts["guided-item-position"].label, "Word \(index + 1) of 13")
      recordAndCheck(app)
      if index < 12 { activate("guided-next", app) }
    }
    activate("guided-next", app)
    XCTAssertTrue(app.staticTexts["guided-summary-title"].waitForExistence(timeout: 5))
    XCTAssertEqual(app.staticTexts["guided-summary-title"].label, "First round summary")
    XCTAssertEqual(rows(app).count, 13)
    let original = row("r-middle-bread", app).label
    attach(app, "generated-full-first-summary")
    activate("guided-counts", app)
    XCTAssertTrue(app.staticTexts["guided-counts-first"].label.contains("Requests started: 13"))
    XCTAssertTrue(app.staticTexts["guided-counts-first"].label.contains("Validated responses: 13"))
    activate("guided-practice-word-r-middle-bread", app)
    XCTAssertEqual(app.staticTexts["guided-word"].label, "bread")
    record(app)
    XCTAssertFalse(app.buttons["guided-check"].exists)
    activate("guided-listen", app)
    XCTAssertTrue(app.staticTexts["guided-example-playing"].waitForExistence(timeout: 5))
    activate("guided-replay", app)
    XCTAssertEqual(app.buttons["guided-replay"].label, "Stop replay")
    attach(app, "generated-bread-manual-practice-own-replay")
    activate("guided-back-summary", app)
    XCTAssertEqual(row("r-middle-bread", app).label, original)
    activate("guided-start-recheck", app)
    XCTAssertEqual(app.staticTexts["guided-round-title"].label, "Recheck")
    for index in 0..<4 {
      recordAndCheck(app)
      if index < 3 { activate("guided-next", app) }
    }
    finish(app)
    XCTAssertEqual(app.staticTexts["guided-summary-title"].label, "Both rounds")
    XCTAssertEqual(rows(app).count, 13)
    XCTAssertTrue(row("r-middle-bread", app).label.contains("First:"))
    XCTAssertTrue(row("zh-middle-treasure", app).label.contains("Not reached"))
    XCTAssertTrue(app.staticTexts["guided-comparison-limit"].exists)
    attach(app, "generated-two-round-observations-partial-recheck")
    app.buttons["guided-close"].tap()
  }

  func testDeniedAttemptSkipAndEarlyFinishKeepAllPlannedWords() throws {
    let app = launch("denied")
    start(app, age: 12)
    activate("guided-record", app)
    XCTAssertTrue(app.staticTexts["guided-status-title"].waitForExistence(timeout: 5))
    XCTAssertEqual(app.staticTexts["guided-status-title"].label, "Microphone access is off")
    activate("guided-skip", app)
    finish(app)
    XCTAssertEqual(rows(app).count, 13)
    XCTAssertTrue(row("r-beginning-rabbit", app).label.contains("Skipped"))
    XCTAssertTrue(row("r-middle-bread", app).label.contains("Not reached"))
    activate("guided-counts", app)
    XCTAssertTrue(app.staticTexts["guided-counts-first"].label.contains("Recording attempts: 1"))
    XCTAssertTrue(app.staticTexts["guided-counts-first"].label.contains("Requests started: 0"))
    attach(app, "generated-denied-early-summary-fixed13")
    app.buttons["guided-close"].tap()
  }

  func testCancelCheckKeepsPrimaryUnavailableAndNoValidatedResponse() throws {
    let app = launch("delayed")
    start(app, age: 6)
    record(app)
    activate("guided-check", app)
    XCTAssertTrue(app.buttons["guided-cancel-check"].waitForExistence(timeout: 5))
    activate("guided-cancel-check", app)
    XCTAssertFalse(app.buttons["guided-check"].exists)
    activate("guided-next", app)
    finish(app)
    XCTAssertEqual(rows(app).count, 13)
    XCTAssertTrue(row("r-beginning-rabbit", app).label.contains("Check unavailable"))
    activate("guided-counts", app)
    XCTAssertTrue(app.staticTexts["guided-counts-first"].label.contains("Submitted checks: 1"))
    XCTAssertTrue(app.staticTexts["guided-counts-first"].label.contains("Requests started: 1"))
    XCTAssertTrue(app.staticTexts["guided-counts-first"].label.contains("Validated responses: 0"))
    attach(app, "generated-cancelled-primary-summary")
    app.buttons["guided-close"].tap()
  }

  func testServicePauseSurvivesNextAndAllowsLocalPractice() throws {
    let app = launch("paused")
    start(app, age: 9)
    recordAndCheck(app)
    XCTAssertTrue(app.staticTexts["guided-paused"].exists)
    activate("guided-next", app)
    record(app)
    XCTAssertFalse(app.buttons["guided-check"].exists && app.buttons["guided-check"].isEnabled)
    finish(app)
    activate("guided-practice-word-r-middle-bread", app)
    activate("guided-listen", app)
    XCTAssertTrue(app.staticTexts["guided-example-playing"].waitForExistence(timeout: 5))
    XCTAssertTrue(app.staticTexts["guided-paused"].exists)
    attach(app, "generated-paused-manual-example")
    app.buttons["guided-close"].tap()
  }

  func testExampleCleanupBlocksPracticeHandoffUntilExplicitRetry() throws {
    let app = launch("cleanupExample")
    start(app, age: 9)
    finish(app)
    activate("guided-practice-word-r-middle-bread", app)
    activate("guided-listen", app)
    XCTAssertTrue(app.staticTexts["guided-example-playing"].waitForExistence(timeout: 5))
    activate("guided-listen", app)
    XCTAssertTrue(app.staticTexts["guided-example-cleanup"].waitForExistence(timeout: 5))
    XCTAssertFalse(app.buttons["guided-back-summary"].isEnabled)
    XCTAssertFalse(app.buttons["guided-start-recheck"].isEnabled)
    attach(app, "generated-example-cleanup-blocked-handoff")
    activate("guided-example-cleanup-retry", app)
    activate("guided-back-summary", app)
    XCTAssertTrue(app.staticTexts["guided-summary-title"].exists)
    app.buttons["guided-close"].tap()
  }

  func testCloseDuringRecordingReportsNewDeletionFailureBeforeLeaving() throws {
    let app = launch("cleanupRecording")
    start(app, age: 9)
    activate("guided-record", app)
    XCTAssertTrue(app.buttons["guided-stop"].waitForExistence(timeout: 5))
    app.buttons["guided-close"].tap()
    XCTAssertTrue(app.staticTexts["guided-close-note"].waitForExistence(timeout: 5))
    XCTAssertTrue(app.staticTexts["guided-close-note"].label.contains("couldn't be removed"))
    XCTAssertTrue(app.staticTexts["guided-ended"].exists)
    XCTAssertTrue(app.buttons["guided-close"].exists)
    XCTAssertFalse(app.buttons["guided-record"].exists)
    attach(app, "generated-active-recording-close-cleanup-warning")
    app.buttons["guided-close"].tap()
    XCTAssertTrue(app.buttons["cadence.start"].waitForExistence(timeout: 5))
  }

  func testExplicitRecordedPracticeSavesOnceAndAppearsInExistingHistory() throws {
    let app = launch("mixed")
    start(app, age: 9)
    finish(app)
    let before = row("r-middle-bread", app).label
    activate("guided-practice-word-r-middle-bread", app)
    XCTAssertFalse(app.buttons["guided-finish-practice"].isEnabled)
    activate("guided-listen", app)
    XCTAssertTrue(app.staticTexts["guided-example-playing"].waitForExistence(timeout: 5))
    XCTAssertFalse(app.buttons["guided-finish-practice"].isEnabled)
    activate("guided-listen", app)
    record(app)
    activate("guided-replay", app)
    XCTAssertEqual(app.buttons["guided-replay"].label, "Stop replay")
    // Capture after the ordinary label transition has settled; no audio clock manipulation.
    Thread.sleep(forTimeInterval: 1)
    scrollTo(app.buttons["guided-replay"], app)
    attach(app, "generated-guided-practice-replay-settled")
    activate("guided-finish-practice", app)
    let status = app.staticTexts["guided-practice-save-status"]
    XCTAssertTrue(status.waitForExistence(timeout: 5))
    XCTAssertEqual(status.label, "Saved to recent practice")
    XCTAssertFalse(
      app.buttons["guided-finish-practice"].exists
        && app.buttons["guided-finish-practice"].isEnabled)
    XCTAssertFalse(app.buttons["guided-record"].exists && app.buttons["guided-record"].isEnabled)
    scrollTo(status, app)
    attach(app, "generated-guided-practice-saved")
    activate("guided-back-summary", app)
    XCTAssertEqual(row("r-middle-bread", app).label, before)
    activate("guided-counts", app)
    XCTAssertTrue(app.staticTexts["guided-counts-first"].label.contains("Recording attempts: 0"))
    activate("guided-start-recheck", app)
    recordAndCheck(app)
    finish(app)
    XCTAssertEqual(rows(app).count, 13)
    app.buttons["guided-close"].tap()
    XCTAssertTrue(app.buttons["cadence.start"].waitForExistence(timeout: 5))
    let entries = historyEntries(app)
    XCTAssertEqual(entries.count, 1)
    XCTAssertTrue(entries.firstMatch.label.contains("R sound · 1 word"))
    scrollTo(entries.firstMatch, app)
    attach(app, "generated-guided-practice-existing-history")
    activate("cadence.history.clear", app)
    let clear = app.buttons["cadence.history.clear-confirmation-confirm"]
    XCTAssertTrue(clear.waitForExistence(timeout: 3))
    XCTAssertTrue(clear.isHittable)
    XCTAssertTrue(clear.isEnabled)
    clear.tap()
    XCTAssertEqual(historyEntries(app).count, 0)
  }

  func testFailedPracticeSaveRetriesSameVisitIntoOneHistoryEntry() throws {
    let app = launch("historySaveFailure")
    start(app, age: 12)
    finish(app)
    activate("guided-practice-word-r-middle-bread", app)
    record(app)
    activate("guided-finish-practice", app)
    let status = app.staticTexts["guided-practice-save-status"]
    XCTAssertEqual(status.label, "Saving not confirmed")
    scrollTo(status, app)
    attach(app, "generated-guided-practice-not-saved")
    activate("guided-retry-practice-save", app)
    XCTAssertEqual(status.label, "Saved to recent practice")
    XCTAssertFalse(app.buttons["guided-retry-practice-save"].exists)
    app.buttons["guided-close"].tap()
    XCTAssertTrue(app.buttons["cadence.start"].waitForExistence(timeout: 5))
    XCTAssertEqual(historyEntries(app).count, 1)
  }

  func testReturningWithoutAcknowledgingRecordedPracticeDoesNotSave() throws {
    let app = launch("mixed")
    start(app, age: 6)
    finish(app)
    activate("guided-practice-word-r-middle-bread", app)
    record(app)
    activate("guided-back-summary", app)
    XCTAssertEqual(rows(app).count, 13)
    app.buttons["guided-close"].tap()
    XCTAssertTrue(app.buttons["cadence.start"].waitForExistence(timeout: 5))
    XCTAssertEqual(historyEntries(app).count, 0)
  }

  func testDeniedManualRecordingCannotFinishOrSaveParticipation() throws {
    let app = launch("denied")
    start(app, age: 9)
    finish(app)
    activate("guided-practice-word-r-middle-bread", app)
    activate("guided-record", app)
    XCTAssertEqual(app.staticTexts["guided-status-title"].label, "Microphone access is off")
    XCTAssertFalse(app.buttons["guided-finish-practice"].isEnabled)
    activate("guided-back-summary", app)
    app.buttons["guided-close"].tap()
    XCTAssertTrue(app.buttons["cadence.start"].waitForExistence(timeout: 5))
    XCTAssertEqual(historyEntries(app).count, 0)
  }

  private func historyEntries(_ app: XCUIApplication) -> XCUIElementQuery {
    app.descendants(matching: .any).matching(
      NSPredicate(format: "identifier BEGINSWITH %@", "cadence.history.entry-"))
  }

  func testProductionLargeTextSetupAndRecordControlWithoutCapture() throws {
    let app = launch(nil, large: true)
    XCTAssertFalse(app.staticTexts["guided-ui-test-banner"].exists)
    XCTAssertFalse(app.buttons["guided-start"].isEnabled)
    start(app, age: 6)
    let button = app.buttons["guided-record"]
    scrollTo(button, app)
    XCTAssertTrue(button.isHittable)
    XCTAssertGreaterThanOrEqual(button.frame.height, 44)
    let viewport = app.scrollViews.firstMatch.frame
    XCTAssertGreaterThanOrEqual(button.frame.minY, viewport.minY)
    XCTAssertLessThanOrEqual(button.frame.maxY, viewport.maxY)
    XCTAssertFalse(app.buttons["guided-stop"].exists)
    XCTAssertFalse(app.buttons["guided-check"].exists)
    XCTAssertFalse(app.buttons["guided-check-sound"].exists)
    attach(app, "production-large-guided-record-control-no-capture")
    try app.performAccessibilityAudit()
    app.buttons["guided-close"].tap()
  }

  private func launch(_ fixture: String?, large: Bool = false) -> XCUIApplication {
    continueAfterFailure = false
    let app = XCUIApplication()
    app.launchArguments = [
      "-CadenceGuidedWordMode", "-UIPreferredContentSizeCategoryName",
      large ? "UICTContentSizeCategoryAccessibilityXXXL" : "UICTContentSizeCategoryL",
    ]
    if let fixture {
      app.launchArguments += ["-CadenceGuidedWordUITestCase", fixture]
      // Generated admission only; ordinary/physical helpers retain their original arguments.
      app.launchEnvironment.removeValue(forKey: "CADENCE_CONTROLLED_UNIT_HOST")
      app.launchEnvironment.removeValue(forKey: "TEST_RUNNER_CADENCE_CONTROLLED_UNIT_HOST")
      app.launchEnvironment.removeValue(forKey: "TEST_RUNNER_CADENCE_CONTROLLED_UI_HOST")
      app.launchEnvironment["CADENCE_CONTROLLED_UI_HOST"] = "1"
      app.launchArguments += ["-CadenceControlledUIRunID", UUID().uuidString.lowercased()]
    }
    app.launch()
    XCTAssertTrue(app.staticTexts["guided-title"].waitForExistence(timeout: 5))
    if fixture != nil { XCTAssertTrue(app.staticTexts["guided-ui-test-banner"].exists) }
    return app
  }
  private func start(_ app: XCUIApplication, age: Int) {
    activate("guided-age-picker", app)
    XCTAssertTrue(app.buttons["\(age) years"].waitForExistence(timeout: 3))
    app.buttons["\(age) years"].tap()
    activate("guided-check-optin", app)
    activate("guided-start", app)
    XCTAssertEqual(app.staticTexts["guided-round-title"].label, "First round")
  }
  private func record(_ app: XCUIApplication) {
    activate("guided-record", app)
    XCTAssertTrue(app.buttons["guided-stop"].waitForExistence(timeout: 5))
    activate("guided-stop", app)
    XCTAssertTrue(app.buttons["guided-replay"].waitForExistence(timeout: 5))
  }
  private func recordAndCheck(_ app: XCUIApplication) {
    record(app)
    activate("guided-check", app)
    XCTAssertTrue(app.buttons["guided-next"].waitForExistence(timeout: 5))
    let done = XCTNSPredicateExpectation(
      predicate: NSPredicate(format: "enabled == YES"), object: app.buttons["guided-next"])
    XCTAssertEqual(XCTWaiter.wait(for: [done], timeout: 5), .completed)
  }
  private func finish(_ app: XCUIApplication) {
    activate("guided-finish-early", app)
    if app.alerts.firstMatch.waitForExistence(timeout: 1) {
      app.alerts.firstMatch.buttons["Finish round"].tap()
    }
    XCTAssertTrue(app.staticTexts["guided-summary-title"].waitForExistence(timeout: 5))
  }
  private func rows(_ app: XCUIApplication) -> XCUIElementQuery {
    app.descendants(matching: .any).matching(
      NSPredicate(format: "identifier BEGINSWITH %@", "guided-row-"))
  }
  private func row(_ id: String, _ app: XCUIApplication) -> XCUIElement {
    app.descendants(matching: .any).matching(identifier: "guided-row-" + id).firstMatch
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
    for _ in 0..<40 {
      let viewport = scroll.frame
      let banner = app.staticTexts["guided-ui-test-banner"]
      let close = app.buttons["guided-close"]
      let headerBottom =
        banner.exists ? banner.frame.maxY : close.exists ? close.frame.maxY : viewport.minY
      let top = max(viewport.minY, headerBottom) + 8
      let frame = target.frame
      if target.isHittable && frame.minY >= top && frame.maxY <= viewport.maxY - 8 {
        return
      }
      let start = scroll.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5))
      let finish = scroll.coordinate(
        withNormalizedOffset: CGVector(dx: 0.5, dy: frame.minY < top ? 0.7 : 0.3))
      start.press(forDuration: 0.01, thenDragTo: finish)
    }
  }
  private func attach(_ app: XCUIApplication, _ name: String) {
    let attachment = XCTAttachment(screenshot: app.screenshot())
    attachment.name = name
    attachment.lifetime = .keepAlways
    add(attachment)
    let tree = XCTAttachment(string: app.debugDescription)
    tree.name = name + "-accessibility"
    tree.lifetime = .keepAlways
    add(tree)
  }

  func testSelectedFocusAppearsOnlyInExplicitManualPracticeAndNotFirstOrRecheck() throws {
    let app = launch("mixed")
    start(app, age: 9)
    XCTAssertEqual(app.staticTexts["guided-round-title"].label, "First round")
    XCTAssertFalse(app.staticTexts["guided-example-cue"].exists)
    finish(app)
    XCTAssertEqual(rows(app).count, 13)
    let original = row("zh-middle-treasure", app).label
    activate("guided-practice-word-zh-middle-treasure", app)
    let cue = app.staticTexts["guided-example-cue"]
    XCTAssertTrue(cue.waitForExistence(timeout: 5))
    XCTAssertEqual(app.staticTexts["guided-word"].label, "treasure")
    XCTAssertTrue(cue.label.contains("middle sound in treasure, as in “measure”"))
    XCTAssertTrue(app.staticTexts["guided-example-generated"].exists)
    XCTAssertFalse(app.buttons["guided-check"].exists)
    XCTAssertFalse(app.buttons["guided-stop"].exists)
    XCTAssertFalse(app.buttons["guided-replay"].exists)
    XCTAssertFalse(app.staticTexts["guided-example-playing"].exists)
    attach(app, "generated-treasure-explicit-manual-focus")
    activate("guided-back-summary", app)
    XCTAssertEqual(row("zh-middle-treasure", app).label, original)
    XCTAssertFalse(cue.exists)
    activate("guided-counts", app)
    XCTAssertTrue(app.staticTexts["guided-counts-first"].label.contains("Recording attempts: 0"))
    activate("guided-start-recheck", app)
    XCTAssertEqual(app.staticTexts["guided-round-title"].label, "Recheck")
    XCTAssertEqual(app.staticTexts["guided-item-position"].label, "Word 1 of 13")
    XCTAssertFalse(cue.exists)
    XCTAssertFalse(app.buttons["guided-listen"].exists)
    attach(app, "generated-full-recheck-no-manual-focus")
    finish(app)
    XCTAssertEqual(rows(app).count, 13)
    XCTAssertFalse(cue.exists)
    app.buttons["guided-close"].tap()
  }

}
