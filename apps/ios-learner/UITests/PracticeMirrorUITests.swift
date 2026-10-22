import XCTest

/// Isolated generated drivers/PCM only. No system permission, sensor or audio output.
@MainActor
final class PracticeMirrorUITests: XCTestCase {
  func testCompactSampleRecordReplayAndCompletionWithoutAutomaticMirrorRestart() {
    sampleJourney("sample")
  }

  func testLargestTextSampleRecordReplayAndCompletionWithoutAutomaticMirrorRestart() {
    sampleJourney("sampleAX")
  }

  func testCompactPermissionCancelKeepsRecordingAvailable() {
    permissionJourney("pending", largeText: false)
  }

  func testLargestTextPermissionCancelKeepsRecordingAvailable() {
    permissionJourney("pending", largeText: true)
  }

  func testCompactUnavailableKeepsRecordingAvailable() {
    permissionJourney("unavailable", largeText: false)
  }

  func testLargestTextUnavailableKeepsRecordingAvailable() {
    permissionJourney("unavailable", largeText: true)
  }

  func testCompactDeniedKeepsRecordingAvailable() {
    permissionJourney("denied", largeText: false)
  }

  func testLargestTextDeniedKeepsRecordingAvailable() {
    permissionJourney("denied", largeText: true)
  }

  func testCompactFailedCameraCloseRequiresExplicitRetry() {
    failedClose("failedStop")
  }

  func testLargestTextFailedCameraCloseRequiresExplicitRetry() {
    failedClose("failedStopAX")
  }

  func testCompactHeldCameraCloseKeepsScreenUntilExactRelease() {
    heldClose("heldStop")
  }

  func testLargestTextHeldCameraCloseKeepsScreenUntilExactRelease() {
    heldClose("heldStopAX")
  }

  func testCompactCompletedPracticeKeepsFailedCameraRecoveryAboveCompletion() {
    completionRecovery("failedStop")
  }

  func testLargestTextCompletedPracticeKeepsFailedCameraRecoveryAboveCompletion() {
    completionRecovery("failedStopAX")
  }

  private func launch(_ testCase: String) -> XCUIApplication {
    continueAfterFailure = false
    let app = XCUIApplication()
    app.launchEnvironment.removeValue(forKey: "CADENCE_CONTROLLED_UNIT_HOST")
    app.launchEnvironment.removeValue(forKey: "TEST_RUNNER_CADENCE_CONTROLLED_UNIT_HOST")
    app.launchEnvironment.removeValue(forKey: "TEST_RUNNER_CADENCE_CONTROLLED_UI_HOST")
    app.launchEnvironment["CADENCE_CONTROLLED_UI_HOST"] = "1"
    app.launchArguments = [
      "-CadenceMirrorMode", "-CadenceMirrorUITestCase", testCase,
      "-CadenceControlledUIRunID", UUID().uuidString.lowercased(),
    ]
    app.launch()
    XCTAssertTrue(app.staticTexts["mirror-generated.banner"].waitForExistence(timeout: 5))
    XCTAssertFalse(app.staticTexts["mirror-generated.closed"].exists)
    XCTAssertTrue(app.staticTexts["cadence.word"].exists)
    XCTAssertTrue(app.buttons["cadence.record"].isEnabled)
    return app
  }

  private func activate(_ id: String, _ app: XCUIApplication) {
    let button = app.buttons[id]
    XCTAssertTrue(button.waitForExistence(timeout: 5), id)
    scrollTo(button, app)
    XCTAssertTrue(button.isHittable, id)
    XCTAssertTrue(button.isEnabled, id)
    // Preserve the 44 pt minimum while removing AX floating-point subtraction noise.
    let height = (button.frame.height * 1_000_000).rounded() / 1_000_000
    XCTAssertGreaterThanOrEqual(height, 44, id)
    button.tap()
  }

  private func scrollTo(_ target: XCUIElement, _ app: XCUIApplication) {
    let scroll = app.scrollViews.firstMatch
    for _ in 0..<24 {
      let viewport = scroll.frame
      let top = max(viewport.minY, app.staticTexts["mirror-generated.banner"].frame.maxY) + 8
      let bottom = min(viewport.maxY, app.windows.firstMatch.frame.maxY) - 8
      let frame = target.frame
      if target.isHittable, frame.minY >= top, frame.maxY <= bottom { return }
      let visibleHeight = bottom - top
      guard visibleHeight > 0 else { return }
      let above = frame.minY < top
      let distance = above ? top - frame.minY : frame.maxY - bottom
      let travel = min(max(distance, visibleHeight * 0.2), visibleHeight * 0.6)
      let centerY = (top + bottom) / 2
      let startY = centerY + (above ? -travel / 2 : travel / 2)
      let finishY = centerY + (above ? travel / 2 : -travel / 2)
      let origin = scroll.coordinate(withNormalizedOffset: .zero)
      let start = origin.withOffset(CGVector(dx: viewport.width / 2, dy: startY - viewport.minY))
      let finish = origin.withOffset(CGVector(dx: viewport.width / 2, dy: finishY - viewport.minY))
      start.press(forDuration: 0.01, thenDragTo: finish)
    }
  }

  private func show(_ app: XCUIApplication) {
    activate("cadence.mirror.show", app)
    XCTAssertTrue(app.staticTexts["cadence.mirror.sample-label"].waitForExistence(timeout: 5))
    XCTAssertTrue(app.buttons["cadence.mirror.hide"].exists)
  }

