import XCTest

/// Isolated generated capturer/player/history only. No system permission, sensor or audio
/// output; playback markers report the generated file requested, never audibility.
@MainActor
final class DirectTryUITests: XCTestCase {
  func testCompactTimedOutCheckRetriesSameSingleTake() {
    timeoutRetryJourney("wordCheckTimeout", twoTakes: false)
  }
  func testLargestTextTimedOutCheckRetriesSameSingleTake() {
    timeoutRetryJourney("wordCheckTimeoutAX", twoTakes: false)
  }
  func testCompactTimedOutCheckRetriesLatestOfTwoTakes() {
    timeoutRetryJourney("wordCheckTimeout", twoTakes: true)
  }
  func testLargestTextTimedOutCheckRetriesLatestOfTwoTakes() {
    timeoutRetryJourney("wordCheckTimeoutAX", twoTakes: true)
  }

  private func timeoutRetryJourney(_ testCase: String, twoTakes: Bool) {
    let app = launch(testCase)
    executionTimeAllowance = 240
    let count = twoTakes ? 2 : 1
    let tag = "generated-timeout-" + testCase + (twoTakes ? "-two" : "-one")
    registerGeneratedTimeoutEvidence(tag, app)
    recordTake(another: false, app)
    if twoTakes { recordTake(another: true, app) }
    expectFiles(made: count, kept: count, requests: count, starts: 0, app)
    expectWordCheck(requests: 0, file: nil, latest: false, cancellations: 0, pending: false, app)
    activate("cadence.word-check", app)
    expectWordCheck(requests: 1, file: count, latest: true, cancellations: 0, pending: true, app)
    releaseGeneratedWordCheck(app)
    let result = app.staticTexts["cadence.word-check-result"]
    waitLabel(result, "Word check took too long. Your recording is still here.")
    captureGeneratedTimeoutText(result, id: "cadence.word-check-result", name: tag + "-timeout", app)
    let retry = app.buttons["cadence.word-check"]
    waitLabel(retry, twoTakes ? "Try word check again on latest try" : "Try word check again")
    revealGeneratedTimeoutControl(retry, id: "cadence.word-check", app)
    captureGeneratedTimeoutState(tag + "-retry-action", app)
    expectWordCheck(requests: 1, file: count, latest: true, cancellations: 0, pending: false, app)
    expectFiles(made: count, kept: count, requests: count, starts: 0, app)
    waitLabel(app.staticTexts["cadence.generated-history"], "Generated history: 0 entries")
    retry.tap()
    expectWordCheck(requests: 2, file: count, latest: true, cancellations: 0, pending: true, app)
    waitLabel(app.staticTexts["cadence.generated-retry-binding"],
      "Generated retry binding: same take yes · new operation yes")
    XCTAssertFalse(app.buttons["cadence.word-check"].exists, "No duplicate check action while pending")
    XCTAssertFalse(app.buttons["cadence.record-another"].isEnabled)
    XCTAssertFalse(app.buttons["cadence.replay"].isEnabled)
    let pending = app.staticTexts["cadence.word-check-status"]
    waitLabel(pending, "Checking words in this try on this device…")
    captureGeneratedTimeoutText(pending, id: "cadence.word-check-status", name: tag + "-pending", app)
    expectWordCheck(requests: 2, file: count, latest: true, cancellations: 0, pending: true, app)
    expectFiles(made: count, kept: count, requests: count, starts: 0, app)
    releaseGeneratedWordCheck(app)
    waitLabel(result, "“ball” matched in this try. Individual sounds aren’t assessed.")
    captureGeneratedTimeoutText(result, id: "cadence.word-check-result", name: tag + "-matched", app)
    XCTAssertFalse(app.buttons["cadence.word-check"].isEnabled)
    if twoTakes {
      XCTAssertFalse(app.staticTexts["cadence.word-check-earlier-result"].exists)
      waitLabel(app.staticTexts["cadence.word-check-earlier-empty"], "No word-check result for this try.")
    }
    expectWordCheck(requests: 2, file: count, latest: true, cancellations: 0, pending: false, app)
    expectFiles(made: count, kept: count, requests: count, starts: 0, app)
    waitLabel(app.staticTexts["cadence.generated-history"], "Generated history: 0 entries")
    close(app, closedFiles: (made: count, kept: 0, requests: count, starts: 0))
  }

  func testCompactSkippedRoundMakesNoMediaOrParticipation() {
    skipJourney("skip", recordMiddle: false)
  }

  func testLargestTextSkippedRoundMakesNoMediaOrParticipation() {
    skipJourney("skipAX", recordMiddle: false)
  }

  func testCompactMixedSkippedRoundCountsOnlyCompletedRecording() {
    skipJourney("skip", recordMiddle: true)
  }

  func testLargestTextMixedSkippedRoundCountsOnlyCompletedRecording() {
    skipJourney("skipAX", recordMiddle: true)
  }

  private func skipJourney(_ testCase: String, recordMiddle: Bool) {
    let app = launch(testCase)
    activate("cadence.skip-word", app)
    waitLabel(app.staticTexts["cadence.word"], "boat")
    expectFiles(made: 0, kept: 0, requests: 0, starts: 0, app)
    waitLabel(app.staticTexts["cadence.generated-history"], "Generated history: 0 entries")
    if recordMiddle {
      recordTake(another: false, app)
      XCTAssertFalse(app.buttons["cadence.skip-word"].exists)
      activate("cadence.continue", app)
    } else {
      activate("cadence.skip-word", app)
    }
    waitLabel(app.staticTexts["cadence.word"], "bee")
    expectFiles(made: recordMiddle ? 1 : 0, kept: 0,
                requests: recordMiddle ? 1 : 0, starts: 0, app)
    waitLabel(app.staticTexts["cadence.generated-history"], "Generated history: 0 entries")
    activate("cadence.skip-word", app)
    let completion = app.staticTexts["cadence.complete"]
    waitLabel(completion, recordMiddle
      ? "You practiced 1 word. Skipped 2 words. Come back whenever you’re ready."
      : "You skipped all 3 words. Nothing was added to recent practice.")
    waitLabel(app.staticTexts["cadence.generated-history"], recordMiddle
      ? "Generated history: 1 entry, b, 1 word" : "Generated history: 0 entries")
    XCTAssertFalse(app.buttons["cadence.history-retry"].exists)
    XCTAssertFalse(app.staticTexts["cadence.history-saved"].exists)
    XCTAssertFalse(app.buttons["cadence.skip-word"].exists)
    scrollTo(completion, app)
    XCTAssertTrue(completion.isHittable)
    let name = recordMiddle ? "skip-mixed-completion" : "skip-all-completion"
    let screenshot = XCTAttachment(screenshot: app.screenshot())
    screenshot.name = name
    screenshot.lifetime = .keepAlways
    add(screenshot)
    let tree = XCTAttachment(string: app.debugDescription)
    tree.name = name + "-accessibility"
    tree.lifetime = .keepAlways
    add(tree)
    close(app, closedFiles: (recordMiddle ? 1 : 0, 0, recordMiddle ? 1 : 0, 0))
    app.terminate()
  }

