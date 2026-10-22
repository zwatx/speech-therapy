import Foundation

/// The runtime entry point derives resources only from this host app. Validation
/// and prediction remain deferred to Check in the existing owned worker.
enum BundledLocalWordRecognizerFactory {
  private static let manifestSHA256 =
    "3a5685954ba13a09b6430ed360afbb8c871033e9d2e90388568ef51a90b64b3d"
  private static let appIdentifier = "com.cadence.speechtherapy.learner"

  @MainActor
  static func make(ownership: ProcessAudioFileOwnership = .shared) -> CoreMLLocalWordRecognizer {
    CoreMLLocalWordRecognizer(resources: bundledResources(), ownership: ownership)
  }

  private static func bundledResources() -> WhisperBundledResources? {
    let app = Bundle.main.bundleURL
    guard let base = Bundle.main.resourceURL else { return nil }
    let root = base.appendingPathComponent("WhisperResources", isDirectory: true)
    guard isCanonicalAppResourceLocation(
      appURL: app, resourceURL: root,
      resolvedAppURL: app.resolvingSymlinksInPath(),
      resolvedResourceURL: root.resolvingSymlinksInPath(),
      bundleIdentifier: Bundle.main.bundleIdentifier),
      isUnlinkedDirectory(app), isUnlinkedDirectory(root)
    else { return nil }
    return WhisperBundledResources(rootURL: root, manifestSHA256: manifestSHA256)
  }

  /// A pure path predicate for tests. It never creates an admitted resource
  /// descriptor; production callers cannot select another resource location.
  static func isCanonicalAppResourceLocation(
    appURL: URL, resourceURL: URL, resolvedAppURL: URL,
    resolvedResourceURL: URL, bundleIdentifier: String?
  ) -> Bool {
    guard appURL.isFileURL, resourceURL.isFileURL,
      bundleIdentifier == appIdentifier,
      appURL.pathExtension == "app",
      appURL == appURL.standardizedFileURL,
      resourceURL == resourceURL.standardizedFileURL,
      appURL == resolvedAppURL, resourceURL == resolvedResourceURL,
      resourceURL.lastPathComponent == "WhisperResources",
      resourceURL.deletingLastPathComponent() == appURL
    else { return false }
    return true
  }

  /// Metadata only: no manifest, model, tokenizer or recording is opened here.
  static func isUnlinkedDirectory(_ url: URL) -> Bool {
    guard url.isFileURL, url == url.standardizedFileURL,
      url == url.resolvingSymlinksInPath(),
      let values = try? url.resourceValues(forKeys: [.isDirectoryKey, .isSymbolicLinkKey])
    else { return false }
    return values.isDirectory == true && values.isSymbolicLink != true
  }
}
