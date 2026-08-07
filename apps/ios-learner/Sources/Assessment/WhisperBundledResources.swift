import CryptoKit
import Foundation

/// Future integration supplies only its reviewed bundled directory and immutable
/// admitted manifest SHA. This draft has no admitted compiled-model manifest.
struct WhisperBundledResources: Sendable {
    let rootURL: URL
    let manifestSHA256: String
}

enum WhisperResourceAdmission {
    private struct Manifest: Decodable {
        struct FilePin: Decodable { let path: String; let bytes: Int; let sha256: String }
        let schema: String
        let admitted: Bool
        let sourceRevision: String
        let sourceWeightsSHA256: String
        let encoderGeneratedParityReceiptSHA256: String
        let decoderGeneratedParityReceiptSHA256: String
        let nativePackageCompilationReceiptSHA256: String
        let preprocessingParityReceiptSHA256: String
        let tokenizerParityReceiptSHA256: String
        let melDerivationPolicy: String
        let melSourceHFSourceSHA256: String
        let melProvenanceReceiptSHA256: String
        let melRoundtripReceiptSHA256: String
        let files: [FilePin]
    }
    struct Assets {
        let encoderURL: URL
        let decoderURL: URL
        let features: WhisperFeatureExtractor
        let tokenizer: WhisperByteDecoder
    }