  func testCompactTwoTriesSwitchExactGeneratedFilesThenCloseRemovesBoth() {
    comparisonAndCloseJourney("twoTry")
  }

  func testLargestTextTwoTriesSwitchExactGeneratedFilesThenCloseRemovesBoth() {
    comparisonAndCloseJourney("twoTryAX")
  }

  func testCompactTwoTriesDeleteBothReturnsToReadyThenClose() {
    deleteBothAndReadyJourney("twoTry")
  }

  func testLargestTextTwoTriesDeleteBothReturnsToReadyThenClose() {
    deleteBothAndReadyJourney("twoTryAX")
  }

  func testCompactTwoTriesNextAndFinishRemoveFilesWithoutRestart() {
    finishJourney("finish")
  }

  func testLargestTextTwoTriesNextAndFinishRemoveFilesWithoutRestart() {
    finishJourney("finishAX")
  }

  func testCompactDeniedReplacementKeepsPriorTakeWithoutNewFile() {
    deniedJourney("denied")
  }

  func testLargestTextDeniedReplacementKeepsPriorTakeWithoutNewFile() {
    deniedJourney("deniedAX")
  }

  func testCompactFailedReplacementStartKeepsPriorTakeAfterCleanup() {
    failedStartJourney("failedStart")
  }

  func testLargestTextFailedReplacementStartKeepsPriorTakeAfterCleanup() {
    failedStartJourney("failedStartAX")
  }

  func testCompactFailedHistorySaveRetriesSameMetadataOnce() {
    saveFailureJourney("saveFailure")
  }

  func testLargestTextFailedHistorySaveRetriesSameMetadataOnce() {
    saveFailureJourney("saveFailureAX")
  }

  private let bannerIDs = [
    "cadence.generated-banner", "cadence.generated-files", "cadence.generated-playback-file",
    "cadence.generated-history", "cadence.generated-word-check",
  ]

  private func launch(_ testCase: String) -> XCUIApplication {
    continueAfterFailure = false
    let app = XCUIApplication()
    app.launchEnvironment.removeValue(forKey: "CADENCE_CONTROLLED_UNIT_HOST")
    app.launchEnvironment.removeValue(forKey: "TEST_RUNNER_CADENCE_CONTROLLED_UNIT_HOST")
    app.launchEnvironment.removeValue(forKey: "TEST_RUNNER_CADENCE_CONTROLLED_UI_HOST")
    app.launchEnvironment["CADENCE_CONTROLLED_UI_HOST"] = "1"
    app.launchArguments = [
      "-CadenceDirectTryMode", "-CadenceDirectTryUITestCase", testCase,
      "-CadenceControlledUIRunID", UUID().uuidString.lowercased(),
    ]
    app.launch()
    XCTAssertTrue(existsOrWait(app.staticTexts["cadence.generated-banner"]))
    XCTAssertFalse(app.staticTexts["cadence.generated-direct-closed"].exists)
    XCTAssertEqual(app.staticTexts["cadence.word"].label, "ball")
    XCTAssertTrue(app.buttons["cadence.record"].isEnabled)
    expectFiles(made: 0, kept: 0, requests: 0, starts: 0, app)
    expectPlayback(nil, app)
    return app
  }

  private func activate(_ id: String, _ app: XCUIApplication) {
    let button = app.buttons[id]
    XCTAssertTrue(existsOrWait(button), id)
    scrollTo(button, app)
    XCTAssertTrue(button.isHittable, id)
    XCTAssertTrue(button.isEnabled, id)
    // AX subtraction can report a 44 pt row as 43.99999999999997. Normalize only
    // floating-point noise; the required 44 pt hit area remains unchanged.
    let height = (button.frame.height * 1_000_000).rounded() / 1_000_000
    XCTAssertGreaterThanOrEqual(height, 44, id)
    button.tap()
  }

  private func bannerBottom(_ app: XCUIApplication) -> CGFloat {
    // Word fixtures end their fixed inset with this button; save-failure is a separate mode.
    // Its frame is read fresh for each scroll. All other fixtures keep the full scan below.
    let release = app.buttons["cadence.generated-release-word-check"]
    if release.exists { return release.frame.maxY }
    var bottom = app.staticTexts["cadence.generated-banner"].frame.maxY
    for id in bannerIDs where app.staticTexts[id].exists {
      bottom = max(bottom, app.staticTexts[id].frame.maxY)
    }
    for id in ["cadence.generated-restore-save", "cadence.generated-release-word-check"] {
      let button = app.buttons[id]
      if button.exists { bottom = max(bottom, button.frame.maxY) }
    }
    return bottom
  }

