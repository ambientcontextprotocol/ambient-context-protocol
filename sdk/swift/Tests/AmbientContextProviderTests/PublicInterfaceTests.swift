import Foundation
import Testing
import AmbientContextProvider

/// The package as an app uses it: only the public interface, over a real
/// socket, found through the descriptor file as a host finds it.
@MainActor
struct PublicInterfaceTests {
    final class Notes: ContextProvider {
        func current() -> ContextCurrent {
            ContextCurrent(focus: ["note-1"], items: [
                ContextItem(id: "note-1", type: "note", title: "Groceries", content: [.text("Eggs, rice")]),
            ])
        }
    }

    final class LocatedNotes: ContextProvider, ContextLocator {
        func current() -> ContextCurrent {
            ContextCurrent(focus: ["note-1"], items: [
                ContextItem(id: "note-1", type: "note", title: "Groceries", locatable: true),
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
    func aProviderThatOnlySaysWhatIsOpen() async throws {
        let (server, descriptor, file) = try await started(Notes())
        #expect(descriptor.pid == ProcessInfo.processInfo.processIdentifier)

        let current = try document(try await call(descriptor, "resources/read", uri: "ambient://current"))
        #expect(current["instance"] as? String == descriptor.instance)
        #expect((current["app"] as? [String: String])?["id"] == "org.example.notes")
        #expect((current["items"] as? [[String: Any]])?.first?["title"] as? String == "Groceries")

        let templates = try await call(descriptor, "resources/templates/list")
        #expect(((templates["result"] as? [String: Any])?["resourceTemplates"] as? [Any])?.isEmpty == true)

        let location = try await call(descriptor, "resources/read", uri: "ambient://location/note-1")
        #expect((location["error"] as? [String: Any])?["code"] as? Int == -32602)

        server.stop()
        #expect(!FileManager.default.fileExists(atPath: file.path))
        #expect(!server.isRunning)
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
}
