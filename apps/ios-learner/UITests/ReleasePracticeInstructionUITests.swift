import XCTest

#if !DEBUG
  @MainActor
  final class ReleasePracticeInstructionUITests: XCTestCase {
    func testReleaseSelectedPracticeShowsCurrentInstructionWithoutMedia() {
      journey(largeText: false)
    }

    func testReleaseLargestTextSelectedPracticeShowsCurrentInstructionWithoutMedia() {
      journey(largeText: true)
    }

    private let pigDetail =
      "Bring your lips together, then let out a small puff of air as you start “pig”. Say the whole word comfortably."
    private let breadDetail =
      "Start with your lips together for B, then move straight into R as you say “bread”. Keep the sounds together in one whole word."

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
      let prefix = "practice-instruction-" + (largeText ? "largest" : "normal")
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
      app.launch()
      waitForPracticeSystemBannerToClear()
      XCTAssertTrue(app.buttons["cadence.local-guided.open"].waitForExistence(timeout: 5))
      XCTAssertFalse(app.staticTexts["cadence.home.ui-test-banner"].exists)
      XCTAssertFalse(app.staticTexts["cadence.generated-guided.banner"].exists)
      XCTAssertFalse(app.buttons["cadence.guided-word.start"].exists)
      let history = historyRows(app)
      activate("cadence.start", app)
      waitLabel(app.staticTexts["cadence.word"], "ball")
      assertNoInstruction(app)
      assertNoAutomaticMedia(app)
      activate("cadence.close", app)

      activate("cadence.local-guided.open", app)
      XCTAssertTrue(app.buttons["cadence.guided.setup.2"].label.contains("moon"))
      activate("cadence.guided.setup.2", app)
      let search = app.descendants(matching: .any)
        .matching(identifier: "cadence.guided.search").firstMatch
      XCTAssertTrue(search.waitForExistence(timeout: 5))
      search.tap()
      search.typeText("bread\n")
      activate("cadence.guided.pick.r-middle-bread", app)
      XCTAssertTrue(app.buttons["cadence.guided.setup.2"].label.contains("bread"))
      activate("cadence.guided.start", app)
      waitLabel(app.staticTexts["cadence.word"], "ball")
      assertNoInstruction(app)
      assertNoAutomaticMedia(app)
      activate("cadence.guided.finish-stage", app)
      activate("cadence.guided.select.p-beginning-pig", app)
      activate("cadence.guided.select.r-middle-bread", app)
      waitLabel(app.buttons["cadence.guided.practice.start"], "Practice selected words (2)")
      activate("cadence.guided.practice.start", app)
      assertInstruction(word: "pig", detail: pigDetail, ordinal: 1, prefix: prefix, app)

      expandWithoutReset("cadence.sound-guide.toggle", name: prefix + "-pig-guide-expansion", app)
      waitLabel(app.staticTexts["cadence.sound-guide.title"], "P at the start of “pig”")
      XCTAssertFalse(app.staticTexts["cadence.sound-guide.detail"].exists)
      XCTAssertTrue(app.staticTexts["cadence.practice-instruction.detail"].exists)
      XCTAssertEqual(exactTextCount(pigDetail, app), 1)
      let sources = app.buttons["cadence.sound-guide.sources"]
      XCTAssertEqual(sources.value as? String, "Collapsed")
      expandWithoutReset("cadence.sound-guide.sources", name: prefix + "-sources-expansion", app)
      XCTAssertEqual(sources.value as? String, "Expanded")
      for (id, label) in [
        ("source-attribution", "Guide text adapted from Essentials of Linguistics, §2.6 Classifying Consonants, © 2018 Catherine Anderson. Shortened and reworded for this guide."),
        ("source-license", "Guide text is licensed under CC BY-SA 4.0. This license applies to the guide text, not the app."),
      ] {
        let text = app.staticTexts["cadence.sound-guide." + id]
        waitLabel(text, label)
        captureText(text, id: "cadence.sound-guide." + id,
                    name: prefix + "-pig-" + id, app)
      }
      for (id, label) in [
        ("source-chapter", "Read the source chapter"),
        ("source-license-link", "CC BY-SA 4.0 license"),
      ] {
        let fullID = "cadence.sound-guide." + id
        let link = app.descendants(matching: .any).matching(identifier: fullID).firstMatch
        waitLabel(link, label)
        reveal(link, id: fullID, app)
        assertControl(link, id: fullID, app)
        keepScreenshot(prefix + "-pig-" + id, app)
      }
      assertNoAutomaticMedia(app)
      activate("cadence.guided.skip", app)
      assertInstruction(word: "bread", detail: breadDetail, ordinal: 2, prefix: prefix, app)
      XCTAssertEqual(exactTextCount(pigDetail, app), 0)
      XCTAssertFalse(app.staticTexts["cadence.sound-guide.source-attribution"].exists)
      XCTAssertFalse(app.staticTexts["cadence.sound-guide.source-license"].exists)
      XCTAssertFalse(app.buttons["cadence.sound-guide.sources"].exists)
      expandWithoutReset("cadence.sound-guide.toggle", name: prefix + "-bread-guide-expansion", app)
      waitLabel(app.staticTexts["cadence.sound-guide.title"], "R in the BR of “bread”")
      XCTAssertEqual(app.buttons["cadence.sound-guide.sources"].value as? String, "Collapsed")
      XCTAssertFalse(app.staticTexts["cadence.sound-guide.detail"].exists)
      XCTAssertEqual(exactTextCount(breadDetail, app), 1)
      keepScreenshot(prefix + "-bread-guide-reset", app)
      activate("cadence.guided.skip", app)
      activate("cadence.guided.recheck.start", app)
      waitLabel(app.staticTexts["cadence.word"], "ball")
      waitLabel(app.staticTexts["cadence.guided.visit-heading"], "Recheck · 1 of 5")
      assertNoInstruction(app)
      assertNoAutomaticMedia(app)
      activate("cadence.guided.skip", app)
      waitLabel(app.staticTexts["cadence.word"], "pig")
      waitLabel(app.staticTexts["cadence.guided.visit-heading"], "Recheck · 2 of 5")
      assertNoInstruction(app)
      XCTAssertEqual(app.buttons["cadence.sound-guide.toggle"].value as? String, "Collapsed")
      expandWithoutReset("cadence.sound-guide.toggle", name: prefix + "-recheck-pig-guide-expansion", app)
      let restored = app.staticTexts["cadence.sound-guide.detail"]
      waitLabel(restored, pigDetail)
      XCTAssertEqual(exactTextCount(pigDetail, app), 1)
      captureText(restored, id: "cadence.sound-guide.detail",
                  name: prefix + "-recheck-pig-restored-detail", app)
      assertNoAutomaticMedia(app)
      activate("cadence.guided.finish-stage", app)
      XCTAssertTrue(app.buttons["cadence.guided.done"].waitForExistence(timeout: 5))
      keepScreenshot(prefix + "-summary", app)
      activate("cadence.guided.close", app)
      XCTAssertTrue(app.buttons["cadence.local-guided.open"].waitForExistence(timeout: 5))
      XCTAssertEqual(historyRows(app), history)
    }

    private func assertInstruction(
      word: String, detail: String, ordinal: Int, prefix: String, _ app: XCUIApplication
    ) {
      waitLabel(app.staticTexts["cadence.word"], word)
      waitLabel(app.staticTexts["cadence.guided.visit-heading"], "Practice · \(ordinal) of 2")
      let currentWord = app.staticTexts["cadence.word"]
      let scroll = app.scrollViews.firstMatch
      let initialViewport = viewport(scroll, app)
      let exposed = NSPredicate { _, _ in
        guard currentWord.exists else { return false }
        let frame = currentWord.frame
        return !frame.isEmpty && frame.minX.isFinite && frame.maxX.isFinite
          && frame.minY.isFinite && frame.maxY.isFinite && currentWord.isHittable
          && frame.minX >= initialViewport.minX && frame.maxX <= initialViewport.maxX
          && frame.minY >= initialViewport.minY && frame.maxY <= initialViewport.maxY
      }
      let settled = XCTWaiter.wait(for: [
        XCTNSPredicateExpectation(predicate: exposed, object: currentWord),
      ], timeout: 5)
      let wordFrame = currentWord.exists ? currentWord.frame : .zero
      let entryViewport = viewport(scroll, app)
      let title = app.staticTexts["cadence.practice-instruction.title"]
      let instruction = app.staticTexts["cadence.practice-instruction.detail"]
      let record = app.buttons["cadence.record"]
      keepScreenshot(prefix + "-" + word + "-initial-entry", app)
      let entryTree = XCTAttachment(string: app.debugDescription)
      entryTree.name = prefix + "-" + word + "-initial-entry-accessibility"
      entryTree.lifetime = .keepAlways
      add(entryTree)
      attachGeometry(prefix + "-" + word + "-initial-entry-geometry", [
        "word": rect(wordFrame), "wordExists": currentWord.exists,
        "viewport": rect(entryViewport),
        "visitHeading": rect(app.staticTexts["cadence.guided.visit-heading"].frame),
        "title": title.exists ? rect(title.frame) : [],
        "instruction": instruction.exists ? rect(instruction.frame) : [],
        "record": record.exists ? rect(record.frame) : [],
        "window": rect(app.windows.firstMatch.frame),
      ])
      XCTAssertEqual(settled, .completed, "New practice word must appear without test scrolling")
      XCTAssertTrue(currentWord.exists)
      XCTAssertFalse(wordFrame.isEmpty)
      XCTAssertTrue(wordFrame.minX.isFinite && wordFrame.maxX.isFinite
        && wordFrame.minY.isFinite && wordFrame.maxY.isFinite)
      XCTAssertTrue(currentWord.isHittable)
      XCTAssertGreaterThanOrEqual(wordFrame.minX, entryViewport.minX)
      XCTAssertLessThanOrEqual(wordFrame.maxX, entryViewport.maxX)
      XCTAssertGreaterThanOrEqual(wordFrame.minY, entryViewport.minY)
      XCTAssertLessThanOrEqual(wordFrame.maxY, entryViewport.maxY)
      waitLabel(title, "Try this")
      waitLabel(instruction, detail)
      XCTAssertEqual(app.buttons["cadence.sound-guide.toggle"].value as? String, "Collapsed")
      XCTAssertFalse(app.staticTexts["cadence.sound-guide.detail"].exists)
      XCTAssertEqual(exactTextCount(detail, app), 1)
      XCTAssertTrue(record.exists)
      XCTAssertLessThanOrEqual(title.frame.maxY, instruction.frame.minY)
      XCTAssertLessThanOrEqual(instruction.frame.maxY, record.frame.minY,
                               "Current instruction must precede Record")
      attachGeometry(prefix + "-" + word + "-instruction-order", [
        "title": rect(title.frame), "instruction": rect(instruction.frame),
        "record": rect(record.frame),
      ])
      keepScreenshot(prefix + "-" + word + "-ready", app)
      captureText(title, id: "cadence.practice-instruction.title",
                  name: prefix + "-" + word + "-try-this", app)
      captureText(instruction, id: "cadence.practice-instruction.detail",
                  name: prefix + "-" + word + "-instruction", app)
      reveal(record, id: "cadence.record", app)
      assertControl(record, id: "cadence.record", app)
      keepScreenshot(prefix + "-" + word + "-record-reachable", app)
      assertNoAutomaticMedia(app)
    }

    private func expandWithoutReset(_ id: String, name: String, _ app: XCUIApplication) {
      let toggle = app.buttons[id]
      XCTAssertTrue(toggle.waitForExistence(timeout: 5), id)
      reveal(toggle, id: id, app)
      assertControl(toggle, id: id, app)
      let currentWord = app.staticTexts["cadence.word"]
      XCTAssertTrue(currentWord.exists)
      let before = toggle.frame, beforeWord = currentWord.frame
      let beforeViewport = viewport(app.scrollViews.firstMatch, app)
      attachGeometry(name + "-before-position", [
        "control": rect(before), "word": rect(beforeWord), "viewport": rect(beforeViewport),
      ])
      keepScreenshot(name + "-before-tap", app)
      XCTAssertLessThanOrEqual(beforeWord.maxY, beforeViewport.minY,
                               "Disclosure check must start after scrolling past the word")
      toggle.tap()
      let after = toggle.frame, afterWord = currentWord.frame
      let afterViewport = viewport(app.scrollViews.firstMatch, app)
      attachGeometry(name + "-position", [
        "before": rect(before), "after": rect(after),
        "wordBefore": rect(beforeWord), "wordAfter": rect(afterWord),
        "viewportBefore": rect(beforeViewport), "viewportAfter": rect(afterViewport),
      ])
      keepScreenshot(name + "-after-tap", app)
      assertControl(toggle, id: id, app)
      XCTAssertLessThanOrEqual(afterWord.maxY, afterViewport.minY,
                               "Opening a disclosure must not return to the current word")
      XCTAssertGreaterThanOrEqual(after.minX, afterViewport.minX, id)
      XCTAssertLessThanOrEqual(after.maxX, afterViewport.maxX, id)
      XCTAssertGreaterThanOrEqual(after.minY, afterViewport.minY, id)
      XCTAssertLessThanOrEqual(after.maxY, afterViewport.maxY, id)
    }

    private func assertNoInstruction(_ app: XCUIApplication) {
      XCTAssertFalse(app.staticTexts["cadence.practice-instruction.title"].exists)
      XCTAssertFalse(app.staticTexts["cadence.practice-instruction.detail"].exists)
    }

    private func exactTextCount(_ text: String, _ app: XCUIApplication) -> Int {
      app.staticTexts.matching(NSPredicate(format: "label == %@", text)).count
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

    private func activate(_ id: String, _ app: XCUIApplication) {
      let target = app.buttons[id]
      if !id.hasPrefix("cadence.guided.pick.") {
        XCTAssertTrue(target.waitForExistence(timeout: 5), id)
      }
      if id == "cadence.guided.close" {
        assertControl(target, id: id, app)
      } else {
        reveal(target, id: id, app)
        assertControl(target, id: id, app)
      }
      target.tap()
    }

    private func assertControl(_ target: XCUIElement, id: String, _ app: XCUIApplication) {
      XCTAssertTrue(target.exists, id)
      XCTAssertTrue(target.isEnabled, id)
      XCTAssertTrue(target.isHittable, id)
      XCTAssertGreaterThanOrEqual(target.frame.height, 44, id)
      XCTAssertGreaterThanOrEqual(target.frame.width, 44, id)
      let window = app.windows.firstMatch.frame, frame = target.frame
      XCTAssertGreaterThanOrEqual(frame.minX, window.minX, id)
      XCTAssertLessThanOrEqual(frame.maxX, window.maxX, id)
      XCTAssertGreaterThanOrEqual(frame.minY, window.minY, id)
      XCTAssertLessThanOrEqual(frame.maxY, window.maxY, id)
      if id == "cadence.record" || id == "cadence.sound-guide.source-chapter"
        || id == "cadence.sound-guide.source-license-link" {
        let visible = viewport(app.scrollViews.firstMatch, app)
        XCTAssertGreaterThanOrEqual(frame.minY, visible.minY, id)
        XCTAssertLessThanOrEqual(frame.maxY, visible.maxY, id)
      }
    }

    private func viewport(_ scroll: XCUIElement, _ app: XCUIApplication) -> CGRect {
      var visible = scroll.frame.intersection(app.windows.firstMatch.frame)
      let close = app.buttons["cadence.guided.close"]
      if close.exists { visible.origin.y = max(visible.minY, close.frame.maxY) }
      visible.size.height = max(0, min(scroll.frame.maxY, app.windows.firstMatch.frame.maxY)
        - visible.minY)
      let tabs = app.tabBars.firstMatch
      if tabs.exists, tabs.isHittable, tabs.frame.intersects(visible) {
        visible.size.height = max(0, tabs.frame.minY - visible.minY)
      }
      return visible.insetBy(dx: 0, dy: 8)
    }

    private func pan(
      _ scroll: XCUIElement, viewport: CGRect, travel: CGFloat, down: Bool,
      target: CGRect, _ app: XCUIApplication
    ) {
      let frames = (scroll.buttons.allElementsBoundByIndex.map(\.frame) + [target]).filter {
        !$0.isEmpty && $0.maxX > viewport.minX && $0.minX < viewport.maxX
      }
      guard frames.allSatisfy({ $0.minX.isFinite && $0.maxX.isFinite }),
        let leading = frames.map(\.minX).min(), let trailing = frames.map(\.maxX).max()
      else { XCTFail("Invalid scroll geometry"); return }
      let x: CGFloat
      if leading - viewport.minX >= 16 {
        x = (viewport.minX + leading) / 2
      } else if viewport.maxX - trailing >= 16 {
        x = (viewport.maxX + trailing) / 2
      } else { XCTFail("No observed blank scroll gutter"); return }
      drag(scroll, x: x, viewport: viewport, travel: travel, down: down)
    }

    private func drag(
      _ scroll: XCUIElement, x: CGFloat, viewport: CGRect, travel: CGFloat, down: Bool
    ) {
      let origin = scroll.coordinate(withNormalizedOffset: .zero)
      let start = origin.withOffset(CGVector(dx: x - scroll.frame.minX,
        dy: viewport.midY + (down ? -travel / 2 : travel / 2) - scroll.frame.minY))
      let finish = origin.withOffset(CGVector(dx: x - scroll.frame.minX,
        dy: viewport.midY + (down ? travel / 2 : -travel / 2) - scroll.frame.minY))
      start.press(forDuration: 0.01, thenDragTo: finish,
                  withVelocity: .slow, thenHoldForDuration: 0.2)
    }

    private func reveal(_ target: XCUIElement, id: String, _ app: XCUIApplication) {
      let picker = app.collectionViews["cadence.guided.picker.scroll"]
      if picker.exists {
        // Native List choices occupy full-width cells, with no blank gutter.
        for _ in 0..<12 {
          let visible = picker.frame.intersection(app.windows.firstMatch.frame).insetBy(dx: 0, dy: 8)
          guard target.exists else { picker.swipeUp(velocity: .slow); continue }
          let frame = target.frame
          guard !frame.isEmpty, frame.minY.isFinite, frame.maxY.isFinite,
            frame.minX.isFinite, frame.maxX.isFinite, visible.minY.isFinite,
            visible.maxY.isFinite, visible.height > 0, frame.height <= visible.height
          else { XCTFail("Invalid picker choice geometry: \(id)"); return }
          if frame.minY >= visible.minY, frame.maxY <= visible.maxY, target.isHittable { return }
          let delta = frame.midY - visible.midY
          let travel = min(max(abs(delta), 12), visible.height * 0.35)
          drag(picker, x: visible.minX + 12, viewport: visible, travel: travel, down: delta < 0)
        }
        XCTFail("Picker choice did not enter viewport: \(id)")
        return
      }
      let scroll = app.scrollViews.firstMatch
      XCTAssertTrue(scroll.exists, id)
      var previousFrame: CGRect?, previousTravel: CGFloat = 0, previousAbove: Bool?
      for _ in 0..<24 {
        guard target.exists else { XCTFail("Missing target: \(id)"); return }
        let frame = target.frame, visible = viewport(scroll, app)
        guard !frame.isEmpty, frame.minY.isFinite, frame.maxY.isFinite, visible.height > 0
        else { XCTFail("Invalid target geometry: \(id)"); return }
        let oversized = frame.height > visible.height
        if frame.minY >= visible.minY,
          oversized ? frame.minY <= visible.minY + visible.height * 0.2 : frame.maxY <= visible.maxY,
          target.isHittable { return }
        let desiredTop = oversized ? visible.minY
          : visible.minY + (visible.height - frame.height) / 2
        let above = frame.minY < desiredTop, distance = abs(frame.minY - desiredTop)
        var travel = oversized ? min(max(distance, visible.height * 0.2), visible.height * 0.6)
          : min(distance, visible.height * 0.6)
        if !oversized, distance > 0, distance <= 24,
          let previousFrame, previousTravel > 0, previousAbove == above,
          previousFrame.minX == frame.minX, previousFrame.size == frame.size {
          let movement = (frame.minY - previousFrame.minY) * (above ? 1 : -1)
          if movement >= 0, movement <= previousTravel {
            travel = min(distance + min(previousTravel - movement, 24), visible.height * 0.6)
          }
        }
        guard travel > 0 else { continue }
        previousFrame = frame
        previousTravel = travel
        previousAbove = above
        pan(scroll, viewport: visible, travel: travel, down: above, target: frame, app)
      }
      XCTFail("Target did not enter viewport: \(id)")
    }

    private func captureText(_ text: XCUIElement, id: String, name: String, _ app: XCUIApplication) {
      reveal(text, id: id, app)
      keepScreenshot(name, app)
      let scroll = app.scrollViews.firstMatch
      for segment in 0..<8 {
        guard text.exists else { XCTFail("Missing paragraph: \(id)"); return }
        let frame = text.frame, visible = viewport(scroll, app)
        guard !frame.isEmpty, frame.minY.isFinite, frame.maxY.isFinite, visible.height > 0
        else { XCTFail("Invalid paragraph geometry: \(id)"); return }
        attachGeometry(name + "-segment-\(segment)-geometry", [
          "text": rect(frame), "viewport": rect(visible),
        ])
        if frame.maxY <= visible.maxY { return }
        let travel = min(max(frame.maxY - visible.maxY + 4, 24), visible.height * 0.55)
        pan(scroll, viewport: visible, travel: travel, down: false, target: frame, app)
        let after = text.frame
        let movement = frame.minY - after.minY
        keepScreenshot(name + "-segment-\(segment + 1)", app)
        attachGeometry(name + "-segment-\(segment + 1)-movement", [
          "before": rect(frame), "after": rect(after), "viewport": rect(visible),
          "travel": travel, "movement": movement,
        ])
        XCTAssertGreaterThan(movement, 1, "Paragraph must scroll toward its end: \(id)")
        XCTAssertLessThanOrEqual(movement, visible.height - 8,
                                "Paragraph captures must overlap: \(id)")
        if after.maxY <= visible.maxY { return }
      }
      XCTFail("Paragraph end not captured within eight measured moves: \(id)")
    }

    private func historyRows(_ app: XCUIApplication) -> [String] {
      app.descendants(matching: .any).matching(
        NSPredicate(format: "identifier BEGINSWITH %@", "cadence.history.entry-")
      ).allElementsBoundByIndex.map(\.identifier).sorted()
    }

    private func waitLabel(_ target: XCUIElement, _ label: String) {
      let match = XCTNSPredicateExpectation(
        predicate: NSPredicate(format: "label == %@", label), object: target)
      XCTAssertEqual(XCTWaiter.wait(for: [match], timeout: 5), .completed, label)
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
