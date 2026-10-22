@preconcurrency import AVFoundation
import CoreImage
import CryptoKit
import Foundation
import Vision
import VisualSpeechCore

private let usage = """
Offline research observations; no camera, network, diagnosis, or speech scoring.
visual-speech --input /local/video.mov --output /new/features.ndjson \
  --provenance /local/permission.json --audio-timebase /local/timebase.json [--fps 10]
An explicit audio clock is required even when the video contains an audio track.
The output contains per-frame facial geometry: treat it as sensitive research data.
"""

private func json(_ value: some Encodable) throws -> Any {
    try JSONSerialization.jsonObject(with: JSONEncoder().encode(value))
}
private func digest(_ url: URL) throws -> String {
    let handle = try FileHandle(forReadingFrom: url)
    defer { try? handle.close() }
    var hash = SHA256()
    while let chunk = try handle.read(upToCount: 1_048_576), !chunk.isEmpty { hash.update(data: chunk) }
    return hash.finalize().map { String(format: "%02x", $0) }.joined()
}
private func nullable(_ number: NSNumber?) -> Any {
    guard let number, number.doubleValue.isFinite else { return NSNull() }
    return number.doubleValue
}

@main
struct VisualSpeech {
    static func main() async {
        do { try await run() }
        catch {
            FileHandle.standardError.write(Data("visual-speech: \(error)\n".utf8))
            exit(1)
        }
    }

