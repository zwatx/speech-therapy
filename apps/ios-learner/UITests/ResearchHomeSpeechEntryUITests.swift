import XCTest

/// Actual home navigation. Generated seams replace sensors/models; production cases never record.
@MainActor
final class ResearchHomeSpeechEntryUITests: XCTestCase {
  func testCompactHomePrivacyFooterIsFullyReadableAboveTabs() {
    let app = launch()
    defer { app.terminate() }
    let footer = app.staticTexts.matching(
      NSPredicate(format: "label BEGINSWITH %@", "Practice recordings stay local")
    ).firstMatch
    XCTAssertTrue(footer.waitForExistence(timeout: 5))
    scrollTo(footer, app)
    XCTAssertTrue(footer.isHittable)
    XCTAssertTrue(footer.label.contains("Example recordings are requested only when you tap Play."))
    let viewport = app.scrollViews.firstMatch.frame
    XCTAssertGreaterThanOrEqual(footer.frame.minY, viewport.minY)
    XCTAssertLessThanOrEqual(footer.frame.maxY, viewport.maxY)
    XCTAssertLessThanOrEqual(footer.frame.maxY, app.tabBars.firstMatch.frame.minY)
    XCTAssertTrue(app.buttons["About practice and privacy"].isHittable)
    attach(app, "production-home-complete-privacy-footer-above-tabs")
    XCTAssertFalse(app.buttons["guided-stop"].exists)
    XCTAssertFalse(app.buttons["feedback-stop"].exists)
  }

  func testLargestTextHomeKeepsPrivacyHeaderWhileScrolling() throws {
    let app = launch(large: true)
    defer { app.terminate() }
    let about = app.buttons["About practice and privacy"]
    XCTAssertTrue(about.waitForExistence(timeout: 5))
    let headerActionFrame = about.frame
    XCTAssertTrue(app.windows.firstMatch.frame.contains(headerActionFrame))
    XCTAssertTrue(about.isHittable)
    XCTAssertGreaterThanOrEqual(headerActionFrame.height, 44)
    for id in ["cadence.guided-word.start", "cadence.feedback.start", "cadence.start"] {
      scrollTo(app.buttons[id], app)
      XCTAssertTrue(app.buttons[id].isHittable)
      XCTAssertEqual(about.frame, headerActionFrame)
      XCTAssertTrue(about.isHittable)
      XCTAssertGreaterThanOrEqual(app.scrollViews.firstMatch.frame.minY, about.frame.maxY)
      XCTAssertLessThanOrEqual(app.scrollViews.firstMatch.frame.maxY, app.tabBars.firstMatch.frame.minY)
    }
    attach(app, "production-home-largest-persistent-privacy-header")
    about.tap()
    XCTAssertTrue(app.staticTexts["About practice"].waitForExistence(timeout: 5))
    let done = app.buttons["Done"]
    XCTAssertTrue(done.waitForExistence(timeout: 5))
    XCTAssertTrue(done.isHittable)
    done.tap()
    XCTAssertTrue(app.buttons["cadence.start"].waitForExistence(timeout: 5))
    XCTAssertEqual(about.frame, headerActionFrame)
    XCTAssertFalse(app.buttons["guided-stop"].exists)
    XCTAssertFalse(app.buttons["feedback-stop"].exists)
  }

  func testProductionCompactHomeOpensBothRoutesWithoutEnablingChecksOrCapture() throws {
    let app = launch()
    XCTAssertFalse(app.staticTexts["cadence.home.ui-test-banner"].exists)
    XCTAssertTrue(app.buttons["cadence.start"].exists)
    app.selectPracticeTab("Sounds")
    XCTAssertTrue(app.buttons["cadence.search.open"].exists)
    app.selectPracticeTab("Today")
    activate("cadence.guided-word.start", app)
    assertUnsetGuided(app)
    attach(app, "production-home-guided-unset-no-capture")
    app.buttons["guided-close"].tap()
    XCTAssertTrue(app.buttons["cadence.feedback.start"].waitForExistence(timeout: 5))
    activate("cadence.feedback.start", app)
    XCTAssertTrue(app.staticTexts["feedback-state-ready"].waitForExistence(timeout: 5))
    let context = element("feedback-context", app)
    XCTAssertTrue(
      context.label.contains("Not set") || (context.value as? String)?.contains("Not set") == true)
    XCTAssertEqual(element("feedback-opt-in", app).value as? String, "Off")
    XCTAssertFalse(app.buttons["feedback-stop"].exists)
    XCTAssertFalse(app.buttons["feedback-replay"].exists)
    XCTAssertFalse(app.staticTexts["feedback-state-result-matched"].exists)
    app.buttons["feedback-close"].tap()
    XCTAssertTrue(app.buttons["cadence.guided-word.start"].waitForExistence(timeout: 5))
    scrollTo(app.buttons["cadence.guided-word.start"], app)
    attach(app, "production-home-compact-speech-entry")
    try app.performAccessibilityAudit()
  }