  private func scrollTo(_ target: XCUIElement, _ app: XCUIApplication) {
    let scroll = app.scrollViews.firstMatch
    // The generated host's inset and viewport stay fixed during this one scroll action.
    // Read their bounds once; the target's frame and hittability remain fresh on every drag.
    let viewport = scroll.frame
    let top = max(viewport.minY, bannerBottom(app)) + 8
    let bottom = min(viewport.maxY, app.windows.firstMatch.frame.maxY) - 8
    let visibleHeight = bottom - top
    guard visibleHeight > 0 else { return }
    for _ in 0..<24 {
      let frame = target.frame
      // Dynamic Type targets can be taller than the viewport. Align their leading edge;
      // demanding both edges be visible would alternate drags without a possible fit.
      // Full-label and any explicit frame assertions in the journeys remain unchanged.
      let oversizedTarget = frame.height > visibleHeight
      if frame.minY >= top,
        oversizedTarget ? frame.minY <= top + visibleHeight * 0.2 : frame.maxY <= bottom,
        target.isHittable
      {
        return
      }
      // Near-fit targets have a narrow containment interval. Aim at its midpoint
      // without a minimum step that could repeatedly jump across the whole interval.
      let desiredTop = oversizedTarget ? top : top + (visibleHeight - frame.height) / 2
      let above = frame.minY < desiredTop
      let distance = abs(frame.minY - desiredTop)
      let travel =
        oversizedTarget
        ? min(max(distance, visibleHeight * 0.2), visibleHeight * 0.6)
        : min(distance, visibleHeight * 0.6)
      // At the desired position, an unhittable target stays unproved; do not tap it.
      if travel == 0 { continue }
      let centerY = (top + bottom) / 2
      let startY = centerY + (above ? -travel / 2 : travel / 2)
      let finishY = centerY + (above ? travel / 2 : -travel / 2)
      let origin = scroll.coordinate(withNormalizedOffset: .zero)
      let start = origin.withOffset(CGVector(dx: viewport.width / 2, dy: startY - viewport.minY))
      let finish = origin.withOffset(CGVector(dx: viewport.width / 2, dy: finishY - viewport.minY))
      // Use the same controlled positioning gesture as the guided largest-text helper.
      start.press(
        forDuration: 0.01, thenDragTo: finish, withVelocity: .slow, thenHoldForDuration: 0.2)
    }
  }

  // Already-satisfied generated conditions need no polling interval. Pending conditions
  // still use the original five-second XCTest wait and the caller’s original assertion.
  private func existsOrWait(_ element: XCUIElement) -> Bool {
    element.exists || element.waitForExistence(timeout: 5)
  }

  private func waitLabel(
    _ element: XCUIElement, _ expected: String, file: StaticString = #filePath,
    line: UInt = #line
  ) {
    let match = XCTNSPredicateExpectation(
      predicate: NSPredicate(format: "label == %@", expected), object: element)
    let result: XCTWaiter.Result =
      element.exists && element.label == expected
      ? .completed : XCTWaiter.wait(for: [match], timeout: 5)
    XCTAssertEqual(
      result, .completed,
      "\(element.exists ? element.label : "missing") != \(expected)", file: file, line: line)
  }

