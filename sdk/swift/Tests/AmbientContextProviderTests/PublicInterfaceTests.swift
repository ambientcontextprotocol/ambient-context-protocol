import Foundation
import Testing
import AmbientContextProvider

/// The package as an app uses it: only the public interface, over a real
/// socket, found through the descriptor file as a host finds it.
@MainActor
struct PublicInterfaceTests {
    final class Notes: ContextProvider {
        func current() -> ContextElement {
            ContextElement(id: "app", role: .application, title: "Notes", children: [
                ContextElement(
                    id: "note-1", role: .document, subrole: "note", title: "Groceries",
                    content: [.text("Eggs, rice")], focused: true
                ),
            ])
        }
    }

    final class LocatedNotes: ContextProvider, ContextLocator {
        func current() -> ContextElement {
            ContextElement(id: "app", role: .application, title: "Notes", children: [
                ContextElement(id: "note-1", role: .document, subrole: "note", title: "Groceries", focused: true),
            ])
        }

        func locate(_ id: String) -> ContextLocation? {
            id == "note-1"
                ? ContextLocation(id: id, state: .visible, rects: [ContextRect(x: 10, y: 20, w: 300, h: 40)])
                : nil
        }
    }

    private struct Descriptor: Decodable {
        var endpoint: String
        var token: String
        var instance: String
        var pid: Int32
    }

    private func started(_ provider: any ContextProvider) async throws -> (ContextServer, Descriptor, URL) {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("acp-\(UUID().uuidString)", isDirectory: true)
        let app = ContextApp(id: "org.example.notes", name: "Notes", version: "1.0")
        let server = ContextServer(provider: provider, app: app, directory: directory)
        server.start()
        let file = directory.appendingPathComponent(
            ContextDescriptor.fileName(bundleID: app.id, pid: ProcessInfo.processInfo.processIdentifier)
        )
        for _ in 0..<200 where !FileManager.default.fileExists(atPath: file.path) {
            try await Task.sleep(for: .milliseconds(10))
        }
        let descriptor = try JSONDecoder().decode(Descriptor.self, from: Data(contentsOf: file))
        return (server, descriptor, file)
    }

