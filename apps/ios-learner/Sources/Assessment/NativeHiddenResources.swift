import CryptoKit
import Darwin
import Foundation

enum NativeHiddenFailure: Error { case unavailable, rejectedInput, invalidTensor, nonfiniteTensor }

struct NativeHiddenFileIdentity: Equatable, Sendable {
  let device: Int64
  let inode: UInt64
  let size: Int64
  let mode: UInt32
  let uid: UInt32
  let links: UInt64
  let modifiedSeconds: Int64
  let modifiedNanoseconds: Int64
  let changedSeconds: Int64
  let changedNanoseconds: Int64

  init(_ value: stat) {
    device = Int64(value.st_dev)
    inode = UInt64(value.st_ino)
    size = Int64(value.st_size)
    mode = UInt32(value.st_mode)
    uid = value.st_uid
    links = UInt64(value.st_nlink)
    modifiedSeconds = Int64(value.st_mtimespec.tv_sec)
    modifiedNanoseconds = Int64(value.st_mtimespec.tv_nsec)
    changedSeconds = Int64(value.st_ctimespec.tv_sec)
    changedNanoseconds = Int64(value.st_ctimespec.tv_nsec)
  }
}

/// Fixed app location and reviewed identity only; construction does no file/model loading.
struct NativeHiddenResources: Sendable {
  let rootURL: URL
  let manifestSHA256: String
  private static let reviewedManifestSHA256 =
    "e0a72539aa1860875765a800dea4f72a9ce444b94a9ddd14a1db353d4a61e297"

  private init(rootURL: URL, manifestSHA256: String) {
    self.rootURL = rootURL
    self.manifestSHA256 = manifestSHA256
  }

  static func bundled() -> Self? {
    guard let base = Bundle.main.resourceURL,
      Bundle.main.bundleIdentifier == "com.cadence.speechtherapy.learner"
    else { return nil }
    let root = base.appendingPathComponent("HiddenResources", isDirectory: true)
    guard isCanonicalAppLocation(app: Bundle.main.bundleURL, root: root) else { return nil }
    return Self(rootURL: root, manifestSHA256: reviewedManifestSHA256)
  }

  static func isCanonicalAppLocation(app: URL, root: URL) -> Bool {
    app.isFileURL && root.isFileURL && app.pathExtension == "app"
      && app == app.standardizedFileURL && root == root.standardizedFileURL
      && app == app.resolvingSymlinksInPath() && root == root.resolvingSymlinksInPath()
      && root.lastPathComponent == "HiddenResources" && root.deletingLastPathComponent() == app
  }

  #if DEBUG
    /// Explicit copied-fixture seam; ordinary app code resolves only bundled().
    static func fixture(rootURL: URL, manifestSHA256: String) -> Self {
      Self(rootURL: rootURL, manifestSHA256: manifestSHA256)
    }
  #endif
}

enum NativeHiddenResourceAdmission {
  static let modelNames = [
    "PhoneticFrontend.mlmodelc", "PhoneticMaterializedPadding.mlmodelc",
    "PhoneticEncoderBody.mlmodelc",
  ]
  static let pieces = ["frontend", "positional", "encoderBody"]
  static let finalAuditSHA256 = "d0dbca5d660bb0d662b2da57e95ae37fe8553844772f5f550b11b038d5e63f74"

  struct Manifest: Decodable {
    struct FilePin: Decodable {
      let path: String
      let bytes: Int
      let sha256: String
    }
    struct Model: Decodable {
      let piece: String
      let path: String
      let files: [FilePin]
    }
    let schema: String
    let admitted: Bool
    let finalAuditSHA256: String
    let models: [Model]
  }

  struct Assets {
    let frontendURL: URL
    let positionalURL: URL
    let encoderBodyURL: URL
    let files: [URL: NativeHiddenFileIdentity]
    let directories: [URL: NativeHiddenFileIdentity]

    func checkCurrent(stop: WhisperOperationStop) throws {
      for (url, expected) in files {
        try stop.check()
        guard try NativeHiddenFiles.identity(url, directory: false) == expected else {
          throw NativeHiddenFailure.unavailable
        }
      }
      for (url, expected) in directories {
        try stop.check()
        guard try NativeHiddenFiles.identity(url, directory: true) == expected else {
          throw NativeHiddenFailure.unavailable
        }
      }
    }
  }

