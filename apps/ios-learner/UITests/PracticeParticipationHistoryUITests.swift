import XCTest

#if DEBUG && targetEnvironment(simulator)
  @MainActor
  final class PracticeParticipationHistoryUITests: XCTestCase {
    private var historyGestures = 0
    private var confirmationGestures = 0
    private var confirmationRecoveryGestures = 0
    func testCompactFourRecordsFullHistoryBackAndClearCancelThenConfirm() throws {
      let app = try launch("historyfour")
      defer { finish(app) }
      let home = app.scrollViews["cadence.generated-history.home"]
      XCTAssertEqual(entryIDs(home), [1, 2, 3].map(entryID))
      XCTAssertFalse(
        home.descendants(matching: .any).matching(identifier: entryID(4)).firstMatch.exists)
      let before = try receipt(app)
      activate("cadence.history.all", app)
      for ordinal in 1...4 {
        let row = reach(ordinal, app)
        XCTAssertTrue(
          row.label.contains(
            "\(1 + (ordinal - 1) % 3) \((ordinal - 1) % 3 == 0 ? "word" : "words")"))
        if ordinal == 1 { XCTAssertTrue(row.label.contains("TH · feather")) }
        let link = app.scrollViews["cadence.history.all-list"].buttons[practiceID(ordinal)]
        XCTAssertTrue(link.exists)
        XCTAssertFalse(link.isEnabled)
      }
      screenshot("four-oldest-retained", app)
      back(app)
      inspect(app)
      XCTAssertEqual(
        try receipt(app)["currentFileSHA256"] as? String, before["currentFileSHA256"] as? String)
      XCTAssertEqual(entryIDs(home), [1, 2, 3].map(entryID))
      clear(app, confirm: false)
      inspect(app)
      XCTAssertEqual(try receipt(app)["currentCount"] as? Int, 4)
      XCTAssertEqual(
        try receipt(app)["currentFileSHA256"] as? String, before["currentFileSHA256"] as? String)
      clear(app, confirm: true)
      inspect(app)
      XCTAssertEqual(try receipt(app)["currentCount"] as? Int, 0)
      XCTAssertEqual(try receipt(app)["reopenedCount"] as? Int, 0)
      XCTAssertEqual(try receipt(app)["reopenedMatches"] as? Bool, true)
      XCTAssertFalse(app.buttons["cadence.history.all"].exists)
      XCTAssertTrue(entryIDs(home).isEmpty)
    }

    func testLargestTextHundredRecordsFirstMiddleOldestBackAndClearCancel() throws {
      let app = try launch("hundred", largeText: true)
      defer { finish(app) }
      let initial = try receipt(app)
      XCTAssertEqual(initial["currentCount"] as? Int, 100)
      XCTAssertEqual(initial["seedOrderConfirmed"] as? Bool, true)
      XCTAssertEqual(initial["seedReadbackConfirmed"] as? Bool, true)
      activate("cadence.history.all", app)
      for (ordinal, name) in [
        (1, "hundred-first"), (51, "hundred-middle"), (100, "hundred-oldest"),
      ] {
        let row = reach(ordinal, app)
        XCTAssertTrue(row.isHittable)
        if ordinal == 1 { XCTAssertTrue(row.label.contains("TH · feather")) }
        screenshot(name, app)
      }
      back(app)
      clear(app, confirm: false)
      inspect(app)
      let final = try receipt(app)
      XCTAssertEqual(final["currentCount"] as? Int, 100)
      XCTAssertEqual(final["currentFileSHA256"] as? String, initial["currentFileSHA256"] as? String)
      XCTAssertEqual(
        final["currentOrderSHA256"] as? String, initial["currentOrderSHA256"] as? String)
      XCTAssertEqual(
        entryIDs(app.scrollViews["cadence.generated-history.home"]), [1, 2, 3].map(entryID))
    }

    func testNormalEmptyDestinationHasBackAndNoUnreadableWarning() throws {
      let app = try launch("empty")
      defer { finish(app) }
      activate("cadence.generated-history.open-state", app)
      XCTAssertTrue(app.staticTexts["cadence.history.empty"].waitForExistence(timeout: 5))
      XCTAssertFalse(app.staticTexts["cadence.history.load-error"].exists)
      back(app)
      XCTAssertFalse(app.buttons["cadence.history.clear"].exists)
    }

    func testUnreadableHistoryWarnsThenActualHomeClearRecovers() throws {
      let app = try launch("unreadable")
      defer { finish(app) }
      let initial = try receipt(app)
      XCTAssertEqual(initial["loadError"] as? Bool, true)
      activate("cadence.generated-history.open-state", app)
      XCTAssertTrue(app.staticTexts["cadence.history.load-error"].waitForExistence(timeout: 5))
      XCTAssertFalse(app.staticTexts["cadence.history.empty"].exists)
      screenshot("unreadable-history-warning", app)
      back(app)
      clear(app, confirm: false)
      inspect(app)
      XCTAssertEqual(
        try receipt(app)["currentFileSHA256"] as? String, initial["currentFileSHA256"] as? String)
      clear(app, confirm: true)
      inspect(app)
      XCTAssertEqual(try receipt(app)["loadError"] as? Bool, false)
      XCTAssertEqual(try receipt(app)["reopenedCount"] as? Int, 0)
    }

    func testFailedClearKeepsRecordsUntilGeneratedObstacleRepairAndActualClearRetry() throws {
      let app = try launch("clearFailure")
      defer { finish(app) }
      clear(app, confirm: true)
      XCTAssertTrue(app.staticTexts["cadence.history.clear-error"].waitForExistence(timeout: 5))
      inspect(app)
      XCTAssertEqual(try receipt(app)["currentCount"] as? Int, 4)
      XCTAssertEqual(try receipt(app)["obstaclePresent"] as? Bool, true)
      screenshot("failed-history-clear-preserves-preview", app)
      activate("cadence.generated-history.repair", app)
      XCTAssertEqual(try receipt(app)["repairCount"] as? Int, 1)
      clear(app, confirm: true)
      inspect(app)
      XCTAssertEqual(try receipt(app)["currentCount"] as? Int, 0)
      XCTAssertEqual(try receipt(app)["reopenedCount"] as? Int, 0)
      XCTAssertEqual(try receipt(app)["reopenedMatches"] as? Bool, true)
      XCTAssertFalse(app.staticTexts["cadence.history.clear-error"].exists)
    }

    func testObservedClearWhileRealAllHistoryDestinationOpenShowsEmptyWithoutPopping() throws {
      let app = try launch("historyfour")
      defer { finish(app) }
      activate("cadence.history.all", app)  // The actual consumer route, not host open-state.
      _ = reach(1, app)
      activate("cadence.generated-history.observe-clear", app)
      XCTAssertTrue(app.scrollViews["cadence.history.all-list"].exists)
      XCTAssertTrue(app.navigationBars["Practice history"].exists)
      XCTAssertTrue(app.staticTexts["cadence.history.empty"].waitForExistence(timeout: 5))
      XCTAssertTrue(entryIDs(app.scrollViews["cadence.history.all-list"]).isEmpty)
      screenshot("observed-clear-history-stays-open-empty", app)
      back(app)
      inspect(app)
      XCTAssertEqual(try receipt(app)["observationClearCount"] as? Int, 1)
      XCTAssertEqual(try receipt(app)["reopenedCount"] as? Int, 0)
    }

    func testLargestTextFourRecordsFullConfirmationCopyCancelThenConfirm() throws {
      let app = try launch("historyfour", largeText: true)
      defer { finish(app) }
      let initial = try receipt(app)
      activate("cadence.history.clear", app)
      captureFullConfirmation(app, prefix: "largest-four")
      confirmationAction(app, confirm: false)
      inspect(app)
      let cancelled = try receipt(app)
      XCTAssertEqual(cancelled["currentCount"] as? Int, 4)
      XCTAssertEqual(
        cancelled["currentFileSHA256"] as? String, initial["currentFileSHA256"] as? String)
      XCTAssertEqual(
        cancelled["currentOrderSHA256"] as? String, initial["currentOrderSHA256"] as? String)
      XCTAssertEqual(cancelled["reopenedCount"] as? Int, 4)
      XCTAssertEqual(cancelled["reopenedMatches"] as? Bool, true)
      XCTAssertEqual(
        entryIDs(app.scrollViews["cadence.generated-history.home"]), [1, 2, 3].map(entryID))
      clear(app, confirm: true)
      inspect(app)
      let cleared = try receipt(app)
      XCTAssertEqual(cleared["currentCount"] as? Int, 0)
      XCTAssertEqual(cleared["reopenedCount"] as? Int, 0)
      XCTAssertEqual(cleared["reopenedMatches"] as? Bool, true)
      XCTAssertFalse(app.buttons["cadence.history.all"].exists)
      XCTAssertTrue(entryIDs(app.scrollViews["cadence.generated-history.home"]).isEmpty)
      screenshot("largest-four-cleared", app)
    }

    func testLargestTextFailedConfirmationRetainsHistoryUntilRepairAndActualRetry() throws {
      let app = try launch("clearFailure", largeText: true)
      defer { finish(app) }
      let initial = try receipt(app)
      activate("cadence.history.clear", app)
      captureFullConfirmation(app, prefix: "largest-failed-clear")
      confirmationAction(app, confirm: true)
      let error = app.staticTexts["cadence.history.clear-error"]
      XCTAssertTrue(error.waitForExistence(timeout: 5))
      XCTAssertEqual(error.label, "Recent practice could not be cleared. Try again.")
      revealEntireHomeElement(error, app)
      inspect(app)
      let failed = try receipt(app)
      XCTAssertEqual(failed["currentCount"] as? Int, 4)
      XCTAssertEqual(
        failed["currentOrderSHA256"] as? String, initial["currentOrderSHA256"] as? String)
      XCTAssertEqual(failed["obstaclePresent"] as? Bool, true)
      // The generated obstacle replaces the file with a directory. A failed write cannot
      // truthfully promise a readable persisted file before an explicit successful write.
      XCTAssertEqual(failed["reopenedMatches"] as? Bool, false)
      screenshot("largest-failed-clear-retained-preview", app)
      revealEntireHomeElement(app.buttons["cadence.history.all"], app)
      activate("cadence.history.all", app)
      for ordinal in 1...4 { XCTAssertTrue(reach(ordinal, app).isHittable) }
      screenshot("largest-failed-clear-retained-all-history", app)
      back(app)
      activate("cadence.generated-history.repair", app)
      let repaired = try receipt(app)
      XCTAssertEqual(repaired["repairCount"] as? Int, 1)
      XCTAssertEqual(repaired["currentCount"] as? Int, 4)
      XCTAssertEqual(
        repaired["currentOrderSHA256"] as? String, initial["currentOrderSHA256"] as? String)
      clear(app, confirm: true)
      inspect(app)
      let cleared = try receipt(app)
      XCTAssertEqual(cleared["currentCount"] as? Int, 0)
      XCTAssertEqual(cleared["reopenedCount"] as? Int, 0)
      XCTAssertEqual(cleared["reopenedMatches"] as? Bool, true)
      XCTAssertFalse(app.staticTexts["cadence.history.clear-error"].exists)
      screenshot("largest-failed-clear-explicit-retry-empty", app)
    }

    private func launch(_ value: String, largeText: Bool = false) throws -> XCUIApplication {
      historyGestures = 0
      confirmationGestures = 0
      confirmationRecoveryGestures = 0
      continueAfterFailure = false
      executionTimeAllowance = value == "hundred" ? 300 : 180
      let app = XCUIApplication()
      for key in app.launchEnvironment.keys
      where key.hasPrefix("CADENCE_") || key.hasPrefix("TEST_RUNNER_CADENCE_") {
        app.launchEnvironment.removeValue(forKey: key)
      }
      app.launchEnvironment["CADENCE_CONTROLLED_UI_HOST"] = "1"
      app.launchArguments = [
        "-CadenceHistoryMode", "-CadenceHistoryUITestCase", value,
        "-CadenceControlledUIRunID", UUID().uuidString,
        "-UIPreferredContentSizeCategoryName",
        largeText ? "UICTContentSizeCategoryAccessibilityXXXL" : "UICTContentSizeCategoryL",
      ]
      app.launch()
      XCTAssertTrue(
        app.staticTexts["cadence.generated-history.banner"].waitForExistence(timeout: 5))
      XCTAssertFalse(app.staticTexts["cadence.generated-history.failed"].exists)
      let seed = try receipt(app)
      XCTAssertEqual(seed["seedOrderConfirmed"] as? Bool, true)
      XCTAssertEqual(seed["seedReadbackConfirmed"] as? Bool, true)
      XCTAssertEqual(seed["failed"] as? Bool, false)
      return app
    }

    private func entryID(_ ordinal: Int) -> String { "cadence.history.entry-" + uuid(ordinal) }
    private func practiceID(_ ordinal: Int) -> String {
      "cadence.history.practice-" + uuid(ordinal)
    }
    private func uuid(_ ordinal: Int) -> String {
      String(format: "00000000-0000-0000-0000-%012d", ordinal)
    }
    private func entryIDs(_ scope: XCUIElement) -> [String] {
      scope.descendants(matching: .any).matching(
        NSPredicate(format: "identifier BEGINSWITH %@", "cadence.history.entry-")
      )
      .allElementsBoundByIndex.map(\.identifier)
    }
    private func receipt(_ app: XCUIApplication) throws -> [String: Any] {
      let value = try XCTUnwrap(
        app.staticTexts["cadence.generated-history.receipt"].value as? String)
      return try XCTUnwrap(JSONSerialization.jsonObject(with: Data(value.utf8)) as? [String: Any])
    }
    private func inspect(_ app: XCUIApplication) {
      activate("cadence.generated-history.inspect", app)
    }
    private func activate(_ id: String, _ app: XCUIApplication) {
      let button = app.buttons[id]
      XCTAssertTrue(button.waitForExistence(timeout: 5), id)
      if !id.hasPrefix("cadence.generated-history.") {
        let scroll = app.scrollViews.firstMatch
        for _ in 0..<12 where !button.isHittable { scroll.swipeUp(velocity: .fast) }
      }
      XCTAssertTrue(button.isHittable, id)
      XCTAssertTrue(button.isEnabled, id)
      button.tap()
    }
    private func back(_ app: XCUIApplication) {
      let bar = app.navigationBars["Practice history"]
      XCTAssertTrue(bar.waitForExistence(timeout: 5))
      let back = bar.buttons.firstMatch
      XCTAssertTrue(back.isHittable)
      back.tap()
      XCTAssertTrue(app.scrollViews["cadence.generated-history.home"].waitForExistence(timeout: 5))
    }
    private func clear(_ app: XCUIApplication, confirm: Bool) {
      activate("cadence.history.clear", app)
      confirmationAction(app, confirm: confirm)
    }
    private func confirmationAction(_ app: XCUIApplication, confirm: Bool) {
      let content = app.scrollViews["cadence.history.clear-confirmation-content"]
      XCTAssertTrue(content.waitForExistence(timeout: 5))
      assertConfirmationButtons(app)
      let id =
        confirm
        ? "cadence.history.clear-confirmation-confirm" : "cadence.history.clear-confirmation-cancel"
      if !confirm { screenshot("history-clear-before-explicit-cancel", app) }
      app.buttons[id].tap()
      XCTAssertFalse(content.exists)
    }
    private func assertConfirmationButtons(_ app: XCUIApplication) {
      let cancel = app.buttons["cadence.history.clear-confirmation-cancel"]
      let clear = app.buttons["cadence.history.clear-confirmation-confirm"]
      let window = app.windows.firstMatch.frame
      for button in [cancel, clear] {
        XCTAssertTrue(button.waitForExistence(timeout: 5))
        XCTAssertTrue(button.isHittable)
        XCTAssertTrue(button.isEnabled)
        let frame = button.frame
        XCTAssertTrue(finite(frame) && finite(window))
        XCTAssertGreaterThanOrEqual(frame.width, 48)
        XCTAssertGreaterThanOrEqual(frame.height, 48)
        XCTAssertTrue(
          window.contains(frame), "Confirmation action must stay inside the visible window")
      }
      XCTAssertFalse(cancel.frame.intersects(clear.frame))
      XCTAssertLessThanOrEqual(cancel.frame.maxY, clear.frame.minY)
    }
    private func finite(_ frame: CGRect) -> Bool {
      [frame.minX, frame.minY, frame.width, frame.height].allSatisfy({ $0.isFinite })
        && frame.width > 0 && frame.height > 0
    }
    private func captureFullConfirmation(_ app: XCUIApplication, prefix: String) {
      let content = app.scrollViews["cadence.history.clear-confirmation-content"]
      let title = app.staticTexts["cadence.history.clear-confirmation-title"]
      let message = app.staticTexts["cadence.history.clear-confirmation-message"]
      XCTAssertTrue(content.waitForExistence(timeout: 5))
      XCTAssertEqual(title.label, "Clear recent practice?")
      XCTAssertEqual(
        message.label, "This removes all dates, sound groups and word counts saved on this device.")
      let viewport = content.frame.intersection(app.windows.firstMatch.frame)
      XCTAssertTrue(finite(viewport))
      XCTAssertTrue(viewport.contains(title.frame), "The full heading must be reachable at the top")
      confirmationCheckpoint(app, prefix + "-top", content: content, title: title, message: message)
      // Three real physical content drags, each less than half the viewport, deliberately
      // overlap captured reading regions. Screenshot inspection must account for EVERY phrase;
      // complete AX labels or hittability alone are not a full-copy visibility pass.
      for step in 1...3 {
        guard confirmationGestures < 3 else {
          XCTFail("Confirmation gesture budget exhausted")
          return
        }
        let frame = content.frame
        let bounds = frame.intersection(app.windows.firstMatch.frame)
        guard finite(frame), finite(bounds), bounds.width > 24, bounds.height > 40 else {
          XCTFail("No finite confirmation content drag viewport")
          return
        }
        confirmationGestures += 1
        let x = bounds.midX - frame.minX
        let startY = bounds.minY + bounds.height * 0.75 - frame.minY
        let endY = bounds.minY + bounds.height * 0.30 - frame.minY
        let origin = content.coordinate(withNormalizedOffset: .zero)
        origin.withOffset(CGVector(dx: x, dy: startY)).press(
          forDuration: 0.01,
          thenDragTo: origin.withOffset(CGVector(dx: x, dy: endY)),
          withVelocity: .slow, thenHoldForDuration: 0)
        confirmationCheckpoint(
          app, prefix + "-scroll-\(step)", content: content, title: title, message: message)
      }
      let finalViewport = content.frame.intersection(app.windows.firstMatch.frame)
      XCTAssertTrue(finite(message.frame))
      XCTAssertLessThanOrEqual(
        message.frame.maxY, finalViewport.maxY,
        "The final saved-on-this-device line must be reachable; visual review still required")
      XCTAssertGreaterThan(message.frame.maxY, finalViewport.minY)
    }
    private func confirmationCheckpoint(
      _ app: XCUIApplication, _ name: String,
      content: XCUIElement, title: XCUIElement, message: XCUIElement
    ) {
      assertConfirmationButtons(app)
      let viewport = content.frame.intersection(app.windows.firstMatch.frame)
      let cancel = app.buttons["cadence.history.clear-confirmation-cancel"].frame
      let clear = app.buttons["cadence.history.clear-confirmation-confirm"].frame
      XCTAssertTrue(finite(viewport) && finite(title.frame) && finite(message.frame))
      XCTAssertLessThanOrEqual(
        viewport.maxY, cancel.minY,
        "Persistent actions must not overlay confirmation copy")
      func values(_ rect: CGRect) -> [String: Double] {
        [
          "x": Double(rect.minX), "y": Double(rect.minY),
          "width": Double(rect.width), "height": Double(rect.height),
        ]
      }
      let geometry: [String: Any] = [
        "name": name, "confirmationGestures": confirmationGestures,
        "viewport": values(viewport), "title": values(title.frame),
        "message": values(message.frame),
        "cancel": values(cancel), "clear": values(clear),
      ]
      if let data = try? JSONSerialization.data(withJSONObject: geometry, options: [.sortedKeys]) {
        let attachment = XCTAttachment(data: data, uniformTypeIdentifier: "public.json")
        attachment.name = name + "-geometry"
        attachment.lifetime = .keepAlways
        add(attachment)
      } else {
        XCTFail("Finite confirmation geometry attachment could not be encoded")
      }
      screenshot(name, app)
    }
    private func revealEntireHomeElement(_ element: XCUIElement, _ app: XCUIApplication) {
      let home = app.scrollViews["cadence.generated-history.home"]
      for _ in 0..<12 {
        let frame = home.frame
        let viewport = frame.intersection(app.windows.firstMatch.frame)
        let target = element.frame
        guard finite(frame), finite(viewport), finite(target), viewport.width > 24,
          viewport.height > 40
        else {
          XCTFail("No finite recovery-copy viewport")
          return
        }
        if viewport.contains(target) && element.isHittable { return }
        guard confirmationRecoveryGestures < 12 else {
          XCTFail("Confirmation recovery-copy gesture budget exhausted")
          return
        }
        confirmationRecoveryGestures += 1
        let down = target.midY < viewport.midY
        // Home's real24pt content padding supplies this non-control leading gutter.
        let x = viewport.minX + 8 - frame.minX
        let top = viewport.minY + viewport.height * 0.30 - frame.minY
        let bottom = viewport.minY + viewport.height * 0.75 - frame.minY
        let origin = home.coordinate(withNormalizedOffset: .zero)
        origin.withOffset(CGVector(dx: x, dy: down ? top : bottom)).press(
          forDuration: 0.01,
          thenDragTo: origin.withOffset(CGVector(dx: x, dy: down ? bottom : top)),
          withVelocity: .slow, thenHoldForDuration: 0)
      }
      XCTFail("Full recovery copy was not reachable with bounded real scrolling")
    }
    private func reach(_ ordinal: Int, _ app: XCUIApplication) -> XCUIElement {
      let scroll = app.scrollViews["cadence.history.all-list"]
      XCTAssertTrue(scroll.waitForExistence(timeout: 5))
      let row = scroll.descendants(matching: .any).matching(identifier: entryID(ordinal)).firstMatch
      for _ in 0..<60 {
        let window = app.windows.firstMatch.frame
        let bar = app.navigationBars["Practice history"].frame
        let bounds = scroll.frame.intersection(window)
        let top = max(bounds.minY, bar.maxY)
        let viewport = CGRect(
          x: bounds.minX, y: top, width: bounds.width, height: max(0, bounds.maxY - top))
        guard
          [viewport.minX, viewport.minY, viewport.width, viewport.height].allSatisfy({ $0.isFinite }
          ),
          viewport.width > 0, viewport.height > 0
        else {
          XCTFail("No finite history viewport")
          return row
        }
        if row.exists {
          let frame = row.frame
          if [frame.minX, frame.minY, frame.width, frame.height].allSatisfy({ $0.isFinite }),
            frame.width > 0, frame.height > 0
          {
            if frame.intersects(viewport) && row.isHittable { return row }
            guard historyGestures < 60 else {
              XCTFail("History gesture budget exhausted")
              return row
            }
            historyGestures += 1
            if frame.midY < viewport.midY {
              historyDrag(scroll, viewport: viewport, down: true)
            } else {
              historyDrag(scroll, viewport: viewport, down: false)
            }
            continue
          }
        }
        // Cached offscreen AX rows must not determine direction after an overshoot.
        let ordinals = scroll.descendants(matching: .any).matching(
          NSPredicate(format: "identifier BEGINSWITH %@", "cadence.history.entry-")
        ).allElementsBoundByIndex.filter { $0.isHittable && $0.frame.intersects(viewport) }
          .compactMap { Int($0.identifier.suffix(12)) }
        guard historyGestures < 60 else {
          XCTFail("History gesture budget exhausted")
          return row
        }
        historyGestures += 1
        if let minimum = ordinals.min(), ordinal < minimum {
          historyDrag(scroll, viewport: viewport, down: true)
        } else {
          historyDrag(scroll, viewport: viewport, down: false)
        }
      }
      XCTFail("History sentinel not reached after bounded real scrolling: \(ordinal)")
      return row
    }
    private func historyDrag(_ scroll: XCUIElement, viewport: CGRect, down: Bool) {
      let originFrame = scroll.frame
      guard
        [
          viewport.minX, viewport.minY, viewport.maxX, viewport.maxY,
          originFrame.minX, originFrame.minY,
        ].allSatisfy({ $0.isFinite }),
        viewport.width > 16, viewport.height > 16
      else {
        XCTFail("No finite history drag viewport")
        return
      }
      let buttons = scroll.buttons.allElementsBoundByIndex.map(\.frame).filter {
        [$0.minX, $0.minY, $0.width, $0.height].allSatisfy({ $0.isFinite })
          && !$0.isEmpty && $0.intersects(viewport)
      }
      let leading = buttons.map(\.minX).min() ?? viewport.maxX
      let trailing = buttons.map(\.maxX).max() ?? viewport.minX
      let x: CGFloat
      if leading - viewport.minX >= 16 {
        x = (viewport.minX + leading) / 2
      } else if viewport.maxX - trailing >= 16 {
        x = (trailing + viewport.maxX) / 2
      } else {
        XCTFail("No blank history scroll gutter")
        return
      }
      // Keep real drags inside the content. Starting near the window's bottom edge
      // can invoke the system Home/app-switcher gesture instead of scrolling history.
      let top = viewport.minY + viewport.height * 0.15
      let bottom = viewport.minY + viewport.height * 0.85
      guard x.isFinite, x > viewport.minX, x < viewport.maxX, bottom > top else {
        XCTFail("Invalid history drag coordinates")
        return
      }
      let dx = x - originFrame.minX
      let startY = (down ? top : bottom) - originFrame.minY
      let endY = (down ? bottom : top) - originFrame.minY
      guard [dx, startY, endY].allSatisfy({ $0.isFinite }) else {
        XCTFail("Nonfinite history drag offsets")
        return
      }
      let origin = scroll.coordinate(withNormalizedOffset: .zero)
      let start = origin.withOffset(CGVector(dx: dx, dy: startY))
      let end = origin.withOffset(CGVector(dx: dx, dy: endY))
      start.press(forDuration: 0.01, thenDragTo: end, withVelocity: .fast, thenHoldForDuration: 0)
    }
    private func screenshot(_ name: String, _ app: XCUIApplication) {
      let attachment = XCTAttachment(screenshot: app.screenshot())
      attachment.name = name
      attachment.lifetime = .keepAlways
      add(attachment)
    }
    private func finish(_ app: XCUIApplication) {
      // Explicit host cleanup is independent from product assertions and never marks them passed.
      let finish = app.buttons["cadence.generated-history.finish"]
      if finish.exists && finish.isHittable { finish.tap() }
      XCTAssertTrue(
        app.staticTexts["cadence.generated-history.finished"].waitForExistence(timeout: 5))
      if let value = try? receipt(app) {
        XCTAssertEqual(value["cleanupConfirmed"] as? Bool, true)
        XCTAssertEqual(value["failed"] as? Bool, false)
      } else {
        XCTFail("Actual generated directory cleanup receipt missing")
      }
      app.terminate()
    }
  }
#endif
