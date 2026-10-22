import XCTest

/// Explicitly generated capture/example PCM and invented model replies; no sensors or network.
@MainActor
final class ResearchPracticeExampleUITests: XCTestCase {
  func testProductionLargeTextListeningControlFullyVisibleWithoutPlaying() throws {
    continueAfterFailure = false
    let app = XCUIApplication()
    app.launchArguments = [
      "-CadenceFeedbackMode", "-UIPreferredContentSizeCategoryName",
      "UICTContentSizeCategoryAccessibilityXXXL",
    ]
    app.launch()
    XCTAssertTrue(app.staticTexts["feedback-state-ready"].waitForExistence(timeout: 5))
    XCTAssertFalse(app.staticTexts["feedback-ui-test-banner"].exists)
    activate("feedback-word-picker", app)
    XCTAssertTrue(app.buttons["bread · r sound"].waitForExistence(timeout: 3))
    app.buttons["bread · r sound"].tap()
    let example = app.buttons["feedback-example"]
    scrollTo(example, app)
    XCTAssertTrue(example.isHittable)
    XCTAssertTrue(example.isEnabled)
    XCTAssertEqual(example.label, "Play example")
    let viewport = app.scrollViews.firstMatch.frame
    XCTAssertGreaterThanOrEqual(example.frame.minY, viewport.minY)
    XCTAssertLessThanOrEqual(example.frame.maxY, viewport.maxY)
    XCTAssertGreaterThanOrEqual(example.frame.height, 44)
    attach(app, "production-large-bread-example-control-no-capture")
    XCTAssertFalse(app.buttons["feedback-stop"].exists)
    XCTAssertFalse(app.buttons["feedback-replay"].exists)
    app.buttons["feedback-close"].tap()
  }
  func testProductionBreadCueAndCreditsWithoutPlaybackOrRecording() throws {
    continueAfterFailure = false
    let app = XCUIApplication()
    app.launchArguments = [
      "-CadenceFeedbackMode", "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryL",
    ]
    app.launch()
    XCTAssertTrue(app.staticTexts["feedback-state-ready"].waitForExistence(timeout: 5))
    XCTAssertFalse(app.staticTexts["feedback-ui-test-banner"].exists)
    activate("feedback-word-picker", app)
    XCTAssertTrue(app.buttons["bread · r sound"].waitForExistence(timeout: 3))
    app.buttons["bread · r sound"].tap()
    let example = app.buttons["feedback-example"]
    scrollTo(example, app)
    XCTAssertTrue(example.isEnabled)
    XCTAssertEqual(example.label, "Play example")
    XCTAssertTrue(app.staticTexts["feedback-example-cue"].label.contains("b followed by r"))
    attach(app, "production-bread-listening-controls-no-capture")
    activate("feedback-example-credit", app)
    XCTAssertTrue(app.staticTexts["By Dvortygirl"].exists)
    XCTAssertTrue(app.staticTexts["License: CC-BY-SA-3.0"].exists)
    for label in ["Example source page", "Example license, CC-BY-SA-3.0"] {
      XCTAssertTrue(
        app.descendants(matching: .any).matching(NSPredicate(format: "label == %@", label))
          .firstMatch.exists)
    }
    XCTAssertTrue(
      app.staticTexts.containing(NSPredicate(format: "label CONTAINS %@", "Speaker age is unknown"))
        .firstMatch.exists)
    attach(app, "production-bread-public-attribution-disclosure")
    XCTAssertFalse(app.buttons["feedback-stop"].exists)
    XCTAssertFalse(app.buttons["feedback-replay"].exists)
    XCTAssertFalse(app.staticTexts["feedback-example-state-playing"].exists)
    app.buttons["feedback-close"].tap()
  }
  func testExampleAndOwnReplaySwitchWithoutContextOrCheckConsent() throws {
    let app = launch("listening")
    XCTAssertTrue(app.buttons["feedback-record"].isHittable)
    activate("feedback-example", app)
    XCTAssertTrue(app.staticTexts["feedback-example-state-playing"].waitForExistence(timeout: 5))
    XCTAssertEqual(app.buttons["feedback-example"].label, "Stop example")
    XCTAssertFalse(app.buttons["feedback-replay"].exists)
    attach(app, "generated-example-before-any-recording")
    activate("feedback-example", app)
    record(app)
    activate("feedback-replay", app)
    XCTAssertEqual(app.buttons["feedback-replay"].label, "Stop replay")
    activate("feedback-example", app)
    XCTAssertTrue(app.staticTexts["feedback-example-state-playing"].waitForExistence(timeout: 5))
    XCTAssertEqual(app.buttons["feedback-replay"].label, "Replay this try")
    activate("feedback-replay", app)
    XCTAssertEqual(app.buttons["feedback-replay"].label, "Stop replay")
    XCTAssertFalse(app.staticTexts["feedback-example-state-playing"].exists)
    XCTAssertTrue(app.staticTexts["feedback-state-review"].exists)
    attach(app, "generated-own-replay-after-example-same-take")
    app.buttons["feedback-close"].tap()
  }