  private func waitGone(_ element: XCUIElement, file: StaticString = #filePath, line: UInt = #line)
  {
    let gone = XCTNSPredicateExpectation(
      predicate: NSPredicate(format: "exists == false"), object: element)
    let result: XCTWaiter.Result =
      !element.exists ? .completed : XCTWaiter.wait(for: [gone], timeout: 5)
    XCTAssertEqual(result, .completed, file: file, line: line)
  }

  private func expectFiles(
    made: Int, kept: Int, requests: Int, starts: Int, _ app: XCUIApplication,
    file: StaticString = #filePath, line: UInt = #line
  ) {
    waitLabel(
      app.staticTexts["cadence.generated-files"],
      "Generated files: made \(made), kept \(kept) · microphone requests \(requests)"
        + " · playback starts \(starts)", file: file, line: line)
  }

  /// `index` is the 1-based order of the capturer's returned URL the runtime is playing.
  private func expectPlayback(
    _ index: Int?, _ app: XCUIApplication, file: StaticString = #filePath, line: UInt = #line
  ) {
    waitLabel(
      app.staticTexts["cadence.generated-playback-file"],
      index.map { "Generated playback file \($0)" } ?? "Generated playback: none",
      file: file, line: line)
  }

  private func seconds(_ duration: Double) -> String { String(format: "%.1f seconds", duration) }

  private func recordTake(another: Bool, _ app: XCUIApplication) {
    activate(another ? "cadence.record-another" : "cadence.record", app)
    activate("cadence.stop", app)
    XCTAssertTrue(existsOrWait(app.buttons["cadence.replay"]))
  }

  /// `closedFiles` is the exact (made, kept, requests, starts) read from the host after the
  /// cover's binding is false; the in-cover banner is gone by then.
  private func close(
    _ app: XCUIApplication, closedFiles: (made: Int, kept: Int, requests: Int, starts: Int)? = nil
  ) {
    let closedFilesText = app.staticTexts["cadence.generated-closed-files"]
    XCTAssertFalse(app.staticTexts["cadence.generated-direct-closed"].exists)
    XCTAssertFalse(closedFilesText.exists)
    activate("cadence.close", app)
    XCTAssertTrue(existsOrWait(app.staticTexts["cadence.generated-direct-closed"]))
    if let files = closedFiles {
      XCTAssertTrue(existsOrWait(closedFilesText))
      waitLabel(
        closedFilesText,
        "Generated files: made \(files.made), kept \(files.kept) · microphone requests"
          + " \(files.requests) · playback starts \(files.starts)")
    }
    app.terminate()
  }

  /// Public Record/Stop, then Record another/Stop: two distinct kept files, nothing played.
  private func recordTwoTries(_ app: XCUIApplication) -> (earlier: XCUIElement, latest: XCUIElement)
  {
    recordTake(another: false, app)
    XCTAssertEqual(app.buttons["cadence.replay"].label, "Play recording")
    XCTAssertEqual(app.buttons["cadence.replay"].value as? String, seconds(0.2))
    expectFiles(made: 1, kept: 1, requests: 1, starts: 0, app)
    recordTake(another: true, app)
    let earlier = app.buttons["cadence.replay-earlier"]
    let latest = app.buttons["cadence.replay"]
    XCTAssertTrue(existsOrWait(earlier))
    XCTAssertEqual(earlier.label, "Play earlier try")
    XCTAssertEqual(earlier.value as? String, seconds(0.2))
    XCTAssertEqual(latest.label, "Play latest try")
    XCTAssertEqual(latest.value as? String, seconds(0.35))
    XCTAssertEqual(app.staticTexts["cadence.word"].label, "ball")
    // Two distinct owned files, no playback started by either stop.
    expectFiles(made: 2, kept: 2, requests: 2, starts: 0, app)
    expectPlayback(nil, app)
    return (earlier, latest)
  }

  private func comparisonAndCloseJourney(_ testCase: String) {
    let app = launch(testCase)
    let (earlier, latest) = recordTwoTries(app)
    if ProcessInfo.processInfo.environment["CADENCE_TOUR_DIR"] != nil {
      let size = testCase.hasSuffix("AX") ? "largest" : "normal"
      for id in ["cadence.replay-earlier", "cadence.replay", "cadence.record-another"] {
        let target = app.buttons[id]
        scrollTo(target, app)
        XCTAssertTrue(target.isHittable, id)
        capturePracticeTour("ordinary-review-" + size + "-" + id, app)
      }
    }
    activate("cadence.replay-earlier", app)
    expectPlayback(1, app)
    waitLabel(earlier, "Stop earlier try")
    // Explicit direct switch: the runtime's next playing operation is the second file.
    activate("cadence.replay", app)
    expectPlayback(2, app)
    waitLabel(latest, "Stop latest try")
    waitLabel(earlier, "Play earlier try")
    activate("cadence.replay", app)
    expectPlayback(nil, app)
    waitLabel(latest, "Play latest try")
    // Both tries stay for comparison after the stop, unchanged.
    XCTAssertEqual(earlier.label, "Play earlier try")
    XCTAssertEqual(earlier.value as? String, seconds(0.2))
    XCTAssertEqual(latest.value as? String, seconds(0.35))
    XCTAssertEqual(app.staticTexts["cadence.word"].label, "ball")
    expectFiles(made: 2, kept: 2, requests: 2, starts: 2, app)
    // Close itself removes both exact files.
    close(app, closedFiles: (made: 2, kept: 0, requests: 2, starts: 2))
  }

  private func deleteBothAndReadyJourney(_ testCase: String) {
    let app = launch(testCase)
    _ = recordTwoTries(app)
    activate("cadence.retry", app)
    XCTAssertTrue(app.buttons["cadence.record"].waitForExistence(timeout: 5))
    XCTAssertTrue(app.buttons["cadence.record"].isEnabled)
    XCTAssertFalse(app.buttons["cadence.stop"].exists)
    XCTAssertFalse(app.buttons["cadence.replay"].exists)
    XCTAssertFalse(app.buttons["cadence.replay-earlier"].exists)
    XCTAssertEqual(app.staticTexts["cadence.word"].label, "ball")
    // Both removed with no playback, no new capture and no extra request.
    expectFiles(made: 2, kept: 0, requests: 2, starts: 0, app)
    expectPlayback(nil, app)
    close(app, closedFiles: (made: 2, kept: 0, requests: 2, starts: 0))
  }

  private func finishJourney(_ testCase: String) {
    let app = launch(testCase)
    recordTake(another: false, app)
    recordTake(another: true, app)
    expectFiles(made: 2, kept: 2, requests: 2, starts: 0, app)
    XCTAssertTrue(app.buttons["cadence.continue"].label.hasPrefix("Next word"))
    activate("cadence.continue", app)
    waitLabel(app.staticTexts["cadence.word"], "boat")
    // Both takes removed; the next word waits for an explicit Record.
    expectFiles(made: 2, kept: 0, requests: 2, starts: 0, app)
    XCTAssertTrue(app.buttons["cadence.record"].waitForExistence(timeout: 5))
    XCTAssertFalse(app.buttons["cadence.stop"].exists)
    XCTAssertFalse(app.buttons["cadence.replay"].exists)
    recordTake(another: false, app)
    XCTAssertEqual(app.buttons["cadence.replay"].value as? String, seconds(0.5))
    expectFiles(made: 3, kept: 1, requests: 3, starts: 0, app)
    XCTAssertTrue(app.buttons["cadence.continue"].label.hasPrefix("Finish practice"))
    activate("cadence.continue", app)
    XCTAssertTrue(app.staticTexts["cadence.complete"].waitForExistence(timeout: 5))
    expectFiles(made: 3, kept: 0, requests: 3, starts: 0, app)
    expectPlayback(nil, app)
    XCTAssertFalse(app.buttons["cadence.record"].exists)
    XCTAssertFalse(app.buttons["cadence.stop"].exists)
    XCTAssertFalse(app.staticTexts["cadence.history-error"].exists)
    if ProcessInfo.processInfo.environment["CADENCE_TOUR_DIR"] != nil {
      let size = testCase.hasSuffix("AX") ? "largest" : "normal"
      let heading = app.staticTexts["Practice complete."]
      scrollTo(heading, app)
      XCTAssertTrue(heading.isHittable)
      capturePracticeTour("ordinary-completion-heading-" + size, app)
      let completion = app.staticTexts["cadence.complete"]
      scrollTo(completion, app)
      XCTAssertTrue(completion.isHittable)
      capturePracticeTour("ordinary-completion-" + size, app)
      scrollTo(app.buttons["cadence.more"], app)
      XCTAssertTrue(app.buttons["cadence.more"].isHittable)
      capturePracticeTour("ordinary-completion-actions-" + size, app)
    }
    close(app)
  }

  private func deniedJourney(_ testCase: String) {
    let app = launch(testCase)
    recordTake(another: false, app)
    expectFiles(made: 1, kept: 1, requests: 1, starts: 0, app)
    activate("cadence.record-another", app)
    XCTAssertTrue(app.buttons["cadence.back-to-review"].waitForExistence(timeout: 5))
    // Present for the learner, never tapped: no system Settings in this check.
    XCTAssertTrue(app.buttons["Open Settings"].exists)
    XCTAssertFalse(app.buttons["cadence.replay"].exists)
    // The denied grant allocated no file; the prior take stays owned.
    expectFiles(made: 1, kept: 1, requests: 2, starts: 0, app)
    activate("cadence.back-to-review", app)
    let replay = app.buttons["cadence.replay"]
    XCTAssertTrue(replay.waitForExistence(timeout: 5))
    XCTAssertEqual(replay.label, "Play recording")
    XCTAssertEqual(replay.value as? String, seconds(0.2))
    XCTAssertEqual(app.staticTexts["cadence.word"].label, "ball")
    expectPlayback(nil, app)
    activate("cadence.replay", app)
    expectPlayback(1, app)
    activate("cadence.replay", app)
    expectPlayback(nil, app)
    expectFiles(made: 1, kept: 1, requests: 2, starts: 1, app)
    close(app)
  }

  private func failedStartJourney(_ testCase: String) {
    let app = launch(testCase)
    recordTake(another: false, app)
    activate("cadence.record-another", app)
    XCTAssertTrue(app.buttons["cadence.back-to-review"].waitForExistence(timeout: 5))
    XCTAssertFalse(app.buttons["cadence.stop"].exists)
    // The failed start's own partial file was cancelled; only the prior take is kept.
    expectFiles(made: 2, kept: 1, requests: 2, starts: 0, app)
    activate("cadence.back-to-review", app)
    let replay = app.buttons["cadence.replay"]
    XCTAssertTrue(replay.waitForExistence(timeout: 5))
    XCTAssertEqual(replay.value as? String, seconds(0.2))
    XCTAssertEqual(app.staticTexts["cadence.word"].label, "ball")
    expectPlayback(nil, app)
    activate("cadence.replay", app)
    expectPlayback(1, app)
    activate("cadence.replay", app)
    expectPlayback(nil, app)
    waitLabel(replay, "Play recording")
    activate("cadence.retry", app)
    XCTAssertTrue(app.buttons["cadence.record"].waitForExistence(timeout: 5))
    expectFiles(made: 2, kept: 0, requests: 2, starts: 1, app)
    close(app)
  }

  private func saveFailureJourney(_ testCase: String) {
    let app = launch(testCase)
    let history = app.staticTexts["cadence.generated-history"]
    waitLabel(history, "Generated history: 0 entries")
    recordTake(another: false, app)
    XCTAssertTrue(app.buttons["cadence.continue"].label.hasPrefix("Finish practice"))
    activate("cadence.continue", app)
    XCTAssertTrue(app.staticTexts["cadence.complete"].waitForExistence(timeout: 5))
    XCTAssertTrue(app.staticTexts["cadence.history-error"].waitForExistence(timeout: 5))
    expectFiles(made: 1, kept: 0, requests: 1, starts: 0, app)
    waitLabel(history, "Generated history: 0 entries")
    XCTAssertTrue(app.buttons["cadence.history-retry"].exists)
    XCTAssertTrue(app.buttons["cadence.more"].exists)
    XCTAssertTrue(app.buttons["Explore more sounds"].exists)
    XCTAssertTrue(app.buttons["cadence.close"].isEnabled)
    // Fixed generated setup action, outside product controls: removes only the owned obstacle.
    let restore = app.buttons["cadence.generated-restore-save"]
    XCTAssertTrue(restore.isHittable)
    XCTAssertTrue(restore.isEnabled)
    XCTAssertGreaterThanOrEqual(restore.frame.height, 44)
    restore.tap()
    let restored = XCTNSPredicateExpectation(
      predicate: NSPredicate(format: "enabled == false"), object: restore)
    XCTAssertEqual(XCTWaiter.wait(for: [restored], timeout: 5), .completed)
    waitLabel(history, "Generated history: 0 entries")
    activate("cadence.history-retry", app)
    XCTAssertTrue(app.staticTexts["cadence.history-saved"].waitForExistence(timeout: 5))
    waitGone(app.staticTexts["cadence.history-error"])
    waitGone(app.buttons["cadence.history-retry"])
    waitLabel(history, "Generated history: 1 entry, b, 1 word")
    // Metadata only: no recapture, file or playback change.
    expectFiles(made: 1, kept: 0, requests: 1, starts: 0, app)
    XCTAssertTrue(app.buttons["cadence.more"].exists)
    XCTAssertTrue(app.buttons["Explore more sounds"].exists)
    close(app)
  }
}

/// Append after the original `DirectTryUITests` class. Same file, so the class's private
/// helpers are reachable; existing cases and admission are reused unchanged. Explicit `@objc`
/// keeps the extension's tests visible to XCTest discovery.
extension DirectTryUITests {
  @objc func testCompactListeningFocusFollowsOneThenTwoTries() {
    listeningFocusTwoTryJourney("twoTry")
  }

