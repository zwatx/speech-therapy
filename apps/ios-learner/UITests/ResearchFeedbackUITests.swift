import XCTest

/// Actual simulator rendering/navigation only. Never taps Record, Replay or Check.
@MainActor
final class ResearchFeedbackUITests: XCTestCase {
  func testWordMenuPreservesAllCanonicalChoicesAndSelectsBanana() throws {
    let app = launchFeedback(large: false)
    let menu = app.buttons["feedback-word-picker"]
    scrollTo(menu, app)
    XCTAssertTrue(menu.isHittable)
    menu.tap()
    let labels = [
      "rabbit · r sound", "bread · r sound", "door · r sound",
      "baby · first b sound", "baby · second b sound", "banana · first n sound",
      "backpack · first k sound", "backpack · second k sound", "sky · s sound",
      "vase · v sound", "yo-yo · first y sound", "thumb · th sound",
      "feather · voiced th sound", "ring · ng sound", "treasure · zh sound",
    ]
    let banana = app.buttons["banana · first n sound"]
    XCTAssertTrue(banana.waitForExistence(timeout: 3))
    let inventory = XCTAttachment(string: app.debugDescription)
    inventory.name = "feedback-word-menu-canonical-inventory"
    inventory.lifetime = .keepAlways
    add(inventory)
    attach(app, "feedback-word-menu-options")
    XCTAssertEqual(app.buttons.matching(NSPredicate(format: "label IN %@", labels)).count, 15)
    for label in labels {
      XCTAssertEqual(
        app.buttons.matching(NSPredicate(format: "label == %@", label)).count, 1, label)
    }
    XCTAssertTrue(
      banana.isHittable, "Selection requires the observed menu option, not guessed coordinates.")
    banana.tap()
    XCTAssertEqual(menu.value as? String, "banana · first n sound")
    attach(app, "feedback-word-menu-selected-banana-setup")
    let word = app.staticTexts["feedback-word"]
    scrollTo(word, app)
    XCTAssertTrue(word.isHittable)
    let changedWord = XCTNSPredicateExpectation(
      predicate: NSPredicate(format: "label == %@", "banana"), object: word)
    XCTAssertEqual(XCTWaiter.wait(for: [changedWord], timeout: 5), .completed)
    XCTAssertEqual(word.label, "banana")
    assertNoRecordingOrProcessing(app)
    attach(app, "feedback-word-menu-selected-banana-word")
  }

  func testDefaultAllowsLocalRecordingWithoutAgeOrProcessingAndCloseReturnsPractice() throws {
    let app = launchFeedback(large: false)
    XCTAssertTrue(app.staticTexts["feedback-state-ready"].waitForExistence(timeout: 5))
    XCTAssertTrue(
      app.buttons["feedback-record"].isHittable, "Record must be available before scrolling.")
    let geometry = XCTAttachment(
      string:
        "viewport=\(app.windows.firstMatch.frame)\nRecord.frame=\(app.buttons["feedback-record"].frame)\n"
        + "dynamicType=UICTContentSizeCategoryL\nactual XCTest simulator bounds")
    geometry.name = "feedback-default-record-viewport"
    geometry.lifetime = .keepAlways
    add(geometry)
    attach(app, "feedback-default-top")
    let age = element("feedback-context", app)
    let optIn = element("feedback-opt-in", app)
    scrollTo(age, app)
    XCTAssertTrue(
      age.label.contains("Not set") || (age.value as? String)?.contains("Not set") == true)
    XCTAssertEqual(optIn.value as? String, "Off")
    scrollTo(app.buttons["feedback-record"], app)
    XCTAssertTrue(app.buttons["feedback-record"].isHittable)
    assertNoRecordingOrProcessing(app)
    attach(app, "feedback-default-record-controls")
    let privacyNote = app.staticTexts["feedback-note"]
    scrollTo(privacyNote, app)
    XCTAssertTrue(privacyNote.isHittable)
    attach(app, "feedback-default-privacy-footer")
    app.buttons["feedback-close"].tap()
    XCTAssertTrue(app.buttons["cadence.start"].waitForExistence(timeout: 5))
  }

