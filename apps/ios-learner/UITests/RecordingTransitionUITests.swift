import XCTest

/// Generated capture-transition evidence only. These injected capturers hold until Stop;
/// no system microphone, audible playback, spoken-word provider or model is exercised.
@MainActor
final class RecordingTransitionUITests: XCTestCase {
  func testCompactOrdinaryRecordExposesStopWithoutScrolling() {
    journey(guided: false, largeText: false)
  }
  func testLargestTextOrdinaryRecordExposesStopWithoutScrolling() {
    journey(guided: false, largeText: true)
  }
  func testCompactSelectedPracticeRecordExposesStopWithoutScrolling() {
    journey(guided: true, largeText: false)
  }
  func testLargestTextSelectedPracticeRecordExposesStopWithoutScrolling() {
    journey(guided: true, largeText: true)
  }

  private func journey(guided: Bool, largeText: Bool) {
    continueAfterFailure = false
    executionTimeAllowance = 240
    let app = XCUIApplication()
    for key in app.launchEnvironment.keys
    where key.hasPrefix("CADENCE_") || key.hasPrefix("TEST_RUNNER_CADENCE_") {
      app.launchEnvironment.removeValue(forKey: key)
    }
    app.launchEnvironment["CADENCE_CONTROLLED_UI_HOST"] = "1"
    let mode = guided ? "LocalGuided" : "DirectTry"
    let testCase = (guided ? "practice" : "twoTry") + (largeText ? "AX" : "")
    let name = "generated-recording-transition-" + testCase
    app.launchArguments = [
      "-Cadence\(mode)Mode", "-Cadence\(mode)UITestCase", testCase,
      "-CadenceControlledUIRunID", UUID().uuidString.lowercased(),
    ]
    addTeardownBlock { @MainActor [weak self] () throws -> Void in
      guard let self else { return }
      if app.state == .runningForeground {
        self.capture(name + "-final-state", app, extra: [
          "terminationIsFallbackOnly": true,
        ])
      }
      app.terminate()
    }
    app.launch()
    let bannerID = guided ? "cadence.generated-guided.banner" : "cadence.generated-banner"
    XCTAssertTrue(app.staticTexts[bannerID].waitForExistence(timeout: 5))
    if guided {
      XCTAssertTrue(labelMatches(app.staticTexts["cadence.generated-guided.seed"],
        "Generated stage: five settled first checks; no choices preselected"))
      activateBeforeCapture("cadence.guided.select.p-beginning-pig", app)
      activateBeforeCapture("cadence.guided.practice.start", app)
    }
    XCTAssertTrue(labelMatches(app.staticTexts["cadence.word"], guided ? "pig" : "ball"))
    XCTAssertTrue(app.buttons["cadence.hear-word"].exists)
    XCTAssertFalse(app.buttons["cadence.hear-word"].isEnabled)
    XCTAssertTrue(labelMatches(app.staticTexts["cadence.spoken-word-status"],
      "Spoken words aren't available in this practice session. Use the available practice controls."))
    var observations: [TransitionObservation] = []
    var preparationFailed = false
    var recordTaps = 0
    for attempt in 1...2 {
      let attemptName = name + (attempt == 1 ? "-first" : "-retake")
      let recordID = attempt == 1 ? "cadence.record" : "cadence.record-another"
      let record = app.buttons[recordID]
      let appeared = record.exists || record.waitForExistence(timeout: 5)
      let revealed = appeared && reveal(record, id: recordID, app)
      let recordFrame = record.exists ? record.frame : .zero
      let readyViewport = viewport(app)
      let recordUsable = revealed && controlVisible(record, frame: recordFrame, viewport: readyViewport)
      capture(attemptName + "-ready-before-record", app, extra: [
        "recordID": recordID, "recordFrame": rect(recordFrame), "viewport": rect(readyViewport),
        "recordFullyVisible44": recordUsable,
        "configuration": "Generated nil spoken-word provider; not a real speech/capture claim",
      ])
      guard recordUsable else {
        preparationFailed = true
        break // No tap: retain any first take and proceed to public Close cleanup.
      }
      let touch = CGPoint(x: recordFrame.midX, y: recordFrame.midY)
      record.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
      recordTaps += 1

      // No reveal, drag or other gesture may precede this observation.
      // Keep all success assertions until explicit Stop and final Close below.
      let stop = app.buttons["cadence.stop"]
      let stopAppeared = stop.waitForExistence(timeout: 5)
      let stopExists = stop.exists
      let initialStop = stopExists ? stop.frame : .zero
      let recordingViewport = viewport(app)
      let initiallyHittable = stopExists && stop.isHittable
      let initiallyEnabled = stopExists && stop.isEnabled
      let initiallyVisible = stopExists
        && controlVisible(stop, frame: initialStop, viewport: recordingViewport)
      capture(attemptName + "-initial-recording-no-gesture", app, extra: [
        "stopAppeared": stopAppeared, "stopExists": stopExists,
        "stopFrame": rect(initialStop), "viewport": rect(recordingViewport),
        "hittable": initiallyHittable, "enabled": initiallyEnabled,
        "fullyVisible44": initiallyVisible,
        "recordToStopDelta": [initialStop.minX - recordFrame.minX, initialStop.minY - recordFrame.minY],
        "recordTouchPoint": [touch.x, touch.y],
        "recordTouchPointInsideStop": stopExists && initialStop.contains(touch),
      ])

      var corrected = false
      if !initiallyVisible {
        // This corrective gesture is recovery, never proof that Stop was exposed.
        capture(attemptName + "-corrective-stop-reveal-begins", app, extra: [
          "correctiveGestureRequired": true,
          "excludedFromInitialVisibilityProof": true,
        ])
        corrected = reveal(stop, id: "cadence.stop", app)
        capture(attemptName + "-after-corrective-stop-reveal", app, extra: [
          "correctiveRevealSucceeded": corrected,
        ])
      }
      let stopReachable = stop.exists
        && controlVisible(stop, frame: stop.frame, viewport: viewport(app))
      if stopReachable {
        stop.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
      }
      let reviewReached = app.buttons["cadence.replay"].waitForExistence(timeout: 5)
      let made = (guided ? 5 : 0) + attempt
      let filesID = guided ? "cadence.generated-guided.files" : "cadence.generated-files"
      let stoppedFiles = "Generated files: made \(made), kept \(attempt) · "
        + (guided ? "permission requests" : "microphone requests") + " \(made) · playback starts 0"
      let keptObserved = labelMatches(app.staticTexts[filesID], stoppedFiles)
      let noSavedCompletion = !app.staticTexts["cadence.history-saved"].exists
      let noWordResult = !app.staticTexts["cadence.word-check-result"].exists
      let noActivePlayback = !app.staticTexts["cadence.playback-status"].exists
      let guidedChecksUnchanged = !guided || labelMatches(app.staticTexts["cadence.generated-guided.checks"],
        "Generated checks: 5, pending 0, cancelled 0, borrowed 0")
      let guidedHistoryEmpty = !guided || labelMatches(app.staticTexts["cadence.generated-guided.history"],
        "Generated history: 0 rows []")
      capture(attemptName + "-after-explicit-stop", app, extra: [
        "stopWasReachable": stopReachable, "reviewReached": reviewReached,
        "keptFileCountObserved": keptObserved, "correctiveRevealUsed": !initiallyVisible,
        "correctiveRevealSucceeded": corrected, "guidedChecksUnchanged": guidedChecksUnchanged,
        "guidedHistoryEmpty": guidedHistoryEmpty,
        "noSavedCompletion": noSavedCompletion, "noWordResult": noWordResult,
        "noActivePlayback": noActivePlayback,
      ])
      observations.append(TransitionObservation(
        name: attemptName, stopFrame: initialStop, stopAppeared: stopAppeared && stopExists,
        enabledAndHittable: initiallyEnabled && initiallyHittable, initiallyVisible: initiallyVisible,
        explicitStopAndReview: stopReachable && reviewReached,
        keptAndNoOtherWork: keptObserved && guidedChecksUnchanged && guidedHistoryEmpty
          && noSavedCompletion && noWordResult && noActivePlayback))
      guard stopReachable, reviewReached, keptObserved else { break }
    }
    let made = (guided ? 5 : 0) + recordTaps
    let closeID = guided ? "cadence.guided.close" : "cadence.close"
    let close = app.buttons[closeID]
    let closeReachable: Bool
    if guided {
      closeReachable = close.exists && close.isEnabled && close.isHittable
    } else {
      closeReachable = reveal(close, id: closeID, app)
    }
    if closeReachable { close.tap() }
    let closedID = guided ? "cadence.generated-guided.closed" : "cadence.generated-direct-closed"
    let closed = app.staticTexts[closedID].waitForExistence(timeout: 5)
    let closedFilesID = guided ? "cadence.generated-guided.closed-files" : "cadence.generated-closed-files"
    let closedFiles = "Generated files: made \(made), kept 0 · "
      + (guided ? "permission requests" : "microphone requests") + " \(made) · playback starts 0"
    let cleanupObserved = labelMatches(app.staticTexts[closedFilesID], closedFiles)
    let closedHistoryEmpty = !guided || labelMatches(app.staticTexts["cadence.generated-guided.closed-history"],
      "Generated history: 0 rows []")
    capture(name + "-closed-cleanup-before-visibility-gate", app, extra: [
      "closed": closed, "zeroKeptObserved": cleanupObserved,
      "closedHistoryEmpty": closedHistoryEmpty,
    ])

    // These assertions deliberately follow all public Stop/Close and file proof.
    XCTAssertTrue(closeReachable && closed)
    XCTAssertTrue(cleanupObserved)
    XCTAssertTrue(closedHistoryEmpty)
    XCTAssertFalse(preparationFailed, "Record/Record another must be fully visible before tapping")
    XCTAssertEqual(observations.count, 2, "First and retake transitions must both be observed")
    for observation in observations {
      XCTAssertTrue(observation.explicitStopAndReview, observation.name)
      XCTAssertTrue(observation.keptAndNoOtherWork, observation.name)
      XCTAssertTrue(observation.stopAppeared, observation.name)
      XCTAssertTrue(finite(observation.stopFrame), observation.name)
      XCTAssertTrue(observation.enabledAndHittable, observation.name)
      XCTAssertTrue(observation.initiallyVisible,
                    "Stop must be exposed before any corrective gesture: \(observation.name)")
    }
  }