    static func load(_ resources: WhisperBundledResources, stop: WhisperOperationStop) throws -> Assets {
        try stop.check()
        guard resources.rootURL.isFileURL, validSHA(resources.manifestSHA256) else { throw WhisperProviderError.unavailable }
        try directory(resources.rootURL)
        let manifestData = try boundedData(resources.rootURL.appendingPathComponent("RESOURCE-MANIFEST-v1.json"), maximum: 65536)
        guard SHA256.hash(data: manifestData).map({ String(format: "%02x", $0) }).joined() == resources.manifestSHA256 else {
            throw WhisperProviderError.unavailable
        }
        let manifest = try JSONDecoder().decode(Manifest.self, from: manifestData)
        guard manifest.schema == "WhisperBundledResourcesV1", manifest.admitted,
              manifest.sourceRevision == "911407f4214e0e1d82085af863093ec0b66f9cd6",
              manifest.sourceWeightsSHA256 == "d4dd5542fd6a1d35639e21384238f3bfe6c557c849d392b5905d33ee29e71db5",
              manifest.encoderGeneratedParityReceiptSHA256 == "ddf98014aeca5dddaeede3c4a48379e1809a8eadd2b009222037de69c0315db3",
              manifest.decoderGeneratedParityReceiptSHA256 == manifest.encoderGeneratedParityReceiptSHA256,
              manifest.nativePackageCompilationReceiptSHA256 == "602c730e1c77572f3f10828fe03545d22fb2b7fd9db10f284baacc287bbc8b7f",
              validSHA(manifest.preprocessingParityReceiptSHA256),
              validSHA(manifest.tokenizerParityReceiptSHA256),
              manifest.melDerivationPolicy == "HFCPUFloat32V2",
              manifest.melSourceHFSourceSHA256 == "c209e669fae0ea5de92e1846d8790e3d6d66ce28f4cd4071789c2eec88c84a66",
              validSHA(manifest.melProvenanceReceiptSHA256), validSHA(manifest.melRoundtripReceiptSHA256),
              !manifest.files.isEmpty, manifest.files.count <= 128 else { throw WhisperProviderError.unavailable }
        let originalPins = [
            "tokenizer.json": "5eb60cec1e77aeeb6869a2bb5a8e01a84c3fe5d072d75369343021fe6f5310d0",
            "generation_config.json": "c5750f05d94777579e00ce26ef65e5d87c108439f90e3ac519df2587b9d5d41f",
            "config.json": "160c1df40a60d4ef5a6014d536fd845c33aabfd1f318458ac7f87cfe91ebbe76",
            "special_tokens_map.json": "014f8f802366ed818919550be0ad9e35907327cb9e142e8aaa102420f460bda8",
            "LICENSE": "b5d65a59060e68c4ff940e1eddfa6f94b2d68fdf58ed7f4dd57721c997e35e9d",
            "WhisperEncoder.mlmodelc/analytics/coremldata.bin": "ebbdc4fec0ce3daa5de000442af3c63858d4dd75366f72ae423a4f670b963d09",
            "WhisperEncoder.mlmodelc/coremldata.bin": "02374caad637009f587c287fcf7e935ab4499d279f03d9755eb7ff9634ab96c8",
            "WhisperEncoder.mlmodelc/metadata.json": "f089d1ba843b0a37abe3697e588fbc7caafbfe006b045d86fe15171d9cf944f8",
            "WhisperEncoder.mlmodelc/model.mil": "b3120c842f0856bd03a5ba3ee9d2d1e71180e6b7de050cfe3781fb28dc9d5b93",
            "WhisperEncoder.mlmodelc/weights/weight.bin": "4cc988377a5decff9d7363c048734e77254a5fe1de6139f89762fe12343c7c9c",
            "WhisperDecoder.mlmodelc/analytics/coremldata.bin": "14ab606df92a01d208db343cbcb238f6c204333c59a828991253aca5a8c702a7",
            "WhisperDecoder.mlmodelc/coremldata.bin": "a5dfe8ffca6c79d4e80299a6a1825a282c63d27aad4969d50130ebe4bf7147d6",
            "WhisperDecoder.mlmodelc/metadata.json": "fc72aa654d30e034e72e1f6d694860aee08f42c8844b964457203e1d7c0c0dd2",
            "WhisperDecoder.mlmodelc/model.mil": "b32c25c6db7d4bc514910c939522980857baf384250bb65172aa0497972ca29b",
            "WhisperDecoder.mlmodelc/weights/weight.bin": "dbca95170012a691e6639452142eb978fd9083b8a40952e430de5055814bcae2"
        ]
        var expected = Set<String>()
        var totalBytes = 0
        for pin in manifest.files {
            try stop.check()
            let pieces = pin.path.split(separator: "/", omittingEmptySubsequences: false).map(String.init)
            guard !pieces.isEmpty, pieces.allSatisfy({ !$0.isEmpty && $0 != "." && $0 != ".." }),
                  !pin.path.hasPrefix("/"), !pin.path.contains("\\"), pin.path.utf8.count <= 240,
                  pin.bytes > 0, pin.bytes <= 400_000_000, validSHA(pin.sha256),
                  expected.insert(pin.path).inserted else { throw WhisperProviderError.unavailable }
            if let original = originalPins[pin.path] {
                guard original == pin.sha256 else { throw WhisperProviderError.unavailable }
            } else if pin.path == "MEL.f32" {
                guard pin.bytes == 80 * 201 * 4 else { throw WhisperProviderError.unavailable }
            } else if pin.path == "TRANSFORMERS-LICENSE" || pin.path == "MEL-NOTICE" {
                guard pin.bytes <= 65536 else { throw WhisperProviderError.unavailable }
            } else { throw WhisperProviderError.unavailable }
            totalBytes += pin.bytes
            guard totalBytes <= 1_000_000_000 else { throw WhisperProviderError.unavailable }
            let url = resources.rootURL.appendingPathComponent(pin.path)
            // Reject symlink intermediate directories before hashing a scoped file.
            var parent = resources.rootURL
            for piece in pieces.dropLast() { parent.appendPathComponent(piece); try directory(parent) }
            guard try hashFile(url, bytes: pin.bytes, stop: stop) == pin.sha256 else { throw WhisperProviderError.unavailable }
        }
        guard Set(originalPins.keys).isSubset(of: expected),
              Set(["MEL.f32", "TRANSFORMERS-LICENSE", "MEL-NOTICE"]).isSubset(of: expected),
              expected.contains(where: { $0.hasPrefix("WhisperEncoder.mlmodelc/") }),
              expected.contains(where: { $0.hasPrefix("WhisperDecoder.mlmodelc/") }) else { throw WhisperProviderError.unavailable }
        // Exact resource file set: no undeclared model or tokenizer files are admitted.
        var enumerationFailed = false
        guard let enumerator = FileManager.default.enumerator(at: resources.rootURL,
                includingPropertiesForKeys: [.isRegularFileKey, .isDirectoryKey, .isSymbolicLinkKey],
                errorHandler: { _, _ in enumerationFailed = true; return false }) else {
            throw WhisperProviderError.unavailable
        }
        var observed = Set<String>()
        var nodes = 0
        for case let url as URL in enumerator {
            try stop.check()
            nodes += 1
            guard nodes <= 256 else { throw WhisperProviderError.unavailable }
            let info = try url.resourceValues(forKeys: [.isRegularFileKey, .isDirectoryKey, .isSymbolicLinkKey])
            guard info.isSymbolicLink != true else { throw WhisperProviderError.unavailable }
            guard let relative = relativeResourcePath(url, under: resources.rootURL) else {
                throw WhisperProviderError.unavailable
            }
            if info.isRegularFile == true { observed.insert(relative) }
            else if info.isDirectory != true { throw WhisperProviderError.unavailable }
            guard observed.count <= 129 else { throw WhisperProviderError.unavailable }
        }
        guard !enumerationFailed, observed == expected.union(["RESOURCE-MANIFEST-v1.json"]) else { throw WhisperProviderError.unavailable }
        func data(_ name: String, max: Int) throws -> Data {
            try stop.check()
            return try boundedData(resources.rootURL.appendingPathComponent(name), maximum: max)
        }
        // Separately versioned preprocessing v2 must prove this exact serialized
        // CPU Float32 HF table and roundtrip. No unresolved cached-table fallback.
        let mel = try melCoefficients(data("MEL.f32", max: 80 * 201 * 4), stop: stop)
        let features = try WhisperFeatureExtractor(melCoefficients: mel, isCancelled: { stop.isStopped })
        let tokenizer = try WhisperByteDecoder(tokenizerJSON: data("tokenizer.json", max: 2405679),
            generationConfigJSON: data("generation_config.json", max: 1531),
            modelConfigJSON: data("config.json", max: 1937),
            specialTokensMapJSON: data("special_tokens_map.json", max: 1830), isCancelled: { stop.isStopped })
        try stop.check()
        return Assets(encoderURL: resources.rootURL.appendingPathComponent("WhisperEncoder.mlmodelc"),
                      decoderURL: resources.rootURL.appendingPathComponent("WhisperDecoder.mlmodelc"),
                      features: features, tokenizer: tokenizer)
    }

