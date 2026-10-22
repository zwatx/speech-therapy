// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "CadenceContracts",
    platforms: [
        .iOS(.v17),
        .macOS(.v14),
    ],
    products: [
        .library(name: "CadenceContracts", targets: ["CadenceContracts"]),
    ],
    targets: [
        .target(name: "CadenceContracts"),
        .testTarget(
            name: "CadenceContractsTests",
            dependencies: ["CadenceContracts"]
        ),
    ]
)
