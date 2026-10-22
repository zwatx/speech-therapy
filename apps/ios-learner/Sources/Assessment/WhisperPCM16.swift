import Darwin
import Foundation

enum WhisperProviderError: Error { case unavailable, rejectedInput, invalidTensor, nonfiniteTensor, noEligibleToken }
struct WhisperHandleCleanupFailure: Error, @unchecked Sendable { let handle: FileHandle }

/// Uses the unchanged existing RIFF gate, then decodes the exact admitted data chunk.
/// No resampling, cropping, capture, VAD threshold or admission broadening.
enum WhisperPCM16 {
    struct ReadResult {
        let samples: [Float]?
        let cleanupConfirmed: Bool
        let retainedHandle: FileHandle?
    }

    static func decode(_ data: Data, stop: WhisperOperationStop) throws -> [Float] {
        try stop.check()
        guard LocalWordWAVGate.duration(bytes: data) != nil else { throw WhisperProviderError.rejectedInput }
        func little(_ offset: Int, _ bytes: Int) -> Int {
            (0..<bytes).reduce(0) { $0 | Int(data[offset + $1]) << ($1 * 8) }
        }
        var offset = 12
        while offset < data.count {
            try stop.check()
            let count = little(offset + 4, 4)
            let start = offset + 8
            if data[offset..<(offset + 4)].elementsEqual("data".utf8) {
                var samples = [Float]()
                samples.reserveCapacity(count / 2)
                for index in stride(from: 0, to: count, by: 2) {
                    if index % 2048 == 0 { try stop.check() }
                    let raw = UInt16(data[start + index]) | UInt16(data[start + index + 1]) << 8
                    samples.append(Float(Int16(bitPattern: raw)) / 32768)
                }
                guard (1600...64000).contains(samples.count), samples.allSatisfy(\.isFinite) else {
                    throw WhisperProviderError.rejectedInput
                }
                return samples
            }
            offset = start + count + count % 2 // Gate already validated every boundary.
        }
        throw WhisperProviderError.rejectedInput
    }

    static func read(_ url: URL, stop: WhisperOperationStop) throws -> ReadResult {
        try stop.check()
        guard url.isFileURL else { throw WhisperProviderError.rejectedInput }
        let descriptor = open(url.path, O_RDONLY | O_NOFOLLOW | O_NONBLOCK)
        guard descriptor >= 0 else { throw WhisperProviderError.rejectedInput }
        let handle = FileHandle(fileDescriptor: descriptor, closeOnDealloc: false)
        var samples: [Float]?
        do {
            var before = stat()
            guard fstat(descriptor, &before) == 0, before.st_mode & S_IFMT == S_IFREG,
                  before.st_size >= 44, before.st_size <= LocalWordWAVGate.maximumFileBytes else {
                throw WhisperProviderError.rejectedInput
            }
            let data = try handle.read(upToCount: LocalWordWAVGate.maximumFileBytes) ?? Data()
            var after = stat()
            guard fstat(descriptor, &after) == 0, data.count == before.st_size,
                  before.st_dev == after.st_dev, before.st_ino == after.st_ino,
                  before.st_size == after.st_size,
                  before.st_mtimespec.tv_sec == after.st_mtimespec.tv_sec,
                  before.st_mtimespec.tv_nsec == after.st_mtimespec.tv_nsec,
                  before.st_ctimespec.tv_sec == after.st_ctimespec.tv_sec,
                  before.st_ctimespec.tv_nsec == after.st_ctimespec.tv_nsec else {
                throw WhisperProviderError.rejectedInput
            }
            samples = try decode(data, stop: stop)
        } catch { samples = nil } // Close this exact opened handle on every read/decode failure.
        do {
            try handle.close()
            return .init(samples: samples, cleanupConfirmed: true, retainedHandle: nil)
        } catch {
            return .init(samples: nil, cleanupConfirmed: false, retainedHandle: handle)
        }
    }
}
