import XCTest

/// Bounded generated stage journeys. Seeds are labeled actual coordinator actions; these
/// cases do not establish a single full user journey or real recognition/accessibility.
@MainActor
final class LocalGuidedUITests: XCTestCase {
  func testCompactSelectedPracticeTimedOutCheckRetriesSameTake() {
    practiceTimeoutRetryJourney("practiceTimeoutRetry")
  }
  func testLargestTextSelectedPracticeTimedOutCheckRetriesSameTake() {
    practiceTimeoutRetryJourney("practiceTimeoutRetryAX")
  }

  private func practiceTimeoutRetryJourney(_ testCase: String) {
    let app = launch(testCase)
    executionTimeAllowance = 300
    let tag = "generated-" + testCase
    registerGeneratedTimeoutEvidence(tag, app)
    files(made: 5, kept: 0, app)
    checks(count: 5, app)
    history([], app)
    activate("cadence.guided.select." + entryIDs[1], app)
    activate("cadence.guided.practice.start", app)
    waitLabel(app.staticTexts["cadence.word"], "pig")
    let frozen = "First review: Word matched. Word checks cannot identify which sound was made."
    waitLabel(app.staticTexts["cadence.guided.first-observation"], frozen)
    record(app)
    files(made: 6, kept: 1, app)
    checks(count: 5, app)
    activate("cadence.word-check", app)
    checks(count: 6, pending: 1, app)
    releaseTimeoutPracticeReceipt(app)
    let result = app.staticTexts["cadence.word-check-result"]
    waitLabel(result, "Word check took too long. Your recording is still here.")
    captureGeneratedTimeoutText(result, id: "cadence.word-check-result", name: tag + "-timeout", app)
    let retry = app.buttons["cadence.word-check"]
    waitLabel(retry, "Try word check again")
    revealGeneratedTimeoutControl(retry, id: "cadence.word-check", app)
    captureGeneratedTimeoutState(tag + "-retry-action", app)
    checks(count: 6, app)
    files(made: 6, kept: 1, app)
    history([], app)
    retry.tap()
    checks(count: 7, pending: 1, app)
    waitLabel(app.staticTexts["cadence.generated-guided.retry-binding"],
      "Generated retry binding: same take yes · new operation yes · latest yes")
    XCTAssertFalse(app.buttons["cadence.word-check"].exists)
    XCTAssertFalse(app.buttons["cadence.guided.continue"].isEnabled)
    XCTAssertFalse(app.buttons["cadence.record-another"].isEnabled)
    XCTAssertFalse(app.buttons["cadence.replay"].isEnabled)
    let pending = app.staticTexts["cadence.word-check-status"]
    waitLabel(pending, "Checking words in this try on this device…")
    captureGeneratedTimeoutText(pending, id: "cadence.word-check-status", name: tag + "-pending", app)
    checks(count: 7, pending: 1, app)
    files(made: 6, kept: 1, app)
    releaseTimeoutPracticeReceipt(app)
    waitLabel(result, "“pig” matched in this try. Individual sounds aren’t assessed.")
    captureGeneratedTimeoutText(result, id: "cadence.word-check-result", name: tag + "-matched", app)
    XCTAssertFalse(app.buttons["cadence.word-check"].isEnabled)
    waitLabel(app.staticTexts["cadence.guided.first-observation"], frozen)
    files(made: 6, kept: 1, app)
    checks(count: 7, app)
    history([], app)
    activate("cadence.guided.continue", app)
    history(["p:1"], app)
    waitLabel(app.staticTexts["cadence.generated-guided.receipts"], "Generated practice receipts: 1 exact")
    activate("cadence.guided.recheck.start", app)
    waitLabel(app.staticTexts["cadence.word"], "ball")
    waitLabel(app.staticTexts["cadence.guided.visit-heading"], "Recheck · 1 of 5")
    XCTAssertFalse(app.staticTexts["cadence.word-check-result"].exists)
    XCTAssertFalse(app.buttons["cadence.replay"].exists)
    checks(count: 7, app)
    files(made: 6, kept: 0, app)
    captureGeneratedTimeoutState(tag + "-fresh-recheck", app)
    close(made: 6, rows: ["p:1"], app)
  }

  private func releaseTimeoutPracticeReceipt(_ app: XCUIApplication) {
    let release = app.buttons["cadence.generated-guided.release"]
    XCTAssertTrue(release.waitForExistence(timeout: 5))
    XCTAssertTrue(release.isEnabled && release.isHittable)
    XCTAssertGreaterThanOrEqual((release.frame.width * 1_000_000).rounded() / 1_000_000, 44)
    XCTAssertGreaterThanOrEqual((release.frame.height * 1_000_000).rounded() / 1_000_000, 44)
    release.tap()
  }

  func testCompactResearchDetailsAndCompletePracticeSummary() {
    researchDetailsJourney("researchDetails")
  }

  func testLargestTextResearchDetailsAndCompletePracticeSummary() {
    researchDetailsJourney("researchDetailsAX")
  }

  private func researchDetailsJourney(_ testCase: String) {
    let app = launch(testCase)
    executionTimeAllowance = 480
    let ball = entryIDs[0], pig = entryIDs[1]
    func modelCalls(_ count: Int) {
      waitLabel(app.staticTexts["cadence.generated-guided.model-calls"], "Generated model calls: \(count)")
    }
    func open(_ entry: String) {
      activate("cadence.guided.research-details." + entry, app)
      XCTAssertTrue(app.staticTexts["guided-research-details-title"].waitForExistence(timeout: 5))
      XCTAssertTrue(app.buttons["guided-research-details-close"].isHittable)
    }
    func line(_ id: String, contains value: String, capture: String) {
      let element = app.staticTexts[id]
      XCTAssertTrue(element.waitForExistence(timeout: 5))
      XCTAssertTrue(element.label.contains(value), element.label)
      scrollTo(element, app, targetTag: "researchLine")
      XCTAssertTrue(element.isHittable)
      capturePracticeTour(testCase + "-" + capture, app)
      attach(app, testCase + "-" + capture)
    }
    files(made: 5, kept: 0, app)
    checks(count: 5, app)
    modelCalls(5)
    history([], app)
    open(ball)
    line("guided-research-details-disclaimer", contains: "Not validated pronunciation feedback",
      capture: "boundary")
    let disclaimerHeight = app.staticTexts["guided-research-details-disclaimer"].frame.height
    if testCase.hasSuffix("AX") {
      XCTAssertGreaterThan(disclaimerHeight, 120, "The modal must render the requested largest text size.")
    } else {
      XCTAssertLessThan(disclaimerHeight, 100)
    }
    for (rating, value) in ["0.200000", "0.300000", "0.500000"].enumerated() {
      line("guided-research-details-first-review-target-\(ball)-0-rating-\(rating)",
        contains: value, capture: "first-rating-\(rating)")
    }
    line("guided-research-details-recheck-unavailable", contains: "No recheck result yet",
      capture: "not-yet-rechecked")
    activate("guided-research-details-close", app)
    modelCalls(5)
    checks(count: 5, app)
    files(made: 5, kept: 0, app)
    history([], app)
    activate("cadence.guided.select." + ball, app)
    activate("cadence.guided.practice.start", app)
    record(app)
    activate("cadence.guided.continue", app)
    history(["b:1"], app)
    activate("cadence.guided.recheck.start", app)
    record(app)
    activate("cadence.word-check", app)
    checks(count: 6, app)
    modelCalls(6)
    activate("cadence.guided.continue", app)
    activate("cadence.guided.finish-stage", app)
    let pair = app.staticTexts["cadence.guided.paired." + ball]
    XCTAssertTrue(pair.waitForExistence(timeout: 5))
    XCTAssertTrue(pair.label.contains("Practice: Participation saved"))
    let unselected = app.staticTexts["cadence.guided.paired." + pig]
    XCTAssertTrue(unselected.label.contains("Practice: Not selected"))
    open(ball)
    for (rating, value) in ["0.500000", "0.250000", "0.250000"].enumerated() {
      line("guided-research-details-recheck-target-\(ball)-0-rating-\(rating)",
        contains: value, capture: "recheck-rating-\(rating)")
    }
    activate("guided-research-details-close", app)
    open(pig)
    line("guided-research-details-recheck-unavailable", contains: "No eligible completed word check",
      capture: "unreached-recheck")
    activate("guided-research-details-close", app)
    modelCalls(6)
    files(made: 7, kept: 0, app)
    checks(count: 6, app)
    history(["b:1"], app)
    activate("cadence.guided.repeat", app)
    XCTAssertFalse(app.staticTexts["guided-research-details-title"].exists)
    activate("cadence.guided.finish-stage", app)
    open(ball)
    line("guided-research-details-first-review-unavailable", contains: "No eligible completed word check",
      capture: "fresh-round-no-old-result")
    XCTAssertFalse(app.staticTexts["guided-research-details-first-review-target-\(ball)-0-rating-0"].exists)
    activate("guided-research-details-close", app)
    modelCalls(6)
    checks(count: 6, app)
    close(made: 7, rows: ["b:1"], app)
  }