  func testListeningKeepsBothCheckResultsAndGenericBreadCue() throws {
    let app = launch("listening")
    configureAdult(app)
    record(app)
    activate("feedback-check", app)
    XCTAssertTrue(app.staticTexts["feedback-state-result-matched"].waitForExistence(timeout: 5))
    activate("feedback-check-sound", app)
    XCTAssertTrue(app.staticTexts["feedback-sound-state-result-bw"].waitForExistence(timeout: 5))
    activate("feedback-example", app)
    XCTAssertTrue(app.staticTexts["feedback-example-state-playing"].waitForExistence(timeout: 5))
    XCTAssertTrue(app.staticTexts["feedback-state-result-matched"].exists)
    XCTAssertTrue(app.staticTexts["feedback-sound-state-result-bw"].exists)
    XCTAssertTrue(app.staticTexts["feedback-example-cue"].label.contains("b followed by r"))
    attach(app, "generated-bread-example-retains-word-and-sound-results")
    activate("feedback-replay", app)
    XCTAssertTrue(app.staticTexts["feedback-state-result-matched"].exists)
    XCTAssertTrue(app.staticTexts["feedback-sound-state-result-bw"].exists)
    app.buttons["feedback-close"].tap()
  }

  func testLoadingCancellationAndExampleFailureKeepOwnTake() throws {
    for fixture in ["loadingExample", "unavailableExample"] {
      let app = launch(fixture)
      record(app)
      activate("feedback-example", app)
      if fixture == "loadingExample" {
        XCTAssertTrue(
          app.otherElements["feedback-example-progress"].waitForExistence(timeout: 5)
            || control("feedback-example-progress", app).exists)
        XCTAssertEqual(app.buttons["feedback-example"].label, "Cancel example")
        attach(app, "generated-example-loading-cancel-control")
        activate("feedback-example", app)
        XCTAssertFalse(control("feedback-example-progress", app).exists)
      } else {
        XCTAssertTrue(app.staticTexts["feedback-example-state-failed"].waitForExistence(timeout: 5))
        attach(app, "generated-example-unavailable-own-take-retained")
      }
      XCTAssertTrue(app.staticTexts["feedback-state-review"].exists)
      activate("feedback-replay", app)
      XCTAssertEqual(app.buttons["feedback-replay"].label, "Stop replay")
      app.buttons["feedback-close"].tap()
    }
  }

  func testSharedServicePauseAllowsExampleAndOwnReplay() throws {
    let app = launch("cleanup")
    configureAdult(app)
    record(app)
    activate("feedback-check", app)
    XCTAssertTrue(
      app.staticTexts["feedback-state-result-service-cleanup"].waitForExistence(timeout: 5))
    activate("feedback-example", app)
    XCTAssertTrue(app.staticTexts["feedback-example-state-playing"].waitForExistence(timeout: 5))
    XCTAssertTrue(app.staticTexts["feedback-state-result-service-cleanup"].exists)
    attach(app, "generated-server-pause-example-still-available")
    activate("feedback-replay", app)
    XCTAssertEqual(app.buttons["feedback-replay"].label, "Stop replay")
    XCTAssertTrue(app.staticTexts["feedback-state-result-service-cleanup"].exists)
    app.buttons["feedback-close"].tap()
  }

  func testLargeTextListeningControlsAndGeneratedCreditsAreAccessible() throws {
    let app = launch("listening", large: true)
    for id in ["feedback-record", "feedback-example", "feedback-example-credit"] {
      let target = control(id, app)
      scrollTo(target, app)
      XCTAssertTrue(target.isHittable, id)
      XCTAssertGreaterThanOrEqual(target.frame.height, 44, id)
      attach(app, "generated-large-text-" + id)
    }
    activate("feedback-example-credit", app)
    XCTAssertTrue(
      app.staticTexts.containing(NSPredicate(format: "label CONTAINS %@", "No human spoke"))
        .firstMatch.exists)
    XCTAssertFalse(app.links["Source page"].exists)
    activate("feedback-example", app)
    XCTAssertTrue(app.staticTexts["feedback-example-state-playing"].waitForExistence(timeout: 5))
    attach(app, "generated-large-text-example-playing")
    try app.performAccessibilityAudit()
    app.buttons["feedback-close"].tap()
  }

