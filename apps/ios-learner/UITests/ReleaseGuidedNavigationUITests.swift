import XCTest

// The ordinary Debug root exposes development routes; this suite verifies Release only.
#if !DEBUG
  /// Ordinary Release-root navigation only. No capture, playback, checks or camera actions.
  @MainActor
  final class ReleaseGuidedNavigationUITests: XCTestCase {
    private let words = ["ball", "pig", "moon", "tiger", "dog"]
    private let entryIDs = [
      "b-beginning-ball", "p-beginning-pig", "m-beginning-moon", "t-beginning-tiger",
      "d-beginning-dog",
    ]

    func testReleaseHomeGuidedSkippedRoundsPreserveObservationsAndHistory() {
      let app = launch(largeText: false)
      defer { app.terminate() }
      let history = historyRows(app)
      activate("cadence.local-guided.open", app)
      assertSetup(app)
      keepScreenshot("release-guided-setup", app)
      activate("cadence.guided.setup.0", app)
      XCTAssertTrue(app.navigationBars["Change word"].waitForExistence(timeout: 5))
      let position = app.buttons["cadence.guided.position-filter"]
      XCTAssertEqual(position.value as? String, "All positions")
      activate("cadence.guided.position-filter", app)
      let beginning = app.buttons["Beginning"]
      XCTAssertTrue(beginning.waitForExistence(timeout: 5))
      XCTAssertTrue(beginning.isHittable)
      beginning.tap()
      XCTAssertEqual(position.value as? String, "Beginning")
      activate("cadence.guided.position-filter", app)
      let allPositions = app.buttons["All positions"]
      XCTAssertTrue(allPositions.waitForExistence(timeout: 5))
      XCTAssertTrue(allPositions.isHittable)
      allPositions.tap()
      XCTAssertEqual(position.value as? String, "All positions")
      let cancel = app.buttons["cadence.guided.picker.cancel"]
      XCTAssertTrue(cancel.isHittable)
      cancel.tap()
      assertSetup(app)
      activate("cadence.guided.start", app)
      for (index, word) in words.enumerated() {
        assertReady(word, stage: "First review", index: index, count: 5, app)
        activate("cadence.guided.skip", app)
      }
      let practiceStart = app.buttons["cadence.guided.practice.start"]
      XCTAssertTrue(practiceStart.waitForExistence(timeout: 5))
      XCTAssertFalse(practiceStart.isEnabled)
      for id in entryIDs {
        let choice = app.buttons["cadence.guided.select." + id]
        XCTAssertEqual(choice.value as? String, "Not selected")
        XCTAssertTrue(choice.label.contains("First review: Skipped"))
      }
      activate("cadence.guided.select.p-beginning-pig", app)
      XCTAssertEqual(
        app.buttons["cadence.guided.select.p-beginning-pig"].value as? String, "Selected")
      for id in entryIDs where id != "p-beginning-pig" {
        XCTAssertEqual(app.buttons["cadence.guided.select." + id].value as? String, "Not selected")
      }
      waitLabel(practiceStart, "Practice selected words (1)")
      keepScreenshot("release-guided-manual-choice", app)
      activate("cadence.guided.practice.start", app)
      assertReady("pig", stage: "Practice", index: 0, count: 1, app)
      XCTAssertTrue(
        app.staticTexts["cadence.guided.first-observation"].label.contains("First review: Skipped"))
      activate("cadence.guided.skip", app)
      let recheck = app.buttons["cadence.guided.recheck.start"]
      XCTAssertTrue(recheck.waitForExistence(timeout: 5))
      XCTAssertTrue(app.staticTexts["Skipped"].exists)
      XCTAssertFalse(app.staticTexts["Participation saved"].exists)
      activate("cadence.guided.recheck.start", app)
      for (index, word) in words.enumerated() {
        assertReady(word, stage: "Recheck", index: index, count: 5, app)
        XCTAssertTrue(
          app.staticTexts["cadence.guided.first-observation"].label.contains(
            "First review: Skipped"))
        activate("cadence.guided.skip", app)
      }
      XCTAssertTrue(app.buttons["cadence.guided.done"].waitForExistence(timeout: 5))
      for (index, id) in entryIDs.enumerated() {
        let row = app.staticTexts["cadence.guided.paired." + id]
        XCTAssertTrue(row.waitForExistence(timeout: 5))
        reveal(row, app)
        XCTAssertTrue(row.label.contains(words[index]))
        XCTAssertTrue(row.label.contains("First review: Skipped"))
        XCTAssertTrue(row.label.contains("Recheck: Skipped"))
      }
      keepScreenshot("release-guided-paired-skips", app)
      activate("cadence.guided.done", app)
      assertHome(app)
      XCTAssertEqual(historyRows(app), history)
      activate("cadence.local-guided.open", app)
      assertSetup(app)
      XCTAssertFalse(app.buttons["cadence.guided.done"].exists)
      activate("cadence.guided.close", app)
      assertHome(app)
      XCTAssertEqual(historyRows(app), history)
    }

    func testReleaseLargestTextSetupFirstVisitAndCloseReachHomeWithoutMedia() throws {
      let app = launch(largeText: true)
      defer { app.terminate() }
      let history = historyRows(app)
      activate("cadence.local-guided.open", app)
      assertSetup(app)
      // These same sampled points missed the native toolbar Cancel in the failed run.
      // Require dismissal through the replacement header at centerY ±21 points.
      // A growing large-text label can make these interior points, not actual edges.
      var cancelProbes: [[String: Any]] = []
      for verticalOffset: CGFloat in [-21, 21] {
        activate("cadence.guided.setup.0", app)
        XCTAssertTrue(app.navigationBars["Change word"].waitForExistence(timeout: 5))
        let sound = app.buttons["cadence.guided.sound-filter"]
        let position = app.buttons["cadence.guided.position-filter"]
        XCTAssertEqual(sound.value as? String, "All sounds")
        XCTAssertEqual(position.value as? String, "All positions")
        XCTAssertGreaterThanOrEqual(sound.frame.height, 44)
        XCTAssertGreaterThanOrEqual(position.frame.height, 44)
        let cancel = app.buttons["cadence.guided.picker.cancel"]
        XCTAssertTrue(cancel.isHittable)
        let frame = cancel.frame
        let window = app.windows.firstMatch
        let point = CGPoint(x: frame.midX, y: frame.midY + verticalOffset)
        XCTAssertTrue(window.frame.contains(point))
        keepScreenshot(
          verticalOffset < 0 ? "release-picker-upper-edge" : "release-picker-lower-edge", app)
        window.coordinate(withNormalizedOffset: .zero).withOffset(
          CGVector(dx: point.x - window.frame.minX, dy: point.y - window.frame.minY)
        ).tap()
        let dismissed = XCTNSPredicateExpectation(
          predicate: NSPredicate(format: "exists == false"),
          object: app.navigationBars["Change word"])
        XCTAssertEqual(XCTWaiter.wait(for: [dismissed], timeout: 5), .completed)
        XCTAssertTrue(app.buttons["cadence.guided.setup.0"].isHittable)
        assertSetup(app)
        cancelProbes.append([
          "labelFrame": [frame.minX, frame.minY, frame.width, frame.height],
          "tapPoint": [point.x, point.y], "verticalOffset": verticalOffset,
          "setupReturned": true,
        ])
      }
      let probeData = try JSONSerialization.data(
        withJSONObject: cancelProbes, options: [.sortedKeys])
      let probeAttachment = XCTAttachment(data: probeData, uniformTypeIdentifier: "public.json")
      probeAttachment.name = "release-picker-cancel-touch-probes"
      probeAttachment.lifetime = .keepAlways
      add(probeAttachment)
      activate("cadence.guided.start", app)
      assertReady("ball", stage: "First review", index: 0, count: 5, app)
      reveal(app.buttons["cadence.record"], app)
      keepScreenshot("release-guided-largest-text-ready", app)
      activate("cadence.guided.close", app)
      assertHome(app)
      XCTAssertEqual(historyRows(app), history)
    }

    private func launch(largeText: Bool) -> XCUIApplication {
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
      assertHome(app)
      XCTAssertFalse(app.staticTexts["cadence.home.ui-test-banner"].exists)
      XCTAssertFalse(app.staticTexts["cadence.generated-guided.banner"].exists)
      XCTAssertFalse(app.buttons["cadence.guided-word.start"].exists)
      return app
    }

    private func assertHome(_ app: XCUIApplication) {
      XCTAssertTrue(app.buttons["cadence.local-guided.open"].waitForExistence(timeout: 5))
      XCTAssertFalse(app.buttons["cadence.guided.close"].exists)
    }

    private func assertSetup(_ app: XCUIApplication) {
      XCTAssertTrue(app.buttons["cadence.guided.start"].waitForExistence(timeout: 5))
      for (index, word) in words.enumerated() {
        XCTAssertTrue(
          app.buttons["cadence.guided.setup.\(index)"].label.contains(
            "Change word \(index + 1), \(word),"))
      }
      XCTAssertFalse(app.switches["cadence.guided.model-enabled"].exists)
      XCTAssertFalse(app.buttons["cadence.record"].exists)
    }

    private func assertReady(
      _ word: String, stage: String, index: Int, count: Int, _ app: XCUIApplication
    ) {
      waitLabel(app.staticTexts["cadence.word"], word)
      waitLabel(
        app.staticTexts["cadence.guided.visit-heading"], "\(stage) · \(index + 1) of \(count)")
      XCTAssertTrue(app.buttons["cadence.record"].exists)
      XCTAssertFalse(app.buttons["cadence.guided.continue"].isEnabled)
      XCTAssertFalse(app.buttons["cadence.replay"].exists)
      XCTAssertFalse(app.staticTexts["cadence.word-check-result"].exists)
    }

    private func historyRows(_ app: XCUIApplication) -> [String] {
      app.descendants(matching: .any).matching(
        NSPredicate(format: "identifier BEGINSWITH %@", "cadence.history.entry-")
      ).allElementsBoundByIndex.map(\.identifier).sorted()
    }

    private func activate(_ id: String, _ app: XCUIApplication) {
      let button = app.buttons[id]
      XCTAssertTrue(button.waitForExistence(timeout: 5), id)
      if id == "cadence.guided.close" {
        XCTAssertTrue(button.isHittable, id)
      } else {
        reveal(button, app)
      }
      XCTAssertTrue(button.isEnabled, id)
      XCTAssertGreaterThanOrEqual(button.frame.height, 44, id)
      button.tap()
    }

    private func waitLabel(_ element: XCUIElement, _ expected: String) {
      let match = XCTNSPredicateExpectation(
        predicate: NSPredicate(format: "label == %@", expected), object: element)
      XCTAssertEqual(XCTWaiter.wait(for: [match], timeout: 5), .completed, expected)
    }

    private func keepScreenshot(_ name: String, _ app: XCUIApplication) {
      let attachment = XCTAttachment(screenshot: app.screenshot())
      attachment.name = name
      attachment.lifetime = .keepAlways
      add(attachment)
    }

    // Adapt the existing guided test's observed-gutter scroll: never drag over choice buttons.
    // Targets are measured afresh after every drag, including oversized accessibility text.
    private func reveal(_ target: XCUIElement, _ app: XCUIApplication) {
      let scroll = app.scrollViews.firstMatch
      let viewport = scroll.frame
      let close = app.buttons["cadence.guided.close"]
      let pickerCancel = app.buttons["cadence.guided.picker.cancel"]
      let headerBottom = max(
        close.exists ? close.frame.maxY : viewport.minY,
        pickerCancel.exists ? pickerCancel.frame.maxY : viewport.minY)
      let top = max(viewport.minY, headerBottom) + 8
      let bottom = min(viewport.maxY, app.windows.firstMatch.frame.maxY) - 8
      let height = bottom - top
      guard height > 0 else {
        XCTFail("No unobscured scroll viewport")
        return
      }
      var previousFrame: CGRect?
      var previousTravel: CGFloat = 0
      var previousAbove: Bool?
      for _ in 0..<24 {
        let frame = target.frame
        let oversized = frame.height > height
        if frame.minY >= top,
          oversized ? frame.minY <= top + height * 0.2 : frame.maxY <= bottom,
          target.isHittable
        {
          return
        }
        let desiredTop = oversized ? top : top + (height - frame.height) / 2
        let above = frame.minY < desiredTop
        let distance = abs(frame.minY - desiredTop)
        var travel =
          oversized ? min(max(distance, height * 0.2), height * 0.6) : min(distance, height * 0.6)
        if !oversized, distance > 0, distance <= 24,
          let previousFrame, previousTravel > 0, previousAbove == above,
          previousFrame.minX == frame.minX, previousFrame.size == frame.size
        {
          let movement = (frame.minY - previousFrame.minY) * (above ? 1 : -1)
          if movement >= 0, movement <= previousTravel {
            travel = min(distance + min(previousTravel - movement, 24), height * 0.6)
          }
        }
        guard travel > 0 else { continue }
        let frames = scroll.buttons.allElementsBoundByIndex.map(\.frame) + [frame]
        let left = max(viewport.minX, app.windows.firstMatch.frame.minX)
        let right = min(viewport.maxX, app.windows.firstMatch.frame.maxX)
        let active = frames.filter { !$0.isEmpty && $0.maxX > left && $0.minX < right }
        guard active.allSatisfy({ $0.minX.isFinite && $0.maxX.isFinite }) else {
          XCTFail("Invalid control geometry")
          return
        }
        let leading = active.map(\.minX).min() ?? left
        let trailing = active.map(\.maxX).max() ?? right
        let x: CGFloat
        if leading - left >= 16 {
          x = (left + leading) / 2
        } else if right - trailing >= 16 {
          x = (right + trailing) / 2
        } else {
          XCTFail("No blank scroll gutter")
          return
        }
        let center = (top + bottom) / 2
        let origin = scroll.coordinate(withNormalizedOffset: .zero)
        let start = origin.withOffset(
          CGVector(
            dx: x - viewport.minX, dy: center + (above ? -travel / 2 : travel / 2) - viewport.minY))
        let finish = origin.withOffset(
          CGVector(
            dx: x - viewport.minX, dy: center + (above ? travel / 2 : -travel / 2) - viewport.minY))
        previousFrame = frame
        previousTravel = travel
        previousAbove = above
        start.press(
          forDuration: 0.01, thenDragTo: finish, withVelocity: .slow, thenHoldForDuration: 0.2)
      }
      XCTFail("Control did not enter the unobscured viewport: \(target.identifier)")
    }
  }

#endif