  func testCompactMatchedShortPracticeTakeExplainsRequiredRecordingRecovery() {
    practiceQualityRecoveryJourney("practiceQuality")
  }

  func testLargestTextMatchedShortPracticeTakeExplainsRequiredRecordingRecovery() {
    practiceQualityRecoveryJourney("practiceQualityAX")
  }

  private func practiceQualityRecoveryJourney(_ testCase: String) {
    let app = launch(testCase)
    executionTimeAllowance = 300
    files(made: 5, kept: 0, app)
    checks(count: 5, app)
    history([], app)
    activate("cadence.guided.select." + entryIDs[0], app)
    activate("cadence.guided.practice.start", app)
    waitLabel(app.staticTexts["cadence.word"], "ball")
    let requirement = app.descendants(matching: .any)
      .matching(identifier: "cadence.guided.recording-requirement").firstMatch
    XCTAssertFalse(requirement.exists)
    XCTAssertFalse(app.buttons["cadence.record-and-check"].exists)
    record(app)
    files(made: 6, kept: 1, app)
    checks(count: 5, app)
    XCTAssertTrue(requirement.waitForExistence(timeout: 5))
    XCTAssertTrue(requirement.label.contains("Record another try to finish this word"))
    XCTAssertTrue(requirement.label.contains(
      "Tap Record, say the word at your own pace, then tap Stop. You can also skip this word."))
    XCTAssertFalse(app.buttons["cadence.guided.continue"].isEnabled)
    activate("cadence.word-check", app)
    checks(count: 6, app)
    waitLabel(app.staticTexts["cadence.word-check-result"],
      "“ball” matched in this try. Individual sounds aren’t assessed.")
    XCTAssertTrue(requirement.exists)
    XCTAssertFalse(app.buttons["cadence.guided.continue"].isEnabled)
    XCTAssertEqual(app.staticTexts.matching(
      NSPredicate(format: "label BEGINSWITH %@", "Recording tip for next time:")).count, 0)
    scrollTo(requirement, app, targetTag: "practiceRecordingRequirement")
    XCTAssertTrue(requirement.isHittable)
    attach(app, testCase + "-matched-recording-requirement")
    let retake = app.buttons["cadence.record-another"]
    XCTAssertLessThanOrEqual(requirement.frame.maxY, retake.frame.minY)
    scrollTo(retake, app, targetTag: "recordAnother")
    XCTAssertTrue(retake.isHittable)
    XCTAssertTrue(retake.isEnabled)
    attach(app, testCase + "-required-retake-action")
    activate("cadence.record-another", app)
    XCTAssertFalse(requirement.exists)
    activate("cadence.stop", app)
    files(made: 7, kept: 2, app)
    checks(count: 6, app)
    XCTAssertFalse(requirement.exists, "The earlier short take must not govern the acceptable latest take.")
    XCTAssertFalse(app.staticTexts["cadence.word-check-result"].exists)
    XCTAssertTrue(app.buttons["cadence.guided.continue"].isEnabled)
    history([], app)
    activate("cadence.guided.continue", app)
    XCTAssertTrue(app.buttons["cadence.guided.recheck.start"].waitForExistence(timeout: 5))
    files(made: 7, kept: 0, app)
    checks(count: 6, app)
    history(["b:1"], app)
    waitLabel(app.staticTexts["cadence.generated-guided.receipts"], "Generated practice receipts: 1 exact")
    close(made: 7, rows: ["b:1"], app)
  }

  func testCompactRejectedCaptureOffersExplicitCombinedRetake() {
    combinedRetakeJourney("retake")
  }

  func testLargestTextRejectedCaptureOffersExplicitCombinedRetake() {
    combinedRetakeJourney("retakeAX")
  }

  private func combinedRetakeJourney(_ testCase: String) {
    let app = launch(testCase)
    executionTimeAllowance = 300
    activate("cadence.guided.start", app)
    for round in 0..<2 {
      waitLabel(app.staticTexts["cadence.word"], "ball")
      activate("cadence.record-and-check", app)
      activate("cadence.stop", app)
      files(made: round * 2 + 1, kept: 1, app)
      checks(count: round, app)
      XCTAssertFalse(app.buttons["cadence.guided.continue"].isEnabled)
      let combined = app.buttons["cadence.record-and-check-another"]
      waitLabel(combined, "Record and check another try")
      scrollTo(combined, app, targetTag: "combinedRetake")
      XCTAssertTrue(combined.isHittable)
      XCTAssertTrue(combined.isEnabled)
      XCTAssertTrue(app.buttons["cadence.record-another"].isEnabled)
      attach(app, testCase + "-rejected-" + String(round))
      activate("cadence.record-and-check-another", app)
      checks(count: round, app)
      activate("cadence.stop", app)
      checks(count: round + 1, app)
      files(made: (round + 1) * 2, kept: 2, app)
      let result = app.staticTexts["cadence.word-check-result"]
      waitLabel(result, "“ball” matched in this try. Individual sounds aren’t assessed.")
      XCTAssertFalse(combined.exists)
      XCTAssertFalse(app.buttons["cadence.record-another"].isEnabled)
      XCTAssertTrue(app.buttons["cadence.guided.continue"].isEnabled)
      history([], app)
      activate("cadence.guided.continue", app)
      waitLabel(app.staticTexts["cadence.word"], "pig")
      files(made: (round + 1) * 2, kept: 0, app)
      activate("cadence.guided.finish-stage", app)
      if round == 0 {
        activate("cadence.guided.select." + entryIDs[0], app)
        activate("cadence.guided.practice.start", app)
        XCTAssertFalse(app.buttons["cadence.record-and-check"].exists)
        activate("cadence.guided.finish-stage", app)
        activate("cadence.guided.recheck.start", app)
      }
    }
    checks(count: 2, app)
    close(made: 4, rows: [], app, button: "cadence.guided.done")
  }

  func testCompactFinalWordButtonsOpenNamedStages() {
    continuationJourney(largest: false)
  }

  func testNativeLargestFinalWordButtonsOpenNamedStages() {
    continuationJourney(largest: true)
  }

