import XCTest

/// Explicit combined intent through actual guided owners with generated media/results.
@MainActor
final class GuidedRecordAndCheckUITests: XCTestCase {
  func testCompactRecordAndCheckJourney() { journey(largest: false) }
  func testNativeLargestRecordAndCheckJourney() { journey(largest: true) }

  private func journey(largest: Bool) {
    continueAfterFailure = false
    executionTimeAllowance = 300
    let app = XCUIApplication()
    let category =
      largest
      ? "UICTContentSizeCategoryAccessibilityXXXL" : "UICTContentSizeCategoryL"
    app.launchArguments = [
      "--record-check-private", UUID().uuidString, "--text-size", largest ? "largest" : "compact",
      "-UIPreferredContentSizeCategoryName", category,
    ]
    app.launch()
    label(app.staticTexts["record-check.fixture.text-size"], category)
    activate("cadence.guided.start", app)
    label(app.staticTexts["cadence.word"], "ball")
    label(app.buttons["cadence.record-and-check"], "Record and check")
    label(app.buttons["cadence.record"], "Record only")
    combined(app, count: 1, screenshot: "first")
    activate("cadence.guided.continue", app)

    label(app.staticTexts["cadence.word"], "pig")
    activate("cadence.record", app)
    activate("cadence.stop", app)
    checks(app, count: 1)
    XCTAssertTrue(app.buttons["cadence.word-check"].isEnabled)
    activate("cadence.word-check", app)
    checks(app, count: 2, pending: true)
    activate("cadence.generated-guided.release", app)
    checks(app, count: 2)
    activate("cadence.guided.continue", app)
    for word in ["moon", "tiger", "dog"] {
      label(app.staticTexts["cadence.word"], word)
      activate("cadence.guided.skip", app)
    }

    activate("cadence.guided.select.b-beginning-ball", app)
    activate("cadence.guided.practice.start", app)
    label(app.staticTexts["cadence.word"], "ball")
    XCTAssertFalse(app.buttons["cadence.record-and-check"].exists)
    label(app.buttons["cadence.record"], "Record")
    activate("cadence.record", app)
    activate("cadence.stop", app)
    checks(app, count: 2)
    activate("cadence.guided.continue", app)
    label(app.staticTexts["cadence.generated-guided.history"], "Generated history: 1 rows [b:1]")
    activate("cadence.guided.recheck.start", app)
    label(app.staticTexts["cadence.word"], "ball")
    combined(app, count: 3, screenshot: "recheck")
    activate("cadence.guided.continue", app)
    for word in ["pig", "moon", "tiger", "dog"] {
      label(app.staticTexts["cadence.word"], word)
      activate("cadence.guided.skip", app)
    }
    let paired = app.staticTexts["cadence.guided.paired.b-beginning-ball"]
    XCTAssertTrue(paired.waitForExistence(timeout: 5))
    XCTAssertTrue(paired.label.contains("First review: Word matched"))
    XCTAssertTrue(paired.label.contains("Recheck: Word matched"))
    checks(app, count: 3)
    label(
      app.staticTexts["cadence.generated-guided.files"],
      "Generated files: made 4, kept 0 · permission requests 4 · playback starts 0")
    label(app.staticTexts["cadence.generated-guided.history"], "Generated history: 1 rows [b:1]")
    activate("cadence.guided.close", app)
    label(app.staticTexts["record-check.fixture.closed"], "Generated files kept: 0")
    app.terminate()
  }

  private func combined(_ app: XCUIApplication, count: Int, screenshot: String) {
    activate("cadence.record-and-check", app)
    activate("cadence.stop", app)
    checks(app, count: count, pending: true)
    let cancel = app.buttons["cadence.word-check-cancel"]
    XCTAssertTrue(cancel.waitForExistence(timeout: 5))
    scrollTo(cancel, app)
    XCTAssertTrue(cancel.isEnabled)
    XCTAssertFalse(app.buttons["cadence.guided.continue"].isEnabled)
    attach(app, screenshot + "-checking")
    activate("cadence.generated-guided.release", app)
    checks(app, count: count)
    let result = app.staticTexts["cadence.word-check-result"]
    label(result, "“ball” matched in this try. Individual sounds aren’t assessed.")
    scrollTo(result, app)
    attach(app, screenshot + "-result")
    XCTAssertTrue(app.buttons["cadence.guided.continue"].isEnabled)
  }

  private func checks(_ app: XCUIApplication, count: Int, pending: Bool = false) {
    label(
      app.staticTexts["cadence.generated-guided.checks"],
      "Generated checks: \(count), pending \(pending ? 1 : 0), cancelled 0, borrowed \(pending ? 1 : 0)"
    )
  }

  private func label(_ element: XCUIElement, _ expected: String) {
    let predicate = NSPredicate { _, _ in element.exists && element.label == expected }
    XCTAssertEqual(
      XCTWaiter.wait(
        for: [XCTNSPredicateExpectation(predicate: predicate, object: nil)], timeout: 5),
      .completed, expected)
  }

  private func activate(_ id: String, _ app: XCUIApplication) {
    let button = app.buttons[id]
    XCTAssertTrue(button.exists || button.waitForExistence(timeout: 5), id)
    if id != "cadence.guided.close" && id != "cadence.generated-guided.release" {
      scrollTo(button, app)
    }
    XCTAssertTrue(button.isHittable, id)
    XCTAssertTrue(button.isEnabled, id)
    XCTAssertGreaterThanOrEqual(button.frame.height, 44, id)
    button.tap()
  }

