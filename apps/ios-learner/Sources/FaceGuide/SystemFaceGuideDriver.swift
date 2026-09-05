@preconcurrency import ARKit
@preconcurrency import AVFoundation
import Foundation
import SceneKit
import UIKit

@MainActor
final class SystemFaceGuideHardware: FaceGuideHardware {
  var isSupported: Bool { SystemFaceGuideDriver.trueDepthFormat() != nil }

  var permission: FaceGuidePermission {
    switch AVCaptureDevice.authorizationStatus(for: .video) {
    case .authorized: .authorized
    case .notDetermined: .notDetermined
    default: .denied
    }
  }

  func requestPermission(completion: @escaping @MainActor (Bool) -> Void) {
    AVCaptureDevice.requestAccess(for: .video) { granted in
      Task { @MainActor in completion(granted) }
    }
  }

  func makeDriver() -> any FaceGuideDriver { SystemFaceGuideDriver() }
}

/// ARKit face tracking rendered by ARSCNView: the real front camera plus ARKit's own face
/// mesh. No audio, frame export, files or network. Construction is inert.
@MainActor
final class SystemFaceGuideDriver: FaceGuideDriver {
  private enum Failure: Error { case unsupported, meshUnavailable, teardownUnconfirmed }
  private var sceneView: ARSCNView?
  private var delegate: FaceGuideSessionDelegate?

  var surface: UIView? { sceneView }

  /// ARFaceTrackingConfiguration.isSupported alone does not prove a TrueDepth camera.
  static func trueDepthFormat() -> ARConfiguration.VideoFormat? {
    #if targetEnvironment(simulator)
      return nil
    #else
      guard ARFaceTrackingConfiguration.isSupported else { return nil }
      return ARFaceTrackingConfiguration.supportedVideoFormats.first {
        $0.captureDeviceType == .builtInTrueDepthCamera
      }
    #endif
  }

  func start(events: @escaping @MainActor (FaceGuideEvent) -> Void) throws {
    guard let format = Self.trueDepthFormat() else { throw Failure.unsupported }
    let sceneView = ARSCNView(frame: .zero)
    self.sceneView = sceneView  // Retain partial resources before any fallible step.
    sceneView.scene = SCNScene()
    sceneView.automaticallyUpdatesLighting = false
    sceneView.backgroundColor = .black
    sceneView.isAccessibilityElement = false
    guard let device = sceneView.device,
      let geometry = ARSCNFaceGeometry(device: device, fillMesh: false)
    else { throw Failure.meshUnavailable }
    if let material = geometry.firstMaterial {
      material.fillMode = .lines
      material.lightingModel = .constant
      material.diffuse.contents = UIColor(red: 0.42, green: 0.85, blue: 1, alpha: 1)
      material.transparency = 0.8
    }
    let delegate = FaceGuideSessionDelegate(geometry: geometry, events: events)
    self.delegate = delegate
    sceneView.scene.rootNode.addChildNode(delegate.faceNode)

    let configuration = ARFaceTrackingConfiguration()
    configuration.videoFormat = format
    configuration.maximumNumberOfTrackedFaces = 1
    configuration.providesAudioData = false
    configuration.isLightEstimationEnabled = false
    // Main delegate queue: the delegate updates its own SceneKit node and forwards scalars
    // synchronously, so no ARFrame or ARKit object leaves this thread.
    sceneView.session.delegateQueue = .main
    sceneView.session.delegate = delegate
    sceneView.session.run(configuration, options: [.resetTracking, .removeExistingAnchors])
  }

  func stop() throws {
    let delegate = delegate
    delegate?.detach()
    if let sceneView {
      sceneView.session.pause()
      sceneView.session.delegate = nil
      sceneView.removeFromSuperview()
      guard sceneView.session.delegate == nil, sceneView.superview == nil,
        delegate?.faceNode.parent == nil
      else { throw Failure.teardownUnconfirmed }
    }
    self.delegate = nil
    sceneView = nil
  }
}

/// Runs on the main delegate queue chosen by the driver. Owns the mesh node and sends only
/// Sendable scalar samples to the model.
private final class FaceGuideSessionDelegate: NSObject, ARSessionDelegate {
  let faceNode: SCNNode
  private let geometry: ARSCNFaceGeometry
  private var events: (@MainActor (FaceGuideEvent) -> Void)?

  init(geometry: ARSCNFaceGeometry, events: @escaping @MainActor (FaceGuideEvent) -> Void) {
    let node = SCNNode(geometry: geometry)
    node.isHidden = true
    faceNode = node
    self.geometry = geometry
    self.events = events
    super.init()
  }

  func detach() {
    events = nil
    faceNode.isHidden = true
    faceNode.removeFromParentNode()
  }

  func session(_ session: ARSession, didUpdate frame: ARFrame) {
    guard events != nil else { return }
    let face = frame.anchors.lazy.compactMap { $0 as? ARFaceAnchor }.first { $0.isTracked }
    if let face {
      geometry.update(from: face.geometry)
      faceNode.simdTransform = face.transform
      faceNode.isHidden = false
    } else {
      // Never leave a stale mesh over the camera after the face is lost.
      faceNode.isHidden = true
    }
    send(
      .frame(
        FaceGuideFrame(
          timestamp: frame.timestamp, faceTracked: face != nil,
          depthCaptured: frame.capturedDepthData != nil,
          jawOpen: face?.blendShapes[.jawOpen]?.floatValue,
          mouthPucker: face?.blendShapes[.mouthPucker]?.floatValue)))
  }

  func sessionWasInterrupted(_ session: ARSession) { send(.interrupted) }

  func session(_ session: ARSession, didFailWithError error: any Error) { send(.failed) }

  private func send(_ event: FaceGuideEvent) {
    guard let events else { return }
    MainActor.assumeIsolated { events(event) }
  }
}
