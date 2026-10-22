import XCTest

/// Natural Home navigation with generated local PCM and controlled, invented feedback.
/// Player state verifies explicit source selection, not audible playback or model accuracy.
@MainActor
final class ResearchTwoTryListeningUITests: XCTestCase {
  func testUnsetContextTwoTriesSwitchSourcesReplaceOldestAndClearWithoutHistory() {
    let app = launch()
    let context = element("feedback-context", app)
    XCTAssertTrue(
      context.label.contains("Not set") || (context.value as? String)?.contains("Not set") == true)
    XCTAssertEqual(element("feedback-opt-in", app).value as? String, "Off")
    XCTAssertFalse(element("feedback-sound-opt-in", app).exists)
    XCTAssertTrue(app.staticTexts["feedback-sound-state-adult-only"].exists)
    XCTAssertFalse(app.buttons["feedback-check-sound"].exists)
    recordStop("feedback-record", app)
    XCTAssertTrue(app.buttons["feedback-replay"].exists)
    XCTAssertFalse(app.buttons["feedback-replay-earlier"].exists)
    recordStop("feedback-record-another", app)
    attach(app, "two-try-compact-two-recordings-ready")
    activate("feedback-replay-earlier", app)
    XCTAssertTrue(app.staticTexts["feedback-replay-earlier-playing"].waitForExistence(timeout: 3))
    attach(app, "two-try-compact-earlier-playing")
    activate("feedback-replay", app)
    XCTAssertTrue(app.staticTexts["feedback-replay-latest-playing"].waitForExistence(timeout: 3))
    attach(app, "two-try-compact-latest-playing")
    XCTAssertFalse(app.staticTexts["feedback-replay-earlier-playing"].exists)
    activate("feedback-example", app)
    XCTAssertTrue(element("feedback-example-state-playing", app).waitForExistence(timeout: 3))
    XCTAssertFalse(app.staticTexts["feedback-replay-latest-playing"].exists)
    attach(app, "two-try-compact-public-example-playing")
    activate("feedback-replay-earlier", app)
    XCTAssertTrue(app.staticTexts["feedback-replay-earlier-playing"].waitForExistence(timeout: 3))
    XCTAssertFalse(element("feedback-example-state-playing", app).exists)
    recordStop("feedback-record-another", app)
    XCTAssertEqual(app.buttons.matching(identifier: "feedback-replay-earlier").count, 1)
    XCTAssertEqual(app.buttons.matching(identifier: "feedback-replay").count, 1)
    XCTAssertFalse(app.staticTexts["feedback-state-result-matched"].exists)
    activate("feedback-retake", app)
    XCTAssertTrue(app.buttons["feedback-record"].waitForExistence(timeout: 3))
    XCTAssertFalse(app.buttons["feedback-replay-earlier"].exists)
    XCTAssertFalse(app.buttons["feedback-replay"].exists)
    closeHome(app)
  }

  func testAdultChecksBelongToLatestTryAndReplayDoesNotRestoreEarlierResults() {
    let app = launch()
    activate("feedback-context", app)
    XCTAssertTrue(app.buttons["Adult (18+)"].waitForExistence(timeout: 3))
    app.buttons["Adult (18+)"].tap()
    for id in ["feedback-opt-in", "feedback-sound-adult", "feedback-sound-opt-in"] {
      activate(id, app)
      let on = XCTNSPredicateExpectation(
        predicate: NSPredicate(format: "value == %@", "On"), object: element(id, app))
      XCTAssertEqual(XCTWaiter.wait(for: [on], timeout: 3), .completed)
    }
    recordStop("feedback-record", app)
    checkBoth(app)
    activate("feedback-record-another", app)
    XCTAssertTrue(app.buttons["feedback-stop"].waitForExistence(timeout: 3))
    XCTAssertFalse(app.staticTexts["feedback-state-result-matched"].exists)
    XCTAssertFalse(app.staticTexts["feedback-sound-state-result-bw"].exists)
    activate("feedback-stop", app)
    XCTAssertTrue(app.staticTexts["feedback-state-review"].waitForExistence(timeout: 3))
    activate("feedback-replay", app)
    XCTAssertTrue(app.staticTexts["feedback-replay-latest-playing"].waitForExistence(timeout: 3))
    XCTAssertFalse(app.staticTexts["feedback-state-result-matched"].exists)
    XCTAssertFalse(app.staticTexts["feedback-sound-state-result-bw"].exists)
    activate("feedback-replay", app)
    checkBoth(app)
    scrollTo(element("feedback-state-result-matched", app), app)
    attach(app, "two-try-compact-latest-word-result")
    scrollTo(element("feedback-sound-state-result-bw", app), app)
    attach(app, "two-try-compact-latest-sound-result")
    activate("feedback-replay-earlier", app)
    XCTAssertTrue(app.staticTexts["feedback-replay-earlier-playing"].waitForExistence(timeout: 3))
    XCTAssertTrue(app.staticTexts["feedback-state-result-matched"].exists)
    XCTAssertTrue(app.staticTexts["feedback-sound-state-result-bw"].exists)
    closeHome(app)
  }

