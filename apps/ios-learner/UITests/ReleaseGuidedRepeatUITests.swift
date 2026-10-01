import XCTest

#if !DEBUG
  @MainActor
  final class ReleaseGuidedRepeatUITests: XCTestCase {
    func testReleaseCustomFiveRepeatStartsFreshWithoutMedia() { journey(largeText: false) }
    func testReleaseLargestTextCustomFiveRepeatRemainsReachable() { journey(largeText: true) }

    private func journey(largeText: Bool) {
      continueAfterFailure = false
      executionTimeAllowance = 240
      let app = XCUIApplication()
      for key in app.launchEnvironment.keys
      where key.hasPrefix("CADENCE_") || key.hasPrefix("TEST_RUNNER_CADENCE_") {
        app.launchEnvironment.removeValue(forKey: key)
      }
      app.launchArguments = [
        "-UIPreferredContentSizeCategoryName",
        largeText ? "UICTContentSizeCategoryAccessibilityXXXL" : "UICTContentSizeCategoryL",
      ]
      app.launch()
      defer { app.terminate() }
      XCTAssertTrue(app.buttons["cadence.local-guided.open"].waitForExistence(timeout: 5))
      XCTAssertFalse(app.staticTexts["cadence.generated-guided.banner"].exists)
      XCTAssertFalse(app.staticTexts["cadence.home.ui-test-banner"].exists)
      let history = historyRows(app)
      activate("cadence.local-guided.open", app)
      activate("cadence.guided.setup.0", app)
      let search = app.descendants(matching: .any).matching(identifier: "cadence.guided.search")
        .firstMatch
      XCTAssertTrue(search.waitForExistence(timeout: 5))
      search.tap()
      search.typeText("baby\n")
      activate("cadence.guided.pick.b-beginning-baby", app)
      XCTAssertTrue(app.buttons["cadence.guided.setup.0"].label.contains("baby"))
      activate("cadence.guided.start", app)
      activate("cadence.guided.finish-stage", app)
      activate("cadence.guided.select.b-beginning-baby", app)
      activate("cadence.guided.practice.start", app)
      activate("cadence.guided.skip", app)
      activate("cadence.guided.recheck.start", app)
      activate("cadence.guided.finish-stage", app)
      XCTAssertTrue(app.buttons["cadence.guided.done"].waitForExistence(timeout: 5))
      let repeatButton = app.buttons["cadence.guided.repeat"]
      reveal(repeatButton, app, id: "cadence.guided.repeat")
      let summary = XCTAttachment(screenshot: app.screenshot())
      summary.name = largeText ? "repeat-five-summary-largest-text" : "repeat-five-summary-compact"
      summary.lifetime = .keepAlways
      add(summary)
      activate("cadence.guided.repeat", app)
      for (index, word) in ["baby", "pig", "moon", "tiger", "dog"].enumerated() {
        waitLabel(app.staticTexts["cadence.word"], word)
        waitLabel(
          app.staticTexts["cadence.guided.visit-heading"], "First review · \(index + 1) of 5")
        XCTAssertTrue(app.buttons["cadence.record"].exists)
        XCTAssertFalse(app.buttons["cadence.replay"].exists)
        XCTAssertFalse(app.staticTexts["cadence.word-check-result"].exists)
        XCTAssertFalse(app.staticTexts["cadence.guided.first-observation"].exists)
        XCTAssertFalse(app.buttons["cadence.guided.continue"].isEnabled)
        activate("cadence.guided.skip", app)
      }
      XCTAssertTrue(app.buttons["cadence.guided.practice.start"].waitForExistence(timeout: 5))
      XCTAssertFalse(app.buttons["cadence.guided.practice.start"].isEnabled)
      XCTAssertEqual(
        app.buttons["cadence.guided.select.b-beginning-baby"].value as? String, "Not selected")
      activate("cadence.guided.close", app)
      XCTAssertTrue(app.buttons["cadence.local-guided.open"].waitForExistence(timeout: 5))
      XCTAssertEqual(historyRows(app), history)
    }

    private func historyRows(_ app: XCUIApplication) -> [String] {
      app.descendants(matching: .any).matching(
        NSPredicate(format: "identifier BEGINSWITH %@", "cadence.history.entry-")
      ).allElementsBoundByIndex.map(\.identifier).sorted()
    }
    private func waitLabel(_ element: XCUIElement, _ label: String) {
      let expectation = XCTNSPredicateExpectation(
        predicate: NSPredicate(format: "label == %@", label), object: element)
      XCTAssertEqual(XCTWaiter.wait(for: [expectation], timeout: 5), .completed)
    }
    private func activate(_ id: String, _ app: XCUIApplication) {
      let button = app.buttons[id]
      // Native List choices are materialized as the picker scrolls.
      if !id.hasPrefix("cadence.guided.pick.") {
        XCTAssertTrue(button.waitForExistence(timeout: 5), id)
      }
      reveal(button, app, id: id)
      XCTAssertTrue(button.exists, id)
      XCTAssertTrue(button.isEnabled, id)
      XCTAssertGreaterThanOrEqual(button.frame.height, 44, id)
      button.tap()
    }

    private func keepPickerScreenshot(_ name: String, _ app: XCUIApplication) {
      let attachment = XCTAttachment(screenshot: app.screenshot())
      attachment.name = name
      attachment.lifetime = .keepAlways
      add(attachment)
    }

    // The native picker List scrolls through its full-width cells. Other stages use
    // observed blank gutters so short positioning drags cannot activate word buttons.
    private func reveal(_ target: XCUIElement, _ app: XCUIApplication, id: String) {
      if id == "cadence.guided.close", target.exists {
        XCTAssertTrue(target.isHittable)
        return
      }
      // The picker is a native List (AX CollectionView) above the setup scroll.
      // Its full-width cells have no blank gutter; use its native scrolling gesture.
      let picker = app.collectionViews["cadence.guided.picker.scroll"]
      if picker.exists {
        var measurements: [[String: Any]] = []
        var capturedFirstRealized = false
        defer {
          if let data = try? JSONSerialization.data(
            withJSONObject: measurements, options: [.sortedKeys]) {
            let attachment = XCTAttachment(data: data, uniformTypeIdentifier: "public.json")
            attachment.name = "repeat-picker-movement-" + id
            attachment.lifetime = .keepAlways
            add(attachment)
          }
        }
        for move in 0..<12 {
          let viewport = picker.frame.intersection(app.windows.firstMatch.frame)
          let top = viewport.minY + 8, bottom = viewport.maxY - 8
          guard !viewport.isEmpty, top.isFinite, bottom.isFinite,
            viewport.minX.isFinite, viewport.maxX.isFinite, bottom > top
          else {
            XCTFail("Invalid picker viewport: \(id)")
            return
          }
          guard target.exists else {
            measurements.append(["move": move, "realized": false,
              "viewport": [viewport.minX, top, viewport.width, bottom - top]])
            picker.swipeUp(velocity: .slow)
            continue
          }
          let frame = target.frame
          guard !frame.isEmpty, frame.minY.isFinite, frame.maxY.isFinite,
            frame.minX.isFinite, frame.maxX.isFinite, frame.height <= bottom - top
          else {
            capturePracticeFailure(app)
            XCTFail("Invalid or oversized picker choice: \(id)")
            return
          }
          if !capturedFirstRealized {
            keepPickerScreenshot("repeat-picker-first-realized-" + id, app)
            capturedFirstRealized = true
          }
          var measurement: [String: Any] = [
            "move": move, "realized": true,
            "viewport": [viewport.minX, top, viewport.width, bottom - top],
            "before": [frame.minX, frame.minY, frame.width, frame.height],
            "hittable": target.isHittable,
          ]
          if frame.minY >= top, frame.maxY <= bottom, target.isHittable {
            measurements.append(measurement)
            keepPickerScreenshot("repeat-picker-ready-" + id, app)
            return
          }
          // Native List rows span the width. Use a short native pan, measured
          // from this realized row; a full swipe can unmaterialize it again.
          let desiredTop = top + (bottom - top - frame.height) / 2
          let distance = frame.minY - desiredTop
          guard abs(distance) > 0 else {
            measurements.append(measurement)
            capturePracticeFailure(app)
            XCTFail("Centered picker choice is not hittable: \(id)")
            return
          }
          let travel = min(max(abs(distance), 12), (bottom - top) * 0.35)
          let center = (top + bottom) / 2
          let down = distance < 0
          let origin = picker.coordinate(withNormalizedOffset: .zero)
          let start = origin.withOffset(CGVector(
            dx: viewport.minX + 12 - picker.frame.minX,
            dy: center + (down ? -travel / 2 : travel / 2) - picker.frame.minY))
          let finish = origin.withOffset(CGVector(
            dx: viewport.minX + 12 - picker.frame.minX,
            dy: center + (down ? travel / 2 : -travel / 2) - picker.frame.minY))
          start.press(forDuration: 0.01, thenDragTo: finish,
            withVelocity: .slow, thenHoldForDuration: 0.2)
          measurement["travel"] = travel
          measurement["dragDown"] = down
          measurement["realizedAfter"] = target.exists
          if target.exists {
            let after = target.frame
            measurement["after"] = [after.minX, after.minY, after.width, after.height]
            measurement["movement"] = after.minY - frame.minY
          }
          measurements.append(measurement)
        }
        capturePracticeFailure(app)
        XCTFail("Picker choice did not enter viewport: \(id)")
        return
      }
      let scroll = app.scrollViews.firstMatch
      for _ in 0..<24 {
        let viewport = scroll.frame
        let header = max(
          app.buttons["cadence.guided.close"].exists
            ? app.buttons["cadence.guided.close"].frame.maxY : viewport.minY,
          app.buttons["cadence.guided.picker.cancel"].exists
            ? app.buttons["cadence.guided.picker.cancel"].frame.maxY : viewport.minY)
        let top = max(viewport.minY, header) + 8
        let bottom = min(viewport.maxY, app.windows.firstMatch.frame.maxY) - 8
        let height = bottom - top
        guard height > 0 else {
          XCTFail("No unobscured viewport")
          return
        }
        let frame = target.frame
        let oversized = frame.height > height
        if frame.minY >= top
          && (oversized ? frame.minY <= top + height * 0.2 : frame.maxY <= bottom)
          && target.isHittable
        {
          return
        }
        let desired = oversized ? top : top + (height - frame.height) / 2
        let above = frame.minY < desired
        let travel = min(max(abs(frame.minY - desired), 24), height * 0.6)
        let left = max(viewport.minX, app.windows.firstMatch.frame.minX)
        let right = min(viewport.maxX, app.windows.firstMatch.frame.maxX)
        let frames = (scroll.buttons.allElementsBoundByIndex.map(\.frame) + [frame]).filter {
          !$0.isEmpty && $0.maxX > left && $0.minX < right
        }
        let leading = frames.map(\.minX).min() ?? left
        let trailing = frames.map(\.maxX).max() ?? right
        let x: CGFloat
        if leading - left >= 16 {
          x = (left + leading) / 2
        } else if right - trailing >= 16 {
          x = (right + trailing) / 2
        } else {
          capturePracticeFailure(app)
          XCTFail("No blank scroll gutter")
          return
        }
        let center = (top + bottom) / 2
        let origin = scroll.coordinate(withNormalizedOffset: .zero)
        let start = origin.withOffset(
          CGVector(
            dx: x - viewport.minX,
            dy: center + (above ? -travel / 2 : travel / 2) - viewport.minY))
        let end = origin.withOffset(
          CGVector(
            dx: x - viewport.minX,
            dy: center + (above ? travel / 2 : -travel / 2) - viewport.minY))
        start.press(
          forDuration: 0.01, thenDragTo: end, withVelocity: .slow, thenHoldForDuration: 0.2)
      }
      XCTFail("Control did not enter viewport: \(target.identifier)")
    }
  }
#endif
