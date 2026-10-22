#if DEBUG
  import XCTest

  @testable import CadenceLearner

  @MainActor
  final class MouthMovementLabTests: XCTestCase {
    func testUnsupportedHardwareNeverRequestsPermissionOrStarts() async {
      let tracker = FakeMouthMovementTracker(supported: false)
      let model = MouthMovementLabModel(tracker: tracker)

      await model.start()

      XCTAssertEqual(model.state, .unavailable)
      XCTAssertEqual(tracker.permissionRequests, 0)
      XCTAssertEqual(tracker.starts, 0)
      XCTAssertNil(model.measurements)
    }

    func testDeniedPermissionNeverStartsCamera() async {
      let tracker = FakeMouthMovementTracker()
      tracker.permissionGranted = false
      let model = MouthMovementLabModel(tracker: tracker)

      await model.start()

      XCTAssertEqual(model.state, .denied)
      XCTAssertEqual(tracker.starts, 0)
      XCTAssertFalse(model.isRunning)
    }

    func testStoppingWhilePermissionIsPendingPreventsLateStart() async {
      let tracker = FakeMouthMovementTracker()
      tracker.delayPermission = true
      let model = MouthMovementLabModel(tracker: tracker)
      let request = Task { await model.start() }
      while tracker.permissionRequests == 0 { await Task.yield() }

      model.stop()
      tracker.permissionContinuation?.resume(returning: true)
      await request.value

      XCTAssertEqual(tracker.starts, 0)
      XCTAssertEqual(model.state, .idle)
      XCTAssertFalse(model.isRunning)
    }

    func testFaceTrackingWithoutTrueDepthStillWorksAndLossClearsReadings() async throws {
      let tracker = FakeMouthMovementTracker()
      let model = MouthMovementLabModel(tracker: tracker)
      await model.start()
      XCTAssertFalse(model.capabilities.hasTrueDepthCamera)

      tracker.callbacks.last?(.reading(try reading()))
      XCTAssertEqual(model.state, .tracking)
      XCTAssertNotNil(model.measurements)
      tracker.callbacks.last?(.noFace)
      XCTAssertEqual(model.state, .noFace)
      XCTAssertNil(model.measurements)
      tracker.callbacks.last?(.reading(try reading()))
      tracker.callbacks.last?(.multipleFaces)
      XCTAssertEqual(model.state, .multipleFaces)
      XCTAssertNil(model.measurements)
    }

    func testLateEventsFromPreviousRunCannotRestoreMeasurements() async throws {
      let tracker = FakeMouthMovementTracker()
      let model = MouthMovementLabModel(tracker: tracker)
      await model.start()
      let previousCallback = try XCTUnwrap(tracker.callbacks.last)
      model.stop()
      previousCallback(.reading(try reading()))
      XCTAssertEqual(model.state, .idle)
      XCTAssertNil(model.measurements)

      await model.start()
      previousCallback(.failed)
      previousCallback(.reading(try reading()))
      XCTAssertEqual(model.state, .noFace)
      XCTAssertTrue(model.isRunning)
      XCTAssertNil(model.measurements)
    }

    func testInterruptionAndFailureStopCaptureAndClearMeasurements() async throws {
      for event in [MouthMovementEvent.interrupted, .failed] {
        let tracker = FakeMouthMovementTracker()
        let model = MouthMovementLabModel(tracker: tracker)
        await model.start()
        tracker.callbacks.last?(.reading(try reading()))
        tracker.callbacks.last?(event)

        XCTAssertFalse(model.isRunning)
        XCTAssertNil(model.measurements)
        XCTAssertEqual(tracker.stops, 1)
        XCTAssertTrue(model.state == .interrupted || model.state == .failed)
      }
    }

    func testMissingOrInvalidMeasurementsAreNeverRenderedAsZero() {
      for value: Double? in [nil, .nan, .infinity, -0.1, 1.1] {
        XCTAssertNil(
          MouthMovementMeasurements(
            jawOpen: value, mouthClose: 0, mouthFunnel: 0, mouthPucker: 0
          ))
      }
      XCTAssertNotNil(
        MouthMovementMeasurements(
          jawOpen: 0, mouthClose: 1, mouthFunnel: 0.5, mouthPucker: 0.2
        ))
    }

    private func reading() throws -> MouthMovementMeasurements {
      try XCTUnwrap(
        MouthMovementMeasurements(
          jawOpen: 0.2, mouthClose: 0.3, mouthFunnel: 0.4, mouthPucker: 0.5
        ))
    }
  }

  @MainActor
  private final class FakeMouthMovementTracker: MouthMovementTracking {
    let capabilities: MouthMovementCapabilities
    var permissionGranted = true
    var delayPermission = false
    var permissionContinuation: CheckedContinuation<Bool, Never>?
    var permissionRequests = 0
    var starts = 0
    var stops = 0
    var callbacks: [@MainActor @Sendable (MouthMovementEvent) -> Void] = []

    init(supported: Bool = true) {
      capabilities = .init(supportsFaceTracking: supported, hasTrueDepthCamera: false)
    }

    func requestPermission() async -> Bool {
      permissionRequests += 1
      if delayPermission {
        return await withCheckedContinuation { permissionContinuation = $0 }
      }
      return permissionGranted
    }

    func start(onEvent: @escaping @MainActor @Sendable (MouthMovementEvent) -> Void) {
      starts += 1
      callbacks.append(onEvent)
    }

    func stop() { stops += 1 }
  }
#endif
