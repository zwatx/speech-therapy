import XCTest

/// Invented recognizer tokens and generated PCM, with an isolated participation store.
/// These controls and audits do not establish recognition accuracy or audible playback.
@MainActor
final class ResearchWordGuessUITests: XCTestCase {
  func testCompactMatchedGuessAndAnotherTryClearsIt() throws {
    try showGuess("guessMatched", word: "bread", result: "matched", large: false, finish: false)
  }

  func testLargestMatchedGuessAndFinishClearsIt() throws {
    try showGuess("guessMatched", word: "bread", result: "matched", large: true, finish: true)
  }

  func testCompactDifferentGuessAndFinishClearsIt() throws {
    try showGuess("guessDifferent", word: "red", result: "mismatch", large: false, finish: true)
  }

  func testLargestDifferentGuessAndAnotherTryClearsIt() throws {
    try showGuess("guessDifferent", word: "red", result: "mismatch", large: true, finish: false)
  }

  func testCompactUncertaintyDoesNotInventAGuess() throws {
    try uncertain(large: false)
  }

  func testLargestUncertaintyDoesNotInventAGuess() throws {
    try uncertain(large: true)
  }

  func testCloseClearsCurrentGuessBeforeReentry() {
    let app = launch("guessDifferent", large: false)
    configure(app)
    recordStop("feedback-record", app)
    activate("feedback-check", app)
    XCTAssertTrue(element("feedback-recognizer-guess", app).waitForExistence(timeout: 5))
    closeHome(app)
    assertNoGuess(app)
    activate("cadence.feedback.start", app)
    XCTAssertTrue(element("feedback-state-ready", app).waitForExistence(timeout: 5))
    assertNoGuess(app)
    closeHome(app)
  }

  private func showGuess(
    _ fixture: String, word: String, result: String, large: Bool, finish: Bool
  ) throws {
    let app = launch(fixture, large: large)
    configure(app)
    recordStop("feedback-record", app)
    activate("feedback-check", app)
    let status = element("feedback-state-result-" + result, app)
    XCTAssertTrue(status.waitForExistence(timeout: 5))
    XCTAssertTrue(status.label.lowercased().contains("bread"))
    let guess = element("feedback-recognizer-guess", app)
    scrollTo(guess, app)
    XCTAssertTrue(guess.label.lowercased().contains(word))
    XCTAssertTrue(
      guess.label.lowercased().contains("recognizer") || guess.label.lowercased().contains("model"))
    let note = element("feedback-recognizer-guess-note", app)
    XCTAssertTrue(note.exists)
    XCTAssertFalse(note.label.isEmpty)
    attach(app, "word-guess-" + fixture + (large ? "-largest" : "-compact"))
    try app.performAccessibilityAudit()
    if finish {
      activate("feedback-finish-practice", app)
      XCTAssertTrue(element("feedback-practice-saved", app).waitForExistence(timeout: 5))
    } else {
      activate("feedback-record-another", app)
      XCTAssertTrue(app.buttons["feedback-stop"].waitForExistence(timeout: 5))
    }
    assertNoGuess(app)
    if !finish {
      activate("feedback-stop", app)
      XCTAssertTrue(element("feedback-state-review", app).waitForExistence(timeout: 5))
      assertNoGuess(app)
    }
    closeHome(app)
    assertNoGuess(app)
    activate("cadence.feedback.start", app)
    XCTAssertTrue(element("feedback-state-ready", app).waitForExistence(timeout: 5))
    assertNoGuess(app)
    closeHome(app)
  }

  private func uncertain(large: Bool) throws {
    let app = launch("guessUncertain", large: large)
    configure(app)
    recordStop("feedback-record", app)
    activate("feedback-check", app)
    let status = element("feedback-state-result-uncertain", app)
    XCTAssertTrue(status.waitForExistence(timeout: 5))
    scrollTo(status, app)
    assertNoGuess(app)
    attach(app, large ? "word-guess-uncertain-largest" : "word-guess-uncertain-compact")
    try app.performAccessibilityAudit()
    closeHome(app)
    assertNoGuess(app)
  }

  private func assertNoGuess(_ app: XCUIApplication) {
    XCTAssertFalse(element("feedback-recognizer-guess", app).exists)
    XCTAssertFalse(element("feedback-recognizer-guess-note", app).exists)
  }

  private func configure(_ app: XCUIApplication) {
    activate("feedback-context", app)
    XCTAssertTrue(app.buttons["Adult (18+)"].waitForExistence(timeout: 3))
    app.buttons["Adult (18+)"].tap()
    activate("feedback-opt-in", app)
    XCTAssertEqual(element("feedback-opt-in", app).value as? String, "On")
  }

  private func launch(_ fixture: String, large: Bool) -> XCUIApplication {
    continueAfterFailure = false
    let app = XCUIApplication()
    app.launchArguments = [
      "-UIPreferredContentSizeCategoryName",
      large ? "UICTContentSizeCategoryAccessibilityXXXL" : "UICTContentSizeCategoryL",
      "-CadenceUnifiedFeedbackUITestCase", fixture,
    ]
    app.launch()
    XCTAssertTrue(app.buttons["cadence.feedback.start"].waitForExistence(timeout: 5))
    activate("cadence.feedback.start", app)
    XCTAssertTrue(element("feedback-ui-test-banner", app).waitForExistence(timeout: 5))
    XCTAssertTrue(element("feedback-state-ready", app).exists)
    assertNoGuess(app)
    return app
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
    let dismissed = XCTNSPredicateExpectation(
      predicate: NSPredicate(format: "exists == false"), object: app.staticTexts["feedback-title"])
    XCTAssertEqual(XCTWaiter.wait(for: [dismissed], timeout: 3), .completed)
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
    for _ in 0..<80 {
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
      // Move through long accessibility-size content before making small final corrections.
      let towardTop = frame.minY < top + 8
      // Aim at the middle of the fitting range, rather than a tiny edge correction that
      // may not cross the scroll gesture's activation distance.
      let fittingCenter = (top + 8 + viewport.maxY - 8 - frame.height) / 2
      let adjustment = fittingCenter - frame.minY
      let available = viewport.maxY - top - 48
      let distance = min(available * 0.9, max(6, abs(adjustment) * 0.8))
      // The trailing inset avoids pressing a control while dragging the scroll content.
      let startY = towardTop ? top + 24 : viewport.maxY - 24
      let start = scroll.coordinate(
        withNormalizedOffset: CGVector(dx: 0.96, dy: (startY - viewport.minY) / viewport.height))
      let end = scroll.coordinate(
        withNormalizedOffset: CGVector(
          dx: 0.96,
          dy: (startY + (towardTop ? distance : -distance) - viewport.minY) / viewport.height))
      if abs(adjustment) > available * 1.5 {
        start.press(forDuration: 0.01, thenDragTo: end)
      } else {
        // Hold before releasing a fine correction so inertia cannot fling the aligned control.
        start.press(
          forDuration: 0.1, thenDragTo: end, withVelocity: .slow, thenHoldForDuration: 0.2)
      }
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