  private func continuationJourney(largest: Bool) {
    trace.reset(caseTag: largest ? "continuation-largest" : "continuation-compact")
    continueAfterFailure = false
    executionTimeAllowance = 300
    // Use the app's admitted generated host; the old private probe flag has no
    // handler in the shipping project. The AX case selects accessibility5 in the host.
    let app = launch(largest ? "setupAX" : "setup")
    trace.reset(caseTag: largest ? "continuation-largest" : "continuation-compact")
    executionTimeAllowance = 300
    files(made: 0, kept: 0, app)
    checks(count: 0, app)
    history([], app)
    activate("cadence.guided.start", app)
    for word in words.prefix(4) {
      waitLabel(app.staticTexts["cadence.word"], word)
      waitLabel(app.buttons["cadence.guided.continue"], "Next word")
      activate("cadence.guided.skip", app)
    }
    waitLabel(app.staticTexts["cadence.word"], "dog")
    record(app)
    activate("cadence.word-check", app)
    checks(count: 1, app)
    continuation("Choose practice words", capture: "last-first-review", app)
    XCTAssertTrue(app.buttons["cadence.guided.practice.start"].waitForExistence(timeout: 5))
    XCTAssertFalse(app.buttons["cadence.guided.practice.start"].isEnabled)
    let size = largest ? "largest" : "normal"
    capturePracticeTour("guided-first-review-" + size, app)
    if ProcessInfo.processInfo.environment["CADENCE_TOUR_DIR"] != nil {
      let heading = app.staticTexts["Choose words to practice"]
      scrollTo(heading, app, targetTag: "first-review-heading-capture")
      XCTAssertTrue(heading.isHittable)
      capturePracticeTour("guided-first-review-heading-" + size, app)
      let choice = app.buttons["cadence.guided.select." + entryIDs[4]]
      scrollTo(choice, app, targetTag: "first-review-row-capture")
      XCTAssertTrue(choice.isHittable)
      capturePracticeTour("guided-first-review-row-" + size, app)
    }
    activate("cadence.guided.select." + entryIDs[4], app)
    activate("cadence.guided.practice.start", app)
    waitLabel(app.staticTexts["cadence.word"], "dog")
    waitLabel(app.staticTexts["cadence.guided.visit-heading"], "Practice · 1 of 1")
    record(app)
    continuation("Finish practice", capture: "last-practice", app)
    XCTAssertTrue(app.buttons["cadence.guided.recheck.start"].waitForExistence(timeout: 5))
    history(["d:1"], app)
    capturePracticeTour("guided-practice-review-" + size, app)
    activate("cadence.guided.recheck.start", app)
    for word in words.prefix(4) {
      waitLabel(app.staticTexts["cadence.word"], word)
      waitLabel(app.buttons["cadence.guided.continue"], "Next word")
      activate("cadence.guided.skip", app)
    }
    waitLabel(app.staticTexts["cadence.word"], "dog")
    record(app)
    activate("cadence.word-check", app)
    checks(count: 2, app)
    continuation("View summary", capture: "last-recheck", app)
    XCTAssertTrue(app.buttons["cadence.guided.done"].waitForExistence(timeout: 5))
    let paired = app.staticTexts["cadence.guided.paired." + entryIDs[4]]
    XCTAssertTrue(paired.waitForExistence(timeout: 5))
    XCTAssertTrue(paired.label.contains("First review: Word matched"))
    XCTAssertTrue(paired.label.contains("Recheck: Word matched"))
    if ProcessInfo.processInfo.environment["CADENCE_TOUR_DIR"] != nil {
      let heading = app.staticTexts["Your word observations"]
      scrollTo(heading, app, targetTag: "summary-heading-capture")
      XCTAssertTrue(heading.isHittable)
      capturePracticeTour("guided-summary-heading-" + size, app)
      scrollTo(paired, app, targetTag: "summary-capture")
      XCTAssertTrue(paired.isHittable)
      capturePracticeTour("guided-summary-" + size, app)
    }
    files(made: 3, kept: 0, app)
    history(["d:1"], app)
    close(made: 3, rows: ["d:1"], app, button: "cadence.guided.done")
  }

  private func continuation(_ label: String, capture: String, _ app: XCUIApplication) {
    let button = app.buttons["cadence.guided.continue"]
    waitLabel(button, label)
    scrollTo(button, app, targetTag: capture)
    attach(app, capture)
    activate("cadence.guided.continue", app)
  }

  func testCompactFirstCheckSkipEarlyFinishAndExplicitPracticeChoices() {
    selectionJourney("setup")
  }
  func testLargestTextFirstCheckSkipEarlyFinishAndExplicitPracticeChoices() {
    selectionJourney("setupAX")
  }
  func testCompactChosenPigDogFreshPracticeSavesOnlyExactParticipation() {
    practiceJourney("practice")
  }
  func testLargestTextChosenPigDogFreshPracticeSavesOnlyExactParticipation() {
    practiceJourney("practiceAX")
  }
  func testCompactPracticeManualWordCheckKeepsParticipationOptional() {
    practiceJourney("practice", manualChecks: true)
  }
  func testLargestTextPracticeManualWordCheckKeepsParticipationOptional() {
    practiceJourney("practiceAX", manualChecks: true)
  }
  func testCompactFreshRecheckKeepsFivePairedFirstObservationsThenCloses() {
    recheckJourney("recheck")
  }
  func testLargestTextFreshRecheckKeepsFivePairedFirstObservationsThenCloses() {
    recheckJourney("recheckAX")
  }
  func testCompactCancellationWaitsForExactReceiptBeforeEarlyFinish() {
    cancelJourney("heldFinish")
  }
  func testLargestTextCancellationWaitsForExactReceiptBeforeEarlyFinish() {
    cancelJourney("heldFinishAX")
  }
  func testCompactCloseWaitsForHeldBorrowAndCreatesNoHistory() { heldCloseJourney("heldClose") }
  func testLargestTextCloseWaitsForHeldBorrowAndCreatesNoHistory() {
    heldCloseJourney("heldCloseAX")
  }
  func testCompactTimeoutKeepsReplayManualPracticeAndFrozenFirstReview() {
    timeoutJourney("timeout")
  }
  func testLargestTextTimeoutKeepsReplayManualPracticeAndFrozenFirstReview() {
    timeoutJourney("timeoutAX")
  }

  func testCompactCurrentTryWordGuessClearsOnPracticeReplacementAndKeepsFrozenReview() {
    wordGuessJourney("wordGuess")
  }
  func testLargestTextCurrentTryWordGuessClearsOnPracticeReplacementAndKeepsFrozenReview() {
    wordGuessJourney("wordGuessAX")
  }