  func testProductionLargestTextHomeActionsAreFullyVisibleWithoutCapture() throws {
    let app = launch(large: true)
    for id in ["cadence.guided-word.start", "cadence.feedback.start", "cadence.start"] {
      let button = app.buttons[id]
      scrollTo(button, app)
      XCTAssertTrue(button.isHittable, id)
      XCTAssertGreaterThanOrEqual(button.frame.height, 44, id)
      let viewport = app.scrollViews.firstMatch.frame
      XCTAssertGreaterThanOrEqual(button.frame.minY, viewport.minY, id)
      XCTAssertLessThanOrEqual(button.frame.maxY, viewport.maxY, id)
      attach(app, "production-home-largest-" + id)
    }
    XCTAssertFalse(app.buttons["guided-stop"].exists)
    XCTAssertFalse(app.buttons["feedback-stop"].exists)
    XCTAssertFalse(app.staticTexts["cadence.home.ui-test-banner"].exists)
    try app.performAccessibilityAudit()
  }

  func testNaturalHomeGuidedRecordedPracticeReturnsToOneHistoryEntryAndClear() throws {
    let app = launch(guided: "mixed")
    activate("cadence.guided-word.start", app)
    assertUnsetGuided(app)
    startGuided(app)
    finishRound(app)
    activate("guided-practice-word-r-middle-bread", app)
    XCTAssertFalse(app.buttons["guided-finish-practice"].isEnabled)
    activate("guided-record", app)
    activate("guided-stop", app)
    scrollTo(app.buttons["guided-finish-practice"], app)
    XCTAssertTrue(app.buttons["guided-finish-practice"].isEnabled)
    attach(app, "generated-natural-home-practice-finish-controls")
    activate("guided-finish-practice", app)
    XCTAssertEqual(app.staticTexts["guided-practice-save-status"].label, "Saved to recent practice")
    app.buttons["guided-close"].tap()
    XCTAssertTrue(app.buttons["cadence.guided-word.start"].waitForExistence(timeout: 5))
    XCTAssertFalse(app.navigationBars.buttons["About"].exists)
    XCTAssertEqual(historyEntries(app).count, 1)
    XCTAssertTrue(historyEntries(app).firstMatch.label.contains("R sound · 1 word"))
    scrollTo(historyEntries(app).firstMatch, app)
    attach(app, "generated-natural-home-return-with-saved-history")
    activate("cadence.history.clear", app)
    let clear = app.sheets.buttons["Clear recent practice"].firstMatch
    XCTAssertTrue(clear.waitForExistence(timeout: 3))
    clear.tap()
    XCTAssertEqual(historyEntries(app).count, 0)
  }

