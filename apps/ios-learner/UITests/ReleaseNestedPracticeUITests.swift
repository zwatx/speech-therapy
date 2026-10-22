import XCTest

#if !DEBUG && targetEnvironment(simulator)
  /// Ordinary app navigation. No Record, Check, playback, mirror, settings or Retry action.
  @MainActor
  final class ReleaseNestedPracticeUITests: XCTestCase {
    private var gestures = 0

    func testReleaseCompactSearchAndSoundLibraryReturnToTheirOwnRoutes() throws {
      let app = XCUIApplication()
      defer { app.terminate() }
      launch(app, largest: false)
      app.selectPracticeTab("Sounds")
      activate("cadence.search.open", app)
      XCTAssertTrue(app.navigationBars["Search words"].waitForExistence(timeout: 5))
      let field = searchField(app)
      XCTAssertTrue(field.waitForExistence(timeout: 5))
      XCTAssertTrue(field.isHittable)
      field.tap()
      field.typeText("shoe\n")
      activate("cadence.search.result.sh-beginning-shoe", app)
      assertWordCard("shoe", app)
      screenshot("compact-search-shoe-card", app)
      activate("cadence.close", app)
      assertSearchReturned("shoe", app)
      nativeBack("Search words", app)
      assertSoundsRoot(app)
      app.selectPracticeTab("Today")
      assertHome(app)
      app.selectPracticeTab("Sounds")
      activate("cadence.sound.sh", app)
      XCTAssertTrue(app.navigationBars["Words to practice"].waitForExistence(timeout: 5))
      activate("cadence.library.sh-beginning-shoe", app)
      assertWordCard("shoe", app)
      screenshot("compact-library-shoe-card", app)
      activate("cadence.close", app)
      XCTAssertTrue(app.navigationBars["Words to practice"].waitForExistence(timeout: 5))
      XCTAssertFalse(app.buttons["cadence.close"].exists)
      XCTAssertTrue(app.buttons["cadence.library.sh-beginning-shoe"].exists)
      nativeBack("Words to practice", app)
      assertSoundsRoot(app)
      app.selectPracticeTab("Today")
      assertHome(app)
      screenshot("compact-nested-routes-home", app)
    }

    func testReleaseLargestSearchLettersThenReturnSelectsTelevisionAndReturnsHome() throws {
      let clock = ContinuousClock()
      let started = clock.now
      var result = SearchResult()
      let app = XCUIApplication()
      defer {
        result.elapsedMilliseconds = milliseconds(started.duration(to: clock.now))
        if let data = try? JSONEncoder().encode(result) {
          print("CADENCE_RELEASE_NESTED_SEARCH_V1=" + String(decoding: data, as: UTF8.self))
        }
        app.terminate()
      }
      launch(app, largest: true)
      app.selectPracticeTab("Sounds")
      activate("cadence.search.open", app)
      XCTAssertTrue(app.navigationBars["Search words"].waitForExistence(timeout: 5))
      let field = searchField(app)
      XCTAssertTrue(field.waitForExistence(timeout: 5))
      XCTAssertTrue(field.isHittable)
      field.tap()
      try checkpoint(
        "before-letters", field: field, app: app, result: result,
        started: started, clock: clock)
      let letters = clock.now
      emit("before-letters-input", result, started: started, clock: clock)
      field.typeText("television")
      result.lettersReturned = true
      result.lettersMilliseconds = milliseconds(letters.duration(to: clock.now))
      XCTAssertNotNil(result.lettersMilliseconds)
      emit("letters-returned", result, started: started, clock: clock)
      result.lettersValueExact = (field.value as? String) == "television"
      XCTAssertTrue(result.lettersValueExact)
      // Same actual field, with no result lookup, drag, tap, focus change or dismissal
      // between letters and Return. A stall is evidence, never a reason to bypass Return.
      try checkpoint(
        "after-letters", field: field, app: app, result: result,
        started: started, clock: clock)
      let submit = clock.now
      emit("before-submit-input", result, started: started, clock: clock)
      field.typeText("\n")
      result.submitReturned = true
      result.submitMilliseconds = milliseconds(submit.duration(to: clock.now))
      XCTAssertNotNil(result.submitMilliseconds)
      emit("submit-returned", result, started: started, clock: clock)
      try checkpoint(
        "after-submit", field: field, app: app, result: result,
        started: started, clock: clock)
      result.submittedValueExact = (field.value as? String) == "television"
      XCTAssertTrue(result.submittedValueExact)
      activate("cadence.search.result.zh-middle-television", app)
      assertWordCard("television", app)
      result.correctCard = app.staticTexts["cadence.word"].label == "television"
      XCTAssertTrue(result.correctCard)
      screenshot("largest-search-television-card", app)
      activate("cadence.close", app)
      assertSearchReturned("television", app)
      result.searchReturned =
        app.navigationBars["Search words"].exists
        && (searchField(app).value as? String) == "television"
      XCTAssertTrue(result.searchReturned)
      nativeBack("Search words", app)
      assertSoundsRoot(app)
      app.selectPracticeTab("Today")
      assertHome(app)
      result.homeReturned =
        app.buttons["cadence.local-guided.open"].exists
        && !app.navigationBars["Search words"].exists
      XCTAssertTrue(result.homeReturned)
      screenshot("largest-nested-search-home", app)
    }

    private struct SearchResult: Encodable {
      let schema = "ReleaseNestedPracticeSearchV1"
      var lettersReturned = false, lettersValueExact = false, submitReturned = false
      var submittedValueExact = false, correctCard = false, searchReturned = false
      var homeReturned = false
      var lettersMilliseconds: Double?, submitMilliseconds: Double?, elapsedMilliseconds: Double?
    }

    private func launch(_ app: XCUIApplication, largest: Bool) {
      continueAfterFailure = false
      executionTimeAllowance = 180
      gestures = 0
      for key in app.launchEnvironment.keys
      where key.hasPrefix("CADENCE_") || key.hasPrefix("TEST_RUNNER_CADENCE_") {
        app.launchEnvironment.removeValue(forKey: key)
      }
      app.launchArguments = [
        "-UIPreferredContentSizeCategoryName",
        largest ? "UICTContentSizeCategoryAccessibilityXXXL" : "UICTContentSizeCategoryL",
      ]
      app.launch()
      assertHome(app)
      XCTAssertFalse(app.staticTexts["cadence.home.ui-test-banner"].exists)
      XCTAssertFalse(app.staticTexts["cadence.generated-history.banner"].exists)
      XCTAssertFalse(app.staticTexts["cadence.generated-guided.banner"].exists)
    }

    private func searchField(_ app: XCUIApplication) -> XCUIElement {
      app.descendants(matching: .any).matching(identifier: "cadence.search.field").firstMatch
    }
    private func assertSoundsRoot(_ app: XCUIApplication) {
      XCTAssertTrue(app.tabBars.buttons["Sounds"].isSelected)
      XCTAssertTrue(app.buttons["cadence.search.open"].waitForExistence(timeout: 5))
      XCTAssertFalse(app.navigationBars["Search words"].exists)
      XCTAssertFalse(app.navigationBars["Words to practice"].exists)
    }
    private func assertHome(_ app: XCUIApplication) {
      XCTAssertTrue(app.tabBars.buttons["Today"].isSelected)
      XCTAssertTrue(app.buttons["cadence.local-guided.open"].waitForExistence(timeout: 5))
      XCTAssertTrue(app.buttons["cadence.start"].exists)
      XCTAssertFalse(app.buttons["cadence.close"].exists)
    }
    private func assertWordCard(_ word: String, _ app: XCUIApplication) {
      let card = app.staticTexts["cadence.word"]
      let expected = XCTNSPredicateExpectation(
        predicate: NSPredicate(format: "label == %@", word), object: card)
      XCTAssertEqual(XCTWaiter.wait(for: [expected], timeout: 5), .completed)
      XCTAssertTrue(app.buttons["cadence.record"].exists)
      XCTAssertFalse(app.buttons["cadence.replay"].exists)
      XCTAssertFalse(app.staticTexts["cadence.word-check-result"].exists)
    }
    private func assertSearchReturned(_ value: String, _ app: XCUIApplication) {
      XCTAssertTrue(app.navigationBars["Search words"].waitForExistence(timeout: 5))
      XCTAssertFalse(app.buttons["cadence.close"].exists)
      XCTAssertEqual(searchField(app).value as? String, value)
    }
    private func nativeBack(_ title: String, _ app: XCUIApplication) {
      let bar = app.navigationBars[title]
      XCTAssertTrue(bar.waitForExistence(timeout: 5))
      let back = bar.buttons.firstMatch
      XCTAssertTrue(back.isHittable)
      XCTAssertTrue(back.isEnabled)
      back.tap()
      XCTAssertFalse(bar.exists)
    }

    private func milliseconds(_ duration: Duration) -> Double? {
      let value =
        Double(duration.components.seconds) * 1000
        + Double(duration.components.attoseconds) / 1e15
      return value.isFinite && value >= 0 ? value : nil
    }
    private func emit(
      _ stage: String, _ result: SearchResult,
      started: ContinuousClock.Instant, clock: ContinuousClock
    ) {
      struct Stage: Encodable {
        let stage: String
        let elapsedMilliseconds: Double?
        let result: SearchResult
      }
      let value = Stage(
        stage: stage, elapsedMilliseconds: milliseconds(started.duration(to: clock.now)),
        result: result)
      if let data = try? JSONEncoder().encode(value) {
        print("CADENCE_RELEASE_NESTED_SEARCH_STAGE_V1=" + String(decoding: data, as: UTF8.self))
      }
    }
    private func checkpoint(
      _ name: String, field: XCUIElement, app: XCUIApplication,
      result: SearchResult, started: ContinuousClock.Instant, clock: ContinuousClock
    ) throws {
      screenshot("largest-nested-search-" + name, app)
      let frame = field.frame
      let window = app.windows.firstMatch.frame
      guard finite(frame), finite(window),
        let elapsed = milliseconds(started.duration(to: clock.now))
      else {
        XCTFail("Nonfinite Search checkpoint geometry or elapsed duration")
        return
      }
      let geometry: [String: Any] = [
        "checkpoint": name, "elapsedMilliseconds": elapsed,
        "field": [frame.minX, frame.minY, frame.width, frame.height],
        "window": [window.minX, window.minY, window.width, window.height],
        "keyboardPresent": app.keyboards.firstMatch.exists, "fieldHittable": field.isHittable,
        "gestures": gestures, "lettersReturned": result.lettersReturned,
        "submitReturned": result.submitReturned,
      ]
      let attachment = XCTAttachment(
        data: try JSONSerialization.data(withJSONObject: geometry, options: [.sortedKeys]),
        uniformTypeIdentifier: "public.json")
      attachment.name = "largest-nested-search-" + name + "-geometry"
      attachment.lifetime = .keepAlways
      add(attachment)
    }
    private func screenshot(_ name: String, _ app: XCUIApplication) {
      let attachment = XCTAttachment(screenshot: app.screenshot())
      attachment.name = name
      attachment.lifetime = .keepAlways
      add(attachment)
    }
    private func finite(_ frame: CGRect) -> Bool {
      [frame.minX, frame.minY, frame.width, frame.height].allSatisfy({ $0.isFinite })
        && frame.width > 0 && frame.height > 0
    }
    private func activate(_ identifier: String, _ app: XCUIApplication) {
      let button = app.buttons[identifier]
      XCTAssertTrue(button.waitForExistence(timeout: 5), identifier)
      if identifier == "cadence.close" {
        // Close is initially visible on these fresh, unscrolled word cards.
        // Validate its actual target directly before tapping.
        let frame = button.frame
        let window = app.windows.firstMatch.frame
        XCTAssertTrue(finite(frame) && finite(window), identifier)
        XCTAssertTrue(window.contains(frame), identifier)
        XCTAssertTrue(button.isHittable && button.isEnabled, identifier)
        button.tap()
        return
      }
      reveal(button, app)
      XCTAssertTrue(button.isHittable && button.isEnabled, identifier)
      button.tap()
    }
    /// Existing observed blank-gutter family, with a total24drag budget per method.
    private func reveal(_ target: XCUIElement, _ app: XCUIApplication) {
      let scroll = app.scrollViews.firstMatch
      for _ in 0..<25 {
        let frame = target.frame
        let source = scroll.frame
        let window = app.windows.firstMatch.frame
        guard finite(source), finite(window), finite(frame) else {
          XCTFail("Nonfinite route viewport")
          return
        }
        let bars = app.navigationBars.allElementsBoundByIndex.filter(\.isHittable).map(\.frame)
        let top = max(source.minY, bars.map(\.maxY).max() ?? source.minY) + 8
        let bottom = min(source.maxY, window.maxY) - 8
        let height = bottom - top
        guard height > 0 else {
          XCTFail("No unobscured nested-route viewport")
          return
        }
        let oversized = frame.height > height
        if frame.minY >= top
          && (oversized ? frame.minY <= top + height * 0.2 : frame.maxY <= bottom)
          && target.isHittable
        {
          return
        }
        guard gestures < 24 else {
          XCTFail("Nested-route24drag budget exhausted")
          return
        }
        let left = max(source.minX, window.minX)
        let right = min(source.maxX, window.maxX)
        let controls = (scroll.buttons.allElementsBoundByIndex.map(\.frame) + [frame]).filter {
          finite($0) && $0.maxX > left && $0.minX < right
        }
        let leading = controls.map(\.minX).min() ?? left
        let trailing = controls.map(\.maxX).max() ?? right
        let x: CGFloat
        if leading - left >= 16 {
          x = (left + leading) / 2
        } else if right - trailing >= 16 {
          x = (trailing + right) / 2
        } else {
          XCTFail("No observed blank route scroll gutter")
          return
        }
        let desired = oversized ? top : top + (height - frame.height) / 2
        let above = frame.minY < desired
        let travel = min(max(abs(frame.minY - desired), 24), height * 0.6)
        let center = (top + bottom) / 2
        gestures += 1
        let origin = scroll.coordinate(withNormalizedOffset: .zero)
        origin.withOffset(
          CGVector(
            dx: x - source.minX,
            dy: center + (above ? -travel / 2 : travel / 2) - source.minY)
        ).press(
          forDuration: 0.01,
          thenDragTo: origin.withOffset(
            CGVector(
              dx: x - source.minX,
              dy: center + (above ? travel / 2 : -travel / 2) - source.minY)),
          withVelocity: .slow, thenHoldForDuration: 0.2)
      }
      XCTFail("Target did not enter the nested-route viewport")
    }
  }
#endif
