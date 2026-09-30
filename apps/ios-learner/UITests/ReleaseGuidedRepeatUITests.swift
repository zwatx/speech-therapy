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
      XCTAssertTrue(button.waitForExistence(timeout: 5), id)
      reveal(button, app)
      XCTAssertTrue(button.isEnabled, id)
      XCTAssertGreaterThanOrEqual(button.frame.height, 44, id)
      button.tap()
    }

    // The native picker List scrolls through its full-width cells. Other stages use
    // observed blank gutters so short positioning drags cannot activate word buttons.
    private func reveal(_ target: XCUIElement, _ app: XCUIApplication) {
      if target.identifier == "cadence.guided.close" {
        XCTAssertTrue(target.isHittable)
        return
      }
      // The picker is a native List (AX CollectionView) above the setup scroll.
      // Its full-width cells have no blank gutter; use its native scrolling gesture.
      let picker = app.collectionViews["cadence.guided.picker.scroll"]
      if picker.exists {
        for _ in 0..<12 {
          let viewport = picker.frame.intersection(app.windows.firstMatch.frame)
          let frame = target.frame
          if frame.minY >= viewport.minY + 8, frame.maxY <= viewport.maxY - 40,
            target.isHittable { return }
          if frame.minY < viewport.minY + 8 {
            picker.swipeDown(velocity: .slow)
          } else {
            picker.swipeUp(velocity: .slow)
          }
        }
        capturePracticeFailure(app)
        XCTFail("Picker choice did not enter viewport: \(target.identifier)")
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
