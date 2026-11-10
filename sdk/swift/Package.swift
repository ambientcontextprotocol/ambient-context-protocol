// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "AmbientContext",
    platforms: [.macOS(.v14)],
    products: [
        .library(name: "AmbientContextProvider", targets: ["AmbientContextProvider"]),
    ],
    targets: [
        .target(name: "AmbientContextProvider"),
        .executableTarget(
            name: "MinimalProvider", dependencies: ["AmbientContextProvider"], path: "Examples/MinimalProvider"
        ),
        .testTarget(name: "AmbientContextProviderTests", dependencies: ["AmbientContextProvider"]),
    ]
)
