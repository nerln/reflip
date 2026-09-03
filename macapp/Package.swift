// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "Reflip",
    platforms: [.macOS(.v14)],
    targets: [
        .executableTarget(
            name: "Reflip",
            path: "Sources/Reflip",
            swiftSettings: [.swiftLanguageMode(.v5)]
        ),
        // The window decides nothing. It reads a JSON document another program writes
        // and reassembles lines out of a pipe, and both of those have broken before:
        // a field that changed shape, and a line cut in half at a chunk boundary.
        // Neither needs a screen to be tested, so neither is tested by looking.
        .testTarget(
            name: "ReflipTests",
            dependencies: ["Reflip"],
            path: "Tests/ReflipTests",
            swiftSettings: [.swiftLanguageMode(.v5)]
        )
    ]
)