  private func sampleJourney(_ testCase: String) {
    let app = launch(testCase)
    show(app)
    activate("cadence.mirror.hide", app)
    XCTAssertTrue(app.buttons["cadence.mirror.show"].waitForExistence(timeout: 5))
    // Record appears before the mirror in the actual practice scroll view.
    app.scrollViews.firstMatch.swipeDown()
    activate("cadence.record", app)
    XCTAssertTrue(app.buttons["cadence.stop"].waitForExistence(timeout: 5))
    show(app)  // Authorized show while recording, never a camera permission prompt.
    app.scrollViews.firstMatch.swipeDown()
    activate("cadence.stop", app)
    activate("cadence.replay", app)
    XCTAssertEqual(app.buttons["cadence.replay"].label, "Stop playback")
    activate("cadence.replay", app)
    XCTAssertEqual(app.buttons["cadence.replay"].label, "Play recording")
    activate("cadence.continue", app)
    XCTAssertTrue(app.staticTexts["cadence.complete"].waitForExistence(timeout: 5))
    XCTAssertFalse(app.staticTexts["cadence.mirror.sample-label"].exists)
    let again = app.buttons["Practice these again"]
    scrollTo(again, app)
    XCTAssertTrue(again.isHittable)
    again.tap()
    XCTAssertTrue(app.buttons["cadence.record"].waitForExistence(timeout: 5))
    XCTAssertFalse(app.staticTexts["cadence.mirror.sample-label"].exists)
    activate("cadence.close", app)
    XCTAssertTrue(app.staticTexts["mirror-generated.closed"].waitForExistence(timeout: 5))
    app.terminate()
  }

  private func permissionJourney(_ state: String, largeText: Bool) {
    let suffix = largeText ? "AX" : ""
    let app = launch(state + suffix)
    activate("cadence.mirror.show", app)
    if state == "pending" {
      XCTAssertTrue(app.buttons["cadence.mirror.cancel"].exists)
      XCTAssertFalse(app.buttons["cadence.record"].isEnabled)
      activate("cadence.mirror.cancel", app)
      XCTAssertTrue(app.buttons["cadence.record"].isEnabled)
    } else {
      XCTAssertTrue(
        app.staticTexts["cadence.mirror.status"].label.contains(
          state == "denied" ? "access is off" : "isn't available"))
    }
    app.scrollViews.firstMatch.swipeDown()
    activate("cadence.record", app)
    activate("cadence.stop", app)
    XCTAssertTrue(app.buttons["cadence.replay"].exists)
    activate("cadence.close", app)
    XCTAssertTrue(app.staticTexts["mirror-generated.closed"].waitForExistence(timeout: 5))
    app.terminate()
  }

  private func failedClose(_ testCase: String) {
    let app = launch(testCase)
    show(app)
    activate("cadence.close", app)
    XCTAssertTrue(app.buttons["cadence.mirror.retry-stop"].waitForExistence(timeout: 5))
    XCTAssertFalse(app.staticTexts["cadence.mirror.status"].label.contains("keep practicing"))
    XCTAssertTrue(app.staticTexts["cadence.close-note"].label.contains("camera hasn't confirmed"))
    XCTAssertFalse(app.buttons["cadence.record"].isEnabled)
    XCTAssertFalse(app.staticTexts["mirror-generated.closed"].exists)
    XCTAssertFalse(app.staticTexts["cadence.mirror.sample-label"].exists)
    activate("cadence.mirror.retry-stop", app)
    XCTAssertTrue(app.staticTexts["mirror-generated.closed"].waitForExistence(timeout: 5))
    app.terminate()
  }

  private func heldClose(_ testCase: String) {
    let app = launch(testCase)
    show(app)
    activate("cadence.close", app)
    XCTAssertTrue(app.staticTexts["cadence.close-note"].waitForExistence(timeout: 5))
    XCTAssertFalse(app.staticTexts["mirror-generated.closed"].exists)
    XCTAssertFalse(app.buttons["cadence.record"].isEnabled)
    XCTAssertFalse(app.staticTexts["cadence.mirror.sample-label"].exists)
    let release = app.buttons["mirror-generated.release-stop"]
    XCTAssertTrue(release.isHittable)
    release.tap()
    XCTAssertTrue(app.staticTexts["mirror-generated.closed"].waitForExistence(timeout: 5))
    app.terminate()
  }

  private func completionRecovery(_ testCase: String) {
    let app = launch(testCase)
    activate("cadence.record", app)
    activate("cadence.stop", app)
    show(app)
    activate("cadence.continue", app)
    XCTAssertTrue(app.staticTexts["cadence.complete"].waitForExistence(timeout: 5))
    XCTAssertTrue(app.buttons["cadence.mirror.retry-stop"].waitForExistence(timeout: 5))
    XCTAssertFalse(app.staticTexts["cadence.mirror.status"].label.contains("keep practicing"))
    XCTAssertFalse(app.staticTexts["cadence.mirror.sample-label"].exists)
    XCTAssertFalse(app.buttons["cadence.mirror.show"].exists)
    activate("cadence.mirror.retry-stop", app)
    let retryGone = XCTNSPredicateExpectation(
      predicate: NSPredicate(format: "exists == false"),
      object: app.buttons["cadence.mirror.retry-stop"])
    XCTAssertEqual(XCTWaiter.wait(for: [retryGone], timeout: 5), .completed)
    XCTAssertFalse(app.buttons["cadence.mirror.retry-stop"].exists)
    XCTAssertTrue(app.staticTexts["cadence.complete"].exists)
    activate("cadence.close", app)
    XCTAssertTrue(app.staticTexts["mirror-generated.closed"].waitForExistence(timeout: 5))
    app.terminate()
  }
}
