import XCTest

#if !DEBUG
  /// Ordinary Release-root handoff, without fixture flags or media operations.
  @MainActor
  final class ReleaseGuidedPracticeHandoffUITests: XCTestCase {
    func testReleaseReviewWordOpensIndependentPracticeWithoutMedia() {
      journey(largeText: false)
    }

    func testReleaseLargestTextReviewWordOpensIndependentPracticeWithoutMedia() {
      journey(largeText: true)
    }

    private func journey(largeText: Bool) {
      continueAfterFailure = false
      executionTimeAllowance = 360
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
      defer {
        if let run = testRun, run.failureCount > 0 { capturePracticeFailure(app) }
        app.terminate()
      }
      waitForPracticeSystemBannerToClear()
      assertHome(app)
      XCTAssertFalse(app.staticTexts["cadence.home.ui-test-banner"].exists)
      XCTAssertFalse(app.staticTexts["cadence.generated-guided.banner"].exists)
      XCTAssertFalse(app.buttons["cadence.guided-word.start"].exists)
      let history = historyRows(app)
      let prefix = "guided-practice-handoff-" + (largeText ? "largest" : "normal")

      activate("cadence.local-guided.open", app)
      XCTAssertTrue(app.buttons["cadence.guided.setup.2"].label.contains("moon"))
      activate("cadence.guided.setup.2", app)
      let search = app.descendants(matching: .any)
        .matching(identifier: "cadence.guided.search").firstMatch
      XCTAssertTrue(search.waitForExistence(timeout: 5))
      search.tap()
      search.typeText("bread\n")
      // Bread has B, R and D entries: choose the canonical R-middle entry explicitly.
      activate("cadence.guided.pick.r-middle-bread", app)
      XCTAssertTrue(app.buttons["cadence.guided.setup.2"].label.contains("bread"))
      XCTAssertTrue(app.buttons["cadence.guided.setup.0"].label.contains("ball"))
      activate("cadence.guided.start", app)
      waitLabel(app.staticTexts["cadence.word"], "ball")
      activate("cadence.guided.finish-stage", app)
      activate("cadence.guided.select.r-middle-bread", app)
      waitLabel(app.buttons["cadence.guided.practice.start"], "Practice selected words (1)")
      activate("cadence.guided.practice.start", app)
      waitLabel(app.staticTexts["cadence.word"], "bread")
      assertNoAutomaticMedia(app)
      activate("cadence.guided.skip", app)
      activate("cadence.guided.recheck.start", app)
      waitLabel(app.staticTexts["cadence.word"], "ball")
      activate("cadence.guided.finish-stage", app)
      XCTAssertTrue(app.buttons["cadence.guided.done"].waitForExistence(timeout: 5))
      XCTAssertTrue(app.buttons["cadence.guided.done"].isEnabled)
      XCTAssertTrue(app.buttons["cadence.guided.repeat"].isEnabled)
      XCTAssertTrue(app.buttons["cadence.guided.close"].isEnabled)
      let note = app.staticTexts["cadence.guided.independent-practice-note"]
      waitLabel(note, "Practice ends this review. These observations won’t carry over.")
      captureText(note, name: prefix + "-summary-note", app)
      for (id, word) in [
        ("b-beginning-ball", "ball"), ("p-beginning-pig", "pig"),
        ("r-middle-bread", "bread"), ("t-beginning-tiger", "tiger"),
        ("d-beginning-dog", "dog"),
      ] {
        let button = app.buttons["cadence.guided.independent-practice." + id]
        waitLabel(button, "Practice " + word)
        reveal(button, app)
        XCTAssertTrue(button.isEnabled)
        XCTAssertGreaterThanOrEqual(button.frame.height, 44)
        XCTAssertGreaterThanOrEqual(button.frame.width, 44)
      }
      let firstRow = app.staticTexts["cadence.guided.paired.b-beginning-ball"]
      XCTAssertTrue(firstRow.label.contains("First review: Skipped"))
      XCTAssertTrue(firstRow.label.contains("Practice: Not selected"))
      XCTAssertTrue(firstRow.label.contains("Recheck: Skipped"))
      let tree = XCTAttachment(string: app.debugDescription)
      tree.name = prefix + "-summary-accessibility"
      tree.lifetime = .keepAlways
      add(tree)
      let row = app.staticTexts["cadence.guided.paired.r-middle-bread"]
      XCTAssertTrue(row.exists)
      XCTAssertTrue(row.label.contains("bread"))
      XCTAssertTrue(row.label.contains("First review: Not reached"))
      XCTAssertTrue(row.label.contains("Practice: Skipped"))
      XCTAssertTrue(row.label.contains("Recheck: Not reached"))
      captureText(row, name: prefix + "-bread-observations", app)
      reveal(app.buttons["cadence.guided.independent-practice.r-middle-bread"], app)
      keepScreenshot(prefix + "-bread-practice-action", app)
      activate("cadence.guided.independent-practice.r-middle-bread", app)

      XCTAssertTrue(app.buttons["cadence.close"].waitForExistence(timeout: 5))
      waitLabel(app.staticTexts["cadence.word"], "bread")
      keepScreenshot(prefix + "-ordinary-destination-before-assertions", app)
      let count = app.staticTexts["Word 1 of 1"]
      XCTAssertTrue(count.exists)
      XCTAssertTrue(count.isHittable)
      let position = app.staticTexts["/ɹ/ in the middle"]
      XCTAssertTrue(position.exists)
      reveal(position, app)
      assertFreshOrdinary(app)
      keepScreenshot(prefix + "-ordinary-destination", app)
      activate("cadence.sound-guide.toggle", app)
      let guide = app.staticTexts["cadence.sound-guide.title"]
      waitLabel(guide, "R in the BR of “bread”")
      captureText(guide, name: prefix + "-exact-r-middle-target", app)
      assertFreshOrdinary(app)
      activate("cadence.sound-guide.toggle", app)
      activate("cadence.skip-word", app)
      let completed = app.staticTexts["cadence.complete"]
      waitLabel(completed, "You skipped all 1 word. Nothing was added to recent practice.")
      captureText(completed, name: prefix + "-single-word-completed", app)
      XCTAssertFalse(app.staticTexts["cadence.history-saved"].exists)
      activate("cadence.close", app)
      assertHome(app)
      XCTAssertEqual(historyRows(app), history)
      activate("cadence.local-guided.open", app)
      XCTAssertTrue(app.buttons["cadence.guided.start"].waitForExistence(timeout: 5))
      XCTAssertTrue(app.buttons["cadence.guided.setup.2"].label.contains("moon"))
      XCTAssertFalse(app.buttons["cadence.guided.done"].exists)
      XCTAssertFalse(app.staticTexts["cadence.guided.first-observation"].exists)
      activate("cadence.guided.close", app)
      assertHome(app)
      XCTAssertEqual(historyRows(app), history)
    }

    private func assertFreshOrdinary(_ app: XCUIApplication) {
      for id in ["cadence.guided.done", "cadence.guided.close", "cadence.guided.skip"] {
        XCTAssertFalse(app.buttons[id].exists, id)
      }
      for id in ["cadence.guided.visit-heading", "cadence.guided.first-observation",
                 "cadence.guided.status", "cadence.guided.model-observation"] {
        XCTAssertFalse(app.staticTexts[id].exists, id)
      }
      XCTAssertTrue(app.buttons["cadence.record"].isEnabled)
      assertNoAutomaticMedia(app)
    }

    private func assertNoAutomaticMedia(_ app: XCUIApplication) {
      for id in ["cadence.stop", "cadence.replay", "cadence.replay-earlier",
                 "cadence.word-check-cancel", "cadence.mirror.hide", "cadence.mirror.cancel"] {
        XCTAssertFalse(app.buttons[id].exists, id)
      }
      for id in ["cadence.word-check-result", "cadence.word-check-status",
                 "cadence.playback-status", "cadence.mirror.preview"] {
        XCTAssertFalse(app.descendants(matching: .any).matching(identifier: id).firstMatch.exists, id)
      }
    }

    private func assertHome(_ app: XCUIApplication) {
      XCTAssertTrue(app.buttons["cadence.local-guided.open"].waitForExistence(timeout: 5))
      XCTAssertFalse(app.buttons["cadence.close"].exists)
      XCTAssertFalse(app.buttons["cadence.guided.close"].exists)
    }

    private func historyRows(_ app: XCUIApplication) -> [String] {
      app.descendants(matching: .any).matching(
        NSPredicate(format: "identifier BEGINSWITH %@", "cadence.history.entry-")
      ).allElementsBoundByIndex.map(\.identifier).sorted()
    }

    private func waitLabel(_ element: XCUIElement, _ label: String) {
      let expectation = XCTNSPredicateExpectation(
        predicate: NSPredicate(format: "label == %@", label), object: element)
      XCTAssertEqual(XCTWaiter.wait(for: [expectation], timeout: 5), .completed, label)
    }

    private func activate(_ id: String, _ app: XCUIApplication) {
      let button = app.buttons[id]
      if !id.hasPrefix("cadence.guided.pick.") {
        XCTAssertTrue(button.waitForExistence(timeout: 5), id)
      }
      if id == "cadence.guided.close" {
        XCTAssertTrue(button.isHittable, id)
      } else {
        reveal(button, app)
      }
      XCTAssertTrue(button.exists, id)
      XCTAssertTrue(button.isEnabled, id)
      XCTAssertGreaterThanOrEqual(button.frame.height, 44, id)
      XCTAssertGreaterThanOrEqual(button.frame.width, 44, id)
      button.tap()
    }

    private func keepScreenshot(_ name: String, _ app: XCUIApplication) {
      let attachment = XCTAttachment(screenshot: app.screenshot())
      attachment.name = name
      attachment.lifetime = .keepAlways
      add(attachment)
    }

    private func captureText(_ section: XCUIElement, name: String, _ app: XCUIApplication) {
      reveal(section, app)
      keepScreenshot(name, app)
      let scroll = app.scrollViews.firstMatch
      var measurements: [[String: Any]] = []
      defer {
        if !measurements.isEmpty,
          let data = try? JSONSerialization.data(withJSONObject: measurements, options: [.sortedKeys])
        {
          let attachment = XCTAttachment(data: data, uniformTypeIdentifier: "public.json")
          attachment.name = name + "-text-scroll-geometry"
          attachment.lifetime = .keepAlways
          add(attachment)
        }
      }
      // Keep overlapping text segments when an AX paragraph exceeds the screen.
      // Each move uses current geometry and the same observed blank gutter as reveal.
      for segment in 1...8 {
        let viewport = scroll.frame.intersection(app.windows.firstMatch.frame)
        let guidedClose = app.buttons["cadence.guided.close"]
        let ordinaryClose = app.buttons["cadence.close"]
        let header = max(guidedClose.exists ? guidedClose.frame.maxY : viewport.minY,
                         ordinaryClose.exists ? ordinaryClose.frame.maxY : viewport.minY)
        let top = max(viewport.minY, header) + 8
        let bottom = viewport.maxY - 8
        let frame = section.frame
        guard section.exists, !frame.isEmpty, frame.minY.isFinite, frame.maxY.isFinite,
          bottom > top
        else {
          XCTFail("Invalid text paragraph geometry: \(name)")
          return
        }
        measurements.append([
          "segment": segment, "viewport": [viewport.minX, top, viewport.width, bottom - top],
          "text": [frame.minX, frame.minY, frame.width, frame.height],
        ])
        if frame.maxY <= bottom { return }
        let travel = min(max(frame.maxY - bottom + 4, 24), (bottom - top) * 0.55)
        let frames = scroll.buttons.allElementsBoundByIndex.map(\.frame) + [frame]
        let active = frames.filter { !$0.isEmpty && $0.maxX > viewport.minX && $0.minX < viewport.maxX }
        guard active.allSatisfy({ $0.minX.isFinite && $0.maxX.isFinite }),
          let leading = active.map(\.minX).min(), let trailing = active.map(\.maxX).max()
        else {
          XCTFail("Invalid text scroll control geometry: \(name)")
          return
        }
        let x: CGFloat
        if leading - viewport.minX >= 16 {
          x = (viewport.minX + leading) / 2
        } else if viewport.maxX - trailing >= 16 {
          x = (viewport.maxX + trailing) / 2
        } else {
          XCTFail("No blank text scroll gutter: \(name)")
          return
        }
        let center = (top + bottom) / 2
        let origin = scroll.coordinate(withNormalizedOffset: .zero)
        let start = origin.withOffset(CGVector(
          dx: x - scroll.frame.minX, dy: center + travel / 2 - scroll.frame.minY))
        let finish = origin.withOffset(CGVector(
          dx: x - scroll.frame.minX, dy: center - travel / 2 - scroll.frame.minY))
        start.press(forDuration: 0.01, thenDragTo: finish, withVelocity: .slow, thenHoldForDuration: 0.2)
        let nextFrame = section.frame
        let movement = frame.minY - nextFrame.minY
        measurements.append([
          "viewport": [viewport.minX, top, viewport.width, bottom - top],
          "before": [frame.minX, frame.minY, frame.width, frame.height],
          "after": [nextFrame.minX, nextFrame.minY, nextFrame.width, nextFrame.height],
          "travel": travel, "movement": movement,
        ])
        keepScreenshot(name + "-segment-\(segment)", app)
        guard movement > 1 else {
          XCTFail("Text paragraph did not scroll toward its end: \(name)")
          return
        }
        if nextFrame.maxY <= bottom { return }
      }
      XCTFail("Text paragraph end did not enter the viewport within eight moves: \(name)")
    }

    // Adapt the existing guided test's observed-gutter scroll: never drag over choice buttons.
    // Targets are measured afresh after every drag, including oversized accessibility text.
    private func reveal(_ target: XCUIElement, _ app: XCUIApplication) {
      // Reuse the native List traversal from ReleaseGuidedRepeatUITests. Its
      // full-width AX cells have no blank gutter, unlike the practice ScrollView.
      let picker = app.collectionViews["cadence.guided.picker.scroll"]
      if picker.exists {
        for _ in 0..<12 {
          let viewport = picker.frame.intersection(app.windows.firstMatch.frame)
          if target.exists, !target.frame.isEmpty {
            let frame = target.frame
            // The final result has 24pt content padding; require full visibility,
            // without demanding extra clearance the list cannot scroll to supply.
            let bottomMargin: CGFloat =
              target.identifier.hasPrefix("cadence.guided.pick.") ? 8 : 40
            if frame.minY >= viewport.minY + 8, frame.maxY <= viewport.maxY - bottomMargin,
              target.isHittable { return }
            if frame.minY < viewport.minY + 8 {
              picker.swipeDown(velocity: .slow)
            } else {
              picker.swipeUp(velocity: .slow)
            }
          } else {
            picker.swipeUp(velocity: .slow)
          }
        }
        capturePracticeFailure(app)
        XCTFail("Picker choice did not enter viewport: \(target.identifier)")
        return
      }
      let scroll = app.scrollViews.firstMatch
      XCTAssertTrue(scroll.exists, "Expected the current screen's scroll container")
      let viewport = scroll.frame
      let close = app.buttons["cadence.guided.close"]
      let pickerCancel = app.buttons["cadence.guided.picker.cancel"]
      let ordinaryClose = app.buttons["cadence.close"]
      let headerBottom = max(
        max(close.exists ? close.frame.maxY : viewport.minY,
            ordinaryClose.exists && target.identifier != "cadence.close"
              ? ordinaryClose.frame.maxY : viewport.minY),
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
        guard target.exists, !target.frame.isEmpty,
          target.frame.minY.isFinite, target.frame.maxY.isFinite else {
          capturePracticeFailure(app)
          XCTFail("Target has no realized frame: \(target.identifier)")
          return
        }
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
