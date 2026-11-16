// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "AmbientContextChrome",
    platforms: [.macOS(.v14)],
    dependencies: [
        .package(name: "AmbientContext", path: "../../../sdk/swift"),
    ],
    targets: [
        .target(
            name: "ChromeBridge",
            dependencies: [.product(name: "AmbientContextProvider", package: "AmbientContext")]
        ),
        .executableTarget(
            name: "ambient-context-chrome",
            dependencies: ["ChromeBridge", .product(name: "AmbientContextProvider", package: "AmbientContext")]
        ),
        .testTarget(name: "ChromeBridgeTests", dependencies: ["ChromeBridge"]),
    ]
)
