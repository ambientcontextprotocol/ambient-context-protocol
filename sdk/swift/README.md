# Ambient Context for Swift

Makes a macOS app a provider of the [Ambient Context Protocol](../../docs/spec/index.md), version 0.2.0: it runs the local server, answers the protocol's requests and keeps the descriptor file a host finds the app by. The app writes one thing, a description of what the user has open and selected.

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
    func current() -> ContextElement {
        ContextElement(id: "app", role: .application, title: "Notes", children: [
            ContextElement(id: "w-1", role: .window, focused: true, children: [
                ContextElement(
                    id: "note-1", role: .document, subrole: "note", title: "Groceries",
                    content: [.text("Eggs, rice, limes")], focused: true,
                    children: [ContextElement(id: "sel-1", role: .text, content: [.text("rice")], selected: true)]
                ),
            ]),
        ])
    }
}
```

The answer is one tree, rooted at the app. Each element has a `role` from the protocol's thirteen (how the thing is shown: a window, a list, a row, text) and may have a `subrole`, the app's own word for what it is (`note`, `task`). Selected text is a `.text` element with `selected: true`, placed inside the element it was selected in.

- `focused` goes on every element from the window down to where the user is, with no gaps.
- `hovered` goes on at most one element, the innermost one under the pointer, if the app tracks the pointer. It is optional.
- `visible: false` marks something open but not drawn, such as a background tab.
- `attributes` takes plain literals: `attributes: ["ref": "T-12", "done": false]`.

Report what the user has open and is pointing at, not the whole interface: no buttons, menus or toolbars, and nothing the user would be surprised to see handed to an agent.

`current()` is called on the main actor each time a host asks, and should answer from state already in memory. An id is 1 to 128 letters, digits, hyphens and underscores, unique within the answer, and stays the same for as long as the thing exists in this run of the app.

The server checks each answer against the rules a tree must keep (`ContextTree.check`) and reports a broken one once on standard error, then answers anyway. Call `ContextTree.check` in the app's own tests to catch a mistake there.

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

`ContextProvider` and `ContextServer` are main-actor types. In a module that makes the main actor its default isolation (Swift 6.2), the app's own types are main-actor too, so the file that builds the `ContextElement` tree from them must be in a module, or a type, that is main-actor isolated as well.

## Say where it is (optional)

A provider that can report where an element is on screen also conforms to `ContextLocator`. A host can then place its own interface beside the element.

```swift
extension NotesContext: ContextLocator {
    func locate(_ id: String) -> ContextLocation? {
        guard let frame = screenFrame(of: id) else { return nil }
        return ContextLocation(id: id, state: .visible, rects: [frame], edge: .right)
    }
}
```

Rectangles are in global display coordinates: points, origin at the top left of the primary display, y increasing downward. Return nil for an element that cannot be placed. A provider that is not a locator offers no location resource, and nothing else changes.

## On a server the app already has

An app that already runs a local HTTP or MCP server does not need a second port. It mounts a `ContextResponder` on one path of that server and writes the descriptor itself:

```swift
let token = ContextServer.random(bytes: 32)
let instance = ContextServer.random(bytes: 6)
let responder = try ContextResponder(
    app: app, instance: instance, token: token, path: "/ambient",
    current: { await notesContext.current() }
)

// In the app's server, for every request whose path is /ambient:
let response = await responder.respond(to: ContextHTTPRequest(
    method: method, path: "/ambient", headers: lowercasedHeaders, body: body
))
// Send response.status, response.headers and response.body unchanged.

// Once the listener is up:
let file = try ContextDescriptor(
    app: app, instance: instance, endpoint: "http://127.0.0.1:\(port)/ambient", token: token
).write()
// At quit, and when the user turns the feature off: remove `file`.
```

The responder refuses `Origin` and checks the token before anything else. Four things stay the app's to get right, and the package cannot check them:

- The listener is bound to `127.0.0.1` only, never all interfaces.
- Requests to that path reach the responder before any other handling, and no middleware adds cross-origin headers to its responses or answers a preflight for it.
- The token is made for this endpoint and is not a credential the server accepts anywhere else.
- Neither the token nor a response body is written to the server's logs.

## Try it

```sh
swift test                 # the server, the descriptor and the public interface over a real socket
swift run MinimalProvider  # a small provider; prints its endpoint and token
```

[`Examples/MinimalProvider`](Examples/MinimalProvider/main.swift) is the whole of a provider in about sixty lines.
