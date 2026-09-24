import Foundation
import XCTest

@testable import CadenceLearner

final class WhisperResourcePathTests: XCTestCase {
  func testEnumerationNamesHandleRelativeURLsAndDirectoryAliases() throws {
    let manager = FileManager.default
    let directory = manager.temporaryDirectory.appendingPathComponent(
      UUID().uuidString, isDirectory: true)
    let root = directory.appendingPathComponent("resources", isDirectory: true)
    let alias = directory.appendingPathComponent("alias", isDirectory: true)
    try manager.createDirectory(
      at: root.appendingPathComponent("weights"), withIntermediateDirectories: true)
    defer { try? manager.removeItem(at: directory) }
    try manager.createSymbolicLink(at: alias, withDestinationURL: root)
    let file = root.appendingPathComponent("weights/weight.bin")
    try Data([1, 2, 3]).write(to: file)
    let relative = try XCTUnwrap(URL(string: "weights/weight.bin", relativeTo: alias))
    XCTAssertEqual(
      WhisperResourceAdmission.relativeResourcePath(relative, under: root), "weights/weight.bin")
    XCTAssertEqual(
      WhisperResourceAdmission.relativeResourcePath(file, under: alias), "weights/weight.bin")
    XCTAssertNil(WhisperResourceAdmission.relativeResourcePath(root, under: root))
    XCTAssertNil(
      WhisperResourceAdmission.relativeResourcePath(
        directory.appendingPathComponent("resources-other/file"), under: root))
    XCTAssertNil(
      WhisperResourceAdmission.relativeResourcePath(
        directory.appendingPathComponent("outside"), under: root))
  }
}