  func testOldestCleanupFailureBlocksThirdRecordingAndCloseReturnsHome() {
    let app = launch("twoTryCleanup")
    recordStop("feedback-record", app)
    recordStop("feedback-record-another", app)
    activate("feedback-record-another", app)
    XCTAssertTrue(app.staticTexts["feedback-state-cleanup"].waitForExistence(timeout: 3))
    XCTAssertTrue(app.staticTexts["feedback-detail"].label.contains("replay are paused"))
    XCTAssertFalse(app.staticTexts["feedback-tries-note"].exists)
    XCTAssertFalse(app.buttons["feedback-replay-earlier"].exists)
    XCTAssertFalse(app.buttons["feedback-replay"].exists)
    XCTAssertFalse(app.buttons["feedback-stop"].exists)
    XCTAssertFalse(app.staticTexts["feedback-state-permission"].exists)
    XCTAssertFalse(app.buttons["feedback-record"].exists)
    XCTAssertFalse(app.buttons["feedback-record-another"].exists)
    attach(app, "two-try-oldest-cleanup-blocked")
    closeHome(app)
  }

  func testPublicExampleCleanupFailureKeepsFirstCloseWarningUntilSecondClose() {
    let app = launch("cleanupExample")
    activate("feedback-example", app)
    XCTAssertTrue(element("feedback-example-state-playing", app).waitForExistence(timeout: 3))
    app.buttons["feedback-close"].tap()
    XCTAssertTrue(app.staticTexts["feedback-close-note"].waitForExistence(timeout: 3))
    XCTAssertTrue(app.staticTexts["feedback-title"].exists)
    attach(app, "two-try-public-example-first-close-warning")
    closeHome(app)
  }

  func testLargestTextTwoTryControlsAreFullyVisibleAndAccessible() throws {
    let app = launch(large: true)
    recordStop("feedback-record", app)
    recordStop("feedback-record-another", app)
    for id in ["feedback-record-another", "feedback-replay-earlier", "feedback-replay"] {
      let control = element(id, app)
      scrollTo(control, app)
      XCTAssertTrue(control.isHittable)
      XCTAssertGreaterThanOrEqual(control.frame.height, 44, id)
      attach(app, "two-try-largest-" + id)
    }
    for source in [
      ("feedback-replay-earlier", "feedback-replay-earlier-playing"),
      ("feedback-replay", "feedback-replay-latest-playing"),
    ] {
      activate(source.0, app)
      XCTAssertTrue(app.staticTexts[source.1].waitForExistence(timeout: 3))
      attach(app, "two-try-largest-" + source.1)
    }
    try app.performAccessibilityAudit()
    closeHome(app)
  }

  private func launch(_ fixture: String = "twoTries", large: Bool = false) -> XCUIApplication {
    continueAfterFailure = false
    let app = XCUIApplication()
    app.launchArguments = [
      "-UIPreferredContentSizeCategoryName",
      large ? "UICTContentSizeCategoryAccessibilityXXXL" : "UICTContentSizeCategoryL",
      "-CadenceUnifiedFeedbackUITestCase", fixture, "-CadenceGuidedWordUITestCase", "mixed",
    ]
    app.launch()
    XCTAssertTrue(app.buttons["cadence.feedback.start"].waitForExistence(timeout: 5))
    XCTAssertFalse(app.staticTexts["feedback-title"].exists)
    activate("cadence.feedback.start", app)
    XCTAssertTrue(app.staticTexts["feedback-state-ready"].waitForExistence(timeout: 5))
    XCTAssertFalse(app.buttons["feedback-stop"].exists)
    return app
  }

  private func recordStop(_ id: String, _ app: XCUIApplication) {
    activate(id, app)
    XCTAssertTrue(app.buttons["feedback-stop"].waitForExistence(timeout: 5))
    activate("feedback-stop", app)
    XCTAssertTrue(app.staticTexts["feedback-state-review"].waitForExistence(timeout: 5))
  }

  private func checkBoth(_ app: XCUIApplication) {
    activate("feedback-check", app)
    XCTAssertTrue(app.staticTexts["feedback-state-result-matched"].waitForExistence(timeout: 5))
    activate("feedback-check-sound", app)
    XCTAssertTrue(app.staticTexts["feedback-sound-state-result-bw"].waitForExistence(timeout: 5))
  }

  private func closeHome(_ app: XCUIApplication) {
    app.buttons["feedback-close"].tap()
    XCTAssertTrue(app.buttons["cadence.feedback.start"].waitForExistence(timeout: 5))
    XCTAssertFalse(app.staticTexts["feedback-title"].exists)
    XCTAssertEqual(
      app.descendants(matching: .any).matching(
        NSPredicate(format: "identifier BEGINSWITH %@", "cadence.history.entry-")
      ).count, 0)
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