  func testExplicitAgeOptInAndNextWordStaySensorFreeUntilSeparateActions() throws {
    let app = launchFeedback(large: false)
    let age = element("feedback-context", app)
    scrollTo(age, app)
    age.tap()
    XCTAssertTrue(app.buttons["Child, age 9"].waitForExistence(timeout: 3))
    app.buttons["Child, age 9"].tap()
    XCTAssertTrue(age.label.contains("9") || (age.value as? String)?.contains("9") == true)
    let optIn = element("feedback-opt-in", app)
    scrollTo(optIn, app)
    optIn.tap()
    XCTAssertEqual(optIn.value as? String, "On")
    let next = app.buttons["feedback-next"]
    scrollTo(next, app)
    XCTAssertTrue(next.isEnabled)
    XCTAssertTrue(next.isHittable)
    next.tap()
    attach(app, "feedback-after-next-controls")
    let word = app.staticTexts["feedback-word"]
    scrollTo(word, app)
    XCTAssertTrue(word.isHittable)
    attach(app, "feedback-after-next-visible-word")
    let changedWord = XCTNSPredicateExpectation(
      predicate: NSPredicate(format: "label == %@", "bread"), object: word)
    let nextWordResult = XCTWaiter.wait(for: [changedWord], timeout: 5)
    if nextWordResult != .completed { capturePracticeFailure(app) }
    XCTAssertEqual(nextWordResult, .completed)
    XCTAssertEqual(word.label, "bread")
    XCTAssertTrue(app.staticTexts["feedback-state-ready"].exists)
    assertNoRecordingOrProcessing(app)
    attach(app, "feedback-context-nine-opt-in-next-word")
    app.buttons["feedback-close"].tap()
    XCTAssertTrue(app.buttons["cadence.start"].waitForExistence(timeout: 5))
  }

  func testAboutKeepsBothExistingLabsAndHomeOpensSeparateFeedback() throws {
    continueAfterFailure = false
    let app = XCUIApplication()
    app.launch()
    XCTAssertTrue(app.buttons["cadence.start"].waitForExistence(timeout: 5))
    app.buttons["About practice and privacy"].tap()
    let lab = app.buttons["cadence.lab.open"]
    scrollTo(lab, app)
    XCTAssertTrue(lab.isHittable)
    XCTAssertTrue(app.buttons["cadence.admission-lab.open"].exists)
    XCTAssertFalse(app.buttons["cadence.feedback.open"].exists)
    attach(app, "feedback-about-existing-labs")
    app.buttons["Done"].tap()
    let feedback = app.buttons["cadence.feedback.start"]
    scrollTo(feedback, app)
    XCTAssertTrue(feedback.isHittable)
    feedback.tap()
    XCTAssertTrue(app.staticTexts["feedback-title"].waitForExistence(timeout: 5))
    XCTAssertTrue(app.staticTexts["feedback-state-ready"].exists)
    assertNoRecordingOrProcessing(app)
    attach(app, "feedback-opened-from-home")
    app.buttons["feedback-close"].tap()
    XCTAssertTrue(app.buttons["cadence.start"].waitForExistence(timeout: 5))
  }

  func testLargeDynamicTypeAccessibilityAndHittableMinimumControls() throws {
    let app = launchFeedback(large: true)
    XCTAssertTrue(app.staticTexts["feedback-title"].waitForExistence(timeout: 5))
    attach(app, "feedback-large-text-top")
    for identifier in [
      "feedback-close", "feedback-word-picker", "feedback-context", "feedback-opt-in",
      "feedback-record", "feedback-next",
    ] {
      let control = element(identifier, app)
      scrollTo(control, app)
      XCTAssertTrue(control.isHittable, identifier)
      XCTAssertGreaterThanOrEqual(control.frame.height, 44, identifier)
      XCTAssertGreaterThanOrEqual(control.frame.width, 44, identifier)
      if identifier == "feedback-word-picker" || identifier == "feedback-context" {
        attach(app, "feedback-large-text-setup-\(identifier)")
      }
    }
    assertNoRecordingOrProcessing(app)
    attach(app, "feedback-large-text-controls")
    try app.performAccessibilityAudit()
  }

