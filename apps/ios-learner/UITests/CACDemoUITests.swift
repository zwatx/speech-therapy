import XCTest

/// Requires an app built with CAC_FLOW_UI_VERIFICATION (simulator only) and
/// CADENCE_CAC_UI=1 for the runner. The app then uses inert capture hardware:
/// no microphone, permission prompt or speaker is used.
@MainActor
final class CACDemoUITests: XCTestCase {
  override func setUpWithError() throws {
    continueAfterFailure = false
  }

  func testSoundCheckPracticeAndRecheckJourney() throws {
    let app = try launch()
    try journey(app, name: "normal")
  }

  func testQuietAudioCanContinueWithoutCoachingOrRetry() throws {
    let app = try launch(quietAudio: true)
    tap(app.buttons["cadence.cac-demo.start"], in: app)
    tap(app.buttons["cadence.cac-demo.record"], in: app)
    tap(app.buttons["cadence.cac-demo.stop"], in: app)
    XCTAssertTrue(app.buttons["cadence.cac-demo.check"].waitForExistence(timeout: 5))
    XCTAssertFalse(app.staticTexts["Move a little closer"].exists)
    XCTAssertFalse(app.descendants(matching: .any)["cadence.cac-demo.capture-retry"].exists)
    attach(app, name: "quiet-review")
    tap(app.buttons["cadence.cac-demo.check"], in: app)
    XCTAssertTrue(app.staticTexts["cadence.cac-demo.feedback.clear"].waitForExistence(timeout: 5))
    tap(app.buttons["cadence.cac-demo.next"], in: app)
    expectWord("rabbit", in: app)
    tap(app.buttons["cadence.cac-demo.close"], in: app)
  }

  func testJourneyAtLargestText() throws {
    let app = try launch(largestText: true)
    try journey(app, name: "largest")
  }

  func testRepeatedCheckKeepsResultAndExitReturnsHome() throws {
    let app = try launch()
    tap(app.buttons["cadence.cac-demo.start"], in: app)
    recordAndCheck(app)
    XCTAssertTrue(app.staticTexts["cadence.cac-demo.feedback.clear"].exists)
    XCTAssertFalse(app.buttons["cadence.cac-demo.check"].exists, "A checked take offers Next")
    // The inert speaker fails explicitly; the result and navigation must stay usable.
    tap(app.buttons["cadence.cac-demo.hear-word"], in: app)
    XCTAssertTrue(
      app.staticTexts["cadence.cac-demo.spoken-word-status"].waitForExistence(timeout: 5))
    XCTAssertTrue(app.staticTexts["cadence.cac-demo.feedback.clear"].exists)
    XCTAssertTrue(app.buttons["cadence.cac-demo.next"].exists)
    tap(app.buttons["cadence.cac-demo.record-again"], in: app)
    XCTAssertTrue(app.descendants(matching: .any)["cadence.face-preview.camera"].isHittable)
    XCTAssertTrue(app.buttons["cadence.cac-demo.stop"].isHittable)
    XCTAssertFalse(app.staticTexts["cadence.cac-demo.feedback.title"].exists)
    tap(app.buttons["cadence.cac-demo.stop"], in: app)
    XCTAssertTrue(app.buttons["cadence.cac-demo.check"].waitForExistence(timeout: 5))
    XCTAssertFalse(app.buttons["cadence.cac-demo.next"].exists, "A new take needs its own check")
    tap(app.buttons["cadence.cac-demo.close"], in: app)
    XCTAssertTrue(app.buttons["cadence.cac-demo.start"].waitForExistence(timeout: 5))
    expectGone(app.buttons["cadence.cac-demo.close"])
  }

  func testEndingPracticeKeepsSoundCheckOnHome() throws {
    let app = try launch()
    tap(app.buttons["cadence.cac-demo.start"], in: app)
    for _ in 0..<3 {
      recordAndCheck(app)
      tap(app.buttons["cadence.cac-demo.next"], in: app)
    }
    tap(app.buttons["cadence.cac-demo.start-practice"], in: app)
    expectWord("rain", in: app)
    XCTAssertEqual(app.staticTexts["cadence.cac-demo.session-title"].label, "R practice")
    tap(app.buttons["cadence.cac-demo.close"], in: app)
    XCTAssertTrue(app.staticTexts["cadence.cac-demo.plan-title"].waitForExistence(timeout: 5))
    XCTAssertTrue(app.buttons["cadence.cac-demo.start-practice"].exists)
    expectGone(app.buttons["cadence.cac-demo.close"])
  }

