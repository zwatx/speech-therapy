import XCTest

// The ordinary Debug root exposes development routes; this suite verifies Release only.
#if !DEBUG
  /// Ordinary Release-root navigation only. No capture, playback, checks or camera actions.
  @MainActor
  final class ReleaseGuidedNavigationUITests: XCTestCase {
    func testReleaseSelectedSoundGuidesKeepPracticeMediaFree() {
      soundGuideJourney(largeText: false)
    }

    func testReleaseLargestTextSelectedSoundGuideRemainsReadableAndOptional() {
      soundGuideJourney(largeText: true)
    }

    func testReleaseRAndBRGuidesStayOptionalAndMediaFree() {
      rAndBRGuideJourney(largeText: false)
    }

    func testReleaseLargestTextRAndBRGuidesStayReadableAndResetPerVisit() {
      rAndBRGuideJourney(largeText: true)
    }

    func testReleaseDefaultSoundGuidesStayOptionalAndResetAcrossGuidedVisits() {
      defaultSoundGuidesJourney(largeText: false)
    }

    func testReleaseLargestTextDefaultSoundGuidesStayReadableAndResetAcrossGuidedVisits() {
      defaultSoundGuidesJourney(largeText: true)
    }

    private func defaultSoundGuidesJourney(largeText: Bool) {
      let app = launch(largeText: largeText)
      executionTimeAllowance = 600
      defer { app.terminate() }
      waitForPracticeSystemBannerToClear()
      let history = historyRows(app)
      activate("cadence.local-guided.open", app)
      assertSetup(app)
      activate("cadence.guided.start", app)
      for (index, word) in words.enumerated() {
        assertReady(word, stage: "First review", index: index, count: 5, app)
        assertCollapsedDefaultGuide(app)
        activate("cadence.sound-guide.toggle", app)
        assertExpandedDefaultGuide(index: index, largeText: largeText, app)
        activate("cadence.guided.skip", app)
      }
      activate("cadence.guided.select.p-beginning-pig", app)
      waitLabel(app.buttons["cadence.guided.practice.start"], "Practice selected words (1)")
      activate("cadence.guided.practice.start", app)
      assertReady("pig", stage: "Practice", index: 0, count: 1, app)
      assertCollapsedDefaultGuide(app)
      activate("cadence.sound-guide.toggle", app)
      waitLabel(app.staticTexts["cadence.sound-guide.title"], "P at the start of “pig”")
      waitLabel(app.staticTexts["cadence.sound-guide.detail"], defaultGuideDetails[1])
      captureGuideText(app.staticTexts["cadence.sound-guide.detail"],
        name: "default-guides-\(largeText ? "largest" : "normal")-practice-pig", app)
      activate("cadence.guided.skip", app)
      activate("cadence.guided.recheck.start", app)
      assertReady("ball", stage: "Recheck", index: 0, count: 5, app)
      assertCollapsedDefaultGuide(app)
      activate("cadence.sound-guide.toggle", app)
      waitLabel(app.staticTexts["cadence.sound-guide.title"], "B at the start of “ball”")
      activate("cadence.guided.skip", app)
      assertReady("pig", stage: "Recheck", index: 1, count: 5, app)
      assertCollapsedDefaultGuide(app)
      keepScreenshot("default-guides-\(largeText ? "largest" : "normal")-recheck-pig-collapsed", app)
      activate("cadence.sound-guide.toggle", app)
      waitLabel(app.staticTexts["cadence.sound-guide.title"], "P at the start of “pig”")
      waitLabel(app.staticTexts["cadence.sound-guide.detail"], defaultGuideDetails[1])
      captureGuideText(app.staticTexts["cadence.sound-guide.detail"],
        name: "default-guides-\(largeText ? "largest" : "normal")-recheck-pig", app)
      activate("cadence.guided.close", app)
      assertHome(app)
      XCTAssertEqual(historyRows(app), history)
    }

    private let defaultGuideDetails = [
      "Bring your lips together, then open them as you say “ball”. Use your usual voice.",
      "Bring your lips together, then let out a small puff of air as you start “pig”. Say the whole word comfortably.",
      "Start “moon” with your lips together for a gentle “mmm”, letting air flow through your nose. Continue with the rest of the word comfortably.",
      "Try touching the small ridge just behind your top front teeth with your tongue tip. Release a little air into “tiger”. Say the whole word comfortably.",
      "Try touching the small ridge just behind your top front teeth with your tongue tip. Release your tongue and use your voice as you say “dog”. Keep it comfortable.",
    ]

    private func assertCollapsedDefaultGuide(_ app: XCUIApplication) {
      assertCollapsedRGuide(app)
      XCTAssertEqual(app.buttons["cadence.sound-guide.toggle"].value as? String, "Collapsed")
      XCTAssertGreaterThanOrEqual(app.buttons["cadence.sound-guide.toggle"].frame.height, 48)
      XCTAssertGreaterThanOrEqual(app.buttons["cadence.sound-guide.toggle"].frame.width, 44)
      XCTAssertFalse(app.staticTexts["cadence.sound-guide.closed-caption"].exists)
      XCTAssertFalse(app.staticTexts["cadence.sound-guide.open-caption"].exists)
      XCTAssertFalse(app.staticTexts["cadence.sound-guide.source-attribution"].exists)
    }

    private func assertExpandedDefaultGuide(
      index: Int, largeText: Bool, _ app: XCUIApplication
    ) {
      let word = words[index]
      let sound = ["B", "P", "M", "T", "D"][index]
      let prefix = "default-guides-\(largeText ? "largest" : "normal")-\(word)"
      XCTAssertEqual(app.buttons["cadence.sound-guide.toggle"].value as? String, "Expanded")
      for (id, text) in [
        ("title", "\(sound) at the start of “\(word)”"), ("detail", defaultGuideDetails[index]),
      ] {
        let section = app.staticTexts["cadence.sound-guide." + id]
        waitLabel(section, text)
        captureGuideText(section, name: prefix + "-" + id, app)
      }
      for id in ["r-option-title", "r-option-detail", "r-variation-title", "r-variation-detail", "r-accent"] {
        XCTAssertFalse(app.staticTexts["cadence.sound-guide." + id].exists)
      }
      for (id, text) in [("closed-caption", "1. Lips together"), ("open-caption", "2. Lips open")] {
        let caption = app.staticTexts["cadence.sound-guide." + id]
        if index == 0 {
          waitLabel(caption, text)
          reveal(caption, app)
          keepScreenshot(prefix + "-" + id, app)
        } else {
          XCTAssertFalse(caption.exists, "New guides are text only.")
        }
      }
      XCTAssertTrue(app.staticTexts["A general guide to this sound."].exists)
      let sources = app.buttons["cadence.sound-guide.sources"]
      XCTAssertEqual(sources.value as? String, "Collapsed")
      activate("cadence.sound-guide.sources", app)
      XCTAssertEqual(sources.value as? String, "Expanded")
      let sourceTree = XCTAttachment(string: app.debugDescription)
      sourceTree.name = prefix + "-sources-expanded-accessibility"
      sourceTree.lifetime = .keepAlways
      add(sourceTree)
      if index == 1 {
        activateSourcesLabel(app)
        XCTAssertEqual(sources.value as? String, "Collapsed")
        XCTAssertFalse(app.staticTexts["cadence.sound-guide.source-attribution"].exists)
        keepScreenshot(prefix + "-sources-collapsed", app)
        activateSourcesLabel(app)
        XCTAssertEqual(sources.value as? String, "Expanded")
        XCTAssertTrue(app.staticTexts["cadence.sound-guide.source-attribution"].exists)
        activate("cadence.sound-guide.toggle", app)
        assertCollapsedDefaultGuide(app)
        XCTAssertFalse(sources.exists)
        activate("cadence.sound-guide.toggle", app)
        XCTAssertEqual(sources.value as? String, "Collapsed")
        XCTAssertFalse(app.staticTexts["cadence.sound-guide.source-attribution"].exists)
        activateSourcesLabel(app)
        XCTAssertEqual(sources.value as? String, "Expanded")
      }
      for (id, text) in [
        ("source-attribution", "Guide text adapted from Essentials of Linguistics, §2.6 Classifying Consonants, © 2018 Catherine Anderson. Shortened and reworded for this guide."),
        ("source-license", "Guide text is licensed under CC BY-SA 4.0. This license applies to the guide text, not the app."
          + (index == 0 ? " Original diagram created for this guide." : "")),
      ] {
        let section = app.staticTexts["cadence.sound-guide." + id]
        waitLabel(section, text)
        captureGuideText(section, name: prefix + "-" + id, app)
      }
      for (id, label) in [("source-chapter", "Read the source chapter"),
                          ("source-license-link", "CC BY-SA 4.0 license")] {
        let link = app.descendants(matching: .any)
          .matching(identifier: "cadence.sound-guide." + id).firstMatch
        waitLabel(link, label)
        reveal(link, app)
        XCTAssertTrue(link.isHittable)
        XCTAssertGreaterThanOrEqual(link.frame.height, 44)
        XCTAssertGreaterThanOrEqual(link.frame.width, 44)
        keepScreenshot(prefix + "-" + id, app)
      }
      XCTAssertTrue(app.buttons["cadence.record"].isEnabled)
      XCTAssertFalse(app.buttons["cadence.stop"].exists)
      XCTAssertFalse(app.buttons["cadence.replay"].exists)
      XCTAssertFalse(app.staticTexts["cadence.word-check-result"].exists)
    }

    private func activateSourcesLabel(_ app: XCUIApplication) {
      let sources = app.buttons["cadence.sound-guide.sources"]
      reveal(sources, app)
      XCTAssertTrue(sources.isHittable)
      XCTAssertGreaterThanOrEqual(sources.frame.height, 44)
      XCTAssertGreaterThanOrEqual(sources.frame.width, 44)
      let label = sources.staticTexts["Sources"]
      XCTAssertTrue(label.exists)
      XCTAssertTrue(label.isHittable)
      label.tap()
    }

    private func captureGuideText(_ section: XCUIElement, name: String, _ app: XCUIApplication) {
      reveal(section, app)
      let scroll = app.scrollViews.firstMatch
      var measurements: [[String: Any]] = []
      var complete = false
      defer {
        if !measurements.isEmpty,
          let data = try? JSONSerialization.data(withJSONObject: measurements, options: [.sortedKeys])
        {
          let attachment = XCTAttachment(data: data, uniformTypeIdentifier: "public.json")
          attachment.name = name + "-text-scroll-geometry"
          attachment.lifetime = .keepAlways
          add(attachment)
        }
        if complete { print("CADENCE_GUIDE_PARAGRAPH_COMPLETE=\(name)") }
      }
      typealias ReadFrame = (frame: CGRect, viewport: CGRect, start: CGFloat, end: CGFloat)
      func snapshot(segment: Int, travel: CGFloat, previous: ReadFrame?) -> ReadFrame? {
        guard section.exists else { XCTFail("Missing guide paragraph: \(name)"); return nil }
        let visible = scroll.frame.intersection(app.windows.firstMatch.frame)
        guard !visible.isNull, !visible.isEmpty,
          [visible.minX, visible.minY, visible.width, visible.height].allSatisfy({ $0.isFinite })
        else { XCTFail("Invalid guide viewport: \(name)"); return nil }
        var top = visible.minY + 8
        // Ordinary Close scrolls with the content; an offscreen frame is not an occlusion.
        for id in ["cadence.guided.close", "cadence.close"] {
          let close = app.buttons[id]
          if close.exists {
            let header = close.frame
            guard [header.minX, header.minY, header.width, header.height].allSatisfy({ $0.isFinite })
            else { XCTFail("Invalid guide header: \(name)"); return nil }
            let intersection = header.intersection(visible)
            if !intersection.isNull, !intersection.isEmpty {
              top = max(top, intersection.maxY + 8)
            }
          }
        }
        let viewport = CGRect(x: visible.minX, y: top, width: visible.width,
                              height: visible.maxY - 8 - top)
        let frame = section.frame
        guard viewport.height > 0, !frame.isEmpty,
          [frame.minX, frame.minY, frame.width, frame.height].allSatisfy({ $0.isFinite }),
          frame.minX >= viewport.minX, frame.maxX <= viewport.maxX
        else { XCTFail("Invalid or horizontally clipped guide paragraph: \(name)"); return nil }
        let start = max(0, viewport.minY - frame.minY)
        let end = min(frame.height, viewport.maxY - frame.minY)
        guard end > start else { XCTFail("Guide paragraph is outside viewport: \(name)"); return nil }
        let movement = previous.map { $0.frame.minY - frame.minY } ?? 0
        let overlap = previous.map { min($0.end, end) - max($0.start, start) } ?? 0
        measurements.append([
          "segment": segment,
          "frame": [frame.minX, frame.minY, frame.width, frame.height],
          "viewport": [viewport.minX, viewport.minY, viewport.width, viewport.height],
          "visibleStart": start, "visibleEnd": end,
          "travel": travel, "movement": movement, "overlap": overlap,
        ])
        keepScreenshot(name + (segment == 0 ? "" : "-segment-\(segment)"), app)
        if let previous {
          guard frame.minX == previous.frame.minX, frame.size == previous.frame.size,
            movement > 1, overlap > 0, end > previous.end
          else { XCTFail("Guide text must advance with measured overlap: \(name)"); return nil }
        } else {
          guard start == 0, frame.minY >= viewport.minY
          else { XCTFail("Guide paragraph beginning was not captured: \(name)"); return nil }
        }
        return (frame, viewport, start, end)
      }
      guard var current = snapshot(segment: 0, travel: 0, previous: nil) else { return }
      // Visible intervals use paragraph coordinates, so viewport changes cannot hide a gap.
      for segment in 1...8 {
        if current.end == current.frame.height { complete = true; return }
        let viewport = current.viewport
        let travel = min(max(current.frame.height - current.end + 4, 24), viewport.height * 0.55)
        let frames = scroll.buttons.allElementsBoundByIndex.map(\.frame) + [current.frame]
        let active = frames.filter { !$0.isEmpty && $0.maxX > viewport.minX && $0.minX < viewport.maxX }
        guard active.allSatisfy({ $0.minX.isFinite && $0.maxX.isFinite }),
          let leading = active.map(\.minX).min(), let trailing = active.map(\.maxX).max()
        else {
          XCTFail("Invalid guide scroll control geometry: \(name)")
          return
        }
        let x: CGFloat
        if leading - viewport.minX >= 16 {
          x = (viewport.minX + leading) / 2
        } else if viewport.maxX - trailing >= 16 {
          x = (viewport.maxX + trailing) / 2
        } else {
          XCTFail("No blank guide scroll gutter: \(name)")
          return
        }
        let center = viewport.midY
        let origin = scroll.coordinate(withNormalizedOffset: .zero)
        let start = origin.withOffset(CGVector(
          dx: x - scroll.frame.minX, dy: center + travel / 2 - scroll.frame.minY))
        let finish = origin.withOffset(CGVector(
          dx: x - scroll.frame.minX, dy: center - travel / 2 - scroll.frame.minY))
        start.press(forDuration: 0.01, thenDragTo: finish, withVelocity: .slow, thenHoldForDuration: 0.2)
        guard let next = snapshot(segment: segment, travel: travel, previous: current) else { return }
        current = next
      }
      if current.end == current.frame.height { complete = true; return }
      XCTFail("Guide paragraph end did not enter the viewport within eight moves: \(name)")
    }

    private func rAndBRGuideJourney(largeText: Bool) {
      let app = launch(largeText: largeText)
      // This journey also visits all five first-review words before checking visit reset.
      executionTimeAllowance = 360
      defer { app.terminate() }
      waitForPracticeSystemBannerToClear()
      let history = historyRows(app)
      app.selectPracticeTab("Sounds")
      activate("cadence.search.open", app)
      let search = app.descendants(matching: .any)
        .matching(identifier: "cadence.search.field").firstMatch
      XCTAssertTrue(search.waitForExistence(timeout: 5))
      search.tap()
      search.typeText("bread\n")
      activate("cadence.search.result.r-middle-bread", app)
      waitLabel(app.staticTexts["cadence.word"], "bread")
      assertCollapsedRGuide(app)
      activate("cadence.sound-guide.toggle", app)
      assertExpandedRGuide(word: "bread", blend: true, largeText: largeText, app)
      activate("cadence.sound-guide.toggle", app)
      assertCollapsedRGuide(app)
      activate("cadence.sound-guide.toggle", app)
      waitLabel(app.staticTexts["cadence.sound-guide.title"], "R in the BR of “bread”")
      activate("cadence.close", app)
      XCTAssertTrue(search.waitForExistence(timeout: 5))
      activate("Clear search", app)
      search.tap()
      search.typeText("rabbit\n")
      activate("cadence.search.result.r-beginning-rabbit", app)
      waitLabel(app.staticTexts["cadence.word"], "rabbit")
      assertCollapsedRGuide(app)
      activate("cadence.sound-guide.toggle", app)
      assertExpandedRGuide(word: "rabbit", blend: false, largeText: largeText, app)
      activate("cadence.skip-word", app)
      waitLabel(app.staticTexts["cadence.word"], "rain")
      assertCollapsedRGuide(app)
      activate("cadence.close", app)
      app.selectPracticeTab("Today")
      assertHome(app)
      XCTAssertEqual(historyRows(app), history)

      activate("cadence.local-guided.open", app)
      assertSetup(app)
      activate("cadence.guided.setup.0", app)
      let guidedSearch = app.descendants(matching: .any)
        .matching(identifier: "cadence.guided.search").firstMatch
      XCTAssertTrue(guidedSearch.waitForExistence(timeout: 5))
      guidedSearch.tap()
      guidedSearch.typeText("bread\n")
      activate("cadence.guided.pick.r-middle-bread", app)
      XCTAssertTrue(app.buttons["cadence.guided.setup.0"].label.contains("bread"))
      activate("cadence.guided.start", app)
      let guidedWords = ["bread", "pig", "moon", "tiger", "dog"]
      for (index, word) in guidedWords.enumerated() {
        assertReady(word, stage: "First review", index: index, count: 5, app)
        if index == 0 {
          assertCollapsedRGuide(app)
          activate("cadence.sound-guide.toggle", app)
          waitLabel(app.staticTexts["cadence.sound-guide.title"], "R in the BR of “bread”")
        }
        activate("cadence.guided.skip", app)
      }
      activate("cadence.guided.select.r-middle-bread", app)
      waitLabel(app.buttons["cadence.guided.practice.start"], "Practice selected words (1)")
      activate("cadence.guided.practice.start", app)
      assertReady("bread", stage: "Practice", index: 0, count: 1, app)
      assertCollapsedRGuide(app)
      activate("cadence.sound-guide.toggle", app)
      waitLabel(app.staticTexts["cadence.sound-guide.title"], "R in the BR of “bread”")
      activate("cadence.guided.skip", app)
      activate("cadence.guided.recheck.start", app)
      assertReady("bread", stage: "Recheck", index: 0, count: 5, app)
      assertCollapsedRGuide(app)
      activate("cadence.sound-guide.toggle", app)
      waitLabel(app.staticTexts["cadence.sound-guide.title"], "R in the BR of “bread”")
      activate("cadence.guided.close", app)
      assertHome(app)
      XCTAssertEqual(historyRows(app), history)
    }

    private func assertCollapsedRGuide(_ app: XCUIApplication) {
      XCTAssertTrue(app.buttons["cadence.sound-guide.toggle"].exists)
      for id in ["title", "detail", "r-option-title", "r-option-detail",
                 "r-variation-title", "r-variation-detail", "r-accent"] {
        XCTAssertFalse(app.staticTexts["cadence.sound-guide." + id].exists, id)
      }
    }

    private func assertExpandedRGuide(
      word: String, blend: Bool, largeText: Bool, _ app: XCUIApplication
    ) {
      let sections = [
        ("title", blend ? "R in the BR of “\(word)”" : "R at the start of “\(word)”"),
        ("detail", blend
          ? "Start with your lips together for B, then move straight into R as you say “\(word)”. Keep the sounds together in one whole word."
          : "Say “\(word)” as one whole word."),
        ("r-option-title", "One way to try R"),
        ("r-option-detail", "Try drawing your tongue back and up, with its sides touching the inside of your upper back teeth. Say “\(word)” with your usual voice."),
        ("r-variation-title", "More than one way"),
        ("r-variation-detail", "Some people make R with the tongue tip curled back. Others do not. You do not have to force a curl. Keep practice relaxed."),
        ("r-accent", "US English word list. R varies across English accents."),
      ]
      for (id, text) in sections {
        let section = app.staticTexts["cadence.sound-guide." + id]
        waitLabel(section, text)
        captureGuideText(section,
          name: "release-\(word)-\(largeText ? "largest" : "normal")-\(id)", app)
      }
      XCTAssertTrue(app.staticTexts["A general guide to this sound."].exists)
      XCTAssertFalse(app.staticTexts["cadence.sound-guide.closed-caption"].exists)
      XCTAssertFalse(app.staticTexts["cadence.sound-guide.open-caption"].exists)
      XCTAssertTrue(app.buttons["cadence.record"].isEnabled)
      XCTAssertFalse(app.buttons["cadence.stop"].exists)
      XCTAssertFalse(app.buttons["cadence.replay"].exists)
      XCTAssertFalse(app.staticTexts["cadence.word-check-result"].exists)
    }

    private func soundGuideJourney(largeText: Bool) {
      let app = launch(largeText: largeText)
      defer { app.terminate() }
      waitForPracticeSystemBannerToClear()
      let history = historyRows(app)
      activate("cadence.start", app)
      XCTAssertFalse(app.staticTexts["cadence.sound-guide.detail"].exists)
      activate("cadence.sound-guide.toggle", app)
      waitLabel(app.staticTexts["cadence.sound-guide.title"], "B at the start of “ball”")
      let detail = app.staticTexts["cadence.sound-guide.detail"]
      waitLabel(detail, "Bring your lips together, then open them as you say “ball”. Use your usual voice.")
      reveal(detail, app)
      keepScreenshot(largeText ? "release-sound-guide-largest-text" : "release-sound-guide-text", app)
      for (id, text) in [
        ("cadence.sound-guide.closed-caption", "1. Lips together"),
        ("cadence.sound-guide.open-caption", "2. Lips open"),
      ] {
        let caption = app.staticTexts[id]
        waitLabel(caption, text)
        reveal(caption, app)
        keepScreenshot("release-sound-guide-\(largeText ? "largest-" : "")\(id)", app)
      }
      XCTAssertTrue(app.buttons["cadence.record"].isEnabled)
      XCTAssertFalse(app.buttons["cadence.stop"].exists)
      XCTAssertFalse(app.buttons["cadence.replay"].exists)
      XCTAssertFalse(app.staticTexts["cadence.word-check-result"].exists)
      activate("cadence.skip-word", app)
      waitLabel(app.staticTexts["cadence.word"], "boat")
      XCTAssertFalse(detail.exists, "A new word starts with its own collapsed explanation")
      activate("cadence.sound-guide.toggle", app)
      waitLabel(app.staticTexts["cadence.sound-guide.title"], "B at the start of “boat”")
      activate("cadence.close", app)
      assertHome(app)
      XCTAssertEqual(historyRows(app), history)

      activate("cadence.local-guided.open", app)
      assertSetup(app)
      activate("cadence.guided.start", app)
      assertReady("ball", stage: "First review", index: 0, count: 5, app)
      XCTAssertFalse(app.staticTexts["cadence.sound-guide.detail"].exists)
      activate("cadence.sound-guide.toggle", app)
      waitLabel(app.staticTexts["cadence.sound-guide.title"], "B at the start of “ball”")
      activate("cadence.guided.skip", app)
      assertReady("pig", stage: "First review", index: 1, count: 5, app)
      assertCollapsedDefaultGuide(app)
      activate("cadence.sound-guide.toggle", app)
      waitLabel(app.staticTexts["cadence.sound-guide.title"], "P at the start of “pig”")
      waitLabel(app.staticTexts["cadence.sound-guide.detail"], defaultGuideDetails[1])
      activate("cadence.guided.close", app)
      assertHome(app)
      XCTAssertEqual(historyRows(app), history)
    }

    func testReleaseOrdinarySkippedRoundLeavesHistoryUnchanged() {
      ordinarySkippedRound(largeText: false)
    }

    func testReleaseLargestTextOrdinarySkippedRoundLeavesHistoryUnchanged() {
      ordinarySkippedRound(largeText: true)
    }

    private func ordinarySkippedRound(largeText: Bool) {
      let app = launch(largeText: largeText)
      defer { app.terminate() }
      waitForPracticeSystemBannerToClear()
      let history = historyRows(app)
      activate("cadence.start", app)
      for (index, word) in ["ball", "boat", "bee"].enumerated() {
        waitLabel(app.staticTexts["cadence.word"], word)
        XCTAssertTrue(app.staticTexts["Word \(index + 1) of 3"].exists)
        XCTAssertFalse(app.buttons["cadence.stop"].exists)
        XCTAssertFalse(app.buttons["cadence.replay"].exists)
        activate("cadence.skip-word", app)
      }
      let completion = app.staticTexts["cadence.complete"]
      waitLabel(completion, "You skipped all 3 words. Nothing was added to recent practice.")
      XCTAssertFalse(app.buttons["cadence.skip-word"].exists)
      XCTAssertFalse(app.buttons["cadence.history-retry"].exists)
      XCTAssertFalse(app.staticTexts["cadence.history-saved"].exists)
      reveal(completion, app)
      keepScreenshot(largeText ? "ordinary-skipped-largest" : "ordinary-skipped-compact", app)
      let tree = XCTAttachment(string: app.debugDescription)
      tree.name = "ordinary-skipped-completion-accessibility"
      tree.lifetime = .keepAlways
      add(tree)
      activate("Practice these again", app)
      waitLabel(app.staticTexts["cadence.word"], "ball")
      XCTAssertTrue(app.staticTexts["Word 1 of 3"].exists)
      XCTAssertTrue(app.buttons["cadence.skip-word"].isEnabled)
      activate("cadence.close", app)
      assertHome(app)
      XCTAssertEqual(historyRows(app), history)
    }

    private let words = ["ball", "pig", "moon", "tiger", "dog"]
    private let entryIDs = [
      "b-beginning-ball", "p-beginning-pig", "m-beginning-moon", "t-beginning-tiger",
      "d-beginning-dog",
    ]

    func testReleasePositionChoicesPreserveSearchAndCancel() {
      positionFilterJourney(largeText: false)
    }

    func testReleaseLargestTextPositionChoicesPreserveSearchAndCancel() {
      positionFilterJourney(largeText: true)
    }

    private func positionFilterJourney(largeText: Bool) {
      let app = launch(largeText: largeText)
      executionTimeAllowance = 360
      defer { app.terminate() }
      waitForPracticeSystemBannerToClear()
      let history = historyRows(app)
      activate("cadence.local-guided.open", app)
      assertSetup(app)
      activate("cadence.guided.setup.0", app)
      XCTAssertTrue(app.navigationBars["Change word"].waitForExistence(timeout: 5))
      let search = app.textFields["cadence.guided.search"]
      XCTAssertTrue(search.waitForExistence(timeout: 5))
      search.tap()
      search.typeText("bread")
      XCTAssertTrue(app.keyboards.firstMatch.exists)
      activate("cadence.guided.position-filter", app)
      XCTAssertFalse(app.keyboards.firstMatch.exists)
      XCTAssertEqual(search.value as? String, "bread")
      assertPositionChoices(selected: "all", largeText: largeText, app)
      activate("cadence.guided.position-option.beginning", app)
      assertPositionResult("Beginning", entryID: "b-beginning-bread", app)

      // Reproduce the exact old warning interaction: Beginning -> All positions.
      activate("cadence.guided.position-filter", app)
      assertPositionChoices(selected: "beginning", largeText: largeText, app)
      activate("cadence.guided.position-option.all", app)
      XCTAssertEqual(app.buttons["cadence.guided.position-filter"].value as? String, "All positions")
      XCTAssertEqual(search.value as? String, "bread")
      XCTAssertEqual(positionOptions(app).count, 0)

      for (choice, value, entryID) in [
        ("middle", "Middle", "r-middle-bread"), ("end", "End", "d-end-bread")
      ] {
        activate("cadence.guided.position-filter", app)
        activate("cadence.guided.position-option." + choice, app)
        assertPositionResult(value, entryID: entryID, app)
        keepScreenshot("position-\(largeText ? "largest" : "compact")-\(choice)-result", app)
        if choice == "middle" {
          activate("cadence.guided.position-filter", app)
          let selected = app.buttons["cadence.guided.position-option.middle"]
          reveal(selected, app)
          XCTAssertTrue(selected.isSelected)
          activate("cadence.guided.position-filter", app)
          XCTAssertEqual(positionOptions(app).count, 0)
        }
      }
      activate("cadence.guided.position-filter", app)
      XCTAssertTrue(app.buttons["cadence.guided.position-option.end"].isSelected)
      activate("cadence.guided.position-option.end", app)
      XCTAssertEqual(positionOptions(app).count, 0, "Choosing the existing position also collapses")
      XCTAssertEqual(search.value as? String, "bread")
      activate("cadence.guided.position-filter", app)
      activate("cadence.guided.position-option.all", app)
      XCTAssertEqual(app.buttons["cadence.guided.position-filter"].value as? String, "All positions")
      XCTAssertEqual(search.value as? String, "bread")
      activate("cadence.guided.search.clear", app)
      search.tap()
      search.typeText("pig\n")
      let duplicate = app.buttons["cadence.guided.pick.p-beginning-pig"]
      revealFilteredResult("p-beginning-pig", app)
      XCTAssertTrue(duplicate.exists)
      XCTAssertFalse(duplicate.isEnabled)
      activate("cadence.guided.picker.cancel", app)
      assertSetup(app)
      activate("cadence.guided.close", app)
      assertHome(app)
      XCTAssertEqual(historyRows(app), history)
    }

    private func positionOptions(_ app: XCUIApplication) -> XCUIElementQuery {
      app.buttons.matching(NSPredicate(
        format: "identifier BEGINSWITH %@", "cadence.guided.position-option."))
    }

    private func assertPositionChoices(
      selected: String, largeText: Bool, _ app: XCUIApplication
    ) {
      for option in ["all", "beginning", "middle", "end"] {
        let button = app.buttons["cadence.guided.position-option." + option]
        reveal(button, app)
        XCTAssertTrue(button.isHittable)
        XCTAssertGreaterThanOrEqual(button.frame.height, 44)
        XCTAssertEqual(button.isSelected, option == selected)
        if selected == "all" {
          keepScreenshot("position-\(largeText ? "largest" : "compact")-choice-\(option)", app)
        }
      }
      XCTAssertEqual(positionOptions(app).count, 4)
    }

    private func assertPositionResult(
      _ value: String, entryID: String, _ app: XCUIApplication
    ) {
      XCTAssertEqual(app.buttons["cadence.guided.position-filter"].value as? String, value)
      XCTAssertEqual(positionOptions(app).count, 0)
      XCTAssertEqual(app.textFields["cadence.guided.search"].value as? String, "bread")
      let result = app.buttons["cadence.guided.pick." + entryID]
      revealFilteredResult(entryID, app)
      XCTAssertTrue(result.isHittable)
      XCTAssertTrue(result.isEnabled)
      XCTAssertTrue(result.label.contains("bread"))
      XCTAssertTrue(result.label.contains(value))
      for other in ["b-beginning-bread", "r-middle-bread", "d-end-bread"] where other != entryID {
        XCTAssertFalse(app.buttons["cadence.guided.pick." + other].exists)
      }
    }

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