  private func wordGuessJourney(_ testCase: String) {
    let app = launch(testCase)
    executionTimeAllowance = 300
    let guess = app.staticTexts["cadence.word-check-guess"]
    let focus = app.staticTexts["cadence.listening-focus"]
    let first = app.staticTexts["cadence.guided.first-observation"]
    let frozen = "First review: No word match. Word checks cannot identify which sound was made."
    func assertGuess(_ word: String, _ tag: String, latest: Bool = false) {
      let take = latest ? "the latest try" : "this try"
      waitLabel(guess,
        "Word guess for \(take): “\(word)”. This may be wrong; individual sounds aren’t assessed.")
      waitLabel(app.staticTexts["cadence.word-check-result"],
        "No match for “ball” in this try. No sound error is identified.")
      scrollTo(guess, app, targetTag: "currentGuess")
      XCTAssertTrue(guess.isHittable)
      attach(app, testCase + "-" + tag)
      let ax = XCTAttachment(string: guess.label)
      ax.name = testCase + "-" + tag + "-AX-label"
      ax.lifetime = .keepAlways
      add(ax)
      let expectedFocus = word == "fall"
        ? "Play the earlier try, then the latest. Listen for /b/ at the start of “ball”."
        : "Play your try. Listen for /b/ at the start of “ball”."
      waitLabel(focus, expectedFocus)
      scrollTo(focus, app, targetTag: "listeningFocus")
      let viewport = app.scrollViews.firstMatch.frame
      XCTAssertTrue(focus.isHittable)
      let focusFrame = focus.frame
      XCTAssertGreaterThanOrEqual(focusFrame.minY, max(viewport.minY, bannerBottom(app)))
      XCTAssertLessThanOrEqual(focusFrame.maxY, min(viewport.maxY, app.windows.firstMatch.frame.maxY))
      XCTAssertFalse(app.buttons["cadence.listening-focus"].exists)
      let firstReplay = app.buttons["cadence.replay-earlier"].exists
        ? app.buttons["cadence.replay-earlier"] : app.buttons["cadence.replay"]
      XCTAssertTrue(firstReplay.exists)
      // Same scroll position; do not require oversized focus plus replay to fit together.
      let replayFrame = firstReplay.frame
      XCTAssertLessThanOrEqual(focusFrame.maxY, replayFrame.minY)
      attach(app, testCase + "-" + tag + "-focus-before-replay")
      let focusAX = XCTAttachment(string: focus.label)
      focusAX.name = testCase + "-" + tag + "-focus-AX-label"
      focusAX.lifetime = .keepAlways
      add(focusAX)
    }
    files(made: 0, kept: 0, app)
    checks(count: 0, app)
    history([], app)
    activate("cadence.guided.start", app)
    waitLabel(app.staticTexts["cadence.word"], "ball")
    XCTAssertFalse(guess.exists)
    XCTAssertFalse(focus.exists)
    record(app)
    checks(count: 0, app)
    activate("cadence.word-check", app)
    checks(count: 1, app)
    assertGuess("wall", "initial-current-guess")
    files(made: 1, kept: 1, app)
    XCTAssertFalse(app.buttons["cadence.word-check"].isEnabled)
    XCTAssertFalse(app.buttons["cadence.record-another"].isEnabled)
    activate("cadence.guided.continue", app)
    waitLabel(app.staticTexts["cadence.word"], "pig")
    XCTAssertFalse(guess.exists)
    activate("cadence.guided.finish-stage", app)
    let ball = app.buttons["cadence.guided.select." + entryIDs[0]]
    XCTAssertTrue(ball.waitForExistence(timeout: 5))
    XCTAssertTrue(ball.label.contains("First review: No word match"))
    XCTAssertFalse(ball.label.contains("wall"))
    files(made: 1, kept: 0, app)
    checks(count: 1, app)
    history([], app)
    activate("cadence.guided.select." + entryIDs[0], app)
    activate("cadence.guided.practice.start", app)
    waitLabel(app.staticTexts["cadence.word"], "ball")
    waitLabel(first, frozen)
    XCTAssertFalse(guess.exists)
    record(app)
    checks(count: 1, app)
    activate("cadence.word-check", app)
    checks(count: 2, app)
    assertGuess("call", "practice-current-guess")
    files(made: 2, kept: 1, app)
    waitLabel(first, frozen)
    scrollTo(first, app, targetTag: "firstObservation")
    XCTAssertTrue(first.isHittable)
    attach(app, testCase + "-frozen-first-context")
    let firstAX = XCTAttachment(string: first.label)
    firstAX.name = testCase + "-frozen-first-context-AX-label"
    firstAX.lifetime = .keepAlways
    add(firstAX)
    activate("cadence.record-another", app)
    XCTAssertTrue(app.buttons["cadence.stop"].waitForExistence(timeout: 5))
    XCTAssertFalse(guess.exists)
    XCTAssertFalse(focus.exists)
    checks(count: 2, app)
    activate("cadence.stop", app)
    XCTAssertTrue(app.buttons["cadence.replay"].waitForExistence(timeout: 5))
    XCTAssertFalse(guess.exists)
    waitLabel(first, frozen)
    files(made: 3, kept: 2, app)
    checks(count: 2, app)
    scrollTo(app.buttons["cadence.word-check"], app, targetTag: "check")
    attach(app, testCase + "-replacement-no-guess")
    activate("cadence.word-check", app)
    checks(count: 3, app)
    assertGuess("fall", "replacement-current-guess", latest: true)
    waitLabel(first, frozen)
    activate("cadence.guided.continue", app)
    files(made: 3, kept: 0, app)
    history(["b:1"], app)
    waitLabel(app.staticTexts["cadence.generated-guided.receipts"],
      "Generated practice receipts: 1 exact")
    XCTAssertFalse(guess.exists)
    activate("cadence.guided.recheck.start", app)
    waitLabel(app.staticTexts["cadence.word"], "ball")
    waitLabel(first, frozen)
    XCTAssertFalse(guess.exists)
    checks(count: 3, app)
    record(app)
    checks(count: 3, app)
    activate("cadence.word-check", app)
    checks(count: 4, app)
    assertGuess("tall", "recheck-current-guess")
    files(made: 4, kept: 1, app)
    waitLabel(first, frozen)
    XCTAssertFalse(app.buttons["cadence.record-another"].isEnabled)
    activate("cadence.guided.finish-stage", app)
    let paired = app.staticTexts["cadence.guided.paired." + entryIDs[0]]
    XCTAssertTrue(paired.waitForExistence(timeout: 5))
    XCTAssertTrue(paired.label.contains("First review: No word match"))
    XCTAssertTrue(paired.label.contains("Recheck: No word match"))
    for alternative in ["wall", "call", "fall", "tall"] {
      XCTAssertFalse(paired.label.contains(alternative))
    }
    for index in 1..<entryIDs.count {
      let row = app.staticTexts["cadence.guided.paired." + entryIDs[index]]
      XCTAssertTrue(row.waitForExistence(timeout: 5))
      XCTAssertTrue(row.label.contains(index == 1
        ? "First review: Skipped" : "First review: Not reached"))
      XCTAssertTrue(row.label.contains("Recheck: Not reached"))
    }
    XCTAssertFalse(guess.exists)
    scrollTo(paired, app, targetTag: "paired0")
    XCTAssertFalse(focus.exists)
    attach(app, testCase + "-status-only-summary")
    files(made: 4, kept: 0, app)
    checks(count: 4, app)
    history(["b:1"], app)
    close(made: 4, rows: ["b:1"], app, button: "cadence.guided.done")
  }

  private let trace = GuidedScrollTrace()

  private let words = ["ball", "pig", "moon", "tiger", "dog"]
  private let entryIDs = [
    "b-beginning-ball", "p-beginning-pig", "m-beginning-moon", "t-beginning-tiger",
    "d-beginning-dog",
  ]
  private let bannerIDs = ["banner", "seed", "files", "checks", "history", "receipts"].map {
    "cadence.generated-guided." + $0
  }