  @objc func testLargestTextListeningFocusFollowsOneThenTwoTries() {
    listeningFocusTwoTryJourney("twoTryAX")
  }

  @objc func testCompactListeningFocusFollowsEachWordAndIsGoneAfterFinish() {
    listeningFocusFinishJourney("finish")
  }

  @objc func testLargestTextListeningFocusFollowsEachWordAndIsGoneAfterFinish() {
    listeningFocusFinishJourney("finishAX")
  }

  private var listeningFocusID: String { "cadence.listening-focus" }

  private func singleFocus(_ word: String) -> String {
    "Play your try. Listen for /b/ at the start of “\(word)”."
  }

  private func expectListeningFocus(
    _ expected: String, _ app: XCUIApplication, file: StaticString = #filePath,
    line: UInt = #line
  ) {
    let focus = app.staticTexts[listeningFocusID]
    XCTAssertTrue(focus.waitForExistence(timeout: 5), file: file, line: line)
    waitLabel(focus, expected, file: file, line: line)
    scrollTo(focus, app)
    // Wraps fully inside the viewport, below the generated banner.
    let viewport = app.scrollViews.firstMatch.frame
    XCTAssertTrue(focus.isHittable, file: file, line: line)
    XCTAssertGreaterThanOrEqual(
      focus.frame.minY, max(viewport.minY, bannerBottom(app)), file: file, line: line)
    XCTAssertLessThanOrEqual(
      focus.frame.maxY, min(viewport.maxY, app.windows.firstMatch.frame.maxY), file: file,
      line: line)
    XCTAssertFalse(app.buttons[listeningFocusID].exists, file: file, line: line)
    let firstReplay = app.buttons["cadence.replay-earlier"].exists
      ? app.buttons["cadence.replay-earlier"] : app.buttons["cadence.replay"]
    XCTAssertTrue(firstReplay.exists, file: file, line: line)
    // Read both frames after the same scroll; oversized combined content need not all fit.
    let focusFrame = focus.frame
    let replayFrame = firstReplay.frame
    XCTAssertLessThanOrEqual(focusFrame.maxY, replayFrame.minY, file: file, line: line)
    let screenshot = XCTAttachment(screenshot: app.screenshot())
    screenshot.name = "listening-focus-before-replay-" + expected
    screenshot.lifetime = .keepAlways
    add(screenshot)
    let ax = XCTAttachment(string: focus.label)
    ax.name = "listening-focus-AX-" + expected
    ax.lifetime = .keepAlways
    add(ax)
  }

