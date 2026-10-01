import XCTest

#if !DEBUG
  /// Ordinary Release Home, with actual date text and no media or fixture actions.
  @MainActor
  final class ReleaseHomeHeaderUITests: XCTestCase {
    func testReleaseHomeHeaderRemainsReadableAndUsable() { journey(largeText: false) }
    func testReleaseLargestTextHomeHeaderRemainsReadableAndUsable() { journey(largeText: true) }

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
      let prefix = "home-header-" + (largeText ? "largest" : "normal")
      // Registered teardown preserves the final screen even when XCTest has not
      // yet published its failure count. No Home-only element queries belong here.
      addTeardownBlock { @MainActor [weak self] () throws -> Void in
        guard let self else { return }
        if app.state == .runningForeground {
          self.keepScreenshot(prefix + "-final-state", app)
          let tree = XCTAttachment(string: app.debugDescription)
          tree.name = prefix + "-final-state-accessibility"
          tree.lifetime = .keepAlways
          self.add(tree)
        }
        app.terminate()
      }
      let weekdayBeforeLaunch = Date.now.formatted(.dateTime.weekday(.wide))
      app.launch()
      waitForPracticeSystemBannerToClear()
      XCTAssertTrue(app.buttons["cadence.home.about"].waitForExistence(timeout: 5))
      XCTAssertFalse(app.staticTexts["cadence.home.ui-test-banner"].exists)
      XCTAssertFalse(app.staticTexts["cadence.generated-guided.banner"].exists)
      XCTAssertFalse(app.buttons["cadence.guided-word.start"].exists)
      let history = historyRows(app)
      let weekday = app.staticTexts["cadence.home.weekday"]
      let about = app.buttons["cadence.home.about"]
      let scroll = app.scrollViews.firstMatch
      XCTAssertTrue(scroll.exists)
      assertHeader(app, largeText: largeText, weekdayBeforeLaunch: weekdayBeforeLaunch)
      let initialWeekday = weekday.frame, initialAbout = about.frame, initialViewport = scroll.frame
      captureHeader(prefix + "-initial", app)

      let content = app.staticTexts["Today’s practice."]
      XCTAssertTrue(content.exists)
      let beforeContent = content.frame
      let viewport = usableViewport(scroll, app)
      let contentFrames = scroll.staticTexts.allElementsBoundByIndex.map(\.frame)
        + scroll.buttons.allElementsBoundByIndex.map(\.frame)
      let contentBottom = contentFrames.map(\.maxY).max() ?? beforeContent.maxY
      let contentOverflows = contentBottom > viewport.maxY + 1
      pan(scroll, travel: min(viewport.height * 0.35, 120), down: false,
          targetFrame: beforeContent, app)
      let afterContent = content.frame
      let movement = beforeContent.minY - afterContent.minY
      if contentOverflows {
        XCTAssertGreaterThan(movement, 1, "Overflowing Home content must actually scroll")
      } else {
        // A fresh normal-size Home can fit without saved words or history.
        // A bounded pan still verifies its header; do not invent overflow.
        XCTAssertGreaterThanOrEqual(movement, -0.5)
      }
      attachGeometry(prefix + "-home-scroll", [
        "beforeContent": rect(beforeContent), "afterContent": rect(afterContent),
        "viewport": rect(viewport), "contentBottom": contentBottom,
        "contentOverflows": contentOverflows, "movement": movement,
      ])
      assertHeader(app, largeText: largeText, weekdayBeforeLaunch: weekdayBeforeLaunch)
      assertSameFrame(weekday.frame, initialWeekday, "Weekday moved with Home content")
      assertSameFrame(about.frame, initialAbout, "About moved with Home content")
      assertSameFrame(scroll.frame, initialViewport, "Home viewport changed after scrolling")
      captureHeader(prefix + "-after-home-pan", app)

      assertControl(about, id: "cadence.home.about", app)
      about.tap()
      let aboutScroll = app.scrollViews["cadence.about.scroll"]
      XCTAssertTrue(aboutScroll.waitForExistence(timeout: 5))
      let aboutTitle = app.staticTexts["About practice"]
      XCTAssertTrue(aboutTitle.exists)
      XCTAssertTrue(app.staticTexts["Private, temporary recordings"].exists)
      XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label == %@",
        "During ordinary practice, audio stays on this device. It is removed when you retry, move on, close practice, or leave the app. Practice does not upload audio."
      )).firstMatch.exists)
      let done = app.buttons["Done"]
      XCTAssertTrue(done.waitForExistence(timeout: 5))
      assertControl(done, id: "About Done", app)
      attachGeometry(prefix + "-about-done-geometry", [
        "done": rect(done.frame), "window": rect(app.windows.firstMatch.frame),
      ])
      let titleFrame = aboutTitle.frame
      let aboutWindow = app.windows.firstMatch.frame
      attachGeometry(prefix + "-about-title-geometry", [
        "title": rect(titleFrame), "done": rect(done.frame),
        "scrollViewport": rect(aboutScroll.frame), "window": rect(aboutWindow),
      ])
      let aboutTree = XCTAttachment(string: app.debugDescription)
      aboutTree.name = prefix + "-about-initial-accessibility"
      aboutTree.lifetime = .keepAlways
      add(aboutTree)
      // Preserve the unscrolled sheet before checking its initial title geometry.
      // Privacy-body existence does not claim that its full text is visible.
      keepScreenshot(prefix + "-about-initial", app)
      XCTAssertTrue(aboutTitle.isHittable)
      assertContained(titleFrame, in: aboutWindow, "Initial About title")
      XCTAssertGreaterThanOrEqual(titleFrame.minY, done.frame.maxY + 1,
                                 "About title must begin below Done and its dividing rule")
      done.tap()
      waitAbsent(aboutScroll, "About sheet should dismiss")
      XCTAssertTrue(about.waitForExistence(timeout: 5))
      assertHeader(app, largeText: largeText, weekdayBeforeLaunch: weekdayBeforeLaunch)

      activate("cadence.start", app)
      waitLabel(app.staticTexts["cadence.word"], "ball")
      XCTAssertTrue(app.buttons["cadence.record"].isEnabled)
      assertNoAutomaticMedia(app)
      keepScreenshot(prefix + "-ordinary-ready", app)
      activate("cadence.close", app)
      XCTAssertTrue(about.waitForExistence(timeout: 5))
      XCTAssertEqual(historyRows(app), history)
      activate("cadence.local-guided.open", app, allowOversized: true)
      XCTAssertTrue(app.buttons["cadence.guided.setup.0"].waitForExistence(timeout: 5))
      XCTAssertTrue(app.buttons["cadence.guided.setup.0"].label.contains("Change word 1, ball,"))
      let startReview = app.buttons["cadence.guided.start"]
      XCTAssertTrue(startReview.waitForExistence(timeout: 5))
      reveal(startReview, id: "cadence.guided.start", app)
      assertControl(startReview, id: "cadence.guided.start", app)
      XCTAssertFalse(app.buttons["cadence.record"].exists)
      assertNoAutomaticMedia(app)
      keepScreenshot(prefix + "-guided-setup-ready", app)
      activate("cadence.guided.close", app)
      XCTAssertTrue(about.waitForExistence(timeout: 5))
      XCTAssertEqual(historyRows(app), history)

      app.selectPracticeTab("Sounds")
      XCTAssertTrue(app.staticTexts["Choose a sound."].waitForExistence(timeout: 5))
      app.selectPracticeTab("Progress")
      XCTAssertTrue(app.staticTexts["cadence.progress.headline"].waitForExistence(timeout: 5))
      app.selectPracticeTab("Today")
      XCTAssertTrue(about.waitForExistence(timeout: 5))
      assertHeader(app, largeText: largeText, weekdayBeforeLaunch: weekdayBeforeLaunch)
      XCTAssertEqual(historyRows(app), history)
      captureHeader(prefix + "-returned-home", app)
    }

    private func assertHeader(
      _ app: XCUIApplication, largeText: Bool, weekdayBeforeLaunch: String
    ) {
      let weekdays = app.staticTexts.matching(identifier: "cadence.home.weekday")
      let abouts = app.buttons.matching(identifier: "cadence.home.about")
      XCTAssertEqual(weekdays.count, 1)
      XCTAssertEqual(abouts.count, 1)
      let weekday = weekdays.firstMatch, about = abouts.firstMatch
      let acceptedDates = [weekdayBeforeLaunch, Date.now.formatted(.dateTime.weekday(.wide))]
      XCTAssertTrue(acceptedDates.contains(weekday.label),
                    "Weekday must be the full real date label: \(weekday.label)")
      XCTAssertTrue(weekday.isHittable)
      assertContained(weekday.frame, in: app.windows.firstMatch.frame, "Weekday")
      XCTAssertEqual(about.label, "About practice and privacy")
      assertControl(about, id: "cadence.home.about", app)
      let dateFrame = weekday.frame, aboutFrame = about.frame
      if largeText {
        XCTAssertGreaterThanOrEqual(aboutFrame.minY - dateFrame.maxY, 3.5)
        XCTAssertLessThan(dateFrame.minX, aboutFrame.minX, "Date leads; About trails on its own row")
        XCTAssertGreaterThanOrEqual(aboutFrame.maxX, dateFrame.maxX - 0.5)
      } else {
        XCTAssertGreaterThanOrEqual(aboutFrame.minX - dateFrame.maxX, 15.5)
        XCTAssertGreaterThan(min(dateFrame.maxY, aboutFrame.maxY)
          - max(dateFrame.minY, aboutFrame.minY), 0, "Standard header stays on one row")
      }
      let viewport = app.scrollViews.firstMatch.frame
      XCTAssertLessThanOrEqual(max(dateFrame.maxY, aboutFrame.maxY), viewport.minY + 0.5,
                               "Header must stay above Home’s actual scroll viewport")
      XCTAssertFalse(dateFrame.intersects(viewport))
      XCTAssertFalse(aboutFrame.intersects(viewport))
    }

    private func captureHeader(_ name: String, _ app: XCUIApplication) {
      keepScreenshot(name, app)
      attachGeometry(name + "-geometry", [
        "weekday": rect(app.staticTexts["cadence.home.weekday"].frame),
        "weekdayLabel": app.staticTexts["cadence.home.weekday"].label,
        "about": rect(app.buttons["cadence.home.about"].frame),
        "scrollViewport": rect(app.scrollViews.firstMatch.frame),
        "window": rect(app.windows.firstMatch.frame),
      ])
      let tree = XCTAttachment(string: app.debugDescription)
      tree.name = name + "-accessibility"
      tree.lifetime = .keepAlways
      add(tree)
    }

    private func assertControl(_ target: XCUIElement, id: String, _ app: XCUIApplication) {
      XCTAssertTrue(target.exists, id)
      XCTAssertTrue(target.isEnabled, id)
      XCTAssertTrue(target.isHittable, id)
      XCTAssertGreaterThanOrEqual(target.frame.height, 44, id)
      XCTAssertGreaterThanOrEqual(target.frame.width, 44, id)
      assertContained(target.frame, in: app.windows.firstMatch.frame, id)
    }

    private func assertContained(_ frame: CGRect, in viewport: CGRect, _ message: String) {
      XCTAssertFalse(frame.isEmpty, message)
      XCTAssertTrue(frame.minX.isFinite && frame.maxX.isFinite
        && frame.minY.isFinite && frame.maxY.isFinite, message)
      XCTAssertGreaterThanOrEqual(frame.minX, viewport.minX - 0.5, message)
      XCTAssertLessThanOrEqual(frame.maxX, viewport.maxX + 0.5, message)
      XCTAssertGreaterThanOrEqual(frame.minY, viewport.minY - 0.5, message)
      XCTAssertLessThanOrEqual(frame.maxY, viewport.maxY + 0.5, message)
    }

    private func assertSameFrame(_ actual: CGRect, _ expected: CGRect, _ message: String) {
      XCTAssertEqual(actual.minX, expected.minX, accuracy: 0.5, message)
      XCTAssertEqual(actual.minY, expected.minY, accuracy: 0.5, message)
      XCTAssertEqual(actual.width, expected.width, accuracy: 0.5, message)
      XCTAssertEqual(actual.height, expected.height, accuracy: 0.5, message)
    }

    private func activate(_ id: String, _ app: XCUIApplication, allowOversized: Bool = false) {
      let target = app.buttons[id]
      XCTAssertTrue(target.waitForExistence(timeout: 5), id)
      if id != "cadence.guided.close" {
        reveal(target, id: id, app, allowOversized: allowOversized)
      }
      if allowOversized {
        // A tall entry may span screens. Require its beginning and an actual
        // hittable portion; only the fixed header controls require full containment.
        XCTAssertTrue(target.exists && target.isEnabled && target.isHittable, id)
        XCTAssertGreaterThanOrEqual(target.frame.height, 44, id)
        XCTAssertGreaterThanOrEqual(target.frame.width, 44, id)
      } else {
        assertControl(target, id: id, app)
      }
      target.tap()
    }

    private func usableViewport(_ scroll: XCUIElement, _ app: XCUIApplication) -> CGRect {
      var viewport = scroll.frame.intersection(app.windows.firstMatch.frame)
      let tabBar = app.tabBars.firstMatch
      if tabBar.exists, tabBar.isHittable, tabBar.frame.intersects(viewport) {
        viewport.size.height = max(0, min(viewport.maxY, tabBar.frame.minY) - viewport.minY)
      }
      return viewport.insetBy(dx: 0, dy: 8)
    }

    // Short measured drags use observed blank gutters, never entry-button centers.
    private func pan(
      _ scroll: XCUIElement, travel: CGFloat, down: Bool, targetFrame: CGRect,
      _ app: XCUIApplication
    ) {
      let viewport = usableViewport(scroll, app)
      XCTAssertGreaterThan(viewport.height, 0)
      let frames = (scroll.buttons.allElementsBoundByIndex.map(\.frame)
        + scroll.staticTexts.allElementsBoundByIndex.map(\.frame) + [targetFrame]).filter {
          !$0.isEmpty && $0.intersects(viewport)
        }
      XCTAssertFalse(frames.isEmpty)
      let leading = frames.map(\.minX).min() ?? viewport.minX
      let trailing = frames.map(\.maxX).max() ?? viewport.maxX
      let x: CGFloat
      if leading - viewport.minX >= 16 {
        x = (viewport.minX + leading) / 2
      } else if viewport.maxX - trailing >= 16 {
        x = (viewport.maxX + trailing) / 2
      } else {
        XCTFail("No observed blank scroll gutter")
        return
      }
      let distance = min(travel, viewport.height * 0.6)
      let origin = scroll.coordinate(withNormalizedOffset: .zero)
      let start = origin.withOffset(CGVector(dx: x - scroll.frame.minX,
        dy: viewport.midY + (down ? -distance / 2 : distance / 2) - scroll.frame.minY))
      let finish = origin.withOffset(CGVector(dx: x - scroll.frame.minX,
        dy: viewport.midY + (down ? distance / 2 : -distance / 2) - scroll.frame.minY))
      start.press(forDuration: 0.01, thenDragTo: finish,
                  withVelocity: .slow, thenHoldForDuration: 0.2)
    }

    private func reveal(
      _ target: XCUIElement, id: String, _ app: XCUIApplication, allowOversized: Bool = false
    ) {
      let scroll = app.scrollViews.firstMatch
      XCTAssertTrue(scroll.exists, id)
      for _ in 0..<24 {
        guard target.exists else { XCTFail("Missing target: \(id)"); return }
        let frame = target.frame, viewport = usableViewport(scroll, app)
        guard !frame.isEmpty, frame.minY.isFinite, frame.maxY.isFinite,
          viewport.height > 0 else { XCTFail("Invalid target geometry: \(id)"); return }
        let oversized = frame.height > viewport.height
        if frame.minY >= viewport.minY,
          oversized && allowOversized
            ? frame.minY <= viewport.minY + viewport.height * 0.2
            : frame.maxY <= viewport.maxY,
          target.isHittable { return }
        guard !oversized || allowOversized else {
          XCTFail("Target cannot fit the visible scroll viewport: \(id)")
          return
        }
        let desiredTop = oversized ? viewport.minY
          : viewport.minY + (viewport.height - frame.height) / 2
        let delta = frame.minY - desiredTop
        let travel = min(max(abs(delta), 12), viewport.height * 0.6)
        pan(scroll, travel: travel, down: delta < 0, targetFrame: frame, app)
      }
      capturePracticeFailure(app)
      XCTFail("Target did not enter the measured viewport: \(id)")
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

    private func historyRows(_ app: XCUIApplication) -> [String] {
      app.descendants(matching: .any).matching(
        NSPredicate(format: "identifier BEGINSWITH %@", "cadence.history.entry-")
      ).allElementsBoundByIndex.map(\.identifier).sorted()
    }

    private func waitLabel(_ target: XCUIElement, _ label: String) {
      let expected = XCTNSPredicateExpectation(
        predicate: NSPredicate(format: "label == %@", label), object: target)
      XCTAssertEqual(XCTWaiter.wait(for: [expected], timeout: 5), .completed, label)
    }

    private func waitAbsent(_ target: XCUIElement, _ message: String) {
      let absent = XCTNSPredicateExpectation(
        predicate: NSPredicate(format: "exists == false"), object: target)
      XCTAssertEqual(XCTWaiter.wait(for: [absent], timeout: 5), .completed, message)
    }

    private func rect(_ frame: CGRect) -> [CGFloat] {
      [frame.minX, frame.minY, frame.width, frame.height]
    }

    private func attachGeometry(_ name: String, _ geometry: [String: Any]) {
      guard let data = try? JSONSerialization.data(withJSONObject: geometry, options: [.sortedKeys])
      else { XCTFail("Could not encode measured geometry: \(name)"); return }
      let attachment = XCTAttachment(data: data, uniformTypeIdentifier: "public.json")
      attachment.name = name
      attachment.lifetime = .keepAlways
      add(attachment)
    }

    private func keepScreenshot(_ name: String, _ app: XCUIApplication) {
      let attachment = XCTAttachment(screenshot: app.screenshot())
      attachment.name = name
      attachment.lifetime = .keepAlways
      add(attachment)
    }
  }
#endif