  private func launch(_ testCase: String) -> XCUIApplication {
    trace.reset(caseTag: testCase)
    continueAfterFailure = false
    if testCase == "timeout" || testCase == "timeoutAX" {
      executionTimeAllowance = testCase.hasSuffix("AX") ? 150 : 120
    } else {
      executionTimeAllowance = testCase.hasSuffix("AX") ? 90 : 60
    }
    let app = XCUIApplication()
    app.launchEnvironment.removeValue(forKey: "CADENCE_CONTROLLED_UNIT_HOST")
    app.launchEnvironment.removeValue(forKey: "TEST_RUNNER_CADENCE_CONTROLLED_UNIT_HOST")
    app.launchEnvironment.removeValue(forKey: "TEST_RUNNER_CADENCE_CONTROLLED_UI_HOST")
    app.launchEnvironment["CADENCE_CONTROLLED_UI_HOST"] = "1"
    app.launchArguments = [
      "-CadenceLocalGuidedMode", "-CadenceLocalGuidedUITestCase", testCase,
      "-CadenceControlledUIRunID", UUID().uuidString.lowercased(),
    ]
    if testCase == "researchDetails" || testCase == "researchDetailsAX" {
      app.launchArguments += ["-AppleLanguages", "(en)", "-AppleLocale", "en_US"]
    }
    app.launch()
    XCTAssertTrue(app.staticTexts["cadence.generated-guided.banner"].waitForExistence(timeout: 5))
    let base = testCase.hasSuffix("AX") ? String(testCase.dropLast(2)) : testCase
    let seed =
      base == "practice" || base == "practiceQuality" || base == "researchDetails"
        || base == "practiceTimeoutRetry"
      ? "Generated stage: five settled first checks; no choices preselected"
      : base == "recheck"
        ? "Generated stage: five settled first checks; one fresh pig practice saved"
        : "Generated stage: unseeded setup"
    waitLabel(app.staticTexts["cadence.generated-guided.seed"], seed)
    XCTAssertFalse(app.staticTexts["cadence.generated-guided.failed"].exists)
    XCTAssertFalse(app.staticTexts["cadence.generated-guided.closed"].exists)
    return app
  }

  private func selectionJourney(_ testCase: String) {
    let app = launch(testCase)
    files(made: 0, kept: 0, app)
    checks(count: 0, app)
    history([], app)
    activate("cadence.guided.start", app)
    waitLabel(app.staticTexts["cadence.word"], "ball")
    record(app)
    checks(count: 0, app)  // Start/Record/Stop never automatically submit a check.
    activate("cadence.word-check", app)
    checks(count: 1, app)
    waitLabel(
      app.staticTexts["cadence.word-check-result"],
      "“ball” matched in this try. Individual sounds aren’t assessed.")
    waitLabel(
      app.staticTexts["cadence.guided.first-check-status"],
      "The first check is kept for this review.")
    XCTAssertFalse(app.buttons["cadence.word-check"].isEnabled)
    activate("cadence.guided.continue", app)
    waitLabel(app.staticTexts["cadence.word"], "pig")
    activate("cadence.guided.skip", app)
    waitLabel(app.staticTexts["cadence.word"], "moon")
    activate("cadence.guided.finish-stage", app)
    files(made: 1, kept: 0, app)
    history([], app)
    XCTAssertFalse(app.buttons["cadence.guided.practice.start"].isEnabled)
    for id in entryIDs {
      XCTAssertEqual(app.buttons["cadence.guided.select." + id].value as? String, "Not selected")
    }
    XCTAssertTrue(
      app.buttons["cadence.guided.select." + entryIDs[0]].label.contains(
        "First review: Word matched"))
    XCTAssertTrue(
      app.buttons["cadence.guided.select." + entryIDs[1]].label.contains("First review: Skipped"))
    XCTAssertTrue(
      app.buttons["cadence.guided.select." + entryIDs[2]].label.contains(
        "First review: Skipped"))
    for index in [3, 4] {
      XCTAssertTrue(
        app.buttons["cadence.guided.select." + entryIDs[index]].label.contains(
          "First review: Not reached"))
    }
    for index in [1, 4, 2] { activate("cadence.guided.select." + entryIDs[index], app) }
    XCTAssertFalse(app.buttons["cadence.guided.select." + entryIDs[0]].isEnabled)
    activate("cadence.guided.select." + entryIDs[2], app)
    waitLabel(app.buttons["cadence.guided.practice.start"], "Practice selected words (2)")
    activate("cadence.guided.practice.start", app)
    waitLabel(app.staticTexts["cadence.word"], "pig")
    waitLabel(
      app.staticTexts["cadence.guided.first-observation"],
      "First review: Skipped. Word checks cannot identify which sound was made.")
    XCTAssertFalse(app.buttons["cadence.word-check"].exists)
    files(made: 1, kept: 0, app)  // Starting practice never captures automatically.
    close(made: 1, rows: [], app)
  }

  private func practiceJourney(_ testCase: String, manualChecks: Bool = false) {
    let app = launch(testCase)
    if !manualChecks, ProcessInfo.processInfo.environment["CADENCE_TOUR_DIR"] != nil {
      let heading = app.staticTexts["Choose words to practice"]
      scrollTo(heading, app, targetTag: "seeded-review-heading")
      XCTAssertTrue(heading.isHittable)
      let size = testCase.hasSuffix("AX") ? "largest" : "normal"
      capturePracticeTour("guided-seeded-first-review-heading-" + size, app)
      let row = app.buttons["cadence.guided.select." + entryIDs[4]]
      scrollTo(row, app, targetTag: "seeded-review-row")
      XCTAssertTrue(row.isHittable)
      capturePracticeTour("guided-seeded-first-review-row-" + size, app)
    }
    files(made: 5, kept: 0, app)
    history([], app)
    checks(count: 5, app)
    XCTAssertFalse(app.buttons["cadence.guided.practice.start"].isEnabled)
    for index in [1, 4] { activate("cadence.guided.select." + entryIDs[index], app) }
    activate("cadence.guided.practice.start", app)
    for (index, word) in ["pig", "dog"].enumerated() {
      waitLabel(app.staticTexts["cadence.word"], word)
      waitLabel(
        app.staticTexts["cadence.guided.first-observation"],
        "First review: Word matched. Word checks cannot identify which sound was made.")
      XCTAssertFalse(app.buttons["cadence.word-check"].exists)
      XCTAssertFalse(app.buttons["cadence.replay"].exists)
      record(app)
      files(made: 6 + index, kept: 1, app)
      checks(count: 5 + (manualChecks ? index : 0), app)
      if manualChecks {
        activate("cadence.word-check", app)
        checks(count: 6 + index, app)
        waitLabel(
          app.staticTexts["cadence.word-check-result"],
          "“\(word)” matched in this try. Individual sounds aren’t assessed.")
        XCTAssertFalse(app.buttons["cadence.word-check"].isEnabled)
      }
      activate("cadence.guided.continue", app)
    }
    XCTAssertTrue(app.buttons["cadence.guided.recheck.start"].waitForExistence(timeout: 5))
    files(made: 7, kept: 0, app)
    checks(count: manualChecks ? 7 : 5, app)
    history(["d:1", "p:1"], app)
    waitLabel(
      app.staticTexts["cadence.generated-guided.receipts"], "Generated practice receipts: 2 exact")
    if !manualChecks, ProcessInfo.processInfo.environment["CADENCE_TOUR_DIR"] != nil {
      let heading = app.staticTexts["Revisit the same five"]
      scrollTo(heading, app, targetTag: "seeded-practice-review-heading")
      XCTAssertTrue(heading.isHittable)
      let size = testCase.hasSuffix("AX") ? "largest" : "normal"
      capturePracticeTour("guided-seeded-practice-review-" + size, app)
    }
    close(made: 7, rows: ["d:1", "p:1"], app)
  }

