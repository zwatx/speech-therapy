import XCTest

final class DirectPracticeUITests: XCTestCase {
  @MainActor
  func testHomeAndPromptAreAccessibleWithoutSetup() throws {
    let app = practiceApp()
    app.launch()
    XCTAssertTrue(app.buttons["cadence.start"].waitForExistence(timeout: 5))
    XCTAssertFalse(app.staticTexts["Connect this device"].exists)
    keepScreenshot("home", app: app)
    try app.performAccessibilityAudit()

    app.buttons["cadence.start"].tap()
    XCTAssertTrue(app.buttons["cadence.record"].waitForExistence(timeout: 3))
    XCTAssertEqual(app.staticTexts["cadence.word"].label, "ball")
    keepScreenshot("prompt", app: app)
    try app.performAccessibilityAudit()
    app.buttons["cadence.close"].tap()
    XCTAssertTrue(app.buttons["cadence.start"].waitForExistence(timeout: 3))
  }

  @MainActor
  func testRealRecorderReplayRetryAndCompletion() throws {
    continueAfterFailure = false
    let app = practiceApp()
    let springboard = XCUIApplication(bundleIdentifier: "com.apple.springboard")
    app.launch()
    app.buttons["cadence.start"].tap()

    for index in 0..<3 {
      app.buttons["cadence.record"].tap()
      // This is the real system permission and AVAudioRecorder path, not injected audio.
      if springboard.buttons["Allow"].waitForExistence(timeout: 1) {
        springboard.buttons["Allow"].tap()
      }
      let replay = app.buttons["cadence.replay"]
      XCTAssertTrue(replay.waitForExistence(timeout: 10))
      replay.tap()
      let finished = XCTNSPredicateExpectation(
        predicate: NSPredicate(format: "label == %@", "Play recording"), object: replay)
      XCTAssertEqual(XCTWaiter.wait(for: [finished], timeout: 6), .completed)
      XCTAssertFalse(app.staticTexts["cadence.playback-error"].exists)
      if index == 0 {
        keepScreenshot("replay", app: app)
        app.buttons["cadence.retry"].tap()
        XCTAssertTrue(app.buttons["cadence.record"].waitForExistence(timeout: 3))
        app.buttons["cadence.record"].tap()
        XCTAssertTrue(replay.waitForExistence(timeout: 8))
      }
      app.buttons["cadence.continue"].tap()
    }
    XCTAssertTrue(app.staticTexts["cadence.complete"].waitForExistence(timeout: 3))
    XCTAssertFalse(app.buttons["cadence.replay"].exists)
    keepScreenshot("complete", app: app)
    try app.performAccessibilityAudit()
    app.buttons["Practice these again"].tap()
    XCTAssertEqual(app.staticTexts["cadence.word"].label, "ball")
    XCTAssertTrue(app.buttons["cadence.record"].exists)
    app.buttons["cadence.close"].tap()
    let clear = app.buttons["cadence.history.clear"]
    for _ in 0..<20 where !clear.isHittable { app.swipeUp() }
    XCTAssertTrue(clear.isHittable)
    XCTAssertTrue(app.staticTexts["Recent practice"].exists)
    keepScreenshot("participation-history", app: app)
    app.terminate()
    app.launch()
    for _ in 0..<20 where !clear.isHittable { app.swipeUp() }
    XCTAssertTrue(clear.isHittable, "Completed participation persists across launches")
    clear.tap()
    app.sheets.buttons["Clear recent practice"].tap()
    let removed = XCTNSPredicateExpectation(
      predicate: NSPredicate(format: "exists == false"), object: app.staticTexts["Recent practice"])
    XCTAssertEqual(XCTWaiter.wait(for: [removed], timeout: 5), .completed)
    app.terminate()
    app.launch()
    XCTAssertFalse(app.staticTexts["Recent practice"].exists)
  }

