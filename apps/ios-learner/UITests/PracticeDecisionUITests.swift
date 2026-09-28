import XCTest

/// Generated word guesses exercise the real practice view, without sensors or inference.
@MainActor
final class PracticeDecisionUITests: XCTestCase {
  func testCompactUnmatchedPracticeExplainsAvailableChoices() { journey(largeText: false) }
  func testLargestTextUnmatchedPracticeExplainsAvailableChoices() { journey(largeText: true) }

  private let decisionID = "cadence.practice.word-check-decision"
  private let decision = "A word match isn’t required. You can move on or record another try."
  private let result = "No match for “ball” in this try. No sound error is identified."

  private func journey(largeText: Bool) {
    continueAfterFailure = false
    executionTimeAllowance = 360
    let app = XCUIApplication()
    for key in app.launchEnvironment.keys
    where key.hasPrefix("CADENCE_") || key.hasPrefix("TEST_RUNNER_CADENCE_") {
      app.launchEnvironment.removeValue(forKey: key)
    }
    app.launchEnvironment["CADENCE_CONTROLLED_UI_HOST"] = "1"
    app.launchArguments = [
      "-CadenceLocalGuidedMode", "-CadenceLocalGuidedUITestCase",
      largeText ? "wordGuessAX" : "wordGuess",
      "-CadenceControlledUIRunID", UUID().uuidString.lowercased(),
    ]
    let prefix = "practice-decision-" + (largeText ? "largest" : "normal")
    addTeardownBlock { @MainActor [weak self] () throws -> Void in
      defer { app.terminate() }
      guard let self, app.state == .runningForeground else { return }
      self.captureGeneratedTimeoutState(prefix + "-before-cleanup", app)
      let close = app.buttons["cadence.guided.close"]
      if close.exists, close.isEnabled, close.isHittable {
        close.tap()
        _ = app.staticTexts["cadence.generated-guided.closed"].waitForExistence(timeout: 5)
      }
      self.captureGeneratedTimeoutState(prefix + "-cleanup-result", app)
    }
    app.launch()
    waitLabel(app.staticTexts["cadence.generated-guided.seed"], "Generated stage: unseeded setup")
    activate("cadence.guided.start", app)
    record("cadence.record", app)
    check(1, made: 1, kept: 1, app)
    noDecision(app)
    captureGeneratedTimeoutState(prefix + "-initial-no-cue", app)
    print("CADENCE_PRACTICE_DECISION_STATE=\(prefix)-initial-no-cue")
    activate("cadence.guided.continue", app)
    activate("cadence.guided.finish-stage", app)
    activate("cadence.guided.select.b-beginning-ball", app)
    activate("cadence.guided.practice.start", app)
    waitLabel(app.staticTexts["cadence.word"], "ball")
    let frozen = "First review: No word match. Word checks cannot identify which sound was made."
    waitLabel(app.staticTexts["cadence.guided.first-observation"], frozen)
    noDecision(app)
    record("cadence.record", app)
    noDecision(app)
    check(2, made: 2, kept: 1, app)
    inspectDecision(prefix + "-first-result", app)
    print("CADENCE_PRACTICE_DECISION_STATE=\(prefix)-first-result")

    activate("cadence.record-another", app)
    XCTAssertTrue(app.buttons["cadence.stop"].waitForExistence(timeout: 5))
    noDecision(app)
    activate("cadence.stop", app)
    waitLabel(app.staticTexts["cadence.word-check-earlier-result"], result)
    waitLabel(app.staticTexts["cadence.word-check-empty"], "No word-check result for this try.")
    noDecision(app) // An earlier no-match cannot advise on an unchecked replacement.
    counters(checks: 2, made: 3, kept: 2, app)
    captureGeneratedTimeoutState(prefix + "-retake-no-cue", app)
    print("CADENCE_PRACTICE_DECISION_STATE=\(prefix)-retake-no-cue")
    check(3, made: 3, kept: 2, app)
    inspectDecision(prefix + "-latest-result", app)
    waitLabel(app.staticTexts["cadence.guided.first-observation"], frozen)
    print("CADENCE_PRACTICE_DECISION_STATE=\(prefix)-latest-result")
    activate("cadence.guided.continue", app)
    waitLabel(app.staticTexts["cadence.generated-guided.receipts"], "Generated practice receipts: 1 exact")
    activate("cadence.guided.recheck.start", app)
    waitLabel(app.staticTexts["cadence.guided.visit-heading"], "Recheck · 1 of 5")
    noDecision(app)
    record("cadence.record", app)
    check(4, made: 4, kept: 1, rows: "b:1", app)
    noDecision(app) // Same no-match status in recheck is not selected practice.
    captureGeneratedTimeoutState(prefix + "-recheck-no-cue", app)
    print("CADENCE_PRACTICE_DECISION_STATE=\(prefix)-recheck-no-cue")
    let close = app.buttons["cadence.guided.close"]
    XCTAssertTrue(close.isEnabled && close.isHittable)
    close.tap()
    waitLabel(app.staticTexts["cadence.generated-guided.closed-files"],
      "Generated files: made 4, kept 0 · permission requests 4 · playback starts 0")
    waitLabel(app.staticTexts["cadence.generated-guided.closed-history"], "Generated history: 1 rows [b:1]")
    captureGeneratedTimeoutState(prefix + "-closed", app)
    print("CADENCE_PRACTICE_DECISION_STATE=\(prefix)-closed")
  }

