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
                        guard let message = try? JSONDecoder().decode(ExtensionMessage.self, from: body),
                              message.type == "state", let id = message.id
                        else { continue }
                        self.finish(id, with: message.state ?? PageState())
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

/// The tree builder, which remembers the last selection's id.
actor Pages {
    private var builder: PageTree

    init(appName: String) { builder = PageTree(appName: appName) }

    func tree(_ state: PageState?) -> ContextElement { builder.tree(state) }
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
let pages = Pages(appName: appName)
let server = ContextServer(
    app: ContextApp(id: "io.github.ambientcontextprotocol.chrome", name: "Ambient Context for Chrome", version: version),
    answersFor: ContextTarget(id: targetID, pid: parent),
    directory: directory ?? ContextDescriptor.defaultDirectory,
    current: { await pages.tree(await bridge.current()) }
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

server.start()
bridge.read(onEnd: stop)
RunLoop.main.run()