    static func melCoefficients(_ data: Data, stop: WhisperOperationStop) throws -> [[Float]] {
        guard data.count == 80 * 201 * 4 else { throw WhisperProviderError.unavailable }
        // Copying Data to bounded bytes avoids alignment/host-endian assumptions.
        let bytes = [UInt8](data)
        var rows = [[Float]]()
        rows.reserveCapacity(80)
        for mel in 0..<80 {
            try stop.check()
            var row = [Float]()
            row.reserveCapacity(201)
            for bin in 0..<201 {
                let offset = (mel * 201 + bin) * 4
                let bits = UInt32(bytes[offset]) | UInt32(bytes[offset + 1]) << 8 |
                    UInt32(bytes[offset + 2]) << 16 | UInt32(bytes[offset + 3]) << 24
                let value = Float(bitPattern: bits)
                guard value.isFinite, value >= 0 else { throw WhisperProviderError.unavailable }
                row.append(value)
            }
            rows.append(row)
        }
        try stop.check()
        return rows
    }

    private static func validSHA(_ value: String) -> Bool {
        value.utf8.count == 64 && value.utf8.allSatisfy { (48...57).contains($0) || (97...102).contains($0) }
    }

    /// File enumeration may return base-relative URLs or a different OS container alias.
    /// Compare absolute canonical components before deriving a manifest-relative name.
    static func relativeResourcePath(_ url: URL, under root: URL) -> String? {
        guard url.isFileURL, root.isFileURL else { return nil }
        let parent = root.absoluteURL.resolvingSymlinksInPath().standardizedFileURL.pathComponents
        let child = url.absoluteURL.resolvingSymlinksInPath().standardizedFileURL.pathComponents
        guard child.count > parent.count,
              child.prefix(parent.count).elementsEqual(parent) else { return nil }
        return child.dropFirst(parent.count).joined(separator: "/")
    }
    private static func directory(_ url: URL) throws {
        let info = try url.resourceValues(forKeys: [.isDirectoryKey, .isSymbolicLinkKey])
        guard info.isDirectory == true, info.isSymbolicLink != true else { throw WhisperProviderError.unavailable }
    }
    private static func boundedData(_ url: URL, maximum: Int) throws -> Data {
        let info = try url.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey])
        guard info.isRegularFile == true, info.isSymbolicLink != true,
              let count = info.fileSize, count > 0, count <= maximum else { throw WhisperProviderError.unavailable }
        let data = try Data(contentsOf: url)
        guard data.count == count else { throw WhisperProviderError.unavailable }
        return data
    }
    private static func hashFile(_ url: URL, bytes: Int, stop: WhisperOperationStop) throws -> String {
        let info = try url.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey])
        guard info.isRegularFile == true, info.isSymbolicLink != true, info.fileSize == bytes else { throw WhisperProviderError.unavailable }
        let handle = try FileHandle(forReadingFrom: url)
        let result: Result<String, Error> = Result {
            var hasher = SHA256()
            var read = 0
            while true {
                try stop.check()
                let block = try handle.read(upToCount: 1_048_576) ?? Data()
                if block.isEmpty { break }
                read += block.count
                guard read <= bytes else { throw WhisperProviderError.unavailable }
                hasher.update(data: block)
            }
            guard read == bytes else { throw WhisperProviderError.unavailable }
            return hasher.finalize().map { String(format: "%02x", $0) }.joined()
        }
        do { try handle.close() } catch { throw WhisperHandleCleanupFailure(handle: handle) }
        return try result.get()
    }
}