  func testPublicExampleCleanupRetryPreservesOwnTake() throws {
    let app = launch("cleanupExample")
    record(app)
    activate("feedback-example", app)
    XCTAssertTrue(app.staticTexts["feedback-example-state-playing"].waitForExistence(timeout: 5))
    activate("feedback-example", app)
    XCTAssertTrue(app.staticTexts["feedback-example-state-cleanup"].waitForExistence(timeout: 5))
    XCTAssertFalse(app.buttons["feedback-example"].isEnabled)
    XCTAssertTrue(app.buttons["feedback-replay"].isEnabled)
    XCTAssertTrue(app.staticTexts["feedback-state-review"].exists)
    attach(app, "generated-public-example-cleanup-failure-own-take-safe")
    activate("feedback-example-cleanup", app)
    XCTAssertFalse(app.staticTexts["feedback-example-state-cleanup"].exists)
    XCTAssertTrue(app.buttons["feedback-example"].isEnabled)
    activate("feedback-replay", app)
    XCTAssertEqual(app.buttons["feedback-replay"].label, "Stop replay")
    XCTAssertTrue(app.staticTexts["feedback-state-review"].exists)
    app.buttons["feedback-close"].tap()
  }

  private func launch(_ fixture: String, large: Bool = false) -> XCUIApplication {
    continueAfterFailure = false
    let app = XCUIApplication()
    app.launchArguments = [
      "-CadenceFeedbackMode", "-CadenceUnifiedFeedbackUITestCase", fixture,
      "-UIPreferredContentSizeCategoryName",
      large ? "UICTContentSizeCategoryAccessibilityXXXL" : "UICTContentSizeCategoryL",
    ]
    app.launch()
    XCTAssertTrue(app.staticTexts["feedback-ui-test-banner"].waitForExistence(timeout: 5))
    XCTAssertTrue(app.staticTexts["feedback-state-ready"].exists)
    XCTAssertTrue(app.staticTexts["feedback-example-generated"].exists)
    return app
  }
  private func configureAdult(_ app: XCUIApplication) {
    activate("feedback-context", app)
    XCTAssertTrue(app.buttons["Adult (18+)"].waitForExistence(timeout: 3))
    app.buttons["Adult (18+)"].tap()
    for id in ["feedback-opt-in", "feedback-sound-adult", "feedback-sound-opt-in"] {
      activate(id, app)
      let on = XCTNSPredicateExpectation(
        predicate: NSPredicate(format: "value == %@", "On"), object: control(id, app))
      XCTAssertEqual(XCTWaiter.wait(for: [on], timeout: 3), .completed)
    }
  }
  private func record(_ app: XCUIApplication) {
    activate("feedback-record", app)
    XCTAssertTrue(app.buttons["feedback-stop"].waitForExistence(timeout: 5))
    activate("feedback-stop", app)
    XCTAssertTrue(app.staticTexts["feedback-state-review"].waitForExistence(timeout: 5))
  }
  private func control(_ id: String, _ app: XCUIApplication) -> XCUIElement {
    app.descendants(matching: .any).matching(identifier: id).firstMatch
  }
  private func activate(_ id: String, _ app: XCUIApplication) {
    let target = control(id, app)
    scrollTo(target, app)
    XCTAssertTrue(target.isHittable, id)
    XCTAssertTrue(target.isEnabled, id)
    target.tap()
  }
  private func scrollTo(_ target: XCUIElement, _ app: XCUIApplication) {
    let scroll = app.scrollViews.firstMatch
    for _ in 0..<30 {
      let viewport = scroll.frame
      let banner = app.staticTexts["feedback-ui-test-banner"]
      let top = max(viewport.minY, banner.exists ? banner.frame.maxY : viewport.minY) + 8
      let bottom = min(viewport.maxY, app.windows.firstMatch.frame.maxY) - 8
      let frame = target.frame
      if target.isHittable && frame.minY >= top && frame.maxY <= bottom { return }
      let start = scroll.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5))
      let finish = scroll.coordinate(
        withNormalizedOffset: CGVector(dx: 0.5, dy: frame.minY < top ? 0.7 : 0.3))
      start.press(forDuration: 0.01, thenDragTo: finish)
    }
  }
  private func attach(_ app: XCUIApplication, _ name: String) {
    let screenshot = XCTAttachment(screenshot: app.screenshot())
    screenshot.name = name
    screenshot.lifetime = .keepAlways
    add(screenshot)
    let tree = XCTAttachment(string: app.debugDescription)
    tree.name = name + "-accessibility"
    tree.lifetime = .keepAlways
    add(tree)
  }
}