  private struct TransitionObservation {
    let name: String
    let stopFrame: CGRect
    let stopAppeared: Bool
    let enabledAndHittable: Bool
    let initiallyVisible: Bool
    let explicitStopAndReview: Bool
    let keptAndNoOtherWork: Bool
  }

  private func activateBeforeCapture(_ id: String, _ app: XCUIApplication) {
    let target = app.buttons[id]
    XCTAssertTrue(target.waitForExistence(timeout: 5), id)
    let selectionRow = id.hasPrefix("cadence.guided.select.")
    XCTAssertTrue(reveal(target, id: id, app, allowOversizedSelection: selectionRow), id)
    XCTAssertTrue(target.isEnabled && target.isHittable, id)
    if selectionRow {
      let frame = target.frame, visible = viewport(app)
      let intersection = frame.intersection(visible)
      XCTAssertTrue(finite(frame) && finite(intersection))
      XCTAssertFalse(intersection.isEmpty)
      XCTAssertGreaterThanOrEqual(intersection.width, 44)
      XCTAssertGreaterThanOrEqual(intersection.height, 44)
      let point = CGPoint(x: intersection.midX, y: intersection.midY)
      capture("generated-selection-visible-intersection-" + id, app, extra: [
        "row": rect(frame), "viewport": rect(visible), "visibleIntersection": rect(intersection),
        "tapPoint": [point.x, point.y], "wholeRowVisibilityRequired": false,
      ])
      let window = app.windows.firstMatch
      window.coordinate(withNormalizedOffset: .zero).withOffset(CGVector(
        dx: point.x - window.frame.minX, dy: point.y - window.frame.minY)).tap()
    } else {
      target.tap()
    }
  }