  private func listeningFocusTwoTryJourney(_ testCase: String) {
    let app = launch(testCase)
    let focus = app.staticTexts[listeningFocusID]
    XCTAssertFalse(focus.exists)
    activate("cadence.record", app)
    XCTAssertTrue(app.buttons["cadence.stop"].waitForExistence(timeout: 5))
    XCTAssertFalse(focus.exists)
    activate("cadence.stop", app)
    XCTAssertTrue(app.buttons["cadence.replay"].waitForExistence(timeout: 5))
    expectListeningFocus(singleFocus("ball"), app)
    expectFiles(made: 1, kept: 1, requests: 1, starts: 0, app)
    activate("cadence.record-another", app)
    XCTAssertTrue(app.buttons["cadence.stop"].waitForExistence(timeout: 5))
    XCTAssertFalse(focus.exists)
    activate("cadence.stop", app)
    XCTAssertTrue(app.buttons["cadence.replay-earlier"].waitForExistence(timeout: 5))
    expectListeningFocus(
      "Play the earlier try, then the latest. Listen for /b/ at the start of “ball”.", app)
    // Guidance only: nothing played or recorded by showing it.
    expectFiles(made: 2, kept: 2, requests: 2, starts: 0, app)
    expectPlayback(nil, app)
    close(app, closedFiles: (made: 2, kept: 0, requests: 2, starts: 0))
  }

  private func listeningFocusFinishJourney(_ testCase: String) {
    let app = launch(testCase)
    let focus = app.staticTexts[listeningFocusID]
    recordTake(another: false, app)
    expectListeningFocus(singleFocus("ball"), app)
    activate("cadence.continue", app)
    waitLabel(app.staticTexts["cadence.word"], "boat")
    XCTAssertTrue(app.buttons["cadence.record"].waitForExistence(timeout: 5))
    XCTAssertFalse(focus.exists)
    // Continue removed the ball take before boat is ready.
    expectFiles(made: 1, kept: 0, requests: 1, starts: 0, app)
    recordTake(another: false, app)
    expectListeningFocus(singleFocus("boat"), app)
    XCTAssertTrue(app.buttons["cadence.continue"].label.hasPrefix("Finish practice"))
    activate("cadence.continue", app)
    XCTAssertTrue(app.staticTexts["cadence.complete"].waitForExistence(timeout: 5))
    XCTAssertFalse(focus.exists)
    expectFiles(made: 2, kept: 0, requests: 2, starts: 0, app)
    expectPlayback(nil, app)
    close(app)
  }
}

/// Explicit native recognition UI exercised only through a held, generated protocol fake.
/// Passing these journeys cannot establish Apple recognition quality or physical audio behavior.
extension DirectTryUITests {
  @objc func testCompactWordCheckUsesLatestTryOnlyAndRetakeClearsObservation() {
    wordCheckLatestJourney("wordCheck")
  }

  @objc func testLargestTextWordCheckUsesLatestTryOnlyAndRetakeClearsObservation() {
    wordCheckLatestJourney("wordCheckAX")
  }

  @objc func testCompactWordCheckCancelAndCloseWaitForGeneratedCleanupReceipt() {
    wordCheckCancelJourney("wordCheckCancel")
  }

  @objc func testLargestTextWordCheckCancelAndCloseWaitForGeneratedCleanupReceipt() {
    wordCheckCancelJourney("wordCheckCancelAX")
  }

  @objc func testCompactUnavailableWordCheckKeepsReplayRetakeAndParticipationFinish() {
    wordCheckUnavailableJourney("wordCheckUnavailable")
  }

  @objc func testLargestTextUnavailableWordCheckKeepsReplayRetakeAndParticipationFinish() {
    wordCheckUnavailableJourney("wordCheckUnavailableAX")
  }

  private func expectWordCheck(
    requests: Int, file: Int?, latest: Bool, cancellations: Int, pending: Bool,
    _ app: XCUIApplication
  ) {
    waitLabel(
      app.staticTexts["cadence.generated-word-check"],
      "Generated word checks: \(requests) · file \(file.map(String.init) ?? "none")"
        + " · latest \(latest ? "yes" : "no") · cancellations \(cancellations)"
        + " · pending \(pending ? "yes" : "no")")
  }

  private func releaseGeneratedWordCheck(_ app: XCUIApplication) {
    // Fixed fixture action outside the product scroll view; never a model or device call.
    let release = app.buttons["cadence.generated-release-word-check"]
    XCTAssertTrue(existsOrWait(release))
    XCTAssertTrue(release.isHittable)
    XCTAssertTrue(release.isEnabled)
    XCTAssertGreaterThanOrEqual(release.frame.height, 44)
    release.tap()
  }

  func testCompactRetainedWordChecksStayWithTheirRecordings() {
    retainedWordChecksJourney("wordCheckCompare")
  }

  func testLargestTextRetainedWordChecksStayWithTheirRecordings() {
    retainedWordChecksJourney("wordCheckCompareAX")
  }