  @MainActor
  func testRealRecordingCompletionCanContinueWithNewWords() {
    let app = practiceApp()
    app.launch()
    app.buttons["cadence.start"].tap()
    for _ in 0..<3 {
      app.buttons["cadence.record"].tap()
      let allow = XCUIApplication(bundleIdentifier: "com.apple.springboard").buttons["Allow"]
      if allow.waitForExistence(timeout: 1) { allow.tap() }
      XCTAssertTrue(app.buttons["cadence.replay"].waitForExistence(timeout: 10))
      app.buttons["cadence.continue"].tap()
    }
    let more = app.buttons["cadence.more"]
    for _ in 0..<5 where !more.isHittable { app.swipeUp() }
    XCTAssertTrue(more.isHittable)
    more.tap()
    XCTAssertTrue(app.buttons["cadence.record"].waitForExistence(timeout: 3))
    XCTAssertFalse(["ball", "boat", "bee"].contains(app.staticTexts["cadence.word"].label))
    XCTAssertFalse(app.buttons["cadence.replay"].exists)
    keepScreenshot("practice-more", app: app)
  }

  @MainActor
  func testLargeTextStillReachesPractice() {
    let app = practiceApp(largeText: true)
    app.launch()
    let start = app.buttons["cadence.start"]
    for _ in 0..<5 where !start.isHittable { app.swipeUp() }
    XCTAssertTrue(start.isHittable)
    start.tap()
    let record = app.buttons["cadence.record"]
    for _ in 0..<5 where !record.isHittable { app.swipeUp() }
    XCTAssertTrue(record.isHittable)
    keepScreenshot("large-text-prompt", app: app)
  }

  @MainActor
  func testMicrophoneDenialHasARecoveryPath() {
    let app = practiceApp()
    app.resetAuthorizationStatus(for: .microphone)
    defer {
      app.terminate()
      app.resetAuthorizationStatus(for: .microphone)
    }
    app.launch()
    app.buttons["cadence.start"].tap()
    app.buttons["cadence.record"].tap()
    let springboard = XCUIApplication(bundleIdentifier: "com.apple.springboard")
    let deny = springboard.buttons.matching(
      NSPredicate(format: "label == %@ OR label == %@", "Don’t Allow", "Don't Allow")
    ).firstMatch
    XCTAssertTrue(deny.waitForExistence(timeout: 5))
    deny.tap()
    XCTAssertTrue(app.buttons["Open Settings"].waitForExistence(timeout: 3))
    let retry = app.buttons["Try microphone again"]
    for _ in 0..<5 where !retry.isHittable { app.swipeUp() }
    XCTAssertTrue(retry.isHittable)
    XCTAssertFalse(app.buttons["cadence.replay"].exists)
    XCTAssertFalse(app.buttons["cadence.stop"].exists)
    keepScreenshot("microphone-denied", app: app)
    app.buttons["cadence.close"].tap()
    XCTAssertTrue(app.buttons["cadence.start"].waitForExistence(timeout: 3))
  }

  @MainActor
  func testBackgroundDiscardsARealRecording() {
    let app = practiceApp()
    app.launch()
    app.buttons["cadence.start"].tap()
    app.buttons["cadence.record"].tap()
    let allow = XCUIApplication(bundleIdentifier: "com.apple.springboard").buttons["Allow"]
    if allow.waitForExistence(timeout: 1) { allow.tap() }
    XCTAssertTrue(app.buttons["cadence.replay"].waitForExistence(timeout: 10))
    XCUIDevice.shared.press(.home)
    app.activate()
    XCTAssertTrue(app.buttons["cadence.record"].waitForExistence(timeout: 3))
    XCTAssertFalse(app.buttons["cadence.replay"].exists)
    app.buttons["cadence.close"].tap()
    XCTAssertTrue(app.buttons["cadence.start"].waitForExistence(timeout: 3))
  }

  @MainActor
  func testChooseAnotherSound() {
    let app = practiceApp()
    app.launch()
    let sound = app.buttons["cadence.sound.sh"]
    for _ in 0..<10 where !sound.isHittable { app.swipeUp() }
    XCTAssertTrue(sound.isHittable)
    sound.tap()
    let libraryStart = app.buttons["cadence.library.start"]
    XCTAssertTrue(libraryStart.waitForExistence(timeout: 3))
    libraryStart.tap()
    XCTAssertTrue(app.buttons["cadence.record"].waitForExistence(timeout: 3))
    XCTAssertEqual(app.staticTexts["cadence.word"].label, "ship")
    keepScreenshot("another-sound", app: app)
    app.buttons["cadence.close"].tap()
    XCTAssertTrue(libraryStart.waitForExistence(timeout: 3))
  }

