# Ambient Context for Swift

Makes a macOS app a provider of the [Ambient Context Protocol](../../docs/protocol-v0.md), draft 0.1: it runs the local server, answers the protocol's requests and keeps the descriptor file a host finds the app by. The app writes one thing, a description of what the user has open and selected.

It has no dependencies beyond Foundation and Network, and needs macOS 14 or later.

## Add it

The package is used by local path for now. In another package's manifest:

```swift
dependencies: [
    .package(name: "AmbientContext", path: "../ambient-context-protocol/sdk/swift"),
],
targets: [
    .target(name: "MyApp", dependencies: [
        .product(name: "AmbientContextProvider", package: "AmbientContext"),
    ]),
]
```

In an Xcode project, add the `sdk/swift` folder as a local package and link `AmbientContextProvider`.

## Say what is open

```swift
import AmbientContextProvider

@MainActor
final class NotesContext: ContextProvider {
    func current() -> ContextCurrent {
        ContextCurrent(focus: ["note-1"], items: [
            ContextItem(id: "note-1", type: "note", title: "Groceries", content: [.text("Eggs, rice, limes")]),
        ])
    }
}
```

An item's `payload` takes plain literals: `payload: ["ref": "T-12", "done": false]`.

`current()` is called on the main actor each time a host asks, and should answer from state already in memory. `focus` lists the ids of the items the user is working on now; `items` is everything open. An id is letters, digits, hyphens and underscores, and stays the same for as long as the item exists in this run of the app.

## Serve it

```swift
let server = ContextServer(
    provider: notesContext,
    app: ContextApp(id: Bundle.main.bundleIdentifier!, name: "Notes", version: "1.0")
)
server.start()   // when the user turns the feature on
server.stop()    // when they turn it off, and when the app is about to quit
```

Three things an app should do around it:

- Keep the feature off until the user turns it on, and say plainly what it does: while it is on, any program running as the user can ask what is open and selected.
- Call `ContextDescriptor.removeStale(bundleID:pid:in:)` with `ContextDescriptor.defaultDirectory` at launch, whether or not the feature is on, so a descriptor left by a crash does not outlive it.
- Call `stop()` before the app exits: in `applicationWillTerminate`, or in a SwiftUI app with no app delegate, on `NSApplication.willTerminateNotification`. The server holds off sudden termination while it runs so that this call is reached.

`ContextProvider` and `ContextServer` are main-actor types. In a module that makes the main actor its default isolation (Swift 6.2), the app's own types are main-actor too, so the file that builds `ContextCurrent` from them must be in a module, or a type, that is main-actor isolated as well.

## Say where it is (optional)

A provider that can report where an item is on screen also conforms to `ContextLocator`. A host can then place its own interface beside the item.

```swift
extension NotesContext: ContextLocator {
    func locate(_ id: String) -> ContextLocation? {
        guard let frame = screenFrame(of: id) else { return nil }
        return ContextLocation(id: id, state: .visible, rects: [frame], edge: .right)
    }
}
```

Rectangles are in global display coordinates: points, origin at the top left of the primary display, y increasing downward. Mark an item `locatable: true` in `current()` only if `locate` can answer for it. A provider that is not a locator offers no location resource, and nothing else changes.

## Try it

```sh
swift test                 # the server, the descriptor and the public interface over a real socket
swift run MinimalProvider  # a one-item provider; prints its endpoint and token
```

[`Examples/MinimalProvider`](Examples/MinimalProvider/main.swift) is the whole of a provider in about forty lines.