  private func retainedWordChecksJourney(_ testCase: String) {
    let app = launch(testCase)
    let latest = app.staticTexts["cadence.word-check-result"]
    let earlier = app.staticTexts["cadence.word-check-earlier-result"]
    let empty = app.staticTexts["cadence.word-check-empty"]
    let matched = "“ball” matched in this try. Individual sounds aren’t assessed."
    let uncertain = "No clear match for “ball” in this try. Individual sounds aren’t assessed."
    recordTake(another: false, app)
    waitLabel(empty, "No word-check result for this try.")
    activate("cadence.word-check", app)
    expectWordCheck(requests: 1, file: 1, latest: true, cancellations: 0, pending: true, app)
    releaseGeneratedWordCheck(app)
    waitLabel(latest, matched)
    recordTake(another: true, app)
    waitGone(latest)
    waitLabel(earlier, matched)
    waitLabel(empty, "No word-check result for this try.")
    expectWordCheck(requests: 1, file: 1, latest: false, cancellations: 0, pending: false, app)
    activate("cadence.word-check", app)
    expectWordCheck(requests: 2, file: 2, latest: true, cancellations: 0, pending: true, app)
    XCTAssertFalse(earlier.exists, "Historical copy is suppressed while another check borrows audio")
    releaseGeneratedWordCheck(app)
    waitLabel(earlier, matched)
    waitLabel(latest, uncertain)
    for (id, file) in [("cadence.replay-earlier", 1), ("cadence.replay", 2)] {
      activate(id, app)
      expectPlayback(file, app)
      activate(id, app)
      expectPlayback(nil, app)
    }
    expectWordCheck(requests: 2, file: 2, latest: true, cancellations: 0, pending: false, app)
    for (id, label) in [("cadence.word-check-earlier-result", matched),
                        ("cadence.word-check-result", uncertain)] {
      let result = app.staticTexts[id]
      waitLabel(result, label)
      scrollTo(result, app)
      XCTAssertTrue(result.isHittable)
      XCTAssertGreaterThan(result.frame.width, 0)
      let captureName = testCase + "-" + id
      let shot = XCTAttachment(screenshot: app.screenshot())
      shot.name = captureName
      shot.lifetime = .keepAlways
      add(shot)
      let tree = XCTAttachment(string: app.debugDescription)
      tree.name = captureName + "-accessibility"
      tree.lifetime = .keepAlways
      add(tree)
    }
    recordTake(another: true, app)
    waitGone(latest)
    waitLabel(earlier, uncertain)
    waitLabel(empty, "No word-check result for this try.")
    expectFiles(made: 3, kept: 2, requests: 3, starts: 2, app)
    expectWordCheck(requests: 2, file: 2, latest: false, cancellations: 0, pending: false, app)
    close(app, closedFiles: (made: 3, kept: 0, requests: 3, starts: 2))
  }

  private func wordCheckLatestJourney(_ testCase: String) {
    let app = launch(testCase)
    expectWordCheck(requests: 0, file: nil, latest: false, cancellations: 0, pending: false, app)
    _ = recordTwoTries(app)
    // Neither Record, Stop nor constructing the generated host requests recognition.
    expectWordCheck(requests: 0, file: nil, latest: false, cancellations: 0, pending: false, app)
    let check = app.buttons["cadence.word-check"]
    XCTAssertEqual(check.label, "Check words in latest try")
    XCTAssertFalse(app.staticTexts["cadence.word-check-result"].exists)
    activate("cadence.word-check", app)
    expectWordCheck(requests: 1, file: 2, latest: true, cancellations: 0, pending: true, app)
    waitLabel(
      app.staticTexts["cadence.word-check-status"], "Checking words in this try on this device…")
    XCTAssertFalse(app.buttons["cadence.replay"].isEnabled)
    XCTAssertFalse(app.buttons["cadence.replay-earlier"].isEnabled)
    XCTAssertFalse(app.buttons["cadence.record-another"].isEnabled)
    XCTAssertFalse(app.buttons["cadence.continue"].isEnabled)
    expectFiles(made: 2, kept: 2, requests: 2, starts: 0, app)
    releaseGeneratedWordCheck(app)
    let result = app.staticTexts["cadence.word-check-result"]
    XCTAssertTrue(existsOrWait(result))
    waitLabel(
      result,
      "“ball” matched in this try. Individual sounds aren’t assessed."
    )
    scrollTo(result, app)
    XCTAssertTrue(result.isHittable)
    expectWordCheck(requests: 1, file: 2, latest: true, cancellations: 0, pending: false, app)
    captureReview(testCase, app)
    activate("cadence.replay", app)
    expectPlayback(2, app)
    activate("cadence.replay", app)
    expectPlayback(nil, app)
    expectWordCheck(requests: 1, file: 2, latest: true, cancellations: 0, pending: false, app)
    recordTake(another: true, app)
    waitGone(result)
    XCTAssertTrue(app.buttons["cadence.word-check"].isEnabled)
    expectWordCheck(requests: 1, file: 2, latest: false, cancellations: 0, pending: false, app)
    expectFiles(made: 3, kept: 2, requests: 3, starts: 1, app)
    close(app, closedFiles: (made: 3, kept: 0, requests: 3, starts: 1))
  }

  private func captureReview(_ testCase: String, _ app: XCUIApplication) {
    guard let directory = ProcessInfo.processInfo.environment["CADENCE_TOUR_DIR"] else { return }
    let size = testCase.hasSuffix("AX") ? "largest" : "normal"
    for id in [
      "cadence.replay-earlier", "cadence.replay", "cadence.word-check-result",
      "cadence.record-another",
    ] {
      let target = app.descendants(matching: .any).matching(identifier: id).firstMatch
      scrollTo(target, app)
      XCTAssertTrue(target.isHittable, id)
      let name = "review-" + size + "-" + id.replacingOccurrences(of: "cadence.", with: "")
      let shot = app.screenshot()
      let attachment = XCTAttachment(screenshot: shot)
      attachment.name = name
      attachment.lifetime = .keepAlways
      add(attachment)
      do {
        let folder = URL(fileURLWithPath: directory, isDirectory: true)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        try shot.pngRepresentation.write(to: folder.appendingPathComponent(name + ".png"))
      } catch {
        XCTFail("Could not save review screenshot: \(error)")
      }
    }
  }

  @objc func testCompactWordGuessIsFallibleReplayableAndClearsOnRetake() {
    wordGuessJourney("wordCheckGuess")
  }

  @objc func testLargestTextWordGuessIsFallibleReplayableAndClearsOnRetake() {
    wordGuessJourney("wordCheckGuessAX")
  }

