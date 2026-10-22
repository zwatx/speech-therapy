@preconcurrency import AVFoundation
import Foundation
import ImageIO
import Vision

enum VisualCaptureMonitorError: LocalizedError, Equatable {
  case cameraUnavailable
  case cameraConfigurationFailed
  case landmarkExtractionFailed

  var errorDescription: String? {
    switch self {
    case .cameraUnavailable:
      "The front camera is not available on this device."
    case .cameraConfigurationFailed:
      "The camera could not start. Nothing was recorded."
    case .landmarkExtractionFailed:
      "Face framing could not be checked. Practice can continue without the camera."
    }
  }
}

protocol VisualCaptureMonitoring: AnyObject, Sendable {
  var previewSession: AVCaptureSession? { get }
  func requestPermission() async -> Bool
  func start(
    onUpdate: @escaping @Sendable (Result<VisualQualitySnapshot, Error>) -> Void
  ) async throws
  func stop()
}

final class SystemVisualCaptureMonitor: VisualCaptureMonitoring, @unchecked Sendable {
  private let controller: CameraSessionController

  var previewSession: AVCaptureSession? { controller.session }

  init(
    extractor: any FaceLandmarkExtracting = VisionFaceLandmarkExtractor(),
    assessor: VisualCaptureQualityAssessor = VisualCaptureQualityAssessor()
  ) {
    controller = CameraSessionController(extractor: extractor, assessor: assessor)
  }

  func requestPermission() async -> Bool {
    switch AVCaptureDevice.authorizationStatus(for: .video) {
    case .authorized:
      true
    case .notDetermined:
      await AVCaptureDevice.requestAccess(for: .video)
    case .denied, .restricted:
      false
    @unknown default:
      false
    }
  }

  func start(
    onUpdate: @escaping @Sendable (Result<VisualQualitySnapshot, Error>) -> Void
  ) async throws {
    try await controller.start(onUpdate: onUpdate)
  }

  func stop() {
    controller.stop()
  }
}

protocol FaceLandmarkExtracting: Sendable {
  func observations(from sampleBuffer: CMSampleBuffer) throws -> [VisualFaceObservation]
}

struct VisionFaceLandmarkExtractor: FaceLandmarkExtracting {
  func observations(from sampleBuffer: CMSampleBuffer) throws -> [VisualFaceObservation] {
    guard let pixelBuffer = CMSampleBufferGetImageBuffer(sampleBuffer) else {
      throw VisualCaptureMonitorError.landmarkExtractionFailed
    }
    let request = VNDetectFaceLandmarksRequest()
    let handler = VNImageRequestHandler(
      cvPixelBuffer: pixelBuffer,
      orientation: .leftMirrored,
      options: [:]
    )
    do {
      try handler.perform([request])
    } catch {
      throw VisualCaptureMonitorError.landmarkExtractionFailed
    }
    return (request.results ?? []).map { face in
      VisualFaceObservation(
        bounds: NormalizedVisualRect(
          x: face.boundingBox.origin.x,
          y: face.boundingBox.origin.y,
          width: face.boundingBox.width,
          height: face.boundingBox.height
        ),
        outerLip: points(from: face.landmarks?.outerLips),
        innerLip: points(from: face.landmarks?.innerLips),
        yawRadians: face.yaw?.doubleValue,
        rollRadians: face.roll?.doubleValue
      )
    }
  }

  private func points(
    from region: VNFaceLandmarkRegion2D?
  ) -> [NormalizedVisualPoint] {
    guard let region else { return [] }
    let points = region.normalizedPoints
    return (0..<region.pointCount).map { index in
      NormalizedVisualPoint(
        x: points[index].x,
        y: points[index].y
      )
    }
  }
}

private final class CameraFrameProcessor: NSObject,
  AVCaptureVideoDataOutputSampleBufferDelegate, @unchecked Sendable
{
  private let extractor: any FaceLandmarkExtracting
  private let assessor: VisualCaptureQualityAssessor
  private let lock = NSLock()
  private var update: (@Sendable (Result<VisualQualitySnapshot, Error>) -> Void)?
  private var lastProcessedTime = -Double.infinity

  init(
    extractor: any FaceLandmarkExtracting,
    assessor: VisualCaptureQualityAssessor
  ) {
    self.extractor = extractor
    self.assessor = assessor
  }

  func setUpdate(
    _ update: (@Sendable (Result<VisualQualitySnapshot, Error>) -> Void)?
  ) {
    lock.withLock { self.update = update }
  }

  func captureOutput(
    _ output: AVCaptureOutput,
    didOutput sampleBuffer: CMSampleBuffer,
    from connection: AVCaptureConnection
  ) {
    let time = CMSampleBufferGetPresentationTimeStamp(sampleBuffer).seconds
    guard time.isFinite, time - lastProcessedTime >= 0.1 else { return }
    lastProcessedTime = time
    let startedAt = DispatchTime.now().uptimeNanoseconds
    let result: Result<VisualQualitySnapshot, Error>
    do {
      let snapshot = assessor.assess(try extractor.observations(from: sampleBuffer))
      let finishedAt = DispatchTime.now().uptimeNanoseconds
      let latency = Double(finishedAt - startedAt) / 1_000_000
      result = .success(snapshot.recordingProcessingLatency(latency))
    } catch {
      result = .failure(error)
    }
    let callback = lock.withLock { update }
    callback?(result)
  }
}

private final class CameraSessionController: @unchecked Sendable {
  let session = AVCaptureSession()

  private let queue = DispatchQueue(label: "com.cadence.visual-capture")
  private let output = AVCaptureVideoDataOutput()
  private let processor: CameraFrameProcessor
  private var isConfigured = false

  init(
    extractor: any FaceLandmarkExtracting,
    assessor: VisualCaptureQualityAssessor
  ) {
    processor = CameraFrameProcessor(extractor: extractor, assessor: assessor)
  }

  func start(
    onUpdate: @escaping @Sendable (Result<VisualQualitySnapshot, Error>) -> Void
  ) async throws {
    processor.setUpdate(onUpdate)
    try await withCheckedThrowingContinuation { continuation in
      queue.async { [self] in
        do {
          if !isConfigured { try configure() }
          if !session.isRunning { session.startRunning() }
          continuation.resume()
        } catch {
          processor.setUpdate(nil)
          continuation.resume(throwing: error)
        }
      }
    }
  }

  func stop() {
    processor.setUpdate(nil)
    queue.async { [self] in
      if session.isRunning { session.stopRunning() }
    }
  }

  private func configure() throws {
    guard
      let camera = AVCaptureDevice.default(
        .builtInWideAngleCamera,
        for: .video,
        position: .front
      )
    else {
      throw VisualCaptureMonitorError.cameraUnavailable
    }
    let input: AVCaptureDeviceInput
    do {
      input = try AVCaptureDeviceInput(device: camera)
    } catch {
      throw VisualCaptureMonitorError.cameraConfigurationFailed
    }

    session.beginConfiguration()
    defer { session.commitConfiguration() }
    session.sessionPreset = .vga640x480
    guard session.canAddInput(input), session.canAddOutput(output) else {
      throw VisualCaptureMonitorError.cameraConfigurationFailed
    }
    session.addInput(input)
    output.alwaysDiscardsLateVideoFrames = true
    output.videoSettings = [
      kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA
    ]
    output.setSampleBufferDelegate(processor, queue: queue)
    session.addOutput(output)
    isConfigured = true
  }
}

extension NSLock {
  fileprivate func withLock<T>(_ body: () -> T) -> T {
    lock()
    defer { unlock() }
    return body()
  }
}
