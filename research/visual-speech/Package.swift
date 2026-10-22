// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "VisualSpeechResearch",
    platforms: [.macOS(.v14)],
    products: [.executable(name: "visual-speech", targets: ["VisualSpeechCLI"])],
    targets: [
        .target(name: "VisualSpeechCore"),
        .executableTarget(name: "VisualSpeechCLI", dependencies: ["VisualSpeechCore"]),
        .testTarget(name: "VisualSpeechCoreTests", dependencies: ["VisualSpeechCore"])
    ]
)