    static func run() async throws {
        let args = Array(CommandLine.arguments.dropFirst())
        if args == ["--help"] { print(usage); return }
        let allowed = Set(["--input", "--output", "--provenance", "--audio-timebase", "--fps"])
        guard args.count % 2 == 0 else { throw ResearchError.invalid(usage) }
        var options: [String: String] = [:]
        for index in stride(from: 0, to: args.count, by: 2) {
            guard allowed.contains(args[index]), options[args[index]] == nil else {
                throw ResearchError.invalid("Unknown or repeated argument: \(args[index])")
            }
            options[args[index]] = args[index + 1]
        }
        func path(_ key: String) throws -> URL {
            guard let path = options[key], !path.isEmpty, !path.contains("://") else {
                throw ResearchError.invalid("Required local path: \(key)")
            }
            return URL(fileURLWithPath: path).standardizedFileURL
        }
        let input = try path("--input"), output = try path("--output")
        let provenanceURL = try path("--provenance"), timebaseURL = try path("--audio-timebase")
        guard !FileManager.default.fileExists(atPath: output.path) else {
            throw ResearchError.invalid("Output exists; choose a new path")
        }
        let provenanceData = try Data(contentsOf: provenanceURL)
        let timebaseData = try Data(contentsOf: timebaseURL)
        let provenance = try JSONDecoder().decode(Provenance.self, from: provenanceData)
        let clock = try JSONDecoder().decode(AudioTimebase.self, from: timebaseData)
        try provenance.validate(); try clock.validate()
        guard let fps = Double(options["--fps"] ?? "10") else {
            throw ResearchError.invalid("Invalid fps")
        }
        var sampler = try FrameSampler(fps: fps)
        let sourceHash = try digest(input)
        // A single hashed local file must not resolve unrecorded external media.
        let asset = AVURLAsset(url: input, options: [
            AVURLAssetReferenceRestrictionsKey: AVAssetReferenceRestrictions.forbidAll.rawValue
        ])
        let tracks = try await asset.loadTracks(withMediaType: .video)
        guard tracks.count == 1, let track = tracks.first else {
            throw ResearchError.invalid("Exactly one video track is required")
        }
        let duration = try await asset.load(.duration).seconds
        let transform = try await track.load(.preferredTransform)
        let timeRange = try await track.load(.timeRange)
        try validateVideoGeometry(duration: duration, trackStart: timeRange.start.seconds,
                                  trackDuration: timeRange.duration.seconds, transform: transform)
        for format in try await track.load(.formatDescriptions) { try requireSquarePixels(format) }
        let reader = try AVAssetReader(asset: asset)
        let video = AVAssetReaderTrackOutput(track: track, outputSettings: [
            kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA
        ])
        video.alwaysCopiesSampleData = false
        guard reader.canAdd(video) else { throw ResearchError.invalid("Unsupported video track") }
        reader.add(video)
        guard reader.startReading() else { throw reader.error ?? ResearchError.invalid("Cannot decode video") }
        defer { reader.cancelReading() }

        let temporary = output.deletingLastPathComponent().appendingPathComponent(".visual-speech-\(UUID().uuidString).tmp")
        guard FileManager.default.createFile(atPath: temporary.path, contents: nil,
                                             attributes: [.posixPermissions: 0o600]) else {
            throw ResearchError.invalid("Cannot create output in requested directory")
        }
        defer { try? FileManager.default.removeItem(at: temporary) }
        let sink = try FileHandle(forWritingTo: temporary)
        defer { try? sink.close() }
        func write(_ value: [String: Any]) throws {
            guard JSONSerialization.isValidJSONObject(value) else {
                throw ResearchError.invalid("Observation contains values that cannot be represented in JSON")
            }
            var data = try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys])
            data.append(0x0a)
            try sink.write(contentsOf: data)
        }
        let request = VNDetectFaceLandmarksRequest()
        request.revision = VNDetectFaceLandmarksRequestRevision3
        let context = CIContext(options: [.cacheIntermediates: false])
        try write([
            "type": "header", "schemaVersion": "visual-speech-observations-v1",
            "releasePosture": "research-only", "learnerFeedbackEligible": false,
            "sourceSHA256": sourceHash, "sourceDurationSeconds": duration,
            "videoTrackStartPTSSeconds": timeRange.start.seconds,
            "videoTrackDurationSeconds": timeRange.duration.seconds,
            "provenance": try json(provenance), "audioTimebase": try json(clock),
            "provenanceSHA256": SHA256.hash(data: provenanceData).map { String(format: "%02x", $0) }.joined(),
            "audioTimebaseSHA256": SHA256.hash(data: timebaseData).map { String(format: "%02x", $0) }.joined(),
            "runtime": "Apple Vision VNDetectFaceLandmarksRequest", "requestRevision": request.revision,
            "osVersion": ProcessInfo.processInfo.operatingSystemVersionString,
            "featureVersion": "eye-normalized-visible-contours-v2", "requestedMaxFPS": fps,
            "orientation": "y-down track transform converted to y-up Core Image; lower-left pixel coordinates",
            "pixelAspectRatio": "1:1-required",
            "preferredTransform": [transform.a, transform.b, transform.c, transform.d, transform.tx, transform.ty],
            "audioAlignmentVerified": false, "depth": NSNull(),
            "depthStatus": "not-captured-or-ingested", "teeth": NSNull(), "tongue": NSNull()
        ])
        var decoded = 0, selected = 0, usable = 0, failures = 0
        while let sample = video.copyNextSampleBuffer() {
            decoded += 1
            let stamp = CMSampleBufferGetPresentationTimeStamp(sample)
            guard try sampler.shouldSelect(pts: stamp.seconds) else { continue }
            selected += 1
            try autoreleasepool {
                let aligned = try clock.align(videoPTS: stamp.seconds)
                if let format = CMSampleBufferGetFormatDescription(sample) { try requireSquarePixels(format) }
                let frameDuration = CMSampleBufferGetDuration(sample).seconds
                var row: [String: Any] = [
                    "type": "frame", "decodedFrameIndex": decoded - 1,
                    "videoPTSSeconds": stamp.seconds, "videoPTSValue": stamp.value,
                    "videoPTSTimescale": stamp.timescale,
                    "frameDurationSeconds": frameDuration.isFinite && frameDuration > 0 ? frameDuration as Any : NSNull(),
                    "audioTimeSeconds": aligned.seconds,
                    "audioSampleIndex": aligned.sampleIndex as Any? ?? NSNull(),
                    "withinDeclaredAudio": aligned.sampleIndex != nil,
                    "faceCount": NSNull(), "features": NSNull(), "faceConfidence": NSNull(),
                    "yawRadians": NSNull(), "pitchRadians": NSNull(), "rollRadians": NSNull(),
                    "mouthOcclusion": NSNull(), "lightingQuality": NSNull(), "motionBlur": NSNull(),
                    "depth": NSNull(), "teeth": NSNull(), "tongue": NSNull(),
                    "speechCorrectness": NSNull()
                ]
                guard let buffer = CMSampleBufferGetImageBuffer(sample) else {
                    row["status"] = "decode-buffer-unavailable"; failures += 1
                    try write(row); return
                }
                let oriented = displayOrientedImage(CIImage(cvPixelBuffer: buffer), transform: transform)
                guard let image = context.createCGImage(oriented, from: oriented.extent) else {
                    row["status"] = "image-conversion-failed"; failures += 1
                    try write(row); return
                }
                row["imageWidth"] = image.width; row["imageHeight"] = image.height
                do {
                    try VNImageRequestHandler(cgImage: image, orientation: .up).perform([request])
                } catch {
                    row["status"] = "landmark-extraction-failed"; failures += 1
                    try write(row); return
                }
                let faces = request.results ?? []
                row["faceCount"] = faces.count
                guard faces.count == 1, let face = faces.first else {
                    row["status"] = faces.isEmpty ? "no-face" : "multiple-faces"
                    try write(row); return
                }
                row["faceConfidence"] = face.confidence.isFinite ? face.confidence as Any : NSNull()
                row["yawRadians"] = nullable(face.yaw); row["pitchRadians"] = nullable(face.pitch)
                row["rollRadians"] = nullable(face.roll)
                let bounds = face.boundingBox
                row["faceBoundsNormalized"] = ["x": bounds.minX, "y": bounds.minY,
                                               "width": bounds.width, "height": bounds.height]
                func points(_ region: VNFaceLandmarkRegion2D?) -> [Point] {
                    (region?.pointsInImage(imageSize: CGSize(width: image.width, height: image.height)) ?? [])
                        .map { Point($0.x, $0.y) }
                }
                let landmarks = face.landmarks
                if let features = geometry(outer: points(landmarks?.outerLips), inner: points(landmarks?.innerLips),
                                           contour: points(landmarks?.faceContour), leftEye: points(landmarks?.leftEye),
                                           rightEye: points(landmarks?.rightEye)) {
                    row["features"] = features; row["status"] = "geometry-observed"; usable += 1
                } else { row["status"] = "geometry-unavailable" }
                try write(row)
            }
        }
        guard reader.status == .completed else { throw reader.error ?? ResearchError.invalid("Video decode incomplete") }
        guard selected > 0 else { throw ResearchError.invalid("Video contains no decoded frames") }
        // Detect accidental source edits during extraction before publishing an artifact.
        guard try digest(input) == sourceHash else { throw ResearchError.invalid("Input changed during extraction") }
        try write(["type": "summary", "decodedFrames": decoded, "sampledFrames": selected,
                   "geometryFrames": usable, "processingFailures": failures, "complete": true])
        try sink.synchronize(); try sink.close()
        try FileManager.default.moveItem(at: temporary, to: output)
        print("Wrote \(selected) research observations (\(usable) with geometry, \(failures) processing failures).")
    }
}