  private func recheckJourney(_ testCase: String) {
    let app = launch(testCase)
    files(made: 6, kept: 0, app)
    history(["p:1"], app)
    activate("cadence.guided.recheck.start", app)
    waitLabel(app.staticTexts["cadence.word"], "ball")
    waitLabel(
      app.staticTexts["cadence.guided.first-observation"],
      "First review: Word matched. Word checks cannot identify which sound was made.")
    XCTAssertFalse(app.buttons["cadence.replay"].exists)
    checks(count: 5, app)
    record(app)
    activate("cadence.word-check", app)
    checks(count: 6, app)
    activate("cadence.guided.finish-stage", app)
    XCTAssertTrue(app.buttons["cadence.guided.done"].waitForExistence(timeout: 5))
    for (index, id) in entryIDs.enumerated() {
      let row = app.staticTexts["cadence.guided.paired." + id]
      XCTAssertTrue(row.waitForExistence(timeout: 5))
      scrollTo(row, app, targetTag: "paired" + String(index))
      XCTAssertTrue(row.isHittable)
      XCTAssertTrue(row.label.contains(words[index]))
      XCTAssertTrue(row.label.contains("First review: Word matched"))
      XCTAssertTrue(
        row.label.contains(index == 0 ? "Recheck: Word matched" : "Recheck: Not reached"))
      XCTAssertGreaterThan(row.frame.height, 0)
      XCTAssertLessThanOrEqual(row.frame.maxX, app.windows.firstMatch.frame.maxX)
    }
    if ProcessInfo.processInfo.environment["CADENCE_TOUR_DIR"] != nil {
      let size = testCase.hasSuffix("AX") ? "largest" : "normal"
      capturePracticeTour("guided-seeded-summary-row-" + size, app)
      let heading = app.staticTexts["Your word observations"]
      scrollTo(heading, app, targetTag: "seeded-summary-heading")
      XCTAssertTrue(heading.isHittable)
      capturePracticeTour("guided-seeded-summary-heading-" + size, app)
    }
    files(made: 7, kept: 0, app)
    history(["p:1"], app)
    close(made: 7, rows: ["p:1"], app, button: "cadence.guided.done")
  }

  private func cancelJourney(_ testCase: String) {
    let app = launch(testCase)
    activate("cadence.guided.start", app)
    record(app)
    activate("cadence.word-check", app)
    checks(count: 1, pending: 1, app)
    XCTAssertFalse(app.buttons["cadence.guided.finish-stage"].isEnabled)
    activate("cadence.word-check-cancel", app)
    checks(count: 1, pending: 1, cancelled: 1, app)
    files(made: 1, kept: 1, app)
    XCTAssertFalse(app.buttons["cadence.record-another"].isEnabled)
    activate("cadence.generated-guided.release", app)
    checks(count: 1, cancelled: 1, app)
    activate("cadence.guided.finish-stage", app)
    files(made: 1, kept: 0, app)
    XCTAssertTrue(
      app.buttons["cadence.guided.select." + entryIDs[0]].label.contains(
        "First review: Check cancelled"))
    XCTAssertTrue(
      app.buttons["cadence.guided.select." + entryIDs[1]].label.contains(
        "First review: Not reached"))
    history([], app)
    close(made: 1, rows: [], app)
  }

  private func heldCloseJourney(_ testCase: String) {
    let app = launch(testCase)
    activate("cadence.guided.start", app)
    record(app)
    activate("cadence.word-check", app)
    checks(count: 1, pending: 1, app)
    activate("cadence.guided.close", app)
    checks(count: 1, pending: 1, cancelled: 1, app)
    XCTAssertFalse(app.staticTexts["cadence.generated-guided.closed"].exists)
    files(made: 1, kept: 1, app)
    history([], app)
    activate("cadence.generated-guided.release", app)
    assertClosed(made: 1, rows: [], app)
    app.terminate()
  }

  /// Typed fixture outcome only: no model work or elapsed 15-second deadline.
  private func timeoutJourney(_ testCase: String) {
    let app = launch(testCase)
    activate("cadence.guided.start", app)
    record(app)
    checks(count: 0, app)
    activate("cadence.word-check", app)
    checks(count: 1, app)
    let result = app.staticTexts["cadence.word-check-result"]
    waitLabel(result, "Word check took too long. Your recording is still here.")
    XCTAssertFalse(app.buttons["cadence.word-check"].isEnabled)
    files(made: 1, kept: 1, app)
    history([], app)
    scrollTo(result, app, targetTag: "timeoutResult")
    XCTAssertTrue(result.isHittable)
    attach(app, testCase + "-current-take")

    activate("cadence.replay", app)
    waitLabel(app.buttons["cadence.replay"], "Stop playback")
    files(made: 1, kept: 1, playbackStarts: 1, app)
    activate("cadence.replay", app)
    waitLabel(app.buttons["cadence.replay"], "Play recording")
    waitLabel(result, "Word check took too long. Your recording is still here.")
    checks(count: 1, app)
    activate("cadence.guided.continue", app)
    waitLabel(app.staticTexts["cadence.word"], "pig")
    activate("cadence.guided.finish-stage", app)
    files(made: 1, kept: 0, playbackStarts: 1, app)
    let ball = app.buttons["cadence.guided.select." + entryIDs[0]]
    XCTAssertTrue(ball.waitForExistence(timeout: 5))
    XCTAssertTrue(ball.label.contains("First review: Word check took too long"))
    history([], app)
    activate("cadence.guided.select." + entryIDs[0], app)
    activate("cadence.guided.practice.start", app)
    waitLabel(app.staticTexts["cadence.word"], "ball")
    let first = app.staticTexts["cadence.guided.first-observation"]
    let frozen =
      "First review: Word check took too long. "
      + "Word checks cannot identify which sound was made."
    waitLabel(first, frozen)
    XCTAssertFalse(app.buttons["cadence.replay"].exists)
    record(app)
    files(made: 2, kept: 1, playbackStarts: 1, app)
    checks(count: 1, app)
    XCTAssertFalse(result.exists)
    XCTAssertTrue(app.buttons["cadence.word-check"].isEnabled)
    waitLabel(first, frozen)
    scrollTo(first, app, targetTag: "firstObservation")
    XCTAssertTrue(first.isHittable)
    attach(app, testCase + "-fresh-practice")
    activate("cadence.guided.continue", app)
    files(made: 2, kept: 0, playbackStarts: 1, app)
    history(["b:1"], app)
    activate("cadence.guided.recheck.start", app)
    waitLabel(app.staticTexts["cadence.word"], "ball")
    waitLabel(first, frozen)
    checks(count: 1, app)
    XCTAssertFalse(app.buttons["cadence.replay"].exists)
    activate("cadence.guided.finish-stage", app)
    let paired = app.staticTexts["cadence.guided.paired." + entryIDs[0]]
    XCTAssertTrue(paired.waitForExistence(timeout: 5))
    XCTAssertTrue(paired.label.contains("First review: Word check took too long"))
    XCTAssertTrue(paired.label.contains("Recheck: Skipped"))
    scrollTo(paired, app, targetTag: "paired0")
    XCTAssertTrue(paired.isHittable)
    attach(app, testCase + "-paired-summary")
    checks(count: 1, app)
    close(made: 2, rows: ["b:1"], playbackStarts: 1, app, button: "cadence.guided.done")
  }

  private func attach(_ app: XCUIApplication, _ name: String) {
    let attachment = XCTAttachment(screenshot: app.screenshot())
    attachment.name = name
    attachment.lifetime = .keepAlways
    add(attachment)
  }

