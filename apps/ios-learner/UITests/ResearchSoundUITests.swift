import XCTest

/// Real app/view navigation. Record/Stop/Check are tapped only with explicitly
/// labelled injected generated-byte fixtures; normal routes remain sensor-free.
@MainActor
final class ResearchSoundUITests: XCTestCase {
  override func setUp() {
    super.setUp()
    continueAfterFailure = false
  }
  private enum FixtureError: Error { case missingLabel }
  private func launch(fixture: String? = nil, large: Bool = false, sound: Bool = true)
    -> XCUIApplication
  {
    let app = XCUIApplication()
    app.launchArguments = [
      "-AppleLanguages", "(en)", "-AppleLocale", "en_US", "-AppleInterfaceStyle", "Light",
      "-UIPreferredContentSizeCategoryName",
      large ? "UICTContentSizeCategoryAccessibilityXXXL" : "UICTContentSizeCategoryL",
    ]
    if sound { app.launchArguments += ["-CadenceSoundMode"] }
    if let fixture {
      app.launchArguments += ["-CadenceSoundUITestCase", fixture]
      if sound {
        // Generated admission only; ordinary/physical helpers retain their original arguments.
        app.launchEnvironment.removeValue(forKey: "CADENCE_CONTROLLED_UNIT_HOST")
        app.launchEnvironment.removeValue(forKey: "TEST_RUNNER_CADENCE_CONTROLLED_UNIT_HOST")
        app.launchEnvironment.removeValue(forKey: "TEST_RUNNER_CADENCE_CONTROLLED_UI_HOST")
        app.launchEnvironment["CADENCE_CONTROLLED_UI_HOST"] = "1"
        app.launchArguments += ["-CadenceControlledUIRunID", UUID().uuidString.lowercased()]
      }
    }
    app.launch()
    return app
  }
  private func scrollTo(_ element: XCUIElement, _ app: XCUIApplication) {
    for _ in 0..<14 {
      if element.isHittable { return }
      if element.frame.maxY < app.windows.firstMatch.frame.minY + 150 {
        app.scrollViews.firstMatch.swipeDown()
      } else {
        app.scrollViews.firstMatch.swipeUp()
      }
    }
  }
  private func top(_ app: XCUIApplication) {
    for _ in 0..<14 {
      if app.staticTexts["sound-title"].isHittable { return }
      app.scrollViews.firstMatch.swipeDown()
    }
  }
  private func element(_ id: String, _ app: XCUIApplication) -> XCUIElement {
    app.descendants(matching: .any).matching(identifier: id).firstMatch
  }
  private func attach(_ app: XCUIApplication, _ name: String) {
    let image = XCTAttachment(screenshot: app.screenshot())
    image.name = name
    image.lifetime = .keepAlways
    add(image)
    let tree = XCTAttachment(string: app.debugDescription)
    tree.name = name + "-tree"
    tree.lifetime = .keepAlways
    add(tree)
  }
  private func setOptions(_ app: XCUIApplication) {
    let adult = element("sound-adult", app)
    scrollTo(adult, app)
    adult.tap()
    let optIn = element("sound-optin", app)
    scrollTo(optIn, app)
    optIn.tap()
    XCTAssertEqual(adult.value as? String, "On")
    XCTAssertEqual(optIn.value as? String, "On")
    top(app)
  }
  private func generatedTake(_ app: XCUIApplication) throws {
    guard app.staticTexts["sound-ui-test-banner"].waitForExistence(timeout: 5) else {
      XCTFail("Fixture label is required before any capture action.")
      throw FixtureError.missingLabel
    }
    XCTAssertTrue(app.staticTexts["sound-ui-test-banner"].isHittable)
    setOptions(app)
    let record = app.buttons["sound-record"]
    scrollTo(record, app)
    record.tap()
    XCTAssertTrue(app.buttons["sound-stop"].waitForExistence(timeout: 5))
    app.buttons["sound-stop"].tap()
    XCTAssertTrue(app.buttons["sound-check"].waitForExistence(timeout: 5))
  }
  func testActualDefaultOffAboveFoldCloseAndNoFixture() {
    let app = launch()
    XCTAssertTrue(app.staticTexts["sound-state-ready"].waitForExistence(timeout: 5))
    let record = app.buttons["sound-record"]
    XCTAssertTrue(record.isHittable)
    XCTAssertGreaterThanOrEqual(record.frame.height, 56)
    XCTAssertLessThanOrEqual(record.frame.maxY, app.windows.firstMatch.frame.maxY)
    XCTAssertFalse(app.staticTexts["sound-ui-test-banner"].exists)
    XCTAssertFalse(app.buttons["sound-check"].exists)
    attach(app, "sound-normal-default-record-visible")
    let adult = element("sound-adult", app)
    let optIn = element("sound-optin", app)
    scrollTo(adult, app)
    XCTAssertEqual(adult.value as? String, "Off")
    scrollTo(optIn, app)
    XCTAssertEqual(optIn.value as? String, "Off")
    XCTAssertFalse(optIn.isEnabled)
    attach(app, "sound-normal-default-off-setup")
    app.buttons["sound-close"].tap()
    XCTAssertTrue(app.buttons["cadence.start"].waitForExistence(timeout: 5))
  }
  func testActualAboutEntryPreservesOldLabLinks() {
    let app = launch(sound: false)
    let about = app.buttons["About practice and privacy"]
    XCTAssertTrue(about.waitForExistence(timeout: 5))
    about.tap()
    let sound = app.buttons["cadence.sound-preview.open"]
    for _ in 0..<12 {
      if sound.isHittable { break }
      app.scrollViews.firstMatch.swipeUp()
    }
    XCTAssertTrue(sound.isHittable)
    for id in ["cadence.feedback.open", "cadence.lab.open", "cadence.admission-lab.open"] {
      XCTAssertTrue(app.buttons[id].exists, id)
    }
    attach(app, "sound-about-entry-with-old-labs")
    sound.tap()
    XCTAssertTrue(app.staticTexts["sound-state-ready"].waitForExistence(timeout: 5))
    XCTAssertFalse(app.staticTexts["sound-ui-test-banner"].exists)
    attach(app, "sound-normal-about-open")
  }
  func testActualAccessibilityXXXLSetupAndNoAutomaticProcessing() throws {
    let app = launch(large: true)
    XCTAssertTrue(app.staticTexts["sound-state-ready"].waitForExistence(timeout: 5))
    attach(app, "sound-accessibility-xxxl-default")
    for id in ["sound-adult", "sound-optin"] {
      let control = element(id, app)
      scrollTo(control, app)
      XCTAssertTrue(control.isHittable, id)
      XCTAssertGreaterThanOrEqual(control.frame.height, 44)
      attach(app, "sound-accessibility-xxxl-" + id)
      if id == "sound-adult" { control.tap() }
    }
    let optIn = element("sound-optin", app)
    optIn.tap()
    let optedIn = optIn.value as? String
    if optedIn != "On" { capturePracticeFailure(app) }
    XCTAssertEqual(optedIn, "On")
    XCTAssertFalse(app.buttons["sound-check"].exists)
    XCTAssertFalse(app.progressIndicators["sound-checking-progress"].exists)
    XCTAssertFalse(app.staticTexts["sound-limit"].exists)
    XCTAssertFalse(app.staticTexts["sound-ui-test-banner"].exists)
    top(app)
    attach(app, "sound-accessibility-xxxl-selected-ready")
    try app.performAccessibilityAudit()
  }
  func testGeneratedFourModelStatesActualViewAndLimitations() throws {
    for (fixture, state) in [
      ("br", "result-br"), ("bw", "result-bw"), ("other", "result-other"),
      ("inconclusive", "result-no-clear-pick"),
    ] {
      let app = launch(fixture: fixture, large: true)
      try generatedTake(app)
      app.buttons["sound-check"].tap()
      XCTAssertTrue(app.staticTexts["sound-state-" + state].waitForExistence(timeout: 5), state)
      let heading = app.staticTexts["sound-state-" + state]
      scrollTo(heading, app)
      attach(app, "sound-generated-accessibility-xxxl-" + fixture + "-heading")
      let limit = app.staticTexts["sound-limit"]
      scrollTo(limit, app)
      XCTAssertTrue(limit.isHittable)
      XCTAssertTrue(limit.label.contains("isn't validated for children"))
      let checkExists = app.buttons["sound-check"].exists
      if checkExists { capturePracticeFailure(app) }
      XCTAssertFalse(checkExists)
      attach(app, "sound-generated-accessibility-xxxl-" + fixture + "-limit")
      let retake = app.buttons["sound-retake"]
      scrollTo(retake, app)
      XCTAssertTrue(retake.isHittable)
      XCTAssertGreaterThanOrEqual(retake.frame.height, 56)
      attach(app, "sound-generated-accessibility-xxxl-" + fixture + "-actions")
      app.buttons["sound-close"].tap()
      app.terminate()
    }
  }
  func testGeneratedNormalBWTitleLimitationAndActions() throws {
    let app = launch(fixture: "bw")
    try generatedTake(app)
    app.buttons["sound-check"].tap()
    let title = app.staticTexts["sound-state-result-bw"]
    XCTAssertTrue(title.waitForExistence(timeout: 5))
    scrollTo(title, app)
    XCTAssertTrue(app.staticTexts["sound-ui-test-banner"].isHittable)
    attach(app, "sound-generated-normal-bw-heading")
    let limit = app.staticTexts["sound-limit"]
    scrollTo(limit, app)
    XCTAssertTrue(limit.isHittable)
    XCTAssertTrue(limit.label.contains("whole recording"))
    attach(app, "sound-generated-normal-bw-limit")
    let retake = app.buttons["sound-retake"]
    scrollTo(retake, app)
    XCTAssertTrue(retake.isHittable)
    attach(app, "sound-generated-normal-bw-actions")
    app.buttons["sound-close"].tap()
  }
  func testGeneratedServicePauseLocalCleanupAndCancelActualControls() throws {
    for fixture in ["paused", "cleanup", "cancelled"] {
      let app = launch(fixture: fixture, large: true)
      try generatedTake(app)
      if fixture == "cleanup" {
        let retake = app.buttons["sound-retake"]
        scrollTo(retake, app)
        retake.tap()
        XCTAssertTrue(app.staticTexts["sound-state-cleanup"].waitForExistence(timeout: 5))
        XCTAssertFalse(app.buttons["sound-record"].exists)
        XCTAssertFalse(app.buttons["sound-check"].exists)
      } else {
        app.buttons["sound-check"].tap()
        if fixture == "cancelled" {
          let cancel = app.buttons["sound-cancel"]
          XCTAssertTrue(cancel.waitForExistence(timeout: 5))
          scrollTo(cancel, app)
          cancel.tap()
          XCTAssertTrue(app.staticTexts["sound-state-ready-cancelled"].waitForExistence(timeout: 5))
          XCTAssertFalse(app.staticTexts["sound-limit"].exists)
        } else {
          XCTAssertTrue(app.staticTexts["sound-state-paused"].waitForExistence(timeout: 5))
          let checkExists = app.buttons["sound-check"].exists
          if checkExists { capturePracticeFailure(app) }
          XCTAssertFalse(checkExists)
          let replay = app.buttons["sound-replay"]
          scrollTo(replay, app)
          XCTAssertTrue(replay.isHittable)
          let retake = app.buttons["sound-retake"]
          scrollTo(retake, app)
          retake.tap()
          XCTAssertTrue(app.staticTexts["sound-state-paused"].exists)
          XCTAssertTrue(app.buttons["sound-record"].exists)
        }
      }
      let detail = app.staticTexts["sound-detail"]
      scrollTo(detail, app)
      attach(app, "sound-generated-accessibility-xxxl-" + fixture)
      app.buttons["sound-close"].tap()
      app.terminate()
    }
  }
  func testGeneratedPersistentCleanupRemainsReachableAfterCloseAndAboutReopenNormal() throws {
    try verifyGeneratedPersistentCleanupRemainsReachable(large: false)
  }
  func testGeneratedPersistentCleanupRemainsReachableAfterCloseAndAboutReopenAccessibilityXXXL()
    throws
  {
    try verifyGeneratedPersistentCleanupRemainsReachable(large: true)
  }
  private func readRecoveryNotice(_ text: XCUIElement, _ app: XCUIApplication) {
    let copy = element("cadence.cleanup-recovery.scroll", app)
    for _ in 0..<4 {
      if text.isHittable || !copy.exists { return }
      if text.frame.midY < copy.frame.minY {
        copy.swipeDown()
      } else {
        copy.swipeUp()
      }
    }
  }