  private func launchFeedback(large: Bool) -> XCUIApplication {
    continueAfterFailure = false
    let app = XCUIApplication()
    app.launchArguments = [
      "-CadenceFeedbackMode", "-UIPreferredContentSizeCategoryName",
      large ? "UICTContentSizeCategoryAccessibilityXXXL" : "UICTContentSizeCategoryL",
    ]
    app.launch()
    return app
  }
  private func element(_ id: String, _ app: XCUIApplication) -> XCUIElement {
    app.descendants(matching: .any).matching(identifier: id).firstMatch
  }
  private func scrollTo(_ target: XCUIElement, _ app: XCUIApplication) {
    let window = app.windows.firstMatch.frame
    // Close belongs to the fixed inset, outside the scrolling content.
    if target.identifier == "feedback-close" {
      XCTAssertTrue(window.contains(target.frame) && target.isEnabled && target.isHittable)
      return
    }
    // The underlying Today ScrollView can coexist with the presented Feedback view.
    // Select the actual target's scroll ancestor, never the app's first ScrollView.
    let scroll = app.scrollViews.containing(.any, identifier: target.identifier).firstMatch
    guard !target.identifier.isEmpty, scroll.exists else {
      XCTFail("No scroll ancestor contains \(target.identifier)")
      return
    }
    let viewport = scroll.frame.intersection(window)
    var top = viewport.minY + 8
    for identifier in ["feedback-close", "feedback-close-note", "feedback-ui-test-banner"] {
      let inset = element(identifier, app)
      if inset.exists { top = max(top, inset.frame.maxY + 8) }
    }
    let bottom = viewport.maxY - 8
    let visibleHeight = bottom - top
    guard visibleHeight > 0 else {
      XCTFail("No unobscured Feedback viewport is available")
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
        frame.minX >= viewport.minX && frame.maxX <= viewport.maxX
        && frame.minY >= top
        && (oversizedTarget ? frame.minY <= top + visibleHeight * 0.2 : frame.maxY <= bottom)
      // Preserve the original short circuit: no hittability query when geometry fails.
      let hittable: Bool? = eligible ? target.isHittable : nil
      if eligible, hittable == true, target.isEnabled {
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
      // an observed blank gutter, outside every button, switch and the target in this scroll.
      let controlFrames =
        (scroll.buttons.allElementsBoundByIndex + scroll.switches.allElementsBoundByIndex)
        .map { $0.frame } + [frame]
      guard
        let dragX = gutterX(viewport, window: app.windows.firstMatch.frame, frames: controlFrames)
      else {
        XCTFail("No blank Feedback scroll gutter is available")
        return
      }
      previousFrame = frame
      previousTravel = travel
      previousAbove = above
      let origin = scroll.coordinate(withNormalizedOffset: .zero)
      let start = origin.withOffset(CGVector(dx: dragX - scroll.frame.minX, dy: startY - scroll.frame.minY))
      let finish = origin.withOffset(
        CGVector(dx: dragX - scroll.frame.minX, dy: finishY - scroll.frame.minY))
      // Use a slow drag and held release to reduce flick-like overshoot.
      // This is the existing guided-journey gesture pattern; keep oversized
      // targets inside their eligible leading-edge band without flick overshoot.
      start.press(
        forDuration: 0.01, thenDragTo: finish, withVelocity: .slow, thenHoldForDuration: 0.2)
    }
    XCTFail("Scroll target did not enter the unobscured viewport")
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

  private func assertNoRecordingOrProcessing(_ app: XCUIApplication) {
    for id in [
      "feedback-stop", "feedback-check", "feedback-replay", "feedback-permission-progress",
      "feedback-checking-progress",
    ] { XCTAssertFalse(element(id, app).exists, id) }
  }
  private func attach(_ app: XCUIApplication, _ name: String) {
    let attachment = XCTAttachment(screenshot: app.screenshot())
    attachment.name = name
    attachment.lifetime = .keepAlways
    add(attachment)
  }
}