  private func inspectDecision(_ name: String, _ app: XCUIApplication) {
    let text = app.staticTexts[decisionID]
    waitLabel(text, decision)
    XCTAssertEqual(app.staticTexts.matching(identifier: decisionID).count, 1)
    XCTAssertTrue(app.buttons["cadence.guided.continue"].isEnabled)
    XCTAssertTrue(app.buttons["cadence.record-another"].isEnabled)
    XCTAssertLessThanOrEqual(app.staticTexts["cadence.word-check-result"].frame.maxY, text.frame.minY)
    captureGeneratedTimeoutText(text, id: decisionID, name: name, app)
  }

  private func noDecision(_ app: XCUIApplication) {
    XCTAssertFalse(app.staticTexts[decisionID].exists)
  }

  private func record(_ id: String, _ app: XCUIApplication) {
    activate(id, app)
    XCTAssertTrue(app.buttons["cadence.stop"].waitForExistence(timeout: 5))
    activate("cadence.stop", app)
    XCTAssertTrue(app.buttons["cadence.replay"].waitForExistence(timeout: 5))
  }

  private func check(_ count: Int, made: Int, kept: Int, rows: String = "", _ app: XCUIApplication) {
    noDecision(app)
    activate("cadence.word-check", app)
    waitLabel(app.staticTexts["cadence.word-check-result"], result)
    counters(checks: count, made: made, kept: kept, rows: rows, app)
  }

  private func counters(checks: Int, made: Int, kept: Int, rows: String = "", _ app: XCUIApplication) {
    waitLabel(app.staticTexts["cadence.generated-guided.files"],
      "Generated files: made \(made), kept \(kept) · permission requests \(made) · playback starts 0")
    waitLabel(app.staticTexts["cadence.generated-guided.checks"],
      "Generated checks: \(checks), pending 0, cancelled 0, borrowed 0")
    waitLabel(app.staticTexts["cadence.generated-guided.history"],
      "Generated history: \(rows.isEmpty ? 0 : 1) rows [\(rows)]")
  }

  private func activate(_ id: String, _ app: XCUIApplication) {
    let target = app.buttons[id]
    XCTAssertTrue(target.exists || target.waitForExistence(timeout: 5), id)
    if id.hasPrefix("cadence.guided.select.") {
      // A selection row can exceed the largest-text viewport; tap its visible portion.
      captureGeneratedTimeoutText(target, id: id, name: "practice-decision-selection-row", app)
      let window = app.windows.firstMatch
      let frame = app.scrollViews.firstMatch.frame.intersection(window.frame)
      let top = max(frame.minY, app.buttons["cadence.guided.close"].frame.maxY) + 8
      let visible = target.frame.intersection(CGRect(
        x: frame.minX, y: top, width: frame.width, height: max(0, frame.maxY - top - 8)))
      XCTAssertTrue(target.isEnabled && target.isHittable)
      XCTAssertGreaterThanOrEqual(visible.width, 44)
      XCTAssertGreaterThanOrEqual(visible.height, 44)
      window.coordinate(withNormalizedOffset: .zero).withOffset(CGVector(
        dx: visible.midX - window.frame.minX, dy: visible.midY - window.frame.minY)).tap()
      return
    }
    revealGeneratedTimeoutControl(target, id: id, app)
    target.tap()
  }

  private func waitLabel(_ target: XCUIElement, _ label: String) {
    XCTAssertTrue(target.exists || target.waitForExistence(timeout: 5))
    let match = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == %@", label), object: target)
    XCTAssertEqual(XCTWaiter.wait(for: [match], timeout: 5), .completed, label)
  }
}