  private func viewport(_ app: XCUIApplication) -> CGRect {
    let frame = app.scrollViews.firstMatch.frame.intersection(app.windows.firstMatch.frame)
    var top = frame.minY
    for id in ["cadence.generated-banner", "cadence.generated-files", "cadence.generated-playback-file",
               "cadence.generated-guided.banner", "cadence.generated-guided.seed",
               "cadence.generated-guided.files", "cadence.generated-guided.checks",
               "cadence.generated-guided.history", "cadence.generated-guided.receipts"] {
      let text = app.staticTexts[id]
      if text.exists { top = max(top, text.frame.maxY) }
    }
    let fixedClose = app.buttons["cadence.guided.close"]
    if fixedClose.exists { top = max(top, fixedClose.frame.maxY) }
    return CGRect(x: frame.minX, y: top + 8, width: frame.width,
                  height: max(0, frame.maxY - top - 16))
  }

  private func controlVisible(_ control: XCUIElement, frame: CGRect, viewport: CGRect) -> Bool {
    finite(frame) && !frame.isEmpty && viewport.height > 0
      && control.isEnabled && control.isHittable
      && (frame.width * 1_000_000).rounded() / 1_000_000 >= 44
      && (frame.height * 1_000_000).rounded() / 1_000_000 >= 44
      && frame.minX >= viewport.minX && frame.maxX <= viewport.maxX
      && frame.minY >= viewport.minY && frame.maxY <= viewport.maxY
  }

