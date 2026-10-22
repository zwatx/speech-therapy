@preconcurrency import AVFoundation
import CoreImage
import XCTest
@testable import VisualSpeechCore

final class VideoGeometryTests: XCTestCase {
    func testDisplayTransformsAgainstAVFoundationRenderingOfRealSyntheticMovies() async throws {
        let width = 64.0, height = 48.0
        let transforms: [(String, CGAffineTransform)] = [
            ("identity", .identity),
            ("90", CGAffineTransform(a: 0, b: 1, c: -1, d: 0, tx: height, ty: 0)),
            ("180", CGAffineTransform(a: -1, b: 0, c: 0, d: -1, tx: width, ty: height)),
            ("270", CGAffineTransform(a: 0, b: -1, c: 1, d: 0, tx: 0, ty: width)),
            ("horizontal-mirror", CGAffineTransform(a: -1, b: 0, c: 0, d: 1, tx: width, ty: 0)),
            ("vertical-mirror", CGAffineTransform(a: 1, b: 0, c: 0, d: -1, tx: 0, ty: height)),
            ("90-mirror", CGAffineTransform(a: 0, b: 1, c: 1, d: 0, tx: 0, ty: 0)),
            ("270-mirror", CGAffineTransform(a: 0, b: -1, c: -1, d: 0, tx: height, ty: width))
        ]
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: folder) }
        let context = CIContext()
        var oldPathMismatches = 0
        for (name, transform) in transforms {
            let url = folder.appendingPathComponent("\(name).mov")
            try await writeCornerMovie(url: url, transform: transform, context: context)
            let asset = AVURLAsset(url: url)
            let tracks = try await asset.loadTracks(withMediaType: .video)
            let track = try XCTUnwrap(tracks.first)
            let actualTransform = try await track.load(.preferredTransform)
            let reader = try AVAssetReader(asset: asset)
            let output = AVAssetReaderTrackOutput(track: track, outputSettings: [
                kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA
            ])
            reader.add(output)
            XCTAssertTrue(reader.startReading())
            let sample = try XCTUnwrap(output.copyNextSampleBuffer())
            let buffer = try XCTUnwrap(CMSampleBufferGetImageBuffer(sample))
            let source = CIImage(cvPixelBuffer: buffer)
            // Independent native AVFoundation reference; no hand-reimplemented transform.
            let generator = AVAssetImageGenerator(asset: asset)
            generator.appliesPreferredTrackTransform = true
            let reference = try await generator.image(at: .zero).image
            let expected = cornerMeans(CIImage(cgImage: reference), context: context)
            let converted = displayOrientedImage(source, transform: actualTransform)
            let actual = cornerMeans(converted, context: context)
            XCTAssertEqual(Int(converted.extent.width), reference.width, name)
            XCTAssertEqual(Int(converted.extent.height), reference.height, name)
            XCTAssertEqual(brightest(actual), brightest(expected), name)
            XCTAssertGreaterThan(actual.max()!, 180, name)
            XCTAssertGreaterThan(expected.max()!, 180, name)
            // Reproduce the former bug independently: the old direct CI transform
            // must disagree on the quarter-turn clips, proving regression sensitivity.
            let old = cornerMeans(source.transformed(by: actualTransform), context: context)
            if brightest(old) != brightest(expected) { oldPathMismatches += 1 }
            reader.cancelReading()
        }
        XCTAssertEqual(oldPathMismatches, 4, "90/270 degree transforms and their mirrored variants")
    }

    private func writeCornerMovie(url: URL, transform: CGAffineTransform, context: CIContext) async throws {
        let writer = try AVAssetWriter(outputURL: url, fileType: .mov)
        let input = AVAssetWriterInput(mediaType: .video, outputSettings: [
            AVVideoCodecKey: AVVideoCodecType.h264, AVVideoWidthKey: 64, AVVideoHeightKey: 48
        ])
        input.transform = transform
        let adaptor = AVAssetWriterInputPixelBufferAdaptor(assetWriterInput: input,
            sourcePixelBufferAttributes: [kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA,
                                          kCVPixelBufferWidthKey as String: 64,
                                          kCVPixelBufferHeightKey as String: 48])
        writer.add(input)
        XCTAssertTrue(writer.startWriting())
        writer.startSession(atSourceTime: .zero)
        var buffer: CVPixelBuffer?
        XCTAssertEqual(CVPixelBufferCreate(kCFAllocatorDefault, 64, 48, kCVPixelFormatType_32BGRA,
            [kCVPixelBufferIOSurfacePropertiesKey as String: [:]] as CFDictionary, &buffer), kCVReturnSuccess)
        let pixels = try XCTUnwrap(buffer)
        let black = CIImage(color: .black).cropped(to: CGRect(x: 0, y: 0, width: 64, height: 48))
        let white = CIImage(color: .white).cropped(to: CGRect(x: 0, y: 32, width: 24, height: 16))
        context.render(white.composited(over: black), to: pixels)
        // Bounded wait for the real encoder, not a mocked rendering result.
        for _ in 0..<100 where !input.isReadyForMoreMediaData {
            try await Task.sleep(for: .milliseconds(10))
        }
        XCTAssertTrue(input.isReadyForMoreMediaData)
        XCTAssertTrue(adaptor.append(pixels, withPresentationTime: .zero))
        writer.endSession(atSourceTime: CMTime(value: 1, timescale: 30))
        input.markAsFinished()
        await writer.finishWriting()
        XCTAssertEqual(writer.status, .completed, String(describing: writer.error))
    }

    /// Sample interior corners in CI's y-up space to avoid compression boundary pixels.
    private func cornerMeans(_ image: CIImage, context: CIContext) -> [Double] {
        let extent = image.extent
        return [(0.1, 0.1), (0.9, 0.1), (0.1, 0.9), (0.9, 0.9)].map { x, y in
            var bytes = [UInt8](repeating: 0, count: 4 * 4 * 4)
            let bounds = CGRect(x: extent.minX + extent.width * x - 2,
                                y: extent.minY + extent.height * y - 2, width: 4, height: 4)
            context.render(image, toBitmap: &bytes, rowBytes: 16, bounds: bounds,
                           format: .RGBA8, colorSpace: CGColorSpaceCreateDeviceRGB())
            return stride(from: 0, to: bytes.count, by: 4).map { Double(bytes[$0]) }.reduce(0, +) / 16
        }
    }
    private func brightest(_ values: [Double]) -> Int { values.firstIndex(of: values.max()!)! }

    func testRejectsInvalidTimingAndTransformBeforeSerialization() {
        for bad in [Double.nan, .infinity, -.infinity] {
            XCTAssertThrowsError(try validateVideoGeometry(duration: 1, trackStart: bad,
                                                           trackDuration: 1, transform: .identity))
            XCTAssertThrowsError(try validateVideoGeometry(duration: 1, trackStart: 0,
                                                           trackDuration: bad, transform: .identity))
        }
        XCTAssertThrowsError(try validateVideoGeometry(duration: 1, trackStart: 0,
            trackDuration: 1, transform: CGAffineTransform(scaleX: 0, y: 1)))
        XCTAssertNoThrow(try validateVideoGeometry(duration: 1, trackStart: -0.1,
                                                   trackDuration: 1, transform: .identity))
    }

    func testSquareAndAnamorphicFormatDescriptions() throws {
        func format(horizontal: Int?, vertical: Int?) throws -> CMFormatDescription {
            var value: CMVideoFormatDescription?
            let extensions: [String: Any] = if let horizontal, let vertical {
                [kCMFormatDescriptionExtension_PixelAspectRatio as String: [
                    kCMFormatDescriptionKey_PixelAspectRatioHorizontalSpacing as String: horizontal,
                    kCMFormatDescriptionKey_PixelAspectRatioVerticalSpacing as String: vertical]]
            } else { [:] }
            XCTAssertEqual(CMVideoFormatDescriptionCreate(allocator: kCFAllocatorDefault,
                codecType: kCMVideoCodecType_H264, width: 64, height: 48,
                extensions: extensions as CFDictionary, formatDescriptionOut: &value), noErr)
            return try XCTUnwrap(value)
        }
        XCTAssertNoThrow(try requireSquarePixels(format(horizontal: nil, vertical: nil)))
        XCTAssertNoThrow(try requireSquarePixels(format(horizontal: 1, vertical: 1)))
        XCTAssertNoThrow(try requireSquarePixels(format(horizontal: 4, vertical: 4)))
        XCTAssertThrowsError(try requireSquarePixels(format(horizontal: 4, vertical: 3)))
        XCTAssertThrowsError(try requireSquarePixels(format(horizontal: 0, vertical: 0)))
    }
}