  func testHidingPreviewKeepsAudioPracticeAvailable() throws {
    let app = try launch()
    tap(app.buttons["cadence.cac-demo.start"], in: app)
    let camera = app.descendants(matching: .any)["cadence.face-preview.camera"]
    XCTAssertTrue(camera.waitForExistence(timeout: 5))
    tap(app.buttons["cadence.face-preview.hide"], in: app)
    XCTAssertFalse(camera.exists)
    recordAndCheck(app, preview: false)
    XCTAssertTrue(app.staticTexts["cadence.cac-demo.feedback.clear"].exists)
    tap(app.buttons["cadence.cac-demo.close"], in: app)
    XCTAssertTrue(app.buttons["cadence.cac-demo.start"].waitForExistence(timeout: 5))
  }

  /// Ordinary capture branch, layout only. Never starts recording or audio playback.
  func testOrdinaryReadyLayoutWithoutStartingMedia() throws {
    let app = try launch(inertHardware: false)
    tap(app.buttons["cadence.cac-demo.start"], in: app)
    expectWord("boat", in: app)
    XCTAssertTrue(app.buttons["cadence.cac-demo.hear-word"].isHittable)
    XCTAssertTrue(app.buttons["cadence.cac-demo.hear-word"].isEnabled)
    XCTAssertTrue(app.buttons["cadence.cac-demo.record"].isHittable)
    attach(app, name: "ordinary-ready")
    tap(app.buttons["cadence.cac-demo.close"], in: app)
    XCTAssertTrue(app.buttons["cadence.cac-demo.start"].waitForExistence(timeout: 5))
  }

  // MARK: Steps

  private func journey(_ app: XCUIApplication, name: String) throws {
    XCTAssertTrue(app.staticTexts["cadence.cac-demo.welcome-title"].waitForExistence(timeout: 5))
    attach(app, name: "\(name)-welcome")
    tap(app.buttons["cadence.cac-demo.start"], in: app)

    for (word, outcome) in [("boat", "clear"), ("rabbit", "needs-practice"), ("sun", "clear")] {
      expectWord(word, in: app)
      recordAndCheck(
        app, compact: name == "normal", shot: word == "boat" ? "\(name)-recording" : nil)
      XCTAssertTrue(app.staticTexts["cadence.cac-demo.feedback.\(outcome)"].exists)
      if word == "rabbit" { attach(app, name: "\(name)-needs-practice") }
      tap(app.buttons["cadence.cac-demo.next"], in: app)
    }

    let plan = app.staticTexts["cadence.cac-demo.plan-title"]
    XCTAssertTrue(plan.waitForExistence(timeout: 5))
    XCTAssertTrue(plan.label.contains("R sound"))
    attach(app, name: "\(name)-plan")
    XCTAssertFalse(
      app.buttons["cadence.cac-demo.face-guide"].exists,
      "Face tracking belongs to the word recording screen")
    XCTAssertFalse(app.descendants(matching: .any)["cadence.face-preview.camera"].exists)
    tap(app.buttons["cadence.cac-demo.start-practice"], in: app)

    for word in ["rain", "ring", "rabbit"] {
      expectWord(word, in: app)
      recordAndCheck(
        app, compact: name == "normal", shot: name == "normal" ? "\(name)-\(word)-recording" : nil)
      XCTAssertTrue(app.staticTexts["cadence.cac-demo.feedback.clear"].exists)
      tap(app.buttons["cadence.cac-demo.next"], in: app)
    }

    XCTAssertTrue(app.staticTexts["cadence.cac-demo.recap-title"].waitForExistence(timeout: 5))
    XCTAssertTrue(app.buttons["cadence.cac-demo.practice-again"].exists)
    attach(app, name: "\(name)-recap")

    // Results land in the other tabs too.
    tap(app.tabBars.buttons["Progress"], in: app)
    XCTAssertTrue(app.staticTexts["6 words practiced today."].waitForExistence(timeout: 5))
    attach(app, name: "\(name)-progress")
    tap(app.tabBars.buttons["Sounds"], in: app)
    let r = app.buttons["cadence.cac-demo.sound.r"]
    XCTAssertTrue(r.waitForExistence(timeout: 5))
    attach(app, name: "\(name)-sounds")
    tap(r, in: app)
    XCTAssertTrue(app.staticTexts["rabbit"].waitForExistence(timeout: 5))
    attach(app, name: "\(name)-sound-detail")
    tap(app.tabBars.buttons["Today"], in: app)

    // A new sound check replaces the earlier results.
    tap(app.buttons["cadence.cac-demo.start"], in: app)
    expectWord("boat", in: app)
    tap(app.buttons["cadence.cac-demo.close"], in: app)
    XCTAssertTrue(app.staticTexts["cadence.cac-demo.welcome-title"].waitForExistence(timeout: 5))
  }

