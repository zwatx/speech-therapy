import XCTest

/// Generated signal values through the real guided player; no microphone or audio output.
@MainActor
final class LiveInputUITests: XCTestCase {
  func testCompactInputMeterAndStop() { inputJourney(largest: false) }
  func testNativeLargestInputMeterAndStop() { inputJourney(largest: true) }

  private func inputJourney(largest: Bool) {
    continueAfterFailure = false
    executionTimeAllowance = 180
    let app = XCUIApplication()
    let category =
      largest
      ? "UICTContentSizeCategoryAccessibilityXXXL" : "UICTContentSizeCategoryL"
    app.launchArguments = [
      "--live-input-private", UUID().uuidString, "--text-size",
      largest ? "largest" : "compact", "-UIPreferredContentSizeCategoryName", category,
    ]
    app.launch()
    XCTAssertTrue(app.staticTexts["live-input.fixture.text-size"].waitForExistence(timeout: 5))
    XCTAssertEqual(app.staticTexts["live-input.fixture.text-size"].label, category)
    XCTAssertFalse(app.otherElements["cadence.recording-input"].exists)
    activate("cadence.guided.start", app)
    activate("cadence.record", app)
    let meter = app.otherElements["cadence.recording-input"]
    value("-12 decibels", meter)
    scrollTo(meter, app, including: app.buttons["cadence.stop"])
    let meterFrame = meter.frame
    let stopFrame = app.buttons["cadence.stop"].frame
    attach(app, "input-12")
    activate("live-input.fixture.lower", app)
    value("-36 decibels", meter)
    sameFrame(meter.frame, meterFrame)
    sameFrame(app.buttons["cadence.stop"].frame, stopFrame)
    attach(app, "input-36")
    activate("live-input.fixture.unavailable", app)
    value("Unavailable", meter)
    sameFrame(meter.frame, meterFrame)
    sameFrame(app.buttons["cadence.stop"].frame, stopFrame)
    attach(app, "input-unavailable")
    activate("cadence.stop", app)
    XCTAssertTrue(app.buttons["cadence.replay"].waitForExistence(timeout: 5))
    XCTAssertFalse(meter.exists)
    activate("cadence.guided.close", app)
    XCTAssertTrue(app.staticTexts["live-input.fixture.closed"].waitForExistence(timeout: 5))
    XCTAssertEqual(app.staticTexts["live-input.fixture.closed"].label, "Generated files kept: 0")
    app.terminate()
  }

  private func value(_ expected: String, _ element: XCUIElement) {
    let predicate = NSPredicate { _, _ in
      element.exists && element.value as? String == expected
    }
    XCTAssertEqual(
      XCTWaiter.wait(
        for: [XCTNSPredicateExpectation(predicate: predicate, object: nil)], timeout: 5),
      .completed, expected)
    XCTAssertEqual(element.label, "Microphone input")
  }

  private func sameFrame(_ actual: CGRect, _ expected: CGRect) {
    XCTAssertEqual(actual.minX, expected.minX, accuracy: 1)
    XCTAssertEqual(actual.minY, expected.minY, accuracy: 1)
    XCTAssertEqual(actual.width, expected.width, accuracy: 1)
    XCTAssertEqual(actual.height, expected.height, accuracy: 1)
  }

  private func activate(_ id: String, _ app: XCUIApplication) {
    let button = app.buttons[id]
    XCTAssertTrue(button.exists || button.waitForExistence(timeout: 5), id)
    if !id.hasPrefix("live-input.fixture.") && id != "cadence.guided.close" {
      scrollTo(button, app)
    }
    XCTAssertTrue(button.isHittable, id)
    XCTAssertTrue(button.isEnabled, id)
    XCTAssertGreaterThanOrEqual(button.frame.height, 44, id)
    button.tap()
  }

  private func scrollTo(
    _ target: XCUIElement, _ app: XCUIApplication, including companion: XCUIElement? = nil
  ) {
    let scroll = app.scrollViews.firstMatch
    let viewport = scroll.frame
    let top =
      max(
        viewport.minY, app.buttons["live-input.fixture.unavailable"].frame.maxY,
        app.buttons["cadence.guided.close"].frame.maxY) + 8
    let bottom = min(viewport.maxY, app.windows.firstMatch.frame.maxY) - 8
    let height = bottom - top
    guard height > 0 else { return XCTFail("No unobscured recording viewport") }
    for _ in 0..<12 {
      let frame = companion.map { target.frame.union($0.frame) } ?? target.frame
      guard frame.height <= height else {
        return XCTFail("Recording controls do not fit together in the viewport")
      }
      if frame.minY >= top, frame.maxY <= bottom, target.isHittable,
        companion?.isHittable != false
      {
        return
      }
      let distance = frame.midY - (top + bottom) / 2
      let travel = min(abs(distance), height * 0.6)
      let start = app.coordinate(withNormalizedOffset: .zero).withOffset(
        CGVector(dx: viewport.midX, dy: distance > 0 ? bottom : top))
      let end = start.withOffset(CGVector(dx: 0, dy: distance > 0 ? -travel : travel))
      start.press(forDuration: 0.05, thenDragTo: end)
    }
    XCTFail("Recording control did not become fully visible")
  }

  private func attach(_ app: XCUIApplication, _ name: String) {
    let attachment = XCTAttachment(screenshot: app.screenshot())
    attachment.name = name
    attachment.lifetime = .keepAlways
    add(attachment)
  }
}