  private func scrollTo(_ target: XCUIElement, _ app: XCUIApplication) {
    let scroll = app.scrollViews.firstMatch
    // The generated host's inset and viewport stay fixed during this one scroll action.
    // Read their bounds once; the target's frame and hittability remain fresh on every drag.
    let viewport = scroll.frame
    let top =
      max(
        viewport.minY,
        max(
          app.buttons["cadence.generated-guided.release"].frame.maxY,
          app.buttons["cadence.guided.close"].frame.maxY)) + 8
    let bottom = min(viewport.maxY, app.windows.firstMatch.frame.maxY) - 8
    let visibleHeight = bottom - top
    guard visibleHeight > 0 else {
      XCTFail("No unobscured guided viewport is available")
      return
    }
    var previousFrame: CGRect?
    var previousTravel: CGFloat = 0
    var previousAbove: Bool?
    for _ in 0..<24 {
      let frame = target.frame
      // Dynamic Type text and choice buttons can be taller than the viewport.
      // Align the leading edge while still requiring the actual target to be hittable;
      // demanding both edges be visible would alternate drags without a possible fit.
      // Full-label and any explicit frame assertions in the journeys remain unchanged.
      let oversizedTarget = frame.height > visibleHeight
      let eligible =
        frame.minY >= top
        && (oversizedTarget ? frame.minY <= top + visibleHeight * 0.2 : frame.maxY <= bottom)
      // Preserve the original short circuit: no hittability query when geometry fails.
      let hittable: Bool? = eligible ? target.isHittable : nil
      if eligible, hittable == true {
        return
      }
      // Near-fit targets have a narrow containment interval. Aim at its midpoint
      // without a minimum step that could repeatedly jump across the whole interval.
      let desiredTop = oversizedTarget ? top : top + (visibleHeight - frame.height) / 2
      let above = frame.minY < desiredTop
      let distance = abs(frame.minY - desiredTop)
      var travel =
        oversizedTarget
        ? min(max(distance, visibleHeight * 0.2), visibleHeight * 0.6)
        : min(distance, visibleHeight * 0.6)
      // Estimate only the preceding drag's lost movement, not a cumulative offset.
      // Ignore reflow, reversal and overshoot; they do not measure touch slop.
      if !oversizedTarget, distance > 0, distance <= 24,
        let previousFrame, previousTravel > 0, previousAbove == above,
        previousFrame.minX == frame.minX, previousFrame.size == frame.size
      {
        let movement = (frame.minY - previousFrame.minY) * (above ? 1 : -1)
        if movement >= 0, movement <= previousTravel {
          let lostMovement = min(previousTravel - movement, 24)
          travel = min(distance + lostMovement, visibleHeight * 0.6)
        }
      }
      // At the desired position, an unhittable target stays unproved; do not tap it.
      if travel == 0 { continue }
      let centerY = (top + bottom) / 2
      let startY = centerY + (above ? -travel / 2 : travel / 2)
      let finishY = centerY + (above ? travel / 2 : -travel / 2)
      // A short drag can resolve as a tap. Keep the entire vertical gesture in
      // an observed blank gutter, outside every button in this scroll and the target.
      let buttonFrames = scroll.buttons.allElementsBoundByIndex.map { $0.frame } + [frame]
      guard
        let dragX = gutterX(viewport, window: app.windows.firstMatch.frame, frames: buttonFrames)
      else {
        XCTFail("No blank guided scroll gutter is available")
        return
      }
      previousFrame = frame
      previousTravel = travel
      previousAbove = above
      let origin = scroll.coordinate(withNormalizedOffset: .zero)
      let start = origin.withOffset(CGVector(dx: dragX - viewport.minX, dy: startY - viewport.minY))
      let finish = origin.withOffset(
        CGVector(dx: dragX - viewport.minX, dy: finishY - viewport.minY))
      // Use a slow drag and held release to reduce flick-like overshoot.
      // TRACE-v4 observed frame movement exceeding the requested travel and
      // oscillating across the oversized target’s eligible leading-edge band.
      start.press(
        forDuration: 0.01, thenDragTo: finish, withVelocity: .slow, thenHoldForDuration: 0.2)
    }
    XCTFail("Guided control did not enter the unobscured viewport")
  }

  private func gutterX(_ viewport: CGRect, window: CGRect, frames: [CGRect]) -> CGFloat? {
    let left = max(viewport.minX, window.minX)
    let right = min(viewport.maxX, window.maxX)
    guard left.isFinite, right.isFinite, right > left else { return nil }
    var leading = right
    var trailing = left
    var hasFrame = false
    for frame in frames {
      guard frame.minX.isFinite, frame.maxX.isFinite, frame.width.isFinite,
        frame.height.isFinite, frame.width >= 0, frame.height >= 0
      else { return nil }
      // Empty accessibility frames do not describe a hit region.
      guard frame.width > 0, frame.height > 0 else { continue }
      if frame.maxX > left, frame.minX < right {
        hasFrame = true
        leading = min(leading, max(left, frame.minX))
        trailing = max(trailing, min(right, frame.maxX))
      }
    }
    guard hasFrame else { return nil }
    let leadingWidth = leading - left
    let trailingWidth = right - trailing
    // Eight points from each edge at minimum; never fall back inside a button.
    if leadingWidth >= 16, leadingWidth >= trailingWidth { return left + leadingWidth / 2 }
    if trailingWidth >= 16 { return right - trailingWidth / 2 }
    return nil
  }

  private func attach(_ app: XCUIApplication, _ name: String) {
    let attachment = XCTAttachment(screenshot: app.screenshot())
    attachment.name = name
    attachment.lifetime = .keepAlways
    add(attachment)
  }
}
