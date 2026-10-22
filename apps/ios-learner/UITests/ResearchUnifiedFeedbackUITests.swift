import XCTest

/// Actual simulator UI using visibly labelled generated PCM and invented replies.
/// No SystemAudioCapturer, microphone, camera, sockets or speech model is used.
@MainActor
final class ResearchUnifiedFeedbackUITests: XCTestCase {
  func testWordThenSoundKeepsBothResultsOnOneTakeAndContextChangeClearsThem() throws {
    let app = launch("combined")
    configureAdult(app)
    recordAndStop(app)
    activate("feedback-check", app)
    XCTAssertTrue(app.staticTexts["feedback-state-result-matched"].waitForExistence(timeout: 5))
    activate("feedback-check-sound", app)
    XCTAssertTrue(app.staticTexts["feedback-sound-state-result-bw"].waitForExistence(timeout: 5))
    XCTAssertTrue(app.staticTexts["feedback-state-result-matched"].exists)
    attach(app, "unified-generated-word-and-sound-same-take")
    let context = control("feedback-context", app)
    scrollTo(context, app)
    context.tap()
    XCTAssertTrue(app.buttons["Child, age 9"].waitForExistence(timeout: 3))
    app.buttons["Child, age 9"].tap()
    XCTAssertTrue(app.staticTexts["feedback-state-ready"].exists)
    XCTAssertFalse(app.staticTexts["feedback-state-result-matched"].exists)
    XCTAssertFalse(app.staticTexts["feedback-sound-state-result-bw"].exists)
    XCTAssertFalse(app.buttons["feedback-replay"].exists)
    XCTAssertTrue(app.staticTexts["feedback-sound-state-adult-only"].exists)
    XCTAssertFalse(control("feedback-sound-adult", app).exists)
    XCTAssertFalse(control("feedback-sound-opt-in", app).exists)
    attach(app, "unified-generated-child-context-clears-take")
    closeToHome(app)
  }

  func testSoundThenWordKeepsBothResultsWithoutAnotherRecording() throws {
    let app = launch("combined")
    configureAdult(app)
    recordAndStop(app)
    activate("feedback-check-sound", app)
    XCTAssertTrue(app.staticTexts["feedback-sound-state-result-bw"].waitForExistence(timeout: 5))
    activate("feedback-check", app)
    XCTAssertTrue(app.staticTexts["feedback-state-result-matched"].waitForExistence(timeout: 5))
    XCTAssertTrue(app.staticTexts["feedback-sound-state-result-bw"].exists)
    XCTAssertFalse(app.buttons["feedback-check-sound"].exists)
    attach(app, "unified-generated-sound-before-word-same-take")
    closeToHome(app)
  }

  func testServerCleanupPauseKeepsLocalReplayAvailable() throws {
    let app = launch("cleanup")
    configureAdult(app)
    recordAndStop(app)
    activate("feedback-check", app)
    XCTAssertTrue(
      app.staticTexts["feedback-state-result-service-cleanup"].waitForExistence(timeout: 5))
    let replay = app.buttons["feedback-replay"]
    scrollTo(replay, app)
    XCTAssertTrue(replay.isEnabled)
    XCTAssertTrue(replay.isHittable)
    XCTAssertFalse(app.buttons["feedback-check"].exists)
    XCTAssertFalse(app.buttons["feedback-check-sound"].exists)
    attach(app, "unified-generated-server-cleanup-pause-local-replay")
    closeToHome(app)
  }

  private func closeToHome(_ app: XCUIApplication) {
    app.buttons["feedback-close"].tap()
    XCTAssertTrue(app.buttons["cadence.guided-word.start"].waitForExistence(timeout: 5))
    XCTAssertFalse(app.staticTexts["feedback-title"].exists)
  }

