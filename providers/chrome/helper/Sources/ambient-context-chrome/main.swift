import AmbientContextProvider
import AppKit
import ChromeBridge
import Foundation

// The Ambient Context provider for a Chromium browser. The browser starts
// this program for the extension and talks to it over standard input and
// output (native messaging). It answers `ambient://current` for the
// browser: each time a host asks, it asks the extension what page is in
// front and what is selected there, and builds the tree from the answer.
//
// It names the app it answers for from its own parent process, so it
// knows nothing of any one browser. Standard output carries messages to
// the extension only; nothing from a page is ever written to a log.

let version = "0.1.0"

func note(_ text: String) {
    FileHandle.standardError.write(Data("ambient-context-chrome: \(text)\n".utf8))
}

// MARK: - The extension

/// The questions waiting on the extension, and the way to it.
final class Extension: @unchecked Sendable {
    private let lock = NSLock()
    private var nextID = 0
    private var waiting: [Int: CheckedContinuation<PageState?, Never>] = [:]
    private let output = FileHandle.standardOutput
    /// Called when the extension says the keyboard moved to or from one
    /// of its windows. Set before `read`.
    var onFocusChange: (@Sendable () -> Void)?

    /// How long the extension has to answer. A host waits a fraction of
    /// a second in all, so this is well inside it.
    static let limit: Duration = .milliseconds(150)

    /// What the extension says is in front, or nil if it does not say
    /// in time.
    func current() async -> PageState? {
        let id: Int = lock.withLock {
            nextID += 1
            return nextID
        }
        return await withCheckedContinuation { continuation in
            lock.withLock { waiting[id] = continuation }
            guard send(["type": "current", "id": id]) else {
                finish(id, with: nil)
                return
            }
            Task {
                try? await Task.sleep(for: Self.limit)
                self.finish(id, with: nil)
            }
        }
    }

    /// Answers the question `id`, once: a late or second answer finds
    /// nothing waiting.
    func finish(_ id: Int, with state: PageState?) {
        let continuation = lock.withLock { waiting.removeValue(forKey: id) }
        continuation?.resume(returning: state)
    }

    @discardableResult
    private func send(_ message: [String: Any]) -> Bool {
        guard let body = try? JSONSerialization.data(withJSONObject: message),
              let framed = NativeMessage.frame(body)
        else { return false }
        return lock.withLock {
            do {
                try output.write(contentsOf: framed)
                return true
            } catch {
                return false
            }
        }
    }

    /// Reads the extension's messages until the browser closes the
    /// stream, which is how it says to stop.
    func read(onEnd: @escaping @Sendable () -> Void) {
        let thread = Thread {
            var reader = NativeMessage.Reader()
            let input = FileHandle.standardInput
            while true {
                let bytes = input.availableData
                if bytes.isEmpty { break }
                reader.append(bytes)
                do {
                    while let body = try reader.next() {
                        guard let message = try? JSONDecoder().decode(ExtensionMessage.self, from: body) else {
                            continue
                        }
                        if message.type == "state", let id = message.id {
                            self.finish(id, with: message.state ?? PageState())
                        } else if message.type == "focus" {
                            self.onFocusChange?()
                        }
                    }
                } catch {
                    note("the stream from the browser is not native messaging; stopping")
                    break
                }
            }
            onEnd()
        }
        thread.name = "extension"
        thread.start()
    }
}

/// The tree builder, which remembers the last selection's id, and what
/// is known of which window is the browser's front one.
actor Pages {
    private var builder: PageTree
    private var front: FrontWindow

    init(appName: String, front: FrontWindow) {
        builder = PageTree(appName: appName)
        self.front = front
    }

    func tree(_ state: PageState?, browserActive: Bool) -> ContextElement {
        guard let state else { return builder.tree(nil) }
        let inFront = front.look(focused: state.window?.focused == true, browserActive: browserActive)
        return builder.tree(state, inFront: inFront)
    }

    /// A look with no one asking, so that what was in front is known
    /// later, when another app is.
    func look(_ state: PageState?, browserActive: Bool) {
        guard let state else { return }
        _ = front.look(focused: state.window?.focused == true, browserActive: browserActive)
    }
}