  func testNaturalHomeFeedbackClosesBeforeFreshGuidedOwner() throws {
    let app = launch(guided: "mixed", feedback: "combined")
    activate("cadence.feedback.start", app)
    XCTAssertTrue(app.staticTexts["feedback-ui-test-banner"].waitForExistence(timeout: 5))
    XCTAssertEqual(element("feedback-opt-in", app).value as? String, "Off")
    activate("feedback-record", app)
    activate("feedback-stop", app)
    XCTAssertTrue(app.staticTexts["feedback-state-review"].waitForExistence(timeout: 5))
    XCTAssertTrue(app.buttons["feedback-replay"].exists)
    attach(app, "generated-natural-home-free-local-take")
    app.buttons["feedback-close"].tap()
    XCTAssertTrue(app.buttons["cadence.guided-word.start"].waitForExistence(timeout: 5))
    activate("cadence.guided-word.start", app)
    assertUnsetGuided(app)
    startGuided(app)
    XCTAssertEqual(app.staticTexts["guided-word"].label, "rabbit")
    XCTAssertFalse(app.buttons["guided-replay"].exists)
    XCTAssertFalse(app.staticTexts["feedback-state-review"].exists)
    activate("guided-record", app)
    app.buttons["guided-close"].tap()
    XCTAssertTrue(app.buttons["cadence.feedback.start"].waitForExistence(timeout: 5))
    XCTAssertEqual(historyEntries(app).count, 0)
    activate("cadence.feedback.start", app)
    XCTAssertTrue(app.staticTexts["feedback-state-ready"].waitForExistence(timeout: 5))
    XCTAssertFalse(app.buttons["feedback-replay"].exists)
    XCTAssertEqual(element("feedback-opt-in", app).value as? String, "Off")
    app.buttons["feedback-close"].tap()
  }

  func testNaturalHomeCloseReportsNewCleanupFailureBeforeReturningAndReopensFresh() throws {
    let app = launch(guided: "cleanupRecording")
    activate("cadence.guided-word.start", app)
    startGuided(app)
    activate("guided-record", app)
    app.buttons["guided-close"].tap()
    XCTAssertTrue(app.staticTexts["guided-close-note"].waitForExistence(timeout: 5))
    XCTAssertTrue(app.staticTexts["guided-close-note"].label.contains("couldn't be removed"))
    XCTAssertTrue(app.staticTexts["guided-ended"].exists)
    attach(app, "generated-natural-home-close-cleanup-warning")
    app.buttons["guided-close"].tap()
    XCTAssertTrue(app.buttons["cadence.guided-word.start"].waitForExistence(timeout: 5))
    XCTAssertEqual(historyEntries(app).count, 0)
    activate("cadence.guided-word.start", app)
    assertUnsetGuided(app)
    app.buttons["guided-close"].tap()
  }

  func testConflictingLegacyLaunchFlagsSelectOnlyGuidedAndCloseToHome() throws {
    let app = launch(
      guided: "mixed",
      modes: [
        "-CadenceAssessmentMode", "-CadenceSoundMode", "-CadenceFeedbackMode",
        "-CadenceGuidedWordMode",
      ])
    assertUnsetGuided(app)
    XCTAssertFalse(app.staticTexts["feedback-title"].exists)
    XCTAssertFalse(app.staticTexts["sound-title"].exists)
    app.buttons["guided-close"].tap()
    XCTAssertTrue(app.buttons["cadence.guided-word.start"].waitForExistence(timeout: 5))
    XCTAssertFalse(app.staticTexts["guided-title"].exists)
  }