    private func call(_ descriptor: Descriptor, _ method: String, uri: String? = nil) async throws -> [String: Any] {
        var params: [String: Any] = ["_meta": [
            "io.modelcontextprotocol/protocolVersion": "2026-07-28",
            "io.modelcontextprotocol/clientCapabilities": [String: Any](),
        ]]
        var request = URLRequest(url: try #require(URL(string: descriptor.endpoint)))
        request.httpMethod = "POST"
        request.setValue("Bearer \(descriptor.token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("2026-07-28", forHTTPHeaderField: "MCP-Protocol-Version")
        request.setValue(method, forHTTPHeaderField: "Mcp-Method")
        if let uri {
            params["uri"] = uri
            request.setValue(uri, forHTTPHeaderField: "Mcp-Name")
        }
        request.httpBody = try JSONSerialization.data(withJSONObject: [
            "jsonrpc": "2.0", "id": 1, "method": method, "params": params,
        ])
        let (data, _) = try await URLSession.shared.data(for: request)
        return try #require(try JSONSerialization.jsonObject(with: data) as? [String: Any])
    }

    private func document(_ answer: [String: Any]) throws -> [String: Any] {
        let result = try #require(answer["result"] as? [String: Any])
        let contents = try #require(result["contents"] as? [[String: Any]])
        let text = try #require(contents.first?["text"] as? String)
        return try #require(try JSONSerialization.jsonObject(with: Data(text.utf8)) as? [String: Any])
    }

    @Test
    func attributesAreWrittenAsLiterals() throws {
        let attributes: [String: ContextValue] = [
            "ref": "T-12", "done": false, "order": 3, "weight": 0.5,
            "tags": ["home", "week"], "lines": ["start": 3, "end": 4],
        ]
        #expect(attributes["ref"] == .string("T-12"))
        #expect(attributes["done"] == .bool(false))
        #expect(attributes["order"] == .integer(3))
        #expect(attributes["weight"] == .number(0.5))
        #expect(attributes["tags"] == .array([.string("home"), .string("week")]))
        #expect(attributes["lines"] == .object(["start": .integer(3), "end": .integer(4)]))
    }

    @Test
    func aProviderThatOnlySaysWhatIsOpen() async throws {
        let (server, descriptor, file) = try await started(Notes())
        #expect(descriptor.pid == ProcessInfo.processInfo.processIdentifier)

        let current = try document(try await call(descriptor, "resources/read", uri: "ambient://current"))
        #expect(current["instance"] as? String == descriptor.instance)
        #expect(current["protocol"] as? String == "0.2.3")
        let root = try #require(current["root"] as? [String: Any])
        #expect(root["title"] as? String == "Notes")
        #expect((root["children"] as? [[String: Any]])?.first?["title"] as? String == "Groceries")

        let templates = try await call(descriptor, "resources/templates/list")
        #expect(((templates["result"] as? [String: Any])?["resourceTemplates"] as? [Any])?.isEmpty == true)

        let location = try await call(descriptor, "resources/read", uri: "ambient://location/note-1")
        #expect((location["error"] as? [String: Any])?["code"] as? Int == -32602)

        server.stop()
        #expect(!FileManager.default.fileExists(atPath: file.path))
        #expect(!server.isRunning)
    }

    @MainActor
    final class WordedNotes: ContextProvider {
        func current() -> ContextElement {
            ContextElement(id: "app", role: .application, title: "Notes", children: [
                ContextElement(id: "note-1", role: .document, subrole: "note", title: "Groceries", focused: true),
            ])
        }

        func display() -> ContextDisplay? { ContextDisplay(title: "Groceries", detail: "3 items") }
    }

    @Test
    func aProviderThatWordsItsOwnLine() async throws {
        let (server, descriptor, _) = try await started(WordedNotes())
        defer { server.stop() }
        let current = try document(try await call(descriptor, "resources/read", uri: "ambient://current"))
        #expect(current["display"] as? [String: String] == ["title": "Groceries", "detail": "3 items"])
    }

    @Test
    func aProviderThatOnlySaysWhatIsOpenSendsNoDisplay() async throws {
        let (server, descriptor, _) = try await started(Notes())
        defer { server.stop() }
        let current = try document(try await call(descriptor, "resources/read", uri: "ambient://current"))
        #expect(Set(current.keys) == ["protocol", "instance", "root"])
    }

    @Test
    func aProviderThatAlsoSaysWhere() async throws {
        let (server, descriptor, _) = try await started(LocatedNotes())
        let templates = try await call(descriptor, "resources/templates/list")
        #expect(((templates["result"] as? [String: Any])?["resourceTemplates"] as? [Any])?.count == 1)

        let location = try document(try await call(descriptor, "resources/read", uri: "ambient://location/note-1"))
        #expect(location["state"] as? String == "visible")
        #expect(location["rects"] as? [[String: Double]] == [["x": 10, "y": 20, "w": 300, "h": 40]])
        server.stop()
    }

    /// An app with a server of its own: it mounts the responder on one
    /// path, hands it each request that arrives there, and writes the
    /// descriptor itself (RFC-0002). No `ContextServer` is involved.
    @Test
    func anAppMountsTheResponderOnItsOwnServer() async throws {
        let app = ContextApp(id: "org.example.notes", name: "Notes", version: "1.0")
        let token = ContextServer.random(bytes: 32)
        let instance = ContextServer.random(bytes: 6)
        let provider = Notes()
        let responder = try ContextResponder(
            app: app, instance: instance, token: token, path: "/ambient", check: .refuse,
            current: { await provider.current() }
        )

        // What the app's server would pass on for a request to that path.
        let body = try JSONSerialization.data(withJSONObject: [
            "jsonrpc": "2.0", "id": 1, "method": "resources/read",
            "params": ["uri": "ambient://current", "_meta": [
                "io.modelcontextprotocol/protocolVersion": "2026-07-28",
                "io.modelcontextprotocol/clientCapabilities": [String: Any](),
            ]],
        ])
        var request = ContextHTTPRequest(method: "POST", path: "/ambient", headers: [
            "authorization": "Bearer \(token)", "mcp-protocol-version": "2026-07-28",
            "mcp-method": "resources/read", "mcp-name": "ambient://current",
        ], body: body)
        let response = await responder.respond(to: request)
        #expect(response.status == 200)
        let answer = try #require(try JSONSerialization.jsonObject(with: response.body) as? [String: Any])
        #expect(try document(answer)["instance"] as? String == instance)

        request.headers["authorization"] = nil
        #expect(await responder.respond(to: request).status == 401)

        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("acp-\(UUID().uuidString)", isDirectory: true)
        let file = try ContextDescriptor(
            app: app, instance: instance, endpoint: "http://127.0.0.1:7801/ambient", token: token
        ).write(to: directory)
        let written = try JSONDecoder().decode(Descriptor.self, from: Data(contentsOf: file))
        #expect(written.endpoint == "http://127.0.0.1:7801/ambient")
        #expect(written.instance == instance)
        #expect(written.pid == ProcessInfo.processInfo.processIdentifier)
        try FileManager.default.removeItem(at: directory)
    }

    /// A provider that answers for another app (RFC-0004): the
    /// descriptor says which, and is named so a host finds it by that app.
    @Test func aDescriptorThatAnswersForAnotherApp() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("acp-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let helper = ContextApp(id: "org.example.helper", name: "Helper", version: "1.0")
        let own = ProcessInfo.processInfo.processIdentifier

        let file = try ContextDescriptor(
            app: helper, instance: "i1", endpoint: "http://127.0.0.1:7801/mcp", token: "t",
            answersFor: ContextTarget(id: "org.example.browser", pid: 4242)
        ).write(to: directory)
        #expect(file.lastPathComponent == "org.example.browser.4242.for.\(own).json")
        let written = try #require(try JSONSerialization.jsonObject(with: Data(contentsOf: file)) as? [String: Any])
        let target = try #require(written["for"] as? [String: Any])
        #expect(target["id"] as? String == "org.example.browser")
        #expect(target["pid"] as? Int == 4242)
        #expect(written["pid"] as? Int == Int(own))
        #expect((written["app"] as? [String: Any])?["id"] as? String == "org.example.helper")

        // An app's own descriptor says nothing of the kind.
        let plain = try ContextDescriptor(
            app: helper, instance: "i1", endpoint: "http://127.0.0.1:7801/mcp", token: "t"
        ).write(to: directory)
        let plainFields = try #require(try JSONSerialization.jsonObject(with: Data(contentsOf: plain)) as? [String: Any])
        #expect(plainFields["for"] == nil)

        // One left by a provider that is gone is removed; a live one, and
        // an app's own descriptor, are left alone.
        let dead = directory.appendingPathComponent("org.example.browser.4242.for.2147483646.json")
        try Data("{}".utf8).write(to: dead)
        let live = directory.appendingPathComponent("org.example.browser.4242.for.1.json")
        try Data("{}".utf8).write(to: live)
        ContextDescriptor.removeStale(answeringFor: "org.example.browser", pid: own, in: directory)
        #expect(!FileManager.default.fileExists(atPath: dead.path))
        #expect(!FileManager.default.fileExists(atPath: file.path))
        #expect(FileManager.default.fileExists(atPath: live.path))
        #expect(FileManager.default.fileExists(atPath: plain.path))
    }

    /// A running provider for another app: it writes the descriptor
    /// with `for`, answers `current` from its closure, and declares a
    /// watch only when told it can know of changes.
    @Test(arguments: [true, false])
    func aServerThatAnswersForAnotherApp(watch: Bool) async throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("acp-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let target = ContextTarget(id: "org.example.browser", pid: getppid())
        let server = ContextServer(
            app: ContextApp(id: "org.example.helper", name: "Helper", version: "1.0"),
            answersFor: target, directory: directory, watch: watch,
            current: {
                ContextElement(id: "app", role: .application, title: "Browser", attributes: ["via": "browser-extension"])
            }
        )
        server.start()
        let file = directory.appendingPathComponent(
            ContextDescriptor.fileName(answeringFor: target, pid: ProcessInfo.processInfo.processIdentifier)
        )
        for _ in 0..<200 where !FileManager.default.fileExists(atPath: file.path) {
            try await Task.sleep(for: .milliseconds(10))
        }
        let descriptor = try JSONDecoder().decode(Descriptor.self, from: Data(contentsOf: file))

        let current = try document(try await call(descriptor, "resources/read", uri: "ambient://current"))
        let root = try #require(current["root"] as? [String: Any])
        #expect((root["attributes"] as? [String: Any])?["via"] as? String == "browser-extension")

        let discover = try #require(try await call(descriptor, "server/discover")["result"] as? [String: Any])
        let resources = (discover["capabilities"] as? [String: Any])?["resources"] as? [String: Any]
        #expect((resources?["subscribe"] as? Bool ?? false) == watch)

        server.stop()
        #expect(!FileManager.default.fileExists(atPath: file.path))
    }
}