  private func wordGuessJourney(_ testCase: String) {
    let app = launch(testCase)
    _ = recordTwoTries(app)
    let guess = app.staticTexts["cadence.word-check-guess"]
    XCTAssertFalse(guess.exists)
    activate("cadence.word-check", app)
    expectWordCheck(requests: 1, file: 2, latest: true, cancellations: 0, pending: true, app)
    XCTAssertFalse(guess.exists)
    releaseGeneratedWordCheck(app)
    waitLabel(app.staticTexts["cadence.word-check-result"],
      "No match for “ball” in this try. No sound error is identified.")
    waitLabel(guess, "Word guess: “wall”. This may be wrong; individual sounds aren’t assessed.")
    scrollTo(guess, app)
    XCTAssertTrue(guess.isHittable)
    let screenshot = XCTAttachment(screenshot: app.screenshot())
    screenshot.name = testCase.hasSuffix("AX") ? "word-guess-largest" : "word-guess-compact"
    screenshot.lifetime = .keepAlways
    add(screenshot)
    activate("cadence.replay", app)
    expectPlayback(2, app)
    activate("cadence.replay", app)
    expectPlayback(nil, app)
    expectWordCheck(requests: 1, file: 2, latest: true, cancellations: 0, pending: false, app)
    recordTake(another: true, app)
    waitGone(guess)
    waitGone(app.staticTexts["cadence.word-check-result"])
    expectWordCheck(requests: 1, file: 2, latest: false, cancellations: 0, pending: false, app)
    expectFiles(made: 3, kept: 2, requests: 3, starts: 1, app)
    close(app, closedFiles: (made: 3, kept: 0, requests: 3, starts: 1))
  }

  private func wordCheckUnavailableJourney(_ testCase: String) {
    let app = launch(testCase)
    let history = app.staticTexts["cadence.generated-history"]
    waitLabel(history, "Generated history: 0 entries")
    _ = recordTwoTries(app)
    expectWordCheck(requests: 0, file: nil, latest: false, cancellations: 0, pending: false, app)
    activate("cadence.word-check", app)
    expectWordCheck(requests: 1, file: 2, latest: true, cancellations: 0, pending: true, app)
    releaseGeneratedWordCheck(app)
    let result = app.staticTexts["cadence.word-check-result"]
    waitLabel(result, "Word check unavailable. Your recording is still here.")
    XCTAssertFalse(app.staticTexts["cadence.word-check-guess"].exists)
    scrollTo(result, app)
    XCTAssertTrue(result.isHittable)
    expectWordCheck(requests: 1, file: 2, latest: true, cancellations: 0, pending: false, app)
    expectFiles(made: 2, kept: 2, requests: 2, starts: 0, app)
    XCTAssertTrue(app.buttons["cadence.word-check"].isEnabled)
    XCTAssertTrue(app.buttons["cadence.record-another"].isEnabled)
    XCTAssertTrue(app.buttons["cadence.continue"].isEnabled)
    waitLabel(history, "Generated history: 0 entries")

    // Replay requests the exact latest kept file, without retrying recognition.
    activate("cadence.replay", app)
    expectPlayback(2, app)
    activate("cadence.replay", app)
    expectPlayback(nil, app)
    expectFiles(made: 2, kept: 2, requests: 2, starts: 1, app)
    expectWordCheck(requests: 1, file: 2, latest: true, cancellations: 0, pending: false, app)

    recordTake(another: true, app)
    waitGone(result)
    XCTAssertTrue(app.buttons["cadence.word-check"].isEnabled)
    XCTAssertEqual(app.buttons["cadence.replay-earlier"].value as? String, seconds(0.35))
    XCTAssertEqual(app.buttons["cadence.replay"].value as? String, seconds(0.5))
    expectWordCheck(requests: 1, file: 2, latest: false, cancellations: 0, pending: false, app)
    expectFiles(made: 3, kept: 2, requests: 3, starts: 1, app)
    waitLabel(history, "Generated history: 0 entries")

    XCTAssertTrue(app.buttons["cadence.continue"].label.hasPrefix("Finish practice"))
    activate("cadence.continue", app)
    waitLabel(
      app.staticTexts["cadence.complete"],
      "You practiced 1 word. Come back whenever you’re ready.")
    waitLabel(history, "Generated history: 1 entry, b, 1 word")
    // Initial success announces completion; the Saved notice is only for an explicit retry.
    XCTAssertFalse(app.staticTexts["cadence.history-saved"].exists)
    XCTAssertFalse(app.staticTexts["cadence.history-error"].exists)
    waitGone(result)
    expectFiles(made: 3, kept: 0, requests: 3, starts: 1, app)
    expectPlayback(nil, app)
    expectWordCheck(requests: 1, file: 2, latest: false, cancellations: 0, pending: false, app)
    close(app, closedFiles: (made: 3, kept: 0, requests: 3, starts: 1))
  }

  private func wordCheckCancelJourney(_ testCase: String) {
    let app = launch(testCase)
    recordTake(another: false, app)
    expectWordCheck(requests: 0, file: nil, latest: false, cancellations: 0, pending: false, app)
    activate("cadence.word-check", app)
    expectWordCheck(requests: 1, file: 1, latest: true, cancellations: 0, pending: true, app)
    activate("cadence.word-check-cancel", app)
    waitLabel(
      app.staticTexts["cadence.word-check-status"],
      "Cancelling word check. Waiting for the recognizer to finish cleanup…")
    expectWordCheck(requests: 1, file: 1, latest: true, cancellations: 1, pending: true, app)
    XCTAssertFalse(app.buttons["cadence.replay"].isEnabled)
    XCTAssertFalse(app.buttons["cadence.record-another"].isEnabled)
    XCTAssertFalse(app.buttons["cadence.continue"].isEnabled)
    expectFiles(made: 1, kept: 1, requests: 1, starts: 0, app)
    activate("cadence.close", app)
    XCTAssertFalse(app.staticTexts["cadence.generated-direct-closed"].exists)
    XCTAssertTrue(app.staticTexts["cadence.close-note"].waitForExistence(timeout: 5))
    expectWordCheck(requests: 1, file: 1, latest: true, cancellations: 1, pending: true, app)
    expectFiles(made: 1, kept: 1, requests: 1, starts: 0, app)
    XCTAssertFalse(app.staticTexts["cadence.word-check-result"].exists)
    releaseGeneratedWordCheck(app)
    XCTAssertTrue(app.staticTexts["cadence.generated-direct-closed"].waitForExistence(timeout: 5))
    waitLabel(
      app.staticTexts["cadence.generated-closed-files"],
      "Generated files: made 1, kept 0 · microphone requests 1 · playback starts 0")
    app.terminate()
  }
}
