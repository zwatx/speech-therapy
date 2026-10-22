@preconcurrency import AVFoundation
import Combine
import SwiftUI
import UIKit

/// The serial driver passes this reference only for a running, owned session. The main
/// actor binds its preview layer; configuration/start/stop stay on the worker queue.
final class PracticeMirrorCameraReference: @unchecked Sendable {
  let session: AVCaptureSession
  init(session: AVCaptureSession) { self.session = session }
}

enum PracticeMirrorPreviewSource: Sendable {
  case sample
  case camera(PracticeMirrorCameraReference)
}

/// Shared through the exact recovery runtime. No frames, files, scoring or second
/// resource-owner slot. Bookkeeping commits before synchronous observer publication.
@MainActor
final class PracticeMirrorPresentation: ObservableObject {
  // Combine's requirement is nonisolated. The reference is immutable; all sends
  // and committed presentation state remain MainActor-only.
  nonisolated(unsafe) let objectWillChange = ObservableObjectPublisher()
  private(set) var owner: PracticeMirrorOwner?
  private(set) var source: PracticeMirrorPreviewSource?
  private var eligibleOwner: PracticeMirrorOwner?
  private weak var previewView: PracticeMirrorPreviewView?
  private var previewOwner: PracticeMirrorOwner?

  func prepare(owner: PracticeMirrorOwner) {
    eligibleOwner = owner
    self.owner = nil
    source = nil
  }

  func install(owner: PracticeMirrorOwner, source: PracticeMirrorPreviewSource?) {
    guard eligibleOwner == owner else { return }
    self.owner = owner
    self.source = source
    objectWillChange.send()
  }

  func revoke(owner: PracticeMirrorOwner) {
    if previewOwner == owner {
      previewView?.previewLayer.session = nil
      previewView = nil
      previewOwner = nil
    }
    if eligibleOwner == owner { eligibleOwner = nil }
    guard self.owner == owner else { return }
    self.owner = nil
    source = nil
    objectWillChange.send()
  }

  fileprivate func bind(_ view: PracticeMirrorPreviewView, owner: PracticeMirrorOwner) {
    guard eligibleOwner == owner, self.owner == owner,
      case .camera(let reference) = source
    else {
      view.previewLayer.session = nil
      return
    }
    if previewView !== view { previewView?.previewLayer.session = nil }
    previewView = view
    previewOwner = owner
    view.previewLayer.session = reference.session
    view.setMirrorGeometry()
  }

  fileprivate func unbind(_ view: PracticeMirrorPreviewView) {
    view.previewLayer.session = nil
    if previewView === view {
      previewView = nil
      previewOwner = nil
    }
  }
}

struct PracticeMirrorCameraPreview: UIViewRepresentable {
  let presentation: PracticeMirrorPresentation
  let owner: PracticeMirrorOwner

  @MainActor final class Coordinator {
    let presentation: PracticeMirrorPresentation
    init(_ presentation: PracticeMirrorPresentation) { self.presentation = presentation }
  }

  func makeCoordinator() -> Coordinator { Coordinator(presentation) }

  func makeUIView(context: Context) -> PracticeMirrorPreviewView {
    let view = PracticeMirrorPreviewView()
    presentation.bind(view, owner: owner)
    return view
  }

  func updateUIView(_ view: PracticeMirrorPreviewView, context: Context) {
    presentation.bind(view, owner: owner)
  }

  static func dismantleUIView(_ view: PracticeMirrorPreviewView, coordinator: Coordinator) {
    coordinator.presentation.unbind(view)
  }
}

final class PracticeMirrorPreviewView: UIView {
  override class var layerClass: AnyClass { AVCaptureVideoPreviewLayer.self }
  var previewLayer: AVCaptureVideoPreviewLayer { layer as! AVCaptureVideoPreviewLayer }

  override init(frame: CGRect) {
    super.init(frame: frame)
    previewLayer.videoGravity = .resizeAspectFill
    isAccessibilityElement = false
  }

  override func layoutSubviews() {
    super.layoutSubviews()
    setMirrorGeometry()
  }

  func setMirrorGeometry() {
    guard let connection = previewLayer.connection else { return }
    if connection.isVideoRotationAngleSupported(90) { connection.videoRotationAngle = 90 }
    if connection.isVideoMirroringSupported {
      connection.automaticallyAdjustsVideoMirroring = false
      connection.isVideoMirrored = true
    }
  }

  @available(*, unavailable)
  required init?(coder: NSCoder) { fatalError("init(coder:) is unavailable") }
}