// MARK: - Who started this

// The app answered for is the parent process: the browser. A host accepts
// the descriptor only if that is true, so nothing is gained by claiming
// otherwise. The two variables below are for tests, where the parent is a
// script and the descriptor must not go in the real folder.
let environment = ProcessInfo.processInfo.environment
let parent = getppid()
let browser = NSRunningApplication(processIdentifier: parent)
let targetID = browser?.bundleIdentifier ?? environment["AMBIENT_CONTEXT_TEST_APP"]
guard let targetID else {
    note("not started by an app; a browser starts this program for its extension")
    exit(1)
}
let appName = browser?.localizedName ?? targetID
let directory = environment["AMBIENT_CONTEXT_TEST_DIRECTORY"].map { URL(fileURLWithPath: $0, isDirectory: true) }

// MARK: - Run

let bridge = Extension()
// A stand-in browser in a test is never the app in front, so nothing
// could ever be seen there; it starts with nothing hidden.
let pages = Pages(appName: appName, front: FrontWindow(hidden: browser != nil))

/// Whether the browser is the app in front.
enum Browser {
    static func isActive() async -> Bool {
        let browser = getppid()
        return await MainActor.run { NSWorkspace.shared.frontmostApplication?.processIdentifier == browser }
    }
}

/// Looks at what is in front a moment after it may have changed, once
/// the browser and the system have both settled.
@Sendable func lookSoon() {
    Task {
        try? await Task.sleep(for: .milliseconds(250))
        let state = await bridge.current()
        await pages.look(state, browserActive: await Browser.isActive())
    }
}
let server = ContextServer(
    app: ContextApp(id: "io.github.ambientcontextprotocol.chrome", name: "Ambient Context for Chrome", version: version),
    answersFor: ContextTarget(id: targetID, pid: parent),
    directory: directory ?? ContextDescriptor.defaultDirectory,
    // The extension says nothing when the page or the selection changes,
    // so this program cannot tell a watching host; it offers no watch.
    watch: false,
    // A browser shows mail, banks and whatever the user is signed in to,
    // and this program cannot tell such a page from any other, so every
    // answer is marked sensitive and a host asks before sending it on
    // (RFC-0007). The mark is not the redaction: what must never be
    // reported is left out by the extension, before it gets here.
    sensitive: { true },
    current: {
        let state = await bridge.current()
        return await pages.tree(state, browserActive: await Browser.isActive())
    }
)

@Sendable func stop() {
    DispatchQueue.main.async {
        MainActor.assumeIsolated { server.stop() }
        exit(0)
    }
}

signal(SIGTERM, SIG_IGN)
signal(SIGINT, SIG_IGN)
let signals = [SIGTERM, SIGINT].map { number -> DispatchSourceSignal in
    let source = DispatchSource.makeSignalSource(signal: number, queue: .main)
    source.setEventHandler { stop() }
    source.resume()
    return source
}
// A write to a browser that has gone must fail, not end the process
// before the descriptor is removed.
signal(SIGPIPE, SIG_IGN)

// The keyboard moving between the browser's windows, and the browser
// coming to the front, are the two moments a hidden window can take
// over without anyone asking.
bridge.onFocusChange = lookSoon
let activation = NSWorkspace.shared.notificationCenter.addObserver(
    forName: NSWorkspace.didActivateApplicationNotification, object: nil, queue: .main
) { notification in
    let app = notification.userInfo?[NSWorkspace.applicationUserInfoKey] as? NSRunningApplication
    if app?.processIdentifier == parent { lookSoon() }
}

server.start()
bridge.read(onEnd: stop)
lookSoon()
RunLoop.main.run()