  private func expectGone(_ element: XCUIElement) {
    let gone = XCTNSPredicateExpectation(
      predicate: NSPredicate { _, _ in !element.exists }, object: nil)
    XCTAssertEqual(XCTWaiter.wait(for: [gone], timeout: 5), .completed, "\(element) remained")
  }

  private func expectWord(_ word: String, in app: XCUIApplication) {
    let element = app.staticTexts["cadence.cac-demo.word"]
    let shown = XCTNSPredicateExpectation(
      predicate: NSPredicate { _, _ in element.exists && element.label == word }, object: nil)
    XCTAssertEqual(XCTWaiter.wait(for: [shown], timeout: 5), .completed, "Expected \(word)")
  }

  private func recordAndCheck(
    _ app: XCUIApplication, compact: Bool = false, shot: String? = nil,
    preview: Bool = true
  ) {
    let camera = app.descendants(matching: .any)["cadence.face-preview.camera"]
    if preview { XCTAssertTrue(camera.waitForExistence(timeout: 5)) }
    tap(app.buttons["cadence.cac-demo.record"], in: app)
    let stop = app.buttons["cadence.cac-demo.stop"]
    XCTAssertTrue(stop.waitForExistence(timeout: 5))
    if preview {
      XCTAssertTrue(camera.exists, "Recording must keep the preview mounted")
      if compact {
        XCTAssertTrue(camera.isHittable, "Camera must be visible while recording")
        XCTAssertTrue(app.staticTexts["cadence.cac-demo.word"].isHittable)
        XCTAssertTrue(stop.isHittable, "Stop must share the viewport with the word and camera")
      }
    }
    if let shot { attach(app, name: shot) }
    tap(stop, in: app)
    tap(app.buttons["cadence.cac-demo.check"], in: app)
    XCTAssertTrue(app.staticTexts["cadence.cac-demo.feedback.title"].waitForExistence(timeout: 5))
  }

  // MARK: Harness

  private func launch(
    largestText: Bool = false, inertHardware: Bool = true,
    quietAudio: Bool = false
  ) throws
    -> XCUIApplication
  {
    let environment = ProcessInfo.processInfo.environment
    guard
      environment["CADENCE_CAC_UI"] == "1" || environment["TEST_RUNNER_CADENCE_CAC_UI"] == "1"
    else { throw XCTSkip("Explicit sensor-free CAC journey only.") }
    let app = XCUIApplication()
    app.launchEnvironment["CADENCE_CAC_FLOW_VERIFICATION"] = inertHardware ? "1" : "0"
    if quietAudio { app.launchEnvironment["CADENCE_CAC_QUIET_AUDIO"] = "1" }
    if largestText {
      app.launchArguments += [
        "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL",
      ]
    }
    app.launch()
    let marker = app.descendants(matching: .any)["cadence.cac-demo.verification-host"]
    guard !inertHardware || marker.waitForExistence(timeout: 5)
    else {
      app.terminate()
      throw XCTSkip("App lacks CAC_FLOW_UI_VERIFICATION; refusing to use a live microphone.")
    }
    return app
  }

  private func tap(_ element: XCUIElement, in app: XCUIApplication) {
    XCTAssertTrue(element.waitForExistence(timeout: 5), "Missing \(element.identifier)")
    for _ in 0..<8 {
      if element.isHittable {
        element.tap()
        return
      }
      app.swipeUp()
    }
    XCTFail("Control is not reachable: \(element.identifier)")
  }

  private func attach(_ app: XCUIApplication, name: String) {
    let attachment = XCTAttachment(screenshot: app.screenshot())
    attachment.name = name
    attachment.lifetime = .keepAlways
    add(attachment)
  }
}