  private func launch(_ fixture: String) -> XCUIApplication {
    continueAfterFailure = false
    let app = XCUIApplication()
    app.launchArguments = ["-CadenceFeedbackMode", "-CadenceUnifiedFeedbackUITestCase", fixture]
    // Generated admission only; ordinary/physical helpers retain their original arguments.
    app.launchEnvironment.removeValue(forKey: "CADENCE_CONTROLLED_UNIT_HOST")
    app.launchEnvironment.removeValue(forKey: "TEST_RUNNER_CADENCE_CONTROLLED_UNIT_HOST")
    app.launchEnvironment.removeValue(forKey: "TEST_RUNNER_CADENCE_CONTROLLED_UI_HOST")
    app.launchEnvironment["CADENCE_CONTROLLED_UI_HOST"] = "1"
    app.launchArguments += ["-CadenceControlledUIRunID", UUID().uuidString.lowercased()]
    app.launch()
    XCTAssertTrue(app.staticTexts["feedback-ui-test-banner"].waitForExistence(timeout: 5))
    XCTAssertTrue(app.staticTexts["feedback-state-ready"].exists)
    XCTAssertFalse(app.buttons["feedback-stop"].exists)
    XCTAssertFalse(app.buttons["feedback-replay"].exists)
    return app
  }
  private func configureAdult(_ app: XCUIApplication) {
    let context = control("feedback-context", app)
    scrollTo(context, app)
    context.tap()
    XCTAssertTrue(app.buttons["Adult (18+)"].waitForExistence(timeout: 3))
    app.buttons["Adult (18+)"].tap()
    activate("feedback-opt-in", app)
    assertOn("feedback-opt-in", app)
    activate("feedback-sound-adult", app)
    assertOn("feedback-sound-adult", app)
    activate("feedback-sound-opt-in", app)
    assertOn("feedback-sound-opt-in", app)
    XCTAssertFalse(app.buttons["feedback-stop"].exists)
    XCTAssertFalse(app.buttons["feedback-replay"].exists)
  }
  private func recordAndStop(_ app: XCUIApplication) {
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
    attach(app, "unified-before-" + id)
    XCTAssertTrue(target.isHittable, id)
    XCTAssertTrue(target.isEnabled, id)
    target.tap()
  }
  private func assertOn(_ id: String, _ app: XCUIApplication) {
    let target = control(id, app)
    let on = XCTNSPredicateExpectation(
      predicate: NSPredicate(format: "value == %@", "On"), object: target)
    XCTAssertEqual(XCTWaiter.wait(for: [on], timeout: 3), .completed, id)
    attach(app, "unified-option-on-" + id)
  }
  private func scrollTo(_ target: XCUIElement, _ app: XCUIApplication) {
    // XCUI can report a partially clipped SwiftUI switch as hittable, then tap
    // its offscreen center. Require the whole control below the fixed banner.
    let scroll = app.scrollViews.firstMatch
    for _ in 0..<24 {
      let viewport = scroll.frame
      let top = max(viewport.minY, app.staticTexts["feedback-ui-test-banner"].frame.maxY) + 8
      let bottom = min(viewport.maxY, app.windows.firstMatch.frame.maxY) - 8
      let frame = target.frame
      if target.isHittable && frame.minY >= top && frame.maxY <= bottom { return }
      // Long content needs ordinary larger drags for distant controls. Keep every
      // gesture inside the unobscured viewport and use gentler moves near the target.
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

  func testSelectedFocusChangesOccurrenceWithUnsetContextAndNoMediaStarted() throws {
    let app = launch("listening")
    let cue = app.staticTexts["feedback-example-cue"]
    XCTAssertTrue(cue.label.contains("b followed by r"))
    XCTAssertEqual(control("feedback-opt-in", app).value as? String, "Off")
    let context = control("feedback-context", app)
    XCTAssertTrue(
      context.label.contains("Not set") || (context.value as? String)?.contains("Not set") == true)
    activate("feedback-word-picker", app)
    XCTAssertTrue(app.buttons["baby · first b sound"].waitForExistence(timeout: 3))
    app.buttons["baby · first b sound"].tap()
    XCTAssertTrue(cue.label.contains("first b sound in baby"))
    let first = cue.label
    activate("feedback-word-picker", app)
    XCTAssertTrue(app.buttons["baby · second b sound"].waitForExistence(timeout: 3))
    app.buttons["baby · second b sound"].tap()
    XCTAssertTrue(cue.label.contains("second b sound in baby"))
    XCTAssertNotEqual(cue.label, first)
    XCTAssertFalse(app.buttons["feedback-stop"].exists)
    XCTAssertFalse(app.buttons["feedback-replay"].exists)
    XCTAssertFalse(app.buttons["feedback-check"].exists)
    XCTAssertFalse(app.staticTexts["feedback-example-state-playing"].exists)
    XCTAssertEqual(control("feedback-opt-in", app).value as? String, "Off")
    scrollTo(cue, app)
    XCTAssertTrue(cue.isHittable)
    attach(app, "generated-selected-second-b-focus-no-media")
    closeToHome(app)
  }

  func testMissingExampleMetadataKeepsSelectedFocusWithoutPlayOrCredits() throws {
    let app = launch("missingExample")
    let cue = app.staticTexts["feedback-example-cue"]
    XCTAssertTrue(cue.label.contains("b followed by r in bread"))
    XCTAssertTrue(
      cue.label.hasSuffix("Say the whole word, then replay your try and listen for that sound."))
    XCTAssertEqual(
      app.staticTexts["feedback-example-unavailable"].label,
      "Example recording isn’t available for this word.")
    XCTAssertFalse(app.buttons["feedback-example"].exists)
    XCTAssertFalse(control("feedback-example-credit", app).exists)
    XCTAssertFalse(app.staticTexts["feedback-example-generated"].exists)
    XCTAssertTrue(app.buttons["feedback-record"].exists)
    XCTAssertFalse(app.buttons["feedback-stop"].exists)
    XCTAssertFalse(app.buttons["feedback-replay"].exists)
    XCTAssertFalse(app.buttons["feedback-check"].exists)
    scrollTo(cue, app)
    XCTAssertTrue(cue.isHittable)
    attach(app, "generated-missing-example-selected-focus")
    closeToHome(app)
  }

  func testLongSelectedFocusAtLargestTextLeavesExistingControlsReachable() throws {
    continueAfterFailure = false
    let app = XCUIApplication()
    app.launchArguments = [
      "-CadenceFeedbackMode", "-CadenceUnifiedFeedbackUITestCase", "listeningRing",
      "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL",
      "-CadenceControlledUIRunID", UUID().uuidString.lowercased(),
    ]
    app.launchEnvironment.removeValue(forKey: "CADENCE_CONTROLLED_UNIT_HOST")
    app.launchEnvironment.removeValue(forKey: "TEST_RUNNER_CADENCE_CONTROLLED_UNIT_HOST")
    app.launchEnvironment.removeValue(forKey: "TEST_RUNNER_CADENCE_CONTROLLED_UI_HOST")
    app.launchEnvironment["CADENCE_CONTROLLED_UI_HOST"] = "1"
    app.launch()
    XCTAssertTrue(app.staticTexts["feedback-ui-test-banner"].waitForExistence(timeout: 5))
    XCTAssertTrue(app.staticTexts["feedback-state-ready"].exists)
    XCTAssertEqual(app.staticTexts["feedback-word"].label, "ring")
    let cue = app.staticTexts["feedback-example-cue"]
    XCTAssertTrue(cue.label.contains("one sound, without a separate g"))
    XCTAssertTrue(
      cue.label.hasSuffix(
        "Listen to the whole example, say the whole word, then play your own try."))
    for id in ["feedback-record", "feedback-example", "feedback-example-credit"] {
      let target = control(id, app)
      scrollTo(target, app)
      XCTAssertTrue(target.isHittable, id)
      XCTAssertGreaterThanOrEqual(target.frame.height, 44, id)
      let viewport = app.scrollViews.firstMatch.frame
      XCTAssertGreaterThanOrEqual(target.frame.minY, viewport.minY, id)
      XCTAssertLessThanOrEqual(target.frame.maxY, viewport.maxY, id)
      attach(app, "generated-largest-text-ring-focus-" + id)
    }
    XCTAssertFalse(app.buttons["feedback-stop"].exists)
    XCTAssertFalse(app.buttons["feedback-replay"].exists)
    XCTAssertFalse(app.staticTexts["feedback-example-state-playing"].exists)
    closeToHome(app)
  }

  func testMovedWordMenuSelectsSecondBabyOccurrenceAtNormalText() throws {
    let app = launch("listening")
    XCTAssertEqual(control("feedback-word-picker", app).value as? String, "bread · r sound")
    chooseCanonicalWord("baby · second b sound", app)
    assertWordChooser("baby · second b sound", word: "baby", app)
    let cue = app.staticTexts["feedback-example-cue"]
    XCTAssertTrue(cue.label.contains("second b sound in baby, in the middle"))
    assertUnsetContextAndNoMedia(app)
    attach(app, "generated-normal-word-second-b-full-control")
    scrollTo(cue, app)
    attach(app, "generated-normal-second-b-selected-focus")
    closeToHome(app)
  }

  func testMovedWordMenuSelectsSecondBackpackOccurrenceAtLargestText() throws {
    let app = launchLargestWordMenu()
    chooseCanonicalWord("backpack · second k sound", app, inline: true)
    assertWordChooser("backpack · second k sound", word: "backpack", app)
    let cue = app.staticTexts["feedback-example-cue"]
    XCTAssertTrue(cue.label.contains("last k sound in backpack, at the very end"))
    XCTAssertFalse(cue.label.contains("first k sound"))
    assertUnsetContextAndNoMedia(app)
    attach(app, "generated-largest-word-second-k-full-control")
    closeToHome(app)
  }

  func testMovedWordMenuReachesLowerRingChoiceAtLargestText() throws {
    let app = launchLargestWordMenu()
    chooseCanonicalWord("ring · ng sound", app, inline: true)
    assertWordChooser("ring · ng sound", word: "ring", app)
    let cue = app.staticTexts["feedback-example-cue"]
    XCTAssertTrue(cue.label.contains("ng sound at the end of ring"))
    XCTAssertTrue(cue.label.contains("one sound, without a separate g"))
    assertUnsetContextAndNoMedia(app)
    attach(app, "generated-largest-word-menu-selected-lower-ring")
    closeToHome(app)
  }

  func testMovedWordMenuDifferentSelectionClearsGeneratedRetainedReplay() throws {
    let app = launch("listening")
    recordAndStop(app)
    XCTAssertTrue(app.buttons["feedback-replay"].exists)
    XCTAssertEqual(control("feedback-word-picker", app).value as? String, "bread · r sound")
    chooseCanonicalWord("baby · second b sound", app)
    XCTAssertTrue(app.staticTexts["feedback-state-ready"].waitForExistence(timeout: 5))
    assertWordChooser("baby · second b sound", word: "baby", app)
    XCTAssertTrue(
      app.staticTexts["feedback-example-cue"].label.contains("second b sound in baby"))
    XCTAssertTrue(app.buttons["feedback-record"].isEnabled)
    assertUnsetContextAndNoMedia(app)
    attach(app, "generated-word-change-clears-previous-retained-replay")
    closeToHome(app)
  }

  func testInlineWordChoicesRenderAllCanonicalLabelsAndSelectLastTreasureAtLargestText() throws {
    let app = launchLargestWordMenu()
    activate("feedback-word-picker", app)
    XCTAssertTrue(control("feedback-word-choices", app).waitForExistence(timeout: 3))
    XCTAssertTrue(app.buttons["feedback-word-choices-cancel"].exists)
    let labels = [
      "rabbit · r sound", "bread · r sound", "door · r sound", "baby · first b sound",
      "baby · second b sound", "banana · first n sound", "backpack · first k sound",
      "backpack · second k sound", "sky · s sound", "vase · v sound", "yo-yo · first y sound",
      "thumb · th sound", "feather · voiced th sound", "ring · ng sound", "treasure · zh sound",
    ]
    for label in labels { XCTAssertTrue(app.buttons[label].exists, label) }
    chooseInlineCanonicalWord("treasure · zh sound", app)
    XCTAssertEqual(control("feedback-word-picker", app).value as? String, "treasure · zh sound")
    XCTAssertEqual(app.staticTexts["feedback-word"].label, "treasure")
    let cue = app.staticTexts["feedback-example-cue"]
    XCTAssertTrue(cue.label.contains("middle sound in treasure, as in “measure”"))
    assertUnsetContextAndNoMedia(app)
    attach(app, "generated-largest-inline-last-treasure-selected")
    closeToHome(app)
  }

  func testInlineWordChoicesCancelKeepsGeneratedRetainedTakeAtLargestText() throws {
    let app = launchLargestWordMenu()
    recordAndStop(app)
    let review = app.staticTexts["feedback-state-review"]
    let reviewBefore = review.label
    let cue = app.staticTexts["feedback-example-cue"]
    let cueBefore = cue.label
    XCTAssertTrue(cueBefore.contains("b followed by r in bread"))
    let replay = app.buttons["feedback-replay"]
    XCTAssertTrue(replay.exists)
    let replayBefore = replay.label
    activate("feedback-word-picker", app)
    XCTAssertTrue(control("feedback-word-choices", app).waitForExistence(timeout: 3))
    XCTAssertTrue(app.buttons["feedback-word-choices-cancel"].exists)
    activate("feedback-word-choices-cancel", app)
    XCTAssertFalse(control("feedback-word-choices", app).exists)
    assertWordChooser("bread · r sound", word: "bread", app)
    XCTAssertTrue(review.exists)
    XCTAssertEqual(review.label, reviewBefore)
    XCTAssertEqual(cue.label, cueBefore)
    XCTAssertTrue(replay.exists)
    XCTAssertTrue(replay.isEnabled)
    XCTAssertEqual(replay.label, replayBefore)
    XCTAssertTrue(replay.label.hasPrefix("Replay "))
    let context = control("feedback-context", app)
    XCTAssertTrue(
      context.label.contains("Not set") || (context.value as? String)?.contains("Not set") == true)
    XCTAssertEqual(control("feedback-opt-in", app).value as? String, "Off")
    XCTAssertFalse(control("feedback-sound-adult", app).exists)
    XCTAssertFalse(control("feedback-sound-opt-in", app).exists)
    XCTAssertFalse(app.buttons["feedback-stop"].exists)
    XCTAssertFalse(app.buttons["feedback-check"].exists)
    XCTAssertFalse(app.buttons["feedback-check-sound"].exists)
    XCTAssertFalse(app.staticTexts["feedback-example-state-playing"].exists)
    XCTAssertFalse(control("feedback-example-progress", app).exists)
    XCTAssertFalse(app.staticTexts["feedback-replay-latest-playing"].exists)
    XCTAssertFalse(app.staticTexts["feedback-replay-earlier-playing"].exists)
    attach(app, "generated-largest-inline-cancel-keeps-word-cue-and-retained-replay")
    closeToHome(app)
  }

  private func launchLargestWordMenu() -> XCUIApplication {
    continueAfterFailure = false
    let app = XCUIApplication()
    app.launchArguments = [
      "-CadenceFeedbackMode", "-CadenceUnifiedFeedbackUITestCase", "listening",
      "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL",
      "-CadenceControlledUIRunID", UUID().uuidString.lowercased(),
    ]
    app.launchEnvironment.removeValue(forKey: "CADENCE_CONTROLLED_UNIT_HOST")
    app.launchEnvironment.removeValue(forKey: "TEST_RUNNER_CADENCE_CONTROLLED_UNIT_HOST")
    app.launchEnvironment.removeValue(forKey: "TEST_RUNNER_CADENCE_CONTROLLED_UI_HOST")
    app.launchEnvironment["CADENCE_CONTROLLED_UI_HOST"] = "1"
    app.launch()
    XCTAssertTrue(app.staticTexts["feedback-ui-test-banner"].waitForExistence(timeout: 5))
    XCTAssertTrue(app.staticTexts["feedback-state-ready"].exists)
    XCTAssertEqual(app.staticTexts["feedback-word"].label, "bread")
    XCTAssertEqual(control("feedback-word-picker", app).value as? String, "bread · r sound")
    XCTAssertFalse(app.buttons["feedback-stop"].exists)
    XCTAssertFalse(app.buttons["feedback-replay"].exists)
    return app
  }

  /// Choose the path from launch intent; normal menus retain their observed-frame drags.
  /// Inline choices use the page's existing scroll, without fallback or fixture selection.
  private func chooseCanonicalWord(
    _ label: String, _ app: XCUIApplication, inline: Bool = false
  ) {
    activate("feedback-word-picker", app)
    if inline {
      chooseInlineCanonicalWord(label, app)
      return
    }
    attach(app, "generated-native-word-menu-open-" + label)
    let target = app.buttons[label]
    // Every supplied journey starts on bread. Wait for an actual menu option, not the
    // selector's value, before inspecting the popup's asynchronous presentation.
    guard app.buttons["bread · r sound"].waitForExistence(timeout: 3) else {
      XCTFail(
        "Current bread option did not appear in the native Word menu: "
          + canonicalWordMenuDiagnostics(app))
      return
    }
    for _ in 0..<8 {
      let window = app.windows.firstMatch.frame
      if target.exists, target.isHittable, window.contains(target.frame) {
        attach(app, "generated-native-word-menu-reachable-" + label)
        target.tap()
        return
      }
      let options = app.buttons.matching(
        NSPredicate(format: "label CONTAINS %@ AND label ENDSWITH %@", " · ", " sound")
      ).allElementsBoundByIndex.compactMap { option -> (element: XCUIElement, frame: CGRect)? in
        guard option.isHittable else { return nil }
        let frame = option.frame
        guard frame.width > 0, frame.height > 0, window.contains(frame) else { return nil }
        return (option, frame)
      }.sorted { $0.frame.minY < $1.frame.minY }
      guard let first = options.first, let last = options.last,
        last.frame.midY > first.frame.midY
      else {
        XCTFail(
          "The native Word menu has no observed option span to scroll safely: " + label
            + " " + canonicalWordMenuDiagnostics(app))
        return
      }
      let start = last.element.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5))
      let finish = first.element.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5))
      start.press(forDuration: 0.01, thenDragTo: finish)
    }
    XCTFail(
      "Canonical Word option was not hittable after eight natural menu drags: " + label
        + " " + canonicalWordMenuDiagnostics(app))
  }

  /// The caller explicitly launched accessibility text; a missing inline list must fail.
  private func chooseInlineCanonicalWord(_ label: String, _ app: XCUIApplication) {
    XCTAssertTrue(control("feedback-word-choices", app).waitForExistence(timeout: 3))
    XCTAssertTrue(app.buttons["feedback-word-choices-cancel"].exists)
    let target = app.buttons[label]
    scrollTo(target, app)
    XCTAssertTrue(target.exists, label)
    XCTAssertTrue(target.isHittable, label)
    XCTAssertTrue(target.isEnabled, label)
    XCTAssertGreaterThanOrEqual(target.frame.height, 44, label)
    let viewport = app.scrollViews.firstMatch.frame
    XCTAssertTrue(viewport.contains(target.frame), label)
    XCTAssertTrue(app.windows.firstMatch.frame.contains(target.frame), label)
    attach(app, "generated-inline-word-choice-reachable-" + label)
    target.tap()
    XCTAssertFalse(control("feedback-word-choices", app).exists)
  }

  /// Failure metadata is restricted to public canonical option labels and generated UI geometry.
  private func canonicalWordMenuDiagnostics(_ app: XCUIApplication) -> String {
    let labels = [
      "rabbit · r sound", "bread · r sound", "door · r sound", "baby · first b sound",
      "baby · second b sound", "banana · first n sound", "backpack · first k sound",
      "backpack · second k sound", "sky · s sound", "vase · v sound", "yo-yo · first y sound",
      "thumb · th sound", "feather · voiced th sound", "ring · ng sound", "treasure · zh sound",
    ]
    let observed = labels.compactMap { label -> String? in
      let option = app.buttons[label]
      guard option.exists else { return nil }
      return "\(label): hittable=\(option.isHittable), frame=\(option.frame)"
    }
    return "window=\(app.windows.firstMatch.frame); observed canonical buttons=["
      + observed.joined(separator: "; ") + "]"
  }

  private func assertWordChooser(
    _ value: String, word: String, _ app: XCUIApplication
  ) {
    let chooser = control("feedback-word-picker", app)
    scrollTo(chooser, app)
    XCTAssertEqual(chooser.value as? String, value)
    XCTAssertEqual(app.staticTexts["feedback-word"].label, word)
    XCTAssertTrue(chooser.isHittable)
    XCTAssertTrue(chooser.isEnabled)
    XCTAssertGreaterThanOrEqual(chooser.frame.height, 44)
    let viewport = app.scrollViews.firstMatch.frame
    XCTAssertGreaterThanOrEqual(chooser.frame.minX, viewport.minX)
    XCTAssertLessThanOrEqual(chooser.frame.maxX, viewport.maxX)
    XCTAssertGreaterThanOrEqual(chooser.frame.minY, viewport.minY)
    XCTAssertLessThanOrEqual(chooser.frame.maxY, viewport.maxY)
  }

  private func assertUnsetContextAndNoMedia(_ app: XCUIApplication) {
    let context = control("feedback-context", app)
    XCTAssertTrue(
      context.label.contains("Not set") || (context.value as? String)?.contains("Not set") == true)
    XCTAssertEqual(control("feedback-opt-in", app).value as? String, "Off")
    XCTAssertFalse(control("feedback-sound-adult", app).exists)
    XCTAssertFalse(control("feedback-sound-opt-in", app).exists)
    XCTAssertFalse(app.buttons["feedback-stop"].exists)
    XCTAssertFalse(app.buttons["feedback-replay"].exists)
    XCTAssertFalse(app.buttons["feedback-replay-earlier"].exists)
    XCTAssertFalse(app.buttons["feedback-check"].exists)
    XCTAssertFalse(app.buttons["feedback-check-sound"].exists)
    XCTAssertFalse(app.staticTexts["feedback-example-state-playing"].exists)
    XCTAssertFalse(control("feedback-example-progress", app).exists)
  }

}
