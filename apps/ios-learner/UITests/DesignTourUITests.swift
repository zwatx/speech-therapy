import XCTest

#if !DEBUG && targetEnvironment(simulator)
  /// Visual review tour of the main screens. Navigation only: no Record, Hear, check,
  /// mirror, save or clear action. Set TEST_RUNNER_CADENCE_TOUR_DIR to also write PNGs.
  @MainActor
  final class DesignTourUITests: XCTestCase {
    func testTourMainScreens() throws {
      let app = XCUIApplication()
      defer { app.terminate() }
      app.launch()

      XCTAssertTrue(app.buttons["cadence.start"].waitForExistence(timeout: 10))
      capture("01-today", app)

      app.tabBars.buttons["Sounds"].tap()
      XCTAssertTrue(app.buttons["cadence.search.open"].waitForExistence(timeout: 5))
      capture("02-sounds", app)

      app.buttons["cadence.sound.r"].firstMatch.tap()
      XCTAssertTrue(app.navigationBars["Words to practice"].waitForExistence(timeout: 5))
      capture("03-sound-library", app)
      app.navigationBars.buttons.element(boundBy: 0).tap()

      app.buttons["cadence.search.open"].tap()
      XCTAssertTrue(app.navigationBars["Search words"].waitForExistence(timeout: 5))
      capture("04-search", app)
      app.navigationBars.buttons.element(boundBy: 0).tap()

      app.tabBars.buttons["Progress"].tap()
      XCTAssertTrue(app.staticTexts["cadence.progress.headline"].waitForExistence(timeout: 5))
      capture("05-progress", app)

      app.tabBars.buttons["Today"].tap()
      app.buttons["cadence.start"].tap()
      XCTAssertTrue(app.staticTexts["cadence.word"].waitForExistence(timeout: 10))
      capture("06-practice-ready", app)
      app.buttons["cadence.close"].tap()
      XCTAssertTrue(app.buttons["cadence.start"].waitForExistence(timeout: 10))

      app.buttons["About practice and privacy"].tap()
      XCTAssertTrue(app.staticTexts["About practice"].waitForExistence(timeout: 5))
      capture("07-grown-ups", app)
    }

    private func capture(_ name: String, _ app: XCUIApplication) {
      let shot = app.screenshot()
      let attachment = XCTAttachment(screenshot: shot)
      attachment.name = name
      attachment.lifetime = .keepAlways
      add(attachment)
      if let dir = ProcessInfo.processInfo.environment["CADENCE_TOUR_DIR"] {
        try? shot.pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent(name + ".png"))
      }
    }
  }
#endif
