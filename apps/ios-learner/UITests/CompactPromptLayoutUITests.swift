import XCTest

// Initial ready controls must fit before scrolling or starting any media action.
final class CompactPromptLayoutUITests: XCTestCase {
  @MainActor
  func testInitialBallReadyControlFitsWithoutScrolling() {
    continueAfterFailure = false
    let app = launchOrdinary()
    defer { app.terminate() }
    XCTAssertTrue(app.buttons["cadence.start"].waitForExistence(timeout: 5))
    app.buttons["cadence.start"].tap()
    checkReady(app, word: "ball")
  }

  @MainActor
  func testSearchedSymbolAndLongWordReadyControlsFitWithoutScrolling() {
    continueAfterFailure = false
    // Treasure is the real sparkles fallback; television has an existing emoji.
    for word in ["treasure", "television"] {
      let app = launchOrdinary()
      app.selectPracticeTab("Sounds")
      app.buttons["cadence.search.open"].tap()
      let field = app.textFields["cadence.search.field"]
      XCTAssertTrue(field.waitForExistence(timeout: 3))
      field.tap()
      field.typeText(word + "\n")
      let resultLabel = word == "treasure" ? "treasure, ZH · treasure," : word + ","
      let result = app.buttons.matching(NSPredicate(
        format: "identifier BEGINSWITH %@ AND label BEGINSWITH %@",
        "cadence.search.result.", resultLabel
      )).firstMatch
      XCTAssertTrue(result.waitForExistence(timeout: 3))
      XCTAssertTrue(result.isHittable)
      result.tap()
      checkReady(app, word: word)
      app.terminate()
    }
  }

  @MainActor
  private func launchOrdinary() -> XCUIApplication {
    let app = XCUIApplication()
    app.launchArguments = ["-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryL"]
    app.launch()
    waitForPracticeSystemBannerToClear()
    return app
  }

  @MainActor
  private func checkReady(_ app: XCUIApplication, word: String) {
    let record = app.buttons["cadence.record"]
    XCTAssertTrue(record.waitForExistence(timeout: 3))
    waitForPracticeSystemBannerToClear()
    // Capture before any geometry assertion so failures retain their actual initial pixels.
    let screen = XCTAttachment(screenshot: app.screenshot())
    screen.name = "initial-ready-" + word
    screen.lifetime = .keepAlways
    add(screen)
    let tree = XCTAttachment(string: app.debugDescription)
    tree.name = "initial-ready-" + word + "-accessibility"
    tree.lifetime = .keepAlways
    add(tree)

    let viewport = app.scrollViews.firstMatch.frame.intersection(app.windows.firstMatch.frame)
    XCTAssertFalse(viewport.isNull)
    XCTAssertFalse(viewport.isEmpty)
    XCTAssertEqual(app.staticTexts["cadence.word"].label, word)
    XCTAssertEqual(record.label, "Record")
    XCTAssertTrue(record.isEnabled)
    for control in [record, app.buttons["cadence.close"], app.buttons["cadence.hear-word"]] {
      XCTAssertTrue(control.exists)
      XCTAssertTrue(control.isHittable)
      XCTAssertTrue(viewport.contains(control.frame), "\(control.identifier): \(control.frame) in \(viewport)")
      XCTAssertGreaterThanOrEqual(control.frame.height, 44)
    }
    let progress = app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH %@", "Word 1 of ")).firstMatch
    XCTAssertTrue(progress.exists)
    XCTAssertTrue(viewport.contains(progress.frame))
    // SwiftUI may merge the caption into its button. Never invent a separate caption frame.
    let caption = record.staticTexts["Record"]
    if caption.exists {
      XCTAssertTrue(viewport.contains(caption.frame))
    }
    let geometry = XCTAttachment(string:
      "AX viewport=\(viewport) record=\(record.frame) captionSeparate=\(caption.exists). " +
      "Review screenshot for the complete circle, caption glyphs and bottom safe-area clearance.")
    geometry.name = "initial-ready-" + word + "-geometry"
    geometry.lifetime = .keepAlways
    add(geometry)
    XCTAssertFalse(app.buttons["cadence.stop"].exists)
    XCTAssertFalse(app.buttons["cadence.replay"].exists)
    app.buttons["cadence.close"].tap()
  }
}
