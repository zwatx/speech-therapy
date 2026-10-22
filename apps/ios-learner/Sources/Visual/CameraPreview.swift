@preconcurrency import AVFoundation
import SwiftUI
import UIKit

struct CameraPreview: UIViewRepresentable {
  let session: AVCaptureSession

  func makeUIView(context: Context) -> PreviewView {
    let view = PreviewView()
    view.previewLayer.session = session
    return view
  }

  func updateUIView(_ view: PreviewView, context: Context) {
    if view.previewLayer.session !== session {
      view.previewLayer.session = session
    }
  }
}

final class PreviewView: UIView {
  override class var layerClass: AnyClass { AVCaptureVideoPreviewLayer.self }

  var previewLayer: AVCaptureVideoPreviewLayer {
    layer as! AVCaptureVideoPreviewLayer
  }

  override init(frame: CGRect) {
    super.init(frame: frame)
    previewLayer.videoGravity = .resizeAspectFill
    isAccessibilityElement = false
  }

  override func layoutSubviews() {
    super.layoutSubviews()
    guard let connection = previewLayer.connection else { return }
    if connection.isVideoRotationAngleSupported(90) {
      connection.videoRotationAngle = 90
    }
  }

  @available(*, unavailable)
  required init?(coder: NSCoder) {
    fatalError("init(coder:) is unavailable")
  }
}
