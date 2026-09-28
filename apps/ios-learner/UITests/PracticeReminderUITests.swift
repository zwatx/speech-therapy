import XCTest

/// Existing generated providers only: no real microphone, playback output or model.
@MainActor
final class PracticeReminderUITests: XCTestCase {
  func testCompactSelectedPracticeReminderStaysCanonicalAcrossRetakeAndWord() {
    journey(largeText: false)
  }
  func testLargestTextSelectedPracticeReminderStaysCanonicalAcrossRetakeAndWord() {
    journey(largeText: true)
  }
  func testCompactPracticeReminderSurvivesHeldCheckAndTimeoutRetry() {
    feedbackJourney(largeText: false)
  }
  func testLargestTextPracticeReminderSurvivesHeldCheckAndTimeoutRetry() {
    feedbackJourney(largeText: true)
  }

  private let pigDetail =
    "Bring your lips together, then let out a small puff of air as you start “pig”. Say the whole word comfortably."
  private let breadDetail =
    "Start with your lips together for B, then move straight into R as you say “bread”. Keep the sounds together in one whole word."

  private func feedbackJourney(largeText: Bool) {
    continueAfterFailure = false
    executionTimeAllowance = 480
    let app = XCUIApplication()
    for key in app.launchEnvironment.keys
    where key.hasPrefix("CADENCE_") || key.hasPrefix("TEST_RUNNER_CADENCE_") {
      app.launchEnvironment.removeValue(forKey: key)
    }
    app.launchEnvironment["CADENCE_CONTROLLED_UI_HOST"] = "1"
    app.launchArguments = [
      "-CadenceLocalGuidedMode", "-CadenceLocalGuidedUITestCase",
      largeText ? "practiceTimeoutRetryAX" : "practiceTimeoutRetry",
      "-CadenceControlledUIRunID", UUID().uuidString.lowercased(),
    ]
    let prefix = "generated-reminder-feedback-" + (largeText ? "largest" : "normal")
    addTeardownBlock { @MainActor [weak self] () throws -> Void in
      defer { app.terminate() } // Always run fallback, even if a later teardown assertion fails.
      guard let self else { return }
      if app.state == .runningForeground {
        self.capture(prefix + "-final-before-cleanup", app)
        let checks = app.staticTexts["cadence.generated-guided.checks"]
        let closedFiles = app.staticTexts["cadence.generated-guided.closed-files"]
        var receiptSettled = checks.exists
          && checks.label.contains("pending 0") && checks.label.contains("borrowed 0")
        if closedFiles.exists, closedFiles.label.contains("kept 0") { receiptSettled = true }
        // Cancel alone only marks this fake request; finish its held receipt before Close.
        let release = app.buttons["cadence.generated-guided.release"]
        if release.exists, release.isEnabled, release.isHittable {
          let cancel = app.buttons["cadence.word-check-cancel"]
          if cancel.exists, cancel.isEnabled, cancel.isHittable { cancel.tap() }
          release.tap()
          let settled = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "label CONTAINS %@ AND label CONTAINS %@",
                                   "pending 0", "borrowed 0"),
            object: app.staticTexts["cadence.generated-guided.checks"])
          receiptSettled = XCTWaiter.wait(for: [settled], timeout: 5) == .completed
        }
        self.tryPublicCleanup(prefix + "-teardown", app)
        self.capture(prefix + "-cleanup-result", app, geometry: ["heldReceiptSettled": receiptSettled])
        XCTAssertTrue(receiptSettled, "Held generated receipt did not settle before cleanup")
      }
    }
    app.launch()
    XCTAssertTrue(app.staticTexts["cadence.generated-guided.banner"].waitForExistence(timeout: 5))
    waitLabel(app.staticTexts["cadence.generated-guided.seed"],
      "Generated stage: five settled first checks; no choices preselected")
    activate("cadence.guided.select.p-beginning-pig", app)
    activate("cadence.guided.practice.start", app)
    waitLabel(app.staticTexts["cadence.word"], "pig")
    recordAndStop("cadence.record", name: prefix + "-record", app)
    collapsedReminder(app)
    activate("cadence.practice-reminder.toggle", app)
    expandedReminder(detail: pigDetail, name: prefix + "-before-check", app)
    let frozen = "First review: Word matched. Word checks cannot identify which sound was made."
    waitLabel(app.staticTexts["cadence.guided.first-observation"], frozen)

    for (count, event, result) in [
      (6, "timeout", "Word check took too long. Your recording is still here."),
      (7, "matched", "“pig” matched in this try. Individual sounds aren’t assessed."),
    ] {
      if count == 7 { waitLabel(app.buttons["cadence.word-check"], "Try word check again") }
      activate("cadence.word-check", app)
      feedbackCounters(checks: count, pending: true, app)
      waitLabel(app.staticTexts["cadence.word-check-status"], "Checking words in this try on this device…")
      XCTAssertFalse(app.buttons["cadence.record-another"].isEnabled)
      XCTAssertFalse(app.buttons["cadence.replay"].isEnabled)
      XCTAssertFalse(app.buttons["cadence.guided.continue"].isEnabled)
      if count == 7 {
        waitLabel(app.staticTexts["cadence.generated-guided.retry-binding"],
          "Generated retry binding: same take yes · new operation yes · latest yes")
      }
      expandedReminder(detail: pigDetail, name: prefix + "-pending-\(count)", app)
      waitLabel(app.staticTexts["cadence.guided.first-observation"], frozen)
      print("CADENCE_REMINDER_FEEDBACK_STATE=\(prefix)-pending-\(count)")
      XCTAssertTrue(reveal(app.staticTexts["cadence.practice-reminder.detail"],
                           id: "cadence.practice-reminder.detail", app))
      let before = captureFeedbackProbe(prefix + "-" + event + "-before", app)
      let release = app.buttons["cadence.generated-guided.release"]
      assertControl(release, viewport: app.windows.firstMatch.frame)
      release.tap() // Fixed banner: no scroll/reveal between this pair of passive captures.
      waitLabel(app.staticTexts["cadence.word-check-result"], result)
      feedbackCounters(checks: count, pending: false, app)
      let after = captureFeedbackProbe(prefix + "-" + event + "-after", app)
      XCTAssertGreaterThan(before.upperBound, before.lowerBound)
      // Preserve the text the learner was reading; additional visible text is fine.
      XCTAssertLessThanOrEqual(after.lowerBound, before.lowerBound + 1)
      XCTAssertGreaterThanOrEqual(after.upperBound, before.upperBound - 1)
      waitLabel(app.staticTexts["cadence.guided.first-observation"], frozen)
      expandedReminder(detail: pigDetail, name: prefix + "-" + event, app)
      print("CADENCE_REMINDER_FEEDBACK_STATE=\(prefix)-\(event)")
    }
    activate("cadence.guided.continue", app)
    waitLabel(app.staticTexts["cadence.generated-guided.receipts"], "Generated practice receipts: 1 exact")
    activate("cadence.guided.recheck.start", app)
    waitLabel(app.staticTexts["cadence.word"], "ball")
    waitLabel(app.staticTexts["cadence.guided.visit-heading"], "Recheck · 1 of 5")
    noReminder(app)
    XCTAssertFalse(app.staticTexts["cadence.word-check-result"].exists)
    XCTAssertFalse(app.buttons["cadence.replay"].exists)
    capture(prefix + "-fresh-recheck", app)
    activate("cadence.guided.close", app)
    XCTAssertTrue(app.staticTexts["cadence.generated-guided.closed"].waitForExistence(timeout: 5))
    waitLabel(app.staticTexts["cadence.generated-guided.closed-files"],
      "Generated files: made 6, kept 0 · permission requests 6 · playback starts 0")
    waitLabel(app.staticTexts["cadence.generated-guided.closed-history"], "Generated history: 1 rows [p:1]")
    capture(prefix + "-closed", app)
  }

  private func feedbackCounters(checks: Int, pending: Bool, _ app: XCUIApplication) {
    waitLabel(app.staticTexts["cadence.generated-guided.files"],
      "Generated files: made 6, kept 1 · permission requests 6 · playback starts 0")
    waitLabel(app.staticTexts["cadence.generated-guided.checks"],
      "Generated checks: \(checks), pending \(pending ? 1 : 0), cancelled 0, borrowed \(pending ? 1 : 0)")
    waitLabel(app.staticTexts["cadence.generated-guided.history"], "Generated history: 0 rows []")
  }

  private func captureFeedbackProbe(_ name: String, _ app: XCUIApplication) -> ClosedRange<CGFloat> {
    let text = app.staticTexts["cadence.practice-reminder.detail"]
    waitLabel(text, pigDetail)
    let frame = text.frame, visible = viewport(app)
    XCTAssertTrue(finite(frame) && !frame.isEmpty && finite(visible) && visible.height > 0)
    XCTAssertGreaterThanOrEqual(frame.minX, visible.minX)
    XCTAssertLessThanOrEqual(frame.maxX, visible.maxX)
    let start = min(max(0, visible.minY - frame.minY), frame.height)
    let end = min(max(0, visible.maxY - frame.minY), frame.height)
    capture(name, app, geometry: [
      "passiveReadingProbe": true, "text": rect(frame), "viewport": rect(visible),
      "visibleStart": start, "visibleEnd": end, "readingVisible": end > start,
      "expanded": app.buttons["cadence.practice-reminder.toggle"].value as? String == "Expanded",
      "checks": app.staticTexts["cadence.generated-guided.checks"].label,
    ])
    return start...end
  }

  private func journey(largeText: Bool) {
    continueAfterFailure = false
    executionTimeAllowance = 480
    let app = XCUIApplication()
    for key in app.launchEnvironment.keys
    where key.hasPrefix("CADENCE_") || key.hasPrefix("TEST_RUNNER_CADENCE_") {
      app.launchEnvironment.removeValue(forKey: key)
    }
    app.launchEnvironment["CADENCE_CONTROLLED_UI_HOST"] = "1"
    app.launchArguments = [
      "-CadenceLocalGuidedMode", "-CadenceLocalGuidedUITestCase", largeText ? "setupAX" : "setup",
      "-CadenceControlledUIRunID", UUID().uuidString.lowercased(),
    ]
    let prefix = "generated-practice-reminder-" + (largeText ? "largest" : "normal")
    addTeardownBlock { @MainActor [weak self] () throws -> Void in
      guard let self else { return }
      if app.state == .runningForeground {
        self.capture(prefix + "-final-before-cleanup", app)
        self.tryPublicCleanup(prefix + "-teardown", app)
      }
      app.terminate() // Fallback termination is not an explicit-cleanup claim.
    }
    app.launch()
    XCTAssertTrue(app.staticTexts["cadence.generated-guided.banner"].waitForExistence(timeout: 5))
    waitLabel(app.staticTexts["cadence.generated-guided.seed"], "Generated stage: unseeded setup")
    counters(made: 0, kept: 0, rows: [], app)
    activate("cadence.guided.setup.2", app)
    let search = app.descendants(matching: .any).matching(identifier: "cadence.guided.search").firstMatch
    XCTAssertTrue(search.waitForExistence(timeout: 5))
    search.tap()
    search.typeText("bread\n")
    activate("cadence.guided.pick.r-middle-bread", app)
    XCTAssertTrue(app.buttons["cadence.guided.setup.2"].label.contains("bread"))
    activate("cadence.guided.start", app)
    waitLabel(app.staticTexts["cadence.word"], "ball")
    noReminder(app)
    recordAndStop("cadence.record", name: prefix + "-first-review-ball", app)
    noReminder(app) // A retained first-review take is not selected practice.
    counters(made: 1, kept: 1, rows: [], app)
    activate("cadence.guided.finish-stage", app)
    counters(made: 1, kept: 0, rows: [], app)
    activate("cadence.guided.select.p-beginning-pig", app)
    activate("cadence.guided.select.r-middle-bread", app)
    waitLabel(app.buttons["cadence.guided.practice.start"], "Practice selected words (2)")
    activate("cadence.guided.practice.start", app)
    waitLabel(app.staticTexts["cadence.word"], "pig")
    waitLabel(app.staticTexts["cadence.practice-instruction.detail"], pigDetail)
    noReminder(app)
    recordAndStop("cadence.record", name: prefix + "-pig-first", app)
    counters(made: 2, kept: 1, rows: [], app)
    collapsedReminder(app)

    ensureAboutExpanded(app)
    waitLabel(app.staticTexts["cadence.sound-guide.detail"], pigDetail)
    XCTAssertEqual(exactCount(pigDetail, app), 1)
    activate("cadence.practice-reminder.toggle", app)
    expandedReminder(detail: pigDetail, name: prefix + "-pig-reminder", app)
    XCTAssertFalse(app.staticTexts["cadence.sound-guide.detail"].exists)
    XCTAssertEqual(exactCount(pigDetail, app), 1)
    counters(made: 2, kept: 1, rows: [], app)
    activate("cadence.practice-reminder.toggle", app)
    collapsedReminder(app)
    waitLabel(app.staticTexts["cadence.sound-guide.detail"], pigDetail)
    XCTAssertEqual(exactCount(pigDetail, app), 1)
    counters(made: 2, kept: 1, rows: [], app)
    activate("cadence.practice-reminder.toggle", app)
    waitLabel(app.staticTexts["cadence.practice-reminder.detail"], pigDetail)
    XCTAssertFalse(app.staticTexts["cadence.sound-guide.detail"].exists)
    recordAndStop("cadence.record-another", name: prefix + "-pig-retake", app)
    counters(made: 3, kept: 2, rows: [], app)
    collapsedReminder(app)
    ensureAboutExpanded(app)
    waitLabel(app.staticTexts["cadence.sound-guide.detail"], pigDetail)
    activate("cadence.practice-reminder.toggle", app)
    expandedReminder(detail: pigDetail, name: prefix + "-pig-retake-reminder", app)
    XCTAssertFalse(app.staticTexts["cadence.sound-guide.detail"].exists)
    XCTAssertEqual(exactCount(pigDetail, app), 1)
    counters(made: 3, kept: 2, rows: [], app)
    activate("cadence.guided.continue", app)
    waitLabel(app.staticTexts["cadence.word"], "bread")
    counters(made: 3, kept: 0, rows: ["p:1"], app)
    waitLabel(app.staticTexts["cadence.generated-guided.receipts"], "Generated practice receipts: 1 exact")
    noReminder(app)
    waitLabel(app.staticTexts["cadence.practice-instruction.detail"], breadDetail)
    XCTAssertEqual(exactCount(pigDetail, app), 0)
    recordAndStop("cadence.record", name: prefix + "-bread-first", app)
    counters(made: 4, kept: 1, rows: ["p:1"], app)
    collapsedReminder(app)
    activate("cadence.practice-reminder.toggle", app)
    expandedReminder(detail: breadDetail, name: prefix + "-bread-reminder", app)
    XCTAssertEqual(exactCount(pigDetail, app), 0)
    ensureAboutExpanded(app)
    waitLabel(app.staticTexts["cadence.sound-guide.title"], "R in the BR of “bread”")
    XCTAssertFalse(app.staticTexts["cadence.sound-guide.detail"].exists)
    XCTAssertEqual(exactCount(breadDetail, app), 1)
    counters(made: 4, kept: 1, rows: ["p:1"], app)
    activate("cadence.practice-reminder.toggle", app)
    collapsedReminder(app)
    let restored = app.staticTexts["cadence.sound-guide.detail"]
    waitLabel(restored, breadDetail)
    XCTAssertEqual(exactCount(breadDetail, app), 1)
    captureText(restored, id: "cadence.sound-guide.detail", name: prefix + "-bread-about-restored", app)
    counters(made: 4, kept: 1, rows: ["p:1"], app)
    activate("cadence.guided.skip", app)
    counters(made: 4, kept: 0, rows: ["p:1"], app)
    noReminder(app)
    activate("cadence.guided.recheck.start", app)
    waitLabel(app.staticTexts["cadence.word"], "ball")
    waitLabel(app.staticTexts["cadence.guided.visit-heading"], "Recheck · 1 of 5")
    noReminder(app)
    XCTAssertFalse(app.buttons["cadence.replay"].exists)
    counters(made: 4, kept: 0, rows: ["p:1"], app)
    capture(prefix + "-fresh-recheck", app)
    activate("cadence.guided.close", app)
    XCTAssertTrue(app.staticTexts["cadence.generated-guided.closed"].waitForExistence(timeout: 5))
    waitLabel(app.staticTexts["cadence.generated-guided.closed-files"],
      "Generated files: made 4, kept 0 · permission requests 4 · playback starts 0")
    waitLabel(app.staticTexts["cadence.generated-guided.closed-history"], "Generated history: 1 rows [p:1]")
    capture(prefix + "-closed", app)
  }

  private func collapsedReminder(_ app: XCUIApplication) {
    let toggle = app.buttons["cadence.practice-reminder.toggle"]
    waitLabel(toggle, "Practice reminder")
    XCTAssertEqual(toggle.value as? String, "Collapsed")
    XCTAssertFalse(app.staticTexts["cadence.practice-reminder.detail"].exists)
    XCTAssertTrue(reveal(toggle, id: "cadence.practice-reminder.toggle", app))
    assertControl(toggle, viewport: viewport(app))
    let retake = app.buttons["cadence.record-another"]
    XCTAssertTrue(retake.exists)
    XCTAssertLessThanOrEqual(toggle.frame.maxY, retake.frame.minY)
  }

  private func expandedReminder(detail: String, name: String, _ app: XCUIApplication) {
    XCTAssertEqual(app.buttons["cadence.practice-reminder.toggle"].value as? String, "Expanded")
    let text = app.staticTexts["cadence.practice-reminder.detail"]
    waitLabel(text, detail)
    XCTAssertLessThanOrEqual(text.frame.maxY, app.buttons["cadence.record-another"].frame.minY)
    captureText(text, id: "cadence.practice-reminder.detail", name: name, app)
  }

  private func noReminder(_ app: XCUIApplication) {
    XCTAssertFalse(app.buttons["cadence.practice-reminder.toggle"].exists)
    XCTAssertFalse(app.staticTexts["cadence.practice-reminder.detail"].exists)
  }

  private func ensureAboutExpanded(_ app: XCUIApplication) {
    let about = app.buttons["cadence.sound-guide.toggle"]
    XCTAssertTrue(about.exists)
    if about.value as? String != "Expanded" { activate("cadence.sound-guide.toggle", app) }
    XCTAssertEqual(about.value as? String, "Expanded")
  }

  private func recordAndStop(_ id: String, name: String, _ app: XCUIApplication) {
    activate(id, app)
    let stop = app.buttons["cadence.stop"]
    let appeared = stop.waitForExistence(timeout: 5)
    capture(name + "-recording", app)
    let revealed = appeared && reveal(stop, id: "cadence.stop", app)
    let frame = stop.exists ? stop.frame : .zero
    let visible = viewport(app)
    let reachable = revealed && finite(frame) && !frame.isEmpty
      && (frame.width * 1_000_000).rounded() / 1_000_000 >= 44
      && (frame.height * 1_000_000).rounded() / 1_000_000 >= 44
      && frame.minX >= visible.minX && frame.maxX <= visible.maxX
      && frame.minY >= visible.minY && frame.maxY <= visible.maxY
      && stop.isEnabled && stop.isHittable
    capture(name + "-stop-control", app, geometry: [
      "stop": rect(frame), "viewport": rect(visible), "fullControl44": reachable,
    ])
    if reachable && stop.isEnabled && stop.isHittable { stop.tap() }
    let review = app.buttons["cadence.replay"].waitForExistence(timeout: 5)
    capture(name + "-after-stop", app)
    if !reachable || !review { tryPublicCleanup(name + "-recovery", app) }
    XCTAssertTrue(reachable && review, "Public Stop must settle before review assertions")
  }

  private func counters(made: Int, kept: Int, rows: [String], _ app: XCUIApplication) {
    waitLabel(app.staticTexts["cadence.generated-guided.files"],
      "Generated files: made \(made), kept \(kept) · permission requests \(made) · playback starts 0")
    waitLabel(app.staticTexts["cadence.generated-guided.checks"],
      "Generated checks: 0, pending 0, cancelled 0, borrowed 0")
    waitLabel(app.staticTexts["cadence.generated-guided.history"],
      "Generated history: \(rows.count) rows [\(rows.joined(separator: ","))]")
    XCTAssertFalse(app.staticTexts["cadence.word-check-result"].exists)
  }

  private func activate(_ id: String, _ app: XCUIApplication) {
    let target = app.buttons[id]
    if !id.hasPrefix("cadence.guided.pick.") {
      XCTAssertTrue(target.exists || target.waitForExistence(timeout: 5), id)
    }
    if id == "cadence.guided.close" {
      assertControl(target, viewport: app.windows.firstMatch.frame)
      target.tap()
      return
    }
    XCTAssertTrue(reveal(target, id: id, app), id)
    XCTAssertTrue(target.isEnabled && target.isHittable, id)
    if id.hasPrefix("cadence.guided.select.") {
      let visible = target.frame.intersection(viewport(app))
      XCTAssertTrue(finite(visible) && !visible.isEmpty)
      XCTAssertGreaterThanOrEqual(visible.width, 44)
      XCTAssertGreaterThanOrEqual(visible.height, 44)
      capture("reminder-selection-" + id, app, geometry: [
        "row": rect(target.frame), "visibleIntersection": rect(visible),
      ])
      let window = app.windows.firstMatch
      window.coordinate(withNormalizedOffset: .zero).withOffset(CGVector(
        dx: visible.midX - window.frame.minX, dy: visible.midY - window.frame.minY)).tap()
    } else {
      let visible = app.collectionViews["cadence.guided.picker.scroll"].exists
        ? app.collectionViews["cadence.guided.picker.scroll"].frame
          .intersection(app.windows.firstMatch.frame).insetBy(dx: 0, dy: 8)
        : viewport(app)
      assertControl(target, viewport: visible)
      target.tap()
    }
  }

  private func assertControl(_ target: XCUIElement, viewport: CGRect) {
    XCTAssertTrue(target.exists && target.isEnabled && target.isHittable)
    let frame = target.frame
    XCTAssertTrue(finite(frame) && !frame.isEmpty)
    XCTAssertGreaterThanOrEqual((frame.width * 1_000_000).rounded() / 1_000_000, 44)
    XCTAssertGreaterThanOrEqual((frame.height * 1_000_000).rounded() / 1_000_000, 44)
    XCTAssertGreaterThanOrEqual(frame.minX, viewport.minX)
    XCTAssertLessThanOrEqual(frame.maxX, viewport.maxX)
    XCTAssertGreaterThanOrEqual(frame.minY, viewport.minY)
    XCTAssertLessThanOrEqual(frame.maxY, viewport.maxY)
  }

  private func viewport(_ app: XCUIApplication) -> CGRect {
    let frame = app.scrollViews.firstMatch.frame.intersection(app.windows.firstMatch.frame)
    let close = app.buttons["cadence.guided.close"]
    let top = close.exists ? max(frame.minY, close.frame.maxY) : frame.minY
    return CGRect(x: frame.minX, y: top + 8, width: frame.width,
                  height: max(0, frame.maxY - top - 16))
  }

  private func reveal(_ target: XCUIElement, id: String, _ app: XCUIApplication) -> Bool {
    let picker = app.collectionViews["cadence.guided.picker.scroll"]
    if picker.exists {
      for _ in 0..<12 {
        let visible = picker.frame.intersection(app.windows.firstMatch.frame).insetBy(dx: 0, dy: 8)
        guard target.exists else { picker.swipeUp(velocity: .slow); continue }
        let frame = target.frame
        guard finite(frame), !frame.isEmpty, frame.height <= visible.height else { return false }
        if frame.minY >= visible.minY, frame.maxY <= visible.maxY, target.isHittable { return true }
        let delta = frame.midY - visible.midY
        drag(picker, x: visible.minX + 12, viewport: visible,
             travel: min(max(abs(delta), 12), visible.height * 0.35), down: delta < 0)
      }
      return false
    }
    guard app.scrollViews.firstMatch.exists else { return false }
    var previous: CGRect?, previousTravel: CGFloat = 0, previousDown: Bool?
    for _ in 0..<24 {
      guard target.exists else { return false }
      let frame = target.frame, visible = viewport(app)
      guard finite(frame), !frame.isEmpty, visible.height > 0 else { return false }
      let oversized = frame.height > visible.height
      let permitsOversize = id.hasPrefix("cadence.guided.select.")
        || id == "cadence.practice-reminder.detail" || id == "cadence.sound-guide.detail"
      guard !oversized || permitsOversize else { return false }
      if frame.minY >= visible.minY,
        oversized ? frame.minY <= visible.minY + visible.height * 0.2 : frame.maxY <= visible.maxY,
        target.isHittable { return true }
      let desired = oversized ? visible.minY : visible.minY + (visible.height - frame.height) / 2
      let down = frame.minY < desired, distance = abs(frame.minY - desired)
      var travel = oversized ? min(max(distance, visible.height * 0.2), visible.height * 0.6)
        : min(distance, visible.height * 0.6)
      if !oversized, distance > 0, distance <= 24, let previous,
        previousTravel > 0, previousDown == down, previous.size == frame.size {
        let moved = (frame.minY - previous.minY) * (down ? 1 : -1)
        if moved >= 0, moved <= previousTravel {
          travel = min(distance + min(previousTravel - moved, 24), visible.height * 0.6)
        }
      }
      guard travel > 0 else { continue }
      previous = frame; previousTravel = travel; previousDown = down
      guard pan(travel: travel, down: down, target: frame, app) else { return false }
    }
    return false
  }

  private func pan(travel: CGFloat, down: Bool, target: CGRect, _ app: XCUIApplication) -> Bool {
    let scroll = app.scrollViews.firstMatch, visible = viewport(app)
    let frames = (scroll.buttons.allElementsBoundByIndex.map(\.frame) + [target]).filter {
      !$0.isEmpty && $0.maxX > visible.minX && $0.minX < visible.maxX
    }
    guard frames.allSatisfy({ finite($0) }), let leading = frames.map(\.minX).min(),
      let trailing = frames.map(\.maxX).max() else { return false }
    let x: CGFloat
    if leading - visible.minX >= 16 { x = (leading + visible.minX) / 2 }
    else if visible.maxX - trailing >= 16 { x = (trailing + visible.maxX) / 2 }
    else { return false }
    drag(scroll, x: x, viewport: visible, travel: travel, down: down)
    return true
  }

  private func drag(_ scroll: XCUIElement, x: CGFloat, viewport: CGRect, travel: CGFloat, down: Bool) {
    let origin = scroll.coordinate(withNormalizedOffset: .zero)
    let start = origin.withOffset(CGVector(dx: x - scroll.frame.minX,
      dy: viewport.midY + (down ? -travel / 2 : travel / 2) - scroll.frame.minY))
    let end = origin.withOffset(CGVector(dx: x - scroll.frame.minX,
      dy: viewport.midY + (down ? travel / 2 : -travel / 2) - scroll.frame.minY))
    start.press(forDuration: 0.01, thenDragTo: end, withVelocity: .slow, thenHoldForDuration: 0.2)
  }

  private func captureText(_ text: XCUIElement, id: String, name: String, _ app: XCUIApplication) {
    XCTAssertTrue(reveal(text, id: id, app))
    capture(name, app)
    for segment in 0..<8 {
      let frame = text.frame, visible = viewport(app)
      assertParagraph(frame, viewport: visible)
      capture(name + "-segment-\(segment)", app, geometry: ["text": rect(frame), "viewport": rect(visible)])
      if frame.maxY <= visible.maxY { return }
      let travel = min(max(frame.maxY - visible.maxY + 4, 24), visible.height * 0.55)
      XCTAssertTrue(pan(travel: travel, down: false, target: frame, app))
      let after = text.frame, afterViewport = viewport(app)
      let movement = frame.minY - after.minY
      capture(name + "-movement-\(segment)", app, geometry: [
        "before": rect(frame), "after": rect(after), "viewport": rect(afterViewport), "movement": movement,
      ])
      assertParagraph(after, viewport: afterViewport)
      XCTAssertGreaterThan(movement, 1)
      XCTAssertLessThanOrEqual(movement, visible.height - 8, "Paragraph captures must overlap")
      if after.maxY <= afterViewport.maxY { return }
    }
    XCTFail("Paragraph end not captured within eight measured moves: \(id)")
  }

  private func assertParagraph(_ frame: CGRect, viewport: CGRect) {
    XCTAssertTrue(finite(frame) && !frame.isEmpty)
    XCTAssertGreaterThanOrEqual(frame.minX, viewport.minX)
    XCTAssertLessThanOrEqual(frame.maxX, viewport.maxX)
  }

  private func tryPublicCleanup(_ name: String, _ app: XCUIApplication) {
    let cancel = app.buttons["cadence.guided.picker.cancel"]
    if cancel.exists, cancel.isEnabled, cancel.isHittable { cancel.tap() }
    let stop = app.buttons["cadence.stop"]
    if stop.exists, reveal(stop, id: "cadence.stop", app), stop.isEnabled, stop.isHittable {
      stop.tap()
      _ = app.buttons["cadence.replay"].waitForExistence(timeout: 5)
    }
    let close = app.buttons["cadence.guided.close"]
    if close.exists, close.isEnabled, close.isHittable { close.tap() }
    let closed = app.staticTexts["cadence.generated-guided.closed"].waitForExistence(timeout: 5)
    capture(name + "-public-cleanup", app, geometry: ["closedHostObserved": closed])
  }

  private func exactCount(_ text: String, _ app: XCUIApplication) -> Int {
    app.staticTexts.matching(NSPredicate(format: "label == %@", text)).count
  }
  private func waitLabel(_ target: XCUIElement, _ label: String) {
    XCTAssertTrue(target.exists || target.waitForExistence(timeout: 5))
    let match = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == %@", label), object: target)
    XCTAssertEqual(XCTWaiter.wait(for: [match], timeout: 5), .completed, label)
  }
  private func finite(_ frame: CGRect) -> Bool {
    [frame.minX, frame.minY, frame.width, frame.height, frame.maxX, frame.maxY].allSatisfy(\.isFinite)
  }
  private func rect(_ frame: CGRect) -> [CGFloat] {
    [frame.minX, frame.minY, frame.width, frame.height]
  }
  private func capture(_ name: String, _ app: XCUIApplication, geometry: [String: Any] = [:]) {
    let image = XCTAttachment(screenshot: app.screenshot())
    image.name = name; image.lifetime = .keepAlways; add(image)
    let tree = XCTAttachment(string: app.debugDescription)
    tree.name = name + "-accessibility"; tree.lifetime = .keepAlways; add(tree)
    var values = geometry
    values["window"] = rect(app.windows.firstMatch.frame)
    for id in ["cadence.practice-reminder.toggle", "cadence.practice-reminder.detail", "cadence.record-another"] {
      let element = app.descendants(matching: .any).matching(identifier: id).firstMatch
      if element.exists { values[id] = ["frame": rect(element.frame), "label": element.label] }
    }
    let attachment: XCTAttachment
    if let data = try? JSONSerialization.data(withJSONObject: values, options: [.sortedKeys]) {
      attachment = XCTAttachment(data: data, uniformTypeIdentifier: "public.json")
    } else { attachment = XCTAttachment(string: String(describing: values)) }
    attachment.name = name + "-geometry"; attachment.lifetime = .keepAlways; add(attachment)
  }
}
