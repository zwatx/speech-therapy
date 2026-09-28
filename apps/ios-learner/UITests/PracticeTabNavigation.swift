import XCTest

extension XCUIApplication {
  @MainActor
  func selectPracticeTab(_ title: String, file: StaticString = #filePath, line: UInt = #line) {
    let tab = tabBars.buttons[title]
    XCTAssertTrue(tab.waitForExistence(timeout: 5), title, file: file, line: line)
    XCTAssertTrue(tab.isHittable, title, file: file, line: line)
    tab.tap()
    XCTAssertTrue(tab.isSelected, title, file: file, line: line)
  }
}

extension XCTestCase {
  @MainActor
  func capturePracticeTour(_ name: String, _ app: XCUIApplication) {
    guard let directory = ProcessInfo.processInfo.environment["CADENCE_TOUR_DIR"] else { return }
    let shot = app.screenshot()
    let attachment = XCTAttachment(screenshot: shot)
    attachment.name = name
    attachment.lifetime = .keepAlways
    add(attachment)
    do {
      let folder = URL(fileURLWithPath: directory, isDirectory: true)
      try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
      try shot.pngRepresentation.write(to: folder.appendingPathComponent(name + ".png"))
    } catch {
      XCTFail("Could not save review screenshot: \(error)")
    }
  }
}

extension XCTestCase {
  @MainActor
  func capturePracticeFailure(_ app: XCUIApplication) {
    let stem = "failure-" + name.components(separatedBy: CharacterSet.alphanumerics.inverted)
      .filter { !$0.isEmpty }.joined(separator: "-")
    let tree = app.debugDescription
    let attachment = XCTAttachment(string: tree)
    attachment.name = stem + "-accessibility"
    attachment.lifetime = .keepAlways
    add(attachment)
    guard app.state == .runningForeground else { return }
    let shot = app.screenshot()
    let screenshot = XCTAttachment(screenshot: shot)
    screenshot.name = stem
    screenshot.lifetime = .keepAlways
    add(screenshot)
    guard let directory = ProcessInfo.processInfo.environment["CADENCE_FAILURE_DIR"] else { return }
    do {
      let folder = URL(fileURLWithPath: directory, isDirectory: true)
      try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
      try shot.pngRepresentation.write(to: folder.appendingPathComponent(stem + ".png"))
      try tree.write(to: folder.appendingPathComponent(stem + ".txt"), atomically: true, encoding: .utf8)
    } catch {
      XCTFail("Could not save failure evidence: \(error)")
    }
  }
}

// A first-launch simulator notification can cover app text without belonging to its AX tree.
// Wait for the observed banner to leave; never dismiss it or exclude app audit findings.
extension XCTestCase {
  @MainActor
  func waitForPracticeSystemBannerToClear(file: StaticString = #filePath, line: UInt = #line) {
    let springboard = XCUIApplication(bundleIdentifier: "com.apple.springboard")
    let banner = springboard.descendants(matching: .any)["NotificationShortLookView"].firstMatch
    let gone = XCTNSPredicateExpectation(
      predicate: NSPredicate(format: "exists == false"), object: banner)
    XCTAssertEqual(XCTWaiter.wait(for: [gone], timeout: 20), .completed,
                   "System notification still covers the app", file: file, line: line)
  }
}