  private func record(_ app: XCUIApplication) {
    activate("cadence.record", app)
    activate("cadence.stop", app)
    let replayExists = app.buttons["cadence.replay"].waitForExistence(timeout: 5)
    if !replayExists { capturePracticeFailure(app) }
    XCTAssertTrue(replayExists)
  }
  private func files(made: Int, kept: Int, playbackStarts: Int = 0, _ app: XCUIApplication) {
    waitLabel(
      app.staticTexts["cadence.generated-guided.files"],
      "Generated files: made \(made), kept \(kept) · permission requests \(made) · playback starts \(playbackStarts)"
    )
  }
  private func checks(count: Int, pending: Int = 0, cancelled: Int = 0, _ app: XCUIApplication) {
    waitLabel(
      app.staticTexts["cadence.generated-guided.checks"],
      "Generated checks: \(count), pending \(pending), cancelled \(cancelled), borrowed \(pending)")
  }
  private func history(_ rows: [String], _ app: XCUIApplication) {
    waitLabel(
      app.staticTexts["cadence.generated-guided.history"],
      "Generated history: \(rows.count) rows [\(rows.sorted().joined(separator: ","))]")
  }
  private func close(
    made: Int, rows: [String], playbackStarts: Int = 0, _ app: XCUIApplication,
    button: String = "cadence.guided.close"
  ) {
    activate(button, app)
    assertClosed(made: made, rows: rows, playbackStarts: playbackStarts, app)
    app.terminate()
  }
  private func assertClosed(
    made: Int, rows: [String], playbackStarts: Int = 0, _ app: XCUIApplication
  ) {
    XCTAssertTrue(app.staticTexts["cadence.generated-guided.closed"].waitForExistence(timeout: 5))
    waitLabel(
      app.staticTexts["cadence.generated-guided.closed-files"],
      "Generated files: made \(made), kept 0 · permission requests \(made) · playback starts \(playbackStarts)"
    )
    waitLabel(
      app.staticTexts["cadence.generated-guided.closed-history"],
      "Generated history: \(rows.count) rows [\(rows.sorted().joined(separator: ","))]")
  }
  private func activate(_ id: String, _ app: XCUIApplication) {
    let operation = trace.begin(kind: "activate", targetTag: GuidedScrollTrace.targetTag(id))
    let button = app.buttons[id]
    XCTAssertTrue(button.exists || button.waitForExistence(timeout: 5), id)
    if id == "cadence.generated-guided.release" || id == "cadence.guided.close"
      || id == "guided-research-details-close" {
      XCTAssertTrue(button.isHittable, id)
    } else {
      scrollTo(button, app, targetTag: GuidedScrollTrace.targetTag(id))
    }
    let hittable = button.isHittable
    XCTAssertTrue(hittable, id)
    XCTAssertTrue(button.isEnabled, id)
    let frame = button.frame
    XCTAssertGreaterThanOrEqual(frame.height, 44, id)
    trace.step(operation, index: 0, frame: frame, hittable: hittable)
    button.tap()
    trace.end(operation, outcome: "activated")
  }

  private func bannerBottom(_ app: XCUIApplication) -> CGFloat {
    let detailsClose = app.buttons["guided-research-details-close"]
    if detailsClose.exists { return detailsClose.frame.maxY }
    let release = app.buttons["cadence.generated-guided.release"]
    var bottom = app.staticTexts["cadence.generated-guided.banner"].frame.maxY
    for id in bannerIDs where app.staticTexts[id].exists {
      bottom = max(bottom, app.staticTexts[id].frame.maxY)
    }
    if release.exists { bottom = max(bottom, release.frame.maxY) }
    // Close remains above the active scroll throughout the guided journey.
    // Exclude its overlay so a hittable target cannot be tapped underneath it.
    let close = app.buttons["cadence.guided.close"]
    if close.exists { bottom = max(bottom, close.frame.maxY) }
    return bottom
  }

  private func scrollTo(_ target: XCUIElement, _ app: XCUIApplication, targetTag: String) {
    let operation = trace.begin(kind: "scroll", targetTag: targetTag)
    let detailsScroll = app.scrollViews["guided-research-details-scroll"]
    let scroll = detailsScroll.exists ? detailsScroll : app.scrollViews.firstMatch
    // The generated host's inset and viewport stay fixed during this one scroll action.
    // Read their bounds once; the target's frame and hittability remain fresh on every drag.
    let viewport = scroll.frame
    let top = max(viewport.minY, bannerBottom(app)) + 8
    let bottom = min(viewport.maxY, app.windows.firstMatch.frame.maxY) - 8
    let visibleHeight = bottom - top
    guard visibleHeight > 0 else {
      trace.end(operation, outcome: "invalidViewport")
      XCTFail("No unobscured guided viewport is available")
      return
    }
    var previousFrame: CGRect?
    var previousTravel: CGFloat = 0
    var previousAbove: Bool?
    for step in 0..<24 {
      let frame = target.frame
      // Dynamic Type text and choice buttons can be taller than the viewport.
      // Align the leading edge while still requiring the actual target to be hittable;
      // demanding both edges be visible would alternate drags without a possible fit.
      // Full-label and any explicit frame assertions in the journeys remain unchanged.
      let oversizedTarget = frame.height > visibleHeight
      let eligible =
        frame.minY >= top
        && (oversizedTarget ? frame.minY <= top + visibleHeight * 0.2 : frame.maxY <= bottom)
      // Preserve the original short circuit: no hittability query when geometry fails.
      let hittable: Bool? = eligible ? target.isHittable : nil
      if eligible, hittable == true {
        trace.step(
          operation, index: step, frame: frame, viewport: viewport, top: top,
          bottom: bottom, eligible: eligible, hittable: hittable)
        trace.end(operation, outcome: "hittable")
        return
      }
      // Near-fit targets have a narrow containment interval. Aim at its midpoint
      // without a minimum step that could repeatedly jump across the whole interval.
      let desiredTop = oversizedTarget ? top : top + (visibleHeight - frame.height) / 2
      let above = frame.minY < desiredTop
      let distance = abs(frame.minY - desiredTop)
      var travel =
        oversizedTarget
        ? min(max(distance, visibleHeight * 0.2), visibleHeight * 0.6)
        : min(distance, visibleHeight * 0.6)
      // Estimate only the preceding drag's lost movement, not a cumulative offset.
      // Ignore reflow, reversal and overshoot; they do not measure touch slop.
      if !oversizedTarget, distance > 0, distance <= 24,
        let previousFrame, previousTravel > 0, previousAbove == above,
        previousFrame.minX == frame.minX, previousFrame.size == frame.size
      {
        let movement = (frame.minY - previousFrame.minY) * (above ? 1 : -1)
        if movement >= 0, movement <= previousTravel {
          let lostMovement = min(previousTravel - movement, 24)
          travel = min(distance + lostMovement, visibleHeight * 0.6)
        }
      }
      trace.step(
        operation, index: step, frame: frame, viewport: viewport, top: top,
        bottom: bottom, eligible: eligible, hittable: hittable, above: above, travel: travel)
      // At the desired position, an unhittable target stays unproved; do not tap it.
      if travel == 0 { continue }
      let centerY = (top + bottom) / 2
      let startY = centerY + (above ? -travel / 2 : travel / 2)
      let finishY = centerY + (above ? travel / 2 : -travel / 2)
      // A short drag can resolve as a tap. Keep the entire vertical gesture in
      // an observed blank gutter, outside every button in this scroll and the target.
      let buttonFrames = scroll.buttons.allElementsBoundByIndex.map { $0.frame } + [frame]
      guard
        let dragX = gutterX(viewport, window: app.windows.firstMatch.frame, frames: buttonFrames)
      else {
        trace.end(operation, outcome: "noBlankGutter")
        XCTFail("No blank guided scroll gutter is available")
        return
      }
      previousFrame = frame
      previousTravel = travel
      previousAbove = above
      let origin = scroll.coordinate(withNormalizedOffset: .zero)
      let start = origin.withOffset(CGVector(dx: dragX - viewport.minX, dy: startY - viewport.minY))
      let finish = origin.withOffset(
        CGVector(dx: dragX - viewport.minX, dy: finishY - viewport.minY))
      // Use a slow drag and held release to reduce flick-like overshoot.
      // TRACE-v4 observed frame movement exceeding the requested travel and
      // oscillating across the oversized target’s eligible leading-edge band.
      start.press(
        forDuration: 0.01, thenDragTo: finish, withVelocity: .slow, thenHoldForDuration: 0.2)
    }
    trace.end(operation, outcome: "exhausted")
    XCTFail("Guided control did not enter the unobscured viewport: \(targetTag)")
  }