  /// The About page has long explanatory sections at the largest text size.
  private func scrollToSoundPreview(_ sound: XCUIElement, _ app: XCUIApplication) {
    let scroll = app.scrollViews["cadence.about.scroll"]
    for _ in 0..<14 {
      if sound.isHittable { return }
      let done = app.buttons["Done"]
      let top = max(scroll.frame.minY, done.exists ? done.frame.maxY : scroll.frame.minY)
      if sound.frame.midY < top {
        scroll.swipeDown(velocity: .fast)
      } else {
        scroll.swipeUp(velocity: .fast)
      }
    }
  }

  private func verifyGeneratedPersistentCleanupRemainsReachable(large: Bool) throws {
    let size = large ? "accessibility-xxxl" : "normal"
    let app = launch(fixture: "cleanup", large: large)
    try generatedTake(app)
    let retake = app.buttons["sound-retake"]
    scrollTo(retake, app)
    XCTAssertTrue(retake.isHittable)
    XCTAssertTrue(retake.isEnabled)
    retake.tap()
    XCTAssertTrue(app.staticTexts["sound-state-cleanup"].waitForExistence(timeout: 5))
    XCTAssertFalse(app.buttons["sound-record"].exists)
    XCTAssertFalse(app.buttons["sound-check"].exists)
    attach(app, "sound-generated-persistent-cleanup-" + size + "-local-blocked")

    let close = app.buttons["sound-close"]
    XCTAssertTrue(close.isHittable)
    close.tap()
    let closeNote = app.staticTexts["sound-close-note"]
    XCTAssertTrue(closeNote.waitForExistence(timeout: 5))
    let departureOffered = XCTNSPredicateExpectation(
      predicate: NSPredicate(format: "label CONTAINS %@", "tap Close again"),
      object: closeNote)
    XCTAssertEqual(XCTWaiter.wait(for: [departureOffered], timeout: 5), .completed)
    XCTAssertTrue(closeNote.label.contains("cleanup will remain pending"))
    XCTAssertTrue(app.staticTexts["sound-title"].exists)
    XCTAssertFalse(app.buttons["sound-record"].exists)
    attach(app, "sound-generated-persistent-cleanup-" + size + "-first-close")
    XCTAssertTrue(
      close.isHittable,
      "Close frame: \(close.frame); note: \(closeNote.frame)"
        + "; window: \(app.windows.firstMatch.frame)")
    close.tap()
    XCTAssertTrue(app.buttons["cadence.start"].waitForExistence(timeout: 5))
    XCTAssertFalse(app.staticTexts["sound-title"].exists)

    let notice = element("cadence.cleanup-recovery", app)
    XCTAssertTrue(notice.waitForExistence(timeout: 5))
    XCTAssertTrue(notice.isHittable)
    XCTAssertTrue(app.staticTexts["Recording cleanup pending"].exists)
    let retry = app.buttons["cadence.cleanup-recovery.retry"]
    XCTAssertTrue(retry.waitForExistence(timeout: 5))
    XCTAssertTrue(retry.isEnabled)
    XCTAssertTrue(retry.isHittable)
    XCTAssertEqual(retry.label, "Retry cleanup")
    XCTAssertGreaterThanOrEqual(retry.frame.height, 44)
    XCTAssertGreaterThanOrEqual(retry.frame.width, 44)
    attach(app, "sound-generated-persistent-cleanup-" + size + "-home-recovery")
    retry.tap()
    let failedDetail = app.staticTexts[
      "The temporary practice recording still hasn’t been removed. You can try again."]
    XCTAssertTrue(failedDetail.waitForExistence(timeout: 5))
    XCTAssertTrue(notice.exists)
    readRecoveryNotice(failedDetail, app)
    XCTAssertTrue(failedDetail.isHittable)
    XCTAssertTrue(app.staticTexts["Recording cleanup pending"].exists)
    XCTAssertEqual(retry.label, "Retry cleanup")
    XCTAssertTrue(retry.isEnabled)
    XCTAssertTrue(retry.isHittable)
    attach(app, "sound-generated-persistent-cleanup-" + size + "-retry-still-pending")

    let about = app.buttons["About practice and privacy"]
    XCTAssertTrue(about.waitForExistence(timeout: 5))
    let initialAboutFrame = about.frame
    scrollTo(about, app)
    XCTAssertTrue(
      about.isHittable,
      "About initial: \(initialAboutFrame); current: \(about.frame)"
        + "; scroll: \(app.scrollViews.firstMatch.frame); notice: \(notice.frame)"
        + "; window: \(app.windows.firstMatch.frame)")
    about.tap()
    let sound = app.buttons["cadence.sound-preview.open"]
    XCTAssertTrue(sound.waitForExistence(timeout: 5))
    scrollToSoundPreview(sound, app)
    XCTAssertTrue(sound.isEnabled)
    XCTAssertTrue(sound.isHittable)
    sound.tap()
    XCTAssertTrue(app.staticTexts["sound-state-ready"].waitForExistence(timeout: 5))
    XCTAssertTrue(app.staticTexts["sound-ui-test-banner"].exists)
    XCTAssertFalse(app.buttons["sound-stop"].exists)
    XCTAssertFalse(app.buttons["sound-check"].exists)
    attach(app, "sound-generated-persistent-cleanup-" + size + "-about-reopen-ready")
    // Inspect only: this new session never starts another generated capture.
    app.buttons["sound-close"].tap()
    let done = app.buttons["Done"]
    XCTAssertTrue(done.waitForExistence(timeout: 5))
    XCTAssertTrue(done.isHittable)
    done.tap()
    XCTAssertTrue(app.buttons["cadence.start"].waitForExistence(timeout: 5))
    XCTAssertTrue(notice.waitForExistence(timeout: 5))
    XCTAssertTrue(failedDetail.waitForExistence(timeout: 5))
    XCTAssertTrue(notice.isHittable)
    readRecoveryNotice(failedDetail, app)
    XCTAssertTrue(failedDetail.isHittable)
    XCTAssertTrue(retry.isEnabled)
    XCTAssertTrue(retry.isHittable)
    XCTAssertEqual(retry.label, "Retry cleanup")
    attach(app, "sound-generated-persistent-cleanup-" + size + "-same-pending-home")
    // End this controlled process without fabricating successful file cleanup.
    app.terminate()
  }
}