  @MainActor
  func testSearchStartsAtChosenWordAndEmptySearchIsAccessible() throws {
    let app = practiceApp()
    app.launch()
    app.buttons["cadence.search.open"].tap()
    let field = app.textFields["cadence.search.field"]
    XCTAssertTrue(field.waitForExistence(timeout: 3))
    field.tap()
    field.typeText("shoe\n")
    let result = app.buttons.matching(
      NSPredicate(
        format: "identifier BEGINSWITH %@ AND label BEGINSWITH %@", "cadence.search.result.",
        "shoe, SH sound")
    ).firstMatch
    XCTAssertTrue(result.waitForExistence(timeout: 3))
    result.tap()
    XCTAssertEqual(app.staticTexts["cadence.word"].label, "shoe")
    XCTAssertTrue(app.buttons["cadence.record"].exists)
    keepScreenshot("searched-word", app: app)
    app.buttons["cadence.close"].tap()
    app.buttons["Clear search"].firstMatch.tap()
    field.tap()
    field.typeText("zzzzzz\n")
    XCTAssertTrue(app.staticTexts["cadence.search.empty"].waitForExistence(timeout: 3))
    keepScreenshot("search-empty", app: app)
    try app.performAccessibilityAudit()
  }

  @MainActor
  func testUnavailablePositionOffersAnotherPosition() throws {
    let app = practiceApp()
    app.launch()
    let sound = app.buttons["cadence.sound.h"]
    for _ in 0..<12 where !sound.isHittable { app.swipeUp() }
    XCTAssertTrue(sound.isHittable)
    sound.tap()
    app.buttons["cadence.position.end"].tap()
    XCTAssertTrue(app.staticTexts["cadence.library.empty"].waitForExistence(timeout: 3))
    XCTAssertFalse(app.buttons["cadence.library.start"].exists)
    try app.performAccessibilityAudit()
    app.buttons["cadence.library.change-position"].tap()
    XCTAssertTrue(app.buttons["cadence.library.start"].exists)
    app.buttons["cadence.library.start"].tap()
    XCTAssertEqual(app.staticTexts["cadence.word"].label, "hat")
  }

  @MainActor
  func testLargeTextLibrarySearchReachesLongWord() {
    let app = practiceApp(largeText: true)
    app.launch()
    let open = app.buttons["cadence.search.open"]
    for _ in 0..<6 where !open.isHittable { app.swipeUp() }
    XCTAssertTrue(open.isHittable)
    open.tap()
    let field = app.textFields["cadence.search.field"]
    XCTAssertTrue(field.waitForExistence(timeout: 3))
    field.tap()
    field.typeText("television\n")
    let result = app.buttons.matching(
      NSPredicate(
        format: "identifier BEGINSWITH %@ AND label BEGINSWITH %@", "cadence.search.result.",
        "television, ZH")
    ).firstMatch
    for _ in 0..<6 where !result.isHittable { app.swipeUp() }
    XCTAssertTrue(result.isHittable)
    result.tap()
    XCTAssertEqual(app.staticTexts["cadence.word"].label, "television")
    let record = app.buttons["cadence.record"]
    for _ in 0..<6 where !record.isHittable { app.swipeUp() }
    XCTAssertTrue(record.isHittable)
    keepScreenshot("large-text-library-word", app: app)
  }

  @MainActor
  private func practiceApp(largeText: Bool = false) -> XCUIApplication {
    let app = XCUIApplication()
    // Each launch selects its own size; accessibility launch defaults can persist.
    app.launchArguments = [
      "-UIPreferredContentSizeCategoryName",
      largeText ? "UICTContentSizeCategoryAccessibilityXXXL" : "UICTContentSizeCategoryL",
    ]
    return app
  }

  @MainActor
  private func keepScreenshot(_ name: String, app: XCUIApplication) {
    let attachment = XCTAttachment(screenshot: app.screenshot())
    attachment.name = name
    attachment.lifetime = .keepAlways
    add(attachment)
  }
}