  private func gutterX(_ viewport: CGRect, window: CGRect, frames: [CGRect]) -> CGFloat? {
    let left = max(viewport.minX, window.minX)
    let right = min(viewport.maxX, window.maxX)
    guard left.isFinite, right.isFinite, right > left else { return nil }
    var leading = right
    var trailing = left
    var hasFrame = false
    for frame in frames {
      guard frame.minX.isFinite, frame.maxX.isFinite, frame.width.isFinite,
        frame.height.isFinite, frame.width >= 0, frame.height >= 0
      else { return nil }
      // Empty accessibility frames do not describe a hit region.
      guard frame.width > 0, frame.height > 0 else { continue }
      if frame.maxX > left, frame.minX < right {
        hasFrame = true
        leading = min(leading, max(left, frame.minX))
        trailing = max(trailing, min(right, frame.maxX))
      }
    }
    guard hasFrame else { return nil }
    let leadingWidth = leading - left
    let trailingWidth = right - trailing
    // Eight points from each edge at minimum; never fall back inside a button.
    if leadingWidth >= 16, leadingWidth >= trailingWidth { return left + leadingWidth / 2 }
    if trailingWidth >= 16 { return right - trailingWidth / 2 }
    return nil
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

}

/// Generated-host test telemetry only. Bounded enums and numbers; no UI tree or labels.
@MainActor
private final class GuidedScrollTrace {
  private var caseTag: String?
  private var ordinal = 0
  private var operations: [Int: (String, String, Double)] = [:]
  private static let cases: Set<String> = [
    "setup", "setupAX", "practice", "practiceAX", "recheck", "recheckAX",
    "heldFinish", "heldFinishAX", "heldClose", "heldCloseAX",
    "timeout", "timeoutAX",
  ]
  static func targetTag(_ id: String) -> String {
    let fixed = [
      "cadence.guided.start": "start", "cadence.word-check": "check",
      "cadence.word-check-cancel": "cancelCheck", "cadence.guided.continue": "next",
      "cadence.guided.skip": "skip", "cadence.guided.finish-stage": "finishStage",
      "cadence.guided.practice.start": "startPractice", "cadence.guided.recheck.start": "recheck",
      "cadence.guided.done": "done", "cadence.guided.close": "close",
      "cadence.generated-guided.release": "release", "cadence.record": "record",
      "cadence.stop": "stop", "cadence.replay": "replay",
    ]
    if let tag = fixed[id] { return tag }
    let ids = [
      "b-beginning-ball", "p-beginning-pig", "m-beginning-moon", "t-beginning-tiger",
      "d-beginning-dog",
    ]
    for (index, entry) in ids.enumerated() where id == "cadence.guided.select." + entry {
      return "select" + String(index)
    }
    return "unknown"
  }
  private static let targets: Set<String> = [
    "start", "check", "cancelCheck", "next", "skip", "finishStage", "startPractice", "recheck",
    "done", "close", "release", "record", "stop", "select0", "select1", "select2", "select3",
    "select4",
    "paired0", "paired1", "paired2", "paired3", "paired4",
    "replay", "timeoutResult", "firstObservation",
  ]
  func reset(caseTag: String) {
    self.caseTag = Self.cases.contains(caseTag) ? caseTag : nil
    ordinal = 0
    operations = [:]
  }
  func begin(kind: String, targetTag: String) -> Int? {
    guard caseTag != nil, Self.targets.contains(targetTag), ordinal < 256 else { return nil }
    ordinal += 1
    operations[ordinal] = (kind, targetTag, ProcessInfo.processInfo.systemUptime)
    emit(ordinal, event: "start")
    return ordinal
  }
  func step(
    _ operation: Int?, index: Int, frame: CGRect, viewport: CGRect? = nil,
    top: CGFloat? = nil, bottom: CGFloat? = nil, eligible: Bool? = nil,
    hittable: Bool? = nil, above: Bool? = nil, travel: CGFloat? = nil
  ) {
    guard let operation, (0..<24).contains(index) else { return }
    emit(
      operation, event: "step", index: index, frame: frame, viewport: viewport,
      top: top, bottom: bottom, eligible: eligible, hittable: hittable, above: above, travel: travel
    )
  }
  func end(_ operation: Int?, outcome: String) {
    guard let operation else { return }
    emit(operation, event: "end", outcome: outcome)
    operations.removeValue(forKey: operation)
  }
  private func emit(
    _ operation: Int, event: String, index: Int? = nil, outcome: String? = nil,
    frame: CGRect? = nil, viewport: CGRect? = nil, top: CGFloat? = nil,
    bottom: CGFloat? = nil, eligible: Bool? = nil, hittable: Bool? = nil,
    above: Bool? = nil, travel: CGFloat? = nil
  ) {
    guard let caseTag, let (kind, target, started) = operations[operation] else { return }
    let elapsed = ProcessInfo.processInfo.systemUptime - started
    func rectangle(_ value: CGRect?) -> Any {
      guard let value else { return NSNull() }
      return [
        Double(value.origin.x), Double(value.origin.y), Double(value.width), Double(value.height),
      ]
    }
    var numeric: [Double] = [elapsed]
    for rectangle in [frame, viewport].compactMap({ $0 }) {
      numeric.append(contentsOf: [
        Double(rectangle.origin.x), Double(rectangle.origin.y),
        Double(rectangle.width), Double(rectangle.height),
      ])
    }
    for coordinate in [top, bottom, travel].compactMap({ $0 }) {
      numeric.append(Double(coordinate))
    }
    guard numeric.allSatisfy({ $0.isFinite && abs($0) <= 1_000_000 }), elapsed >= 0, elapsed <= 3600
    else { return }
    let object: [String: Any] = [
      "version": 2, "host": "generated", "case": caseTag, "operation": operation,
      "kind": kind, "target": target, "event": event, "step": index.map { $0 as Any } ?? NSNull(),
      "outcome": outcome.map { $0 as Any } ?? NSNull(), "elapsed": elapsed,
      "frame": rectangle(frame), "viewport": rectangle(viewport),
      "top": top.map { Double($0) as Any } ?? NSNull(),
      "bottom": bottom.map { Double($0) as Any } ?? NSNull(),
      "eligible": eligible.map { $0 as Any } ?? NSNull(),
      "hittable": hittable.map { $0 as Any } ?? NSNull(),
      "above": above.map { $0 as Any } ?? NSNull(),
      "travel": travel.map { Double($0) as Any } ?? NSNull(),
    ]
    guard let bytes = try? JSONSerialization.data(withJSONObject: object, options: [.sortedKeys]),
      let line = String(data: bytes, encoding: .utf8)
    else { return }
    print("CADENCE_GUIDED_SCROLL_TRACE:" + line)
  }
}