  static func load(_ resources: NativeHiddenResources, stop: WhisperOperationStop) throws -> Assets
  {
    try stop.check()
    guard NativeHiddenFiles.validSHA(resources.manifestSHA256) else {
      throw NativeHiddenFailure.unavailable
    }
    let root = resources.rootURL
    let rootIdentity = try NativeHiddenFiles.identity(root, directory: true)
    let manifestURL = root.appendingPathComponent("RESOURCE-MANIFEST-v1.json")
    let manifestRead = try NativeHiddenFiles.read(
      manifestURL, maximum: 65536, retain: true, stop: stop)
    guard manifestRead.sha256 == resources.manifestSHA256 else {
      throw NativeHiddenFailure.unavailable
    }
    let manifest = try JSONDecoder().decode(Manifest.self, from: manifestRead.data)
    guard manifest.schema == "NativeHiddenBundledResourcesV1", manifest.admitted,
      manifest.finalAuditSHA256 == finalAuditSHA256, manifest.models.count == 3
    else { throw NativeHiddenFailure.unavailable }
    var expected = Set<String>()
    var expectedDirectories = Set<String>()
    var identities = [manifestURL: manifestRead.identity]
    var directories = [root: rootIdentity]
    var totalBytes = 0
    for (index, model) in manifest.models.enumerated() {
      guard model.piece == pieces[index], model.path == modelNames[index], !model.files.isEmpty,
        model.files.count <= 1000
      else { throw NativeHiddenFailure.unavailable }
      expectedDirectories.insert(model.path)
      for pin in model.files {
        try stop.check()
        let parts = pin.path.split(separator: "/", omittingEmptySubsequences: false).map(
          String.init)
        guard parts.count >= 2, parts[0] == model.path,
          parts.allSatisfy({ !$0.isEmpty && $0 != "." && $0 != ".." }),
          !pin.path.contains("\\"), pin.path.utf8.count <= 240,
          pin.bytes > 0, pin.bytes <= 2_000_000_000, NativeHiddenFiles.validSHA(pin.sha256),
          expected.insert(pin.path).inserted
        else { throw NativeHiddenFailure.unavailable }
        totalBytes += pin.bytes
        guard totalBytes <= 2_000_000_000 else { throw NativeHiddenFailure.unavailable }
        var parent = root
        for part in parts.dropLast() {
          parent.appendPathComponent(part, isDirectory: true)
          directories[parent] = try NativeHiddenFiles.identity(parent, directory: true)
        }
        for count in 1..<parts.count {
          expectedDirectories.insert(parts.prefix(count).joined(separator: "/"))
        }
        let url = root.appendingPathComponent(pin.path)
        let read = try NativeHiddenFiles.read(url, maximum: pin.bytes, retain: false, stop: stop)
        guard read.identity.size == pin.bytes, read.sha256 == pin.sha256 else {
          throw NativeHiddenFailure.unavailable
        }
        identities[url] = read.identity
      }
    }
    var failed = false
    guard
      let walk = FileManager.default.enumerator(
        at: root, includingPropertiesForKeys: nil,
        errorHandler: { _, _ in
          failed = true
          return false
        })
    else { throw NativeHiddenFailure.unavailable }
    var observed = Set<String>()
    var nodes = 0
    for case let url as URL in walk {
      try stop.check()
      nodes += 1
      guard nodes <= 6144, url.path.hasPrefix(root.path + "/") else {
        throw NativeHiddenFailure.unavailable
      }
      let relative = String(url.path.dropFirst(root.path.count + 1))
      var mode = stat()
      guard lstat(url.path, &mode) == 0 else { throw NativeHiddenFailure.unavailable }
      if mode.st_mode & S_IFMT == S_IFDIR {
        guard expectedDirectories.contains(relative) else { throw NativeHiddenFailure.unavailable }
      } else {
        guard mode.st_mode & S_IFMT == S_IFREG, observed.insert(relative).inserted else {
          throw NativeHiddenFailure.unavailable
        }
      }
    }
    guard !failed, observed == expected.union(["RESOURCE-MANIFEST-v1.json"]) else {
      throw NativeHiddenFailure.unavailable
    }
    let result = Assets(
      frontendURL: root.appendingPathComponent(modelNames[0]),
      positionalURL: root.appendingPathComponent(modelNames[1]),
      encoderBodyURL: root.appendingPathComponent(modelNames[2]),
      files: identities, directories: directories)
    try result.checkCurrent(stop: stop)
    return result
  }
}

/// Checked scoped reads shared only by this concrete operation's resource and WAV admission.
enum NativeHiddenFiles {
  struct Read {
    let data: Data
    let sha256: String
    let identity: NativeHiddenFileIdentity
  }

  static func validSHA(_ value: String) -> Bool {
    value.utf8.count == 64
      && value.utf8.allSatisfy { (48...57).contains($0) || (97...102).contains($0) }
  }

  static func identity(_ url: URL, directory: Bool) throws -> NativeHiddenFileIdentity {
    var value = stat()
    guard url.isFileURL, url == url.standardizedFileURL, url == url.resolvingSymlinksInPath(),
      lstat(url.path, &value) == 0,
      value.st_mode & S_IFMT == (directory ? S_IFDIR : S_IFREG), directory || value.st_nlink == 1
    else {
      throw NativeHiddenFailure.unavailable
    }
    return NativeHiddenFileIdentity(value)
  }

  static func read(_ url: URL, maximum: Int, retain: Bool, stop: WhisperOperationStop) throws
    -> Read
  {
    try stop.check()
    let before = try identity(url, directory: false)
    guard maximum > 0, before.size > 0, before.size <= maximum else {
      throw NativeHiddenFailure.rejectedInput
    }
    let descriptor = open(url.path, O_RDONLY | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC)
    guard descriptor >= 0 else { throw NativeHiddenFailure.unavailable }
    let handle = FileHandle(fileDescriptor: descriptor, closeOnDealloc: false)
    let result: Result<Read, Error> = Result {
      var opened = stat()
      guard fstat(descriptor, &opened) == 0, NativeHiddenFileIdentity(opened) == before else {
        throw NativeHiddenFailure.unavailable
      }
      var hasher = SHA256()
      var data = Data()
      var count = 0
      while true {
        try stop.check()
        let block = try handle.read(upToCount: 1_048_576) ?? Data()
        if block.isEmpty { break }
        count += block.count
        guard count <= maximum else { throw NativeHiddenFailure.rejectedInput }
        hasher.update(data: block)
        if retain { data.append(block) }
      }
      var finished = stat()
      guard count == before.size, fstat(descriptor, &finished) == 0,
        NativeHiddenFileIdentity(finished) == before, try identity(url, directory: false) == before
      else {
        throw NativeHiddenFailure.unavailable
      }
      return Read(
        data: data, sha256: hasher.finalize().map { String(format: "%02x", $0) }.joined(),
        identity: before)
    }
    do { try handle.close() } catch { throw WhisperHandleCleanupFailure(handle: handle) }
    return try result.get()
  }
}