  // Returns a result without assertions so an offscreen Stop can be recovered and
  // cleaned before the saved initial-visibility gate is evaluated.
  private func reveal(
    _ target: XCUIElement, id: String, _ app: XCUIApplication,
    allowOversizedSelection: Bool = false
  ) -> Bool {
    let scroll = app.scrollViews.firstMatch
    guard scroll.exists else { return false }
    var previous: CGRect?, previousTravel: CGFloat = 0, previousDown: Bool?
    for _ in 0..<12 {
      guard target.exists else { return false }
      let frame = target.frame, visible = viewport(app)
      guard finite(frame), !frame.isEmpty, visible.height > 0 else { return false }
      let oversizedSelection = allowOversizedSelection
        && id.hasPrefix("cadence.guided.select.") && frame.height > visible.height
      guard frame.height <= visible.height || oversizedSelection else { return false }
      if oversizedSelection {
        let intersection = frame.intersection(visible)
        if frame.minY >= visible.minY, frame.minY <= visible.minY + visible.height * 0.2,
          finite(intersection), intersection.width >= 44, intersection.height >= 44,
          target.isEnabled, target.isHittable { return true }
      } else if controlVisible(target, frame: frame, viewport: visible) { return true }
      let desired = oversizedSelection ? visible.minY
        : visible.minY + (visible.height - frame.height) / 2
      let down = frame.minY < desired, distance = abs(frame.minY - desired)
      var travel = min(distance, visible.height * 0.6)
      if distance > 0, distance <= 24, let previous,
        previousTravel > 0, previousDown == down, previous.size == frame.size {
        let movement = (frame.minY - previous.minY) * (down ? 1 : -1)
        if movement >= 0, movement <= previousTravel {
          travel = min(distance + min(previousTravel - movement, 24), visible.height * 0.6)
        }
      }
      guard travel > 0 else { continue }
      let frames = (scroll.buttons.allElementsBoundByIndex.map(\.frame) + [frame]).filter {
        !$0.isEmpty && $0.maxX > visible.minX && $0.minX < visible.maxX
      }
      guard frames.allSatisfy({ finite($0) }), let leading = frames.map(\.minX).min(),
        let trailing = frames.map(\.maxX).max() else { return false }
      let x: CGFloat
      if leading - visible.minX >= 16 { x = (leading + visible.minX) / 2 }
      else if visible.maxX - trailing >= 16 { x = (trailing + visible.maxX) / 2 }
      else { return false }
      previous = frame; previousTravel = travel; previousDown = down
      let origin = scroll.coordinate(withNormalizedOffset: .zero)
      let start = origin.withOffset(CGVector(dx: x - scroll.frame.minX,
        dy: visible.midY + (down ? -travel / 2 : travel / 2) - scroll.frame.minY))
      let end = origin.withOffset(CGVector(dx: x - scroll.frame.minX,
        dy: visible.midY + (down ? travel / 2 : -travel / 2) - scroll.frame.minY))
      start.press(forDuration: 0.01, thenDragTo: end,
                  withVelocity: .slow, thenHoldForDuration: 0.2)
    }
    return false
  }

  private func labelMatches(_ target: XCUIElement, _ label: String) -> Bool {
    guard target.exists || target.waitForExistence(timeout: 5) else { return false }
    let expectation = XCTNSPredicateExpectation(
      predicate: NSPredicate(format: "label == %@", label), object: target)
    return XCTWaiter.wait(for: [expectation], timeout: 5) == .completed
  }

  private func capture(_ name: String, _ app: XCUIApplication, extra: [String: Any]) {
    let image = XCTAttachment(screenshot: app.screenshot())
    image.name = name
    image.lifetime = .keepAlways
    add(image)
    let tree = XCTAttachment(string: app.debugDescription)
    tree.name = name + "-accessibility"
    tree.lifetime = .keepAlways
    add(tree)
    var geometry = extra
    geometry["window"] = rect(app.windows.firstMatch.frame)
    var elements: [String: Any] = [:]
    for id in ["cadence.word", "cadence.record", "cadence.record-another", "cadence.stop", "cadence.hear-word",
               "cadence.spoken-word-status", "cadence.guided.visit-heading",
               "cadence.guided.first-observation", "cadence.practice-instruction.title",
               "cadence.practice-instruction.detail", "cadence.recording-startup-unavailable"] {
      let element = app.descendants(matching: .any).matching(identifier: id).firstMatch
      var value: [String: Any] = ["exists": element.exists]
      if element.exists {
        value["frame"] = rect(element.frame)
        value["finite"] = finite(element.frame)
        value["hittable"] = element.isHittable
        value["enabled"] = element.isEnabled
        value["label"] = element.label
      }
      elements[id] = value
    }
    geometry["elements"] = elements
    let attachment: XCTAttachment
    if let data = try? JSONSerialization.data(withJSONObject: geometry, options: [.sortedKeys]) {
      attachment = XCTAttachment(data: data, uniformTypeIdentifier: "public.json")
    } else {
      attachment = XCTAttachment(string: String(describing: geometry))
    }
    attachment.name = name + "-geometry"
    attachment.lifetime = .keepAlways
    add(attachment)
  }

  private func finite(_ frame: CGRect) -> Bool {
    [frame.minX, frame.minY, frame.width, frame.height, frame.maxX, frame.maxY].allSatisfy(\.isFinite)
  }
  private func rect(_ frame: CGRect) -> [CGFloat] {
    [frame.minX, frame.minY, frame.width, frame.height]
  }
}
