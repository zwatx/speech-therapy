import CoreImage
import CoreMedia
import Foundation

/// AVFoundation display matrices use y-down track coordinates. Core Image is y-up.
/// Flip into track space, apply its transform, then return to Core Image space.
/// The caller crops the resulting extent, so translations need not start at zero.
public func displayOrientedImage(_ image: CIImage, transform: CGAffineTransform) -> CIImage {
    let flip = CGAffineTransform(scaleX: 1, y: -1)
    return image.transformed(by: flip).transformed(by: transform).transformed(by: flip)
}

public func validateVideoGeometry(duration: Double, trackStart: Double, trackDuration: Double,
                                  transform: CGAffineTransform) throws {
    guard duration.isFinite, duration > 0, trackStart.isFinite,
          trackDuration.isFinite, trackDuration > 0,
          [transform.a, transform.b, transform.c, transform.d, transform.tx, transform.ty].allSatisfy(\.isFinite),
          abs(transform.a * transform.d - transform.b * transform.c) > 1e-10 else {
        throw ResearchError.invalid("Video timing and display transform must be finite and nondegenerate")
    }
}

/// Features use pixel distances. Reject anamorphic inputs rather than silently skewing them.
public func requireSquarePixels(_ format: CMFormatDescription) throws {
    guard let value = CMFormatDescriptionGetExtension(format, extensionKey: kCMFormatDescriptionExtension_PixelAspectRatio) else {
        return // An absent pixel-aspect extension denotes square pixels.
    }
    guard let ratio = value as? [String: Any],
          let horizontal = ratio[kCMFormatDescriptionKey_PixelAspectRatioHorizontalSpacing as String] as? NSNumber,
          let vertical = ratio[kCMFormatDescriptionKey_PixelAspectRatioVerticalSpacing as String] as? NSNumber,
          horizontal.doubleValue.isFinite, vertical.doubleValue.isFinite,
          horizontal.doubleValue > 0, horizontal.doubleValue == vertical.doubleValue else {
        throw ResearchError.invalid("Non-square or invalid pixel aspect ratio is unsupported")
    }
}