  private func launch(
    guided: String? = nil, feedback: String? = nil, large: Bool = false, modes: [String] = []
  ) -> XCUIApplication {
    continueAfterFailure = false
    let app = XCUIApplication()
    app.launchArguments =
      [
        "-UIPreferredContentSizeCategoryName",
        large ? "UICTContentSizeCategoryAccessibilityXXXL" : "UICTContentSizeCategoryL",
      ] + modes
    if let guided { app.launchArguments += ["-CadenceGuidedWordUITestCase", guided] }
    if let feedback { app.launchArguments += ["-CadenceUnifiedFeedbackUITestCase", feedback] }
    app.launch()
    waitForPracticeSystemBannerToClear()
    if modes.isEmpty {
      XCTAssertTrue(app.buttons["cadence.guided-word.start"].waitForExistence(timeout: 5))
      XCTAssertFalse(app.staticTexts["guided-title"].exists)
      XCTAssertFalse(app.staticTexts["feedback-title"].exists)
      if guided != nil || feedback != nil {
        XCTAssertTrue(app.staticTexts["cadence.home.ui-test-banner"].exists)
      }
    }
    return app
  }
  private func assertUnsetGuided(_ app: XCUIApplication) {
    XCTAssertTrue(app.staticTexts["guided-title"].waitForExistence(timeout: 5))
    XCTAssertFalse(app.buttons["guided-start"].isEnabled)
    XCTAssertFalse(app.buttons["guided-stop"].exists)
    XCTAssertFalse(app.buttons["guided-replay"].exists)
  }
  private func startGuided(_ app: XCUIApplication) {
    activate("guided-age-picker", app)
    XCTAssertTrue(app.buttons["9 years"].waitForExistence(timeout: 3))
    app.buttons["9 years"].tap()
    activate("guided-check-optin", app)
    activate("guided-start", app)
  }
  private func finishRound(_ app: XCUIApplication) {
    activate("guided-finish-early", app)
    XCTAssertTrue(app.alerts.firstMatch.waitForExistence(timeout: 3))
    app.alerts.firstMatch.buttons["Finish round"].tap()
    XCTAssertTrue(app.staticTexts["guided-summary-title"].waitForExistence(timeout: 5))
  }
  private func historyEntries(_ app: XCUIApplication) -> XCUIElementQuery {
    app.descendants(matching: .any).matching(
      NSPredicate(format: "identifier BEGINSWITH %@", "cadence.history.entry-"))
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
    XCTAssertTrue(target.waitForExistence(timeout: 5))
    let scroll = app.scrollViews.firstMatch
    for _ in 0..<40 {
      let viewport = scroll.frame
      var top = viewport.minY
      for id in ["guided-close", "feedback-close"] {
        let close = app.buttons[id]
        if close.exists && close.isHittable { top = max(top, close.frame.maxY) }
      }
      let about = app.buttons["About practice and privacy"]
      if about.exists && about.isHittable { top = max(top, about.frame.maxY) }
      for id in ["guided-ui-test-banner", "feedback-ui-test-banner", "cadence.home.ui-test-banner"]
      {
        let banner = app.staticTexts[id]
        if banner.exists && banner.isHittable { top = max(top, banner.frame.maxY) }
      }
      let frame = target.frame
      if target.isHittable && frame.minY >= top + 8 && frame.maxY <= viewport.maxY - 8 { return }
      let bottom = viewport.maxY - 8
      let center = (top + 8 + bottom) / 2
      let travel = min(abs(frame.midY - center), (bottom - top - 8) * 0.3)
      guard travel.isFinite && travel > 0 else {
        capturePracticeFailure(app)
        XCTFail("Control could not be revealed within the unobscured viewport")
        return
      }
      let controls = scroll.buttons.allElementsBoundByIndex + scroll.switches.allElementsBoundByIndex
        + scroll.links.allElementsBoundByIndex + scroll.sliders.allElementsBoundByIndex
      let left = max(viewport.minX, app.windows.firstMatch.frame.minX)
      let right = min(viewport.maxX, app.windows.firstMatch.frame.maxX)
      let active = (controls.map(\.frame) + [frame]).filter {
        !$0.isEmpty && $0.maxX > left && $0.minX < right
      }
      guard active.allSatisfy({ $0.minX.isFinite && $0.maxX.isFinite }) else {
        XCTFail("Invalid control geometry")
        return
      }
      let leading = active.map(\.minX).min() ?? left
      let trailing = active.map(\.maxX).max() ?? right
      let x: CGFloat
      if leading - left >= 16 { x = (left + leading) / 2 }
      else if right - trailing >= 16 { x = (right + trailing) / 2 }
      else {
        capturePracticeFailure(app)
        XCTFail("No blank scroll gutter")
        return
      }
      let above = frame.midY < center
      let origin = scroll.coordinate(withNormalizedOffset: .zero)
      let start = origin.withOffset(CGVector(
        dx: x - viewport.minX, dy: center + (above ? -travel / 2 : travel / 2) - viewport.minY))
      let finish = origin.withOffset(CGVector(
        dx: x - viewport.minX, dy: center + (above ? travel / 2 : -travel / 2) - viewport.minY))
      start.press(
        forDuration: 0.01, thenDragTo: finish, withVelocity: .slow, thenHoldForDuration: 0.2)
    }
    capturePracticeFailure(app)
    XCTFail("Control did not become fully visible")
  }
  private func attach(_ app: XCUIApplication, _ name: String) {
    let shot = XCTAttachment(screenshot: app.screenshot())
    shot.name = name
    shot.lifetime = .keepAlways
    add(shot)
    let tree = XCTAttachment(string: app.debugDescription)
    tree.name = name + "-accessibility"
    tree.lifetime = .keepAlways
    add(tree)
  }
}
