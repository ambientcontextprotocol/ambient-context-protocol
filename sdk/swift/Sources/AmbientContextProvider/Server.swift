import Foundation
import Network
import Observation

// A provider for the Ambient Context Protocol, version 0.2.2: a small
// MCP server on the loopback interface that answers `current` and
// `locate` as two resources, and the descriptor file that tells a host
// where it is. It is handed a `ContextProvider` and knows nothing else
// about the app it runs in. From its own listener it also offers `watch`
// (RFC-0006): a host may ask to be told when the answer to `current`
// changes, and the app says when with `ContextServer.contextDidChange()`.
//
// Three layers, each usable alone: `ContextHTTP` turns bytes into a
// request, `ContextResponder` turns a request into a response, and
// `ContextServer` owns the listener and the descriptor. `ContextServer`
// is the whole of it for an app with no server of its own. An app that
// already runs a local server mounts a `ContextResponder` on a path of
// that server and writes a `ContextDescriptor` itself (RFC-0002).

// MARK: - HTTP

/// One HTTP request, as a `ContextResponder` takes it.
public struct ContextHTTPRequest: Equatable, Sendable {
    public var method: String
    /// The request target without its query.
    public var path: String
    /// Header values by lowercased name.
    public var headers: [String: String]
    public var body: Data

    public init(method: String, path: String, headers: [String: String] = [:], body: Data = Data()) {
        self.method = method
        self.path = path
        self.headers = headers
        self.body = body
    }
}

/// One HTTP response, as a `ContextResponder` gives it. An app that
/// mounts the responder on its own server sends `status`, `headers` and
/// `body` as they are and adds no header of its own to them.
public struct ContextHTTPResponse: Equatable, Sendable {
    public var status: Int
    public var headers: [String: String]
    public var body: Data

    public init(status: Int, headers: [String: String] = [:], body: Data = Data()) {
        self.status = status
        self.headers = headers
        self.body = body
    }

    /// The response as bytes. Every response closes its connection, so
    /// the server never has to tell one request from the next.
    var serialized: Data {
        var head = "HTTP/1.1 \(status) \(Self.reason(status))\r\n"
        var all = headers
        all["Content-Length"] = String(body.count)
        all["Connection"] = "close"
        if !body.isEmpty, all["Content-Type"] == nil { all["Content-Type"] = "application/json" }
        for name in all.keys.sorted() { head += "\(name): \(all[name] ?? "")\r\n" }
        head += "\r\n"
        return Data(head.utf8) + body
    }

    private static func reason(_ status: Int) -> String {
        switch status {
        case 200: "OK"
        case 202: "Accepted"
        case 400: "Bad Request"
        case 401: "Unauthorized"
        case 403: "Forbidden"
        case 404: "Not Found"
        case 405: "Method Not Allowed"
        case 413: "Content Too Large"
        default: "Error"
        }
    }
}

enum ContextHTTP {
    enum Parse: Equatable, Sendable {
        /// More bytes are needed.
        case incomplete
        case malformed
        case tooLarge
        case request(ContextHTTPRequest)
    }

    static let headerLimit = 16 * 1024
    static let bodyLimit = 1024 * 1024

    /// Reads one request from the start of `buffer`. Only a body with a
    /// `Content-Length` is understood; that is what every JSON-RPC
    /// client sends for a body it holds in memory.
    static func parse(_ buffer: Data) -> Parse {
        let separator = Data("\r\n\r\n".utf8)
        guard let end = buffer.range(of: separator) else {
            return buffer.count > headerLimit ? .tooLarge : .incomplete
        }
        guard end.lowerBound - buffer.startIndex <= headerLimit,
              let head = String(data: buffer[buffer.startIndex..<end.lowerBound], encoding: .utf8) else {
            return .malformed
        }
        var lines = head.components(separatedBy: "\r\n")
        let requestLine = lines.removeFirst().split(separator: " ", omittingEmptySubsequences: false)
        guard requestLine.count == 3, requestLine[2].hasPrefix("HTTP/1."),
              !requestLine[0].isEmpty, requestLine[1].hasPrefix("/") else { return .malformed }

        var headers: [String: String] = [:]
        for line in lines {
            guard let colon = line.firstIndex(of: ":") else { return .malformed }
            let name = line[..<colon].lowercased()
            guard !name.isEmpty, !name.contains(" ") else { return .malformed }
            headers[name] = line[line.index(after: colon)...].trimmingCharacters(in: .whitespaces)
        }
        guard headers["transfer-encoding"] == nil else { return .malformed }

        var length = 0
        if let declared = headers["content-length"] {
            guard let value = Int(declared), value >= 0 else { return .malformed }
            guard value <= bodyLimit else { return .tooLarge }
            length = value
        }
        let bodyStart = end.upperBound
        guard buffer.endIndex - bodyStart >= length else { return .incomplete }

        let target = String(requestLine[1])
        let path = target.split(separator: "?", maxSplits: 1, omittingEmptySubsequences: false).first.map(String.init) ?? target
        return .request(ContextHTTPRequest(
            method: String(requestLine[0]),
            path: path,
            headers: headers,
            body: Data(buffer[bodyStart..<bodyStart + length])
        ))
    }
}

// MARK: - MCP

/// The app a provider speaks for: its bundle identifier, the name people
/// know it by, and its version.
public struct ContextApp: Equatable, Sendable, Encodable {
    public var id: String
    public var name: String
    public var version: String

    public init(id: String, name: String, version: String) {
        self.id = id
        self.name = name
        self.version = version
    }
}

/// What a responder does when the provider's tree breaks a rule that can
/// be told from the tree (`ContextTree.check`).
public enum ContextCheck: Sendable {
    /// Reports each distinct issue once and answers anyway. The default.
    case warn
    /// Answers with an error when there is an issue, for an app's own
    /// tests.
    case refuse
    /// Does not look.
    case off
}

/// Answers one HTTP request as an MCP server offering the protocol's two
/// resources: one request in, one response out, `Origin` refused and the
/// token checked before anything else. Everything it needs arrives with
/// the request, and the two closures reach the app.
///
/// `ContextServer` uses it on a listener of its own. An app with a local
/// server already running hands it every request that arrives on one
/// path of that server, before any other handling, and sends back what
/// it returns unchanged. That listener must be bound to `127.0.0.1`
/// only, and its logs must hold neither the token nor a response body.
public struct ContextResponder: Sendable {
    typealias App = ContextApp

    public static let protocolVersion = "0.2.2"
    public static let extensionID = "io.github.ambientcontextprotocol/context"
    /// The path `ContextServer` listens on, and the default.
    public static let endpointPath = "/mcp"
    static let currentURI = "ambient://current"
    static let locationPrefix = "ambient://location/"
    static let locationTemplate = "ambient://location/{id}"
    static let listenMethod = "subscriptions/listen"
    static let metaSubscription = "io.modelcontextprotocol/subscriptionId"
    /// The MCP revision this server is written for.
    static let mcpVersion = "2026-07-28"
    /// Earlier revisions, which open with `initialize`, served as well.
    static let legacyVersions = ["2025-11-25", "2025-06-18", "2025-03-26"]

    /// A path that does not begin with `/`, or carries a query or a
    /// fragment.
    public struct InvalidPath: Error, Equatable {
        public var path: String
    }

    private static let metaVersion = "io.modelcontextprotocol/protocolVersion"
    private static let metaCapabilities = "io.modelcontextprotocol/clientCapabilities"
    private static let metaServerInfo = "io.modelcontextprotocol/serverInfo"

    var app: App
    var instance: String
    var token: String
    /// The one path this responder answers.
    var path: String = ContextResponder.endpointPath
    var check: ContextCheck = .warn
    var report: @Sendable (ContextIssue) -> Void = ContextResponder.reportToStandardError
    var current: @Sendable () async -> ContextElement
    /// Nil for a provider that leaves the wording to the host.
    var display: (@Sendable () async -> ContextDisplay?)?
    /// The tree and its display read together, for a caller that can
    /// take both at one moment. When set, it is used in place of
    /// `current` and `display`.
    var answer: (@Sendable () async -> (ContextElement, ContextDisplay?))?
    /// Nil for a provider that does not report positions: the location
    /// template is then not offered and no location can be read.
    var locate: (@Sendable (String) async -> ContextLocation?)?
    /// The open watches, for a responder on `ContextServer`'s listener.
    /// Nil for one mounted on an app's own server, which answers one
    /// request with one response and so cannot hold a stream: it does
    /// not declare `subscribe` and does not know the method.
    var watches: ContextWatches?
    private let reported = Reported()

    init(
        app: App, instance: String, token: String,
        current: @escaping @Sendable () async -> ContextElement,
        display: (@Sendable () async -> ContextDisplay?)? = nil,
        locate: (@Sendable (String) async -> ContextLocation?)? = nil
    ) {
        self.app = app
        self.instance = instance
        self.token = token
        self.current = current
        self.display = display
        self.locate = locate
    }

    /// - Parameters:
    ///   - instance: The value minted for this run, the same one the
    ///     descriptor carries.
    ///   - token: Random, made at launch, used for this endpoint only.
    ///   - path: The path the responder is mounted at. It answers `404`
    ///     on any other.
    ///   - report: Where issues go under `warn` and `refuse`. Defaults to
    ///     one line each on standard error.
    ///   - current: The tree, rooted at an `application`.
    ///   - display: The app's own words for what `current` holds. Nil,
    ///     or a closure that answers nil, leaves the wording to the host.
    ///   - locate: Nil for a provider that does not report positions.
    public init(
        app: ContextApp, instance: String, token: String, path: String = ContextResponder.endpointPath,
        check: ContextCheck = .warn, report: (@Sendable (ContextIssue) -> Void)? = nil,
        current: @escaping @Sendable () async -> ContextElement,
        display: (@Sendable () async -> ContextDisplay?)? = nil,
        locate: (@Sendable (String) async -> ContextLocation?)? = nil
    ) throws {
        guard path.hasPrefix("/"), !path.contains("?"), !path.contains("#") else { throw InvalidPath(path: path) }
        self.init(app: app, instance: instance, token: token, current: current, display: display, locate: locate)
        self.path = path
        self.check = check
        if let report { self.report = report }
    }

    static let reportToStandardError: @Sendable (ContextIssue) -> Void = { issue in
        let line = "ambient context: \(issue.severity.rawValue): element '\(issue.element)': \(issue.message)\n"
        FileHandle.standardError.write(Data(line.utf8))
    }

    /// The issues already reported, so each is said once.
    private final class Reported: @unchecked Sendable {
        private let lock = NSLock()
        private var keys = Set<String>()

        func isNew(_ issue: ContextIssue) -> Bool {
            lock.lock()
            defer { lock.unlock() }
            // An app whose ids change every answer would otherwise fill this.
            if keys.count >= 1000 { keys.removeAll() }
            return keys.insert("\(issue.severity.rawValue)\u{0}\(issue.element)\u{0}\(issue.message)").inserted
        }
    }

    public func respond(to request: ContextHTTPRequest) async -> ContextHTTPResponse {
        switch await route(request) {
        case .response(let response): response
        // Only `ContextServer` sets `watches`, and it calls `route`.
        case .watch(let id): Self.failure(404, id: id, code: -32601, message: "Method not found")
        }
    }

    /// What a request gets: one response, or a watch to be held open on
    /// its connection.
    enum Route: Sendable {
        case response(ContextHTTPResponse)
        case watch(RequestID)
    }

    /// Every check a request has, the watch request included, before
    /// anything is answered or any stream opened.
    func route(_ request: ContextHTTPRequest) async -> Route {
        var watch: RequestID?
        let response = await answerOne(request, watch: &watch)
        if let watch { return .watch(watch) }
        return .response(response)
    }

    /// Sets `watch`, and returns a response that is not sent, when the
    /// request is a watch this responder will hold.
    private func answerOne(_ request: ContextHTTPRequest, watch: inout RequestID?) async -> ContextHTTPResponse {
        // A browser attaches Origin to a page's requests, and no page
        // should be calling this server. Refused before the token is
        // looked at, so a page learns nothing about it.
        if request.headers["origin"] != nil {
            return ContextHTTPResponse(status: 403)
        }
        guard let authorization = request.headers["authorization"],
              Self.sameBytes(authorization, "Bearer \(token)") else {
            return ContextHTTPResponse(status: 401, headers: ["WWW-Authenticate": "Bearer"])
        }
        guard request.path == path else {
            return ContextHTTPResponse(status: 404)
        }
        guard request.method == "POST" else {
            return ContextHTTPResponse(status: 405, headers: ["Allow": "POST"])
        }
        guard let message = try? JSONSerialization.jsonObject(with: request.body) as? [String: Any] else {
            return Self.failure(400, id: nil, code: -32700, message: "Parse error")
        }
        let id = message["id"].flatMap(RequestID.init)
        guard message["jsonrpc"] as? String == "2.0", let method = message["method"] as? String else {
            return Self.failure(400, id: id, code: -32600, message: "Invalid request")
        }
        // A notification asks for nothing.
        guard let id else { return ContextHTTPResponse(status: 202) }

        let params = message["params"] as? [String: Any] ?? [:]
        let meta = params["_meta"] as? [String: Any] ?? [:]
        let header = request.headers["mcp-protocol-version"]
        let declared = meta[Self.metaVersion] as? String

        // An older client names its revision in the header alone, or
        // not at all, and never in the body.
        let legacy = method == "initialize"
            || (declared == nil && header.map(Self.legacyVersions.contains) != false)

        if !legacy {
            if let refusal = Self.validate(request: request, method: method, params: params, meta: meta, id: id) {
                return refusal
            }
        }
        if method == Self.listenMethod, !legacy, watches != nil {
            // Whatever else the host asked for, it is told about
            // `ambient://current` or about nothing.
            let filter = params["notifications"] as? [String: Any]
            guard let named = filter?["resourceSubscriptions"] as? [String], named.contains(Self.currentURI) else {
                return Self.failure(400, id: id, code: -32602, message: "Only \(Self.currentURI) can be watched")
            }
            watch = id
            return ContextHTTPResponse(status: 200)
        }
        return await dispatch(method, params: params, id: id, legacy: legacy)
    }

    /// The checks revision 2026-07-28 puts on every request: the version
    /// and the client's capabilities in the body, and headers that agree
    /// with the body.
    private static func validate(
        request: ContextHTTPRequest, method: String, params: [String: Any], meta: [String: Any], id: RequestID
    ) -> ContextHTTPResponse? {
        guard let declared = meta[metaVersion] as? String else {
            return failure(400, id: id, code: -32602, message: "Missing \(metaVersion) in _meta")
        }
        guard let header = request.headers["mcp-protocol-version"] else {
            return failure(400, id: id, code: -32020, message: "Header mismatch: MCP-Protocol-Version header is missing")
        }
        guard header == declared else {
            return failure(400, id: id, code: -32020, message: "Header mismatch: MCP-Protocol-Version header value '\(header)' does not match body value '\(declared)'")
        }
        guard declared == mcpVersion else {
            return failure(400, id: id, code: -32022, message: "Unsupported protocol version", data: [
                "supported": [mcpVersion] + legacyVersions,
                "requested": declared,
            ])
        }
        guard meta[metaCapabilities] is [String: Any] else {
            return failure(400, id: id, code: -32602, message: "Missing \(metaCapabilities) in _meta")
        }
        guard let named = request.headers["mcp-method"] else {
            return failure(400, id: id, code: -32020, message: "Header mismatch: Mcp-Method header is missing")
        }
        guard named == method else {
            return failure(400, id: id, code: -32020, message: "Header mismatch: Mcp-Method header value '\(named)' does not match body value '\(method)'")
        }
        if method == "resources/read", let uri = params["uri"] as? String {
            guard let name = request.headers["mcp-name"].map(decodedHeaderValue) else {
                return failure(400, id: id, code: -32020, message: "Header mismatch: Mcp-Name header is missing")
            }
            guard name == uri else {
                return failure(400, id: id, code: -32020, message: "Header mismatch: Mcp-Name header value '\(name)' does not match body value '\(uri)'")
            }
        }
        return nil
    }

    private func dispatch(_ method: String, params: [String: Any], id: RequestID, legacy: Bool) async -> ContextHTTPResponse {
        switch method {
        case "initialize":
            let asked = params["protocolVersion"] as? String
            let version = asked.flatMap { Self.legacyVersions.contains($0) ? $0 : nil } ?? Self.legacyVersions[0]
            return Self.success(id: id, legacy: true, result: [
                "protocolVersion": version,
                "capabilities": [
                    "resources": [String: Any](),
                    "experimental": [Self.extensionID: ["version": Self.protocolVersion]],
                ],
                "serverInfo": ["name": app.name, "version": app.version],
            ])
        case "ping":
            return Self.success(id: id, legacy: legacy, result: [:])
        case "server/discover" where !legacy:
            return Self.success(id: id, legacy: false, result: [
                "supportedVersions": [Self.mcpVersion] + Self.legacyVersions,
                "capabilities": [
                    "resources": watches == nil ? [String: Any]() : ["subscribe": true],
                    "extensions": [Self.extensionID: ["version": Self.protocolVersion]],
                ],
                "_meta": [Self.metaServerInfo: ["name": app.name, "version": app.version]],
            ])
        case "resources/list":
            return Self.success(id: id, legacy: legacy, result: ["resources": [[
                "uri": Self.currentURI,
                "name": "current",
                "title": "Current context",
                "description": "What the user has open and selected in this app, right now.",
                "mimeType": "application/json",
            ]]])
        case "resources/templates/list":
            let templates: [[String: Any]] = locate == nil ? [] : [[
                "uriTemplate": Self.locationTemplate,
                "name": "location",
                "title": "Location of an element",
                "description": "Where an element from the current context is on screen.",
                "mimeType": "application/json",
            ]]
            return Self.success(id: id, legacy: legacy, result: ["resourceTemplates": templates])
        case "resources/read":
            guard let uri = params["uri"] as? String else {
                return Self.failure(200, id: id, code: -32602, message: "Missing uri")
            }
            guard let text = await read(uri) else {
                // Earlier revisions used their own code for this.
                return Self.failure(200, id: id, code: legacy ? -32002 : -32602, message: "Resource not found", data: ["uri": uri])
            }
            return Self.success(id: id, legacy: legacy, result: ["contents": [[
                "uri": uri,
                "mimeType": "application/json",
                "text": text,
            ]]])
        default:
            return Self.failure(legacy ? 200 : 404, id: id, code: -32601, message: "Method not found")
        }
    }

    /// The JSON document a resource holds, or nil when there is no such
    /// resource.
    private func read(_ uri: String) async -> String? {
        if uri == Self.currentURI {
            let root: ContextElement
            let words: ContextDisplay?
            if let answer {
                (root, words) = await answer()
            } else {
                root = await current()
                words = await display?()
            }
            guard inspect(root) else { return nil }
            watches?.remember(Self.signature(root, words))
            return Self.json(CurrentResult(
                protocol: Self.protocolVersion, instance: instance, display: words?.sent, root: root
            ))
        }
        guard let locate, uri.hasPrefix(Self.locationPrefix),
              let id = String(uri.dropFirst(Self.locationPrefix.count)).removingPercentEncoding,
              ContextTree.isElementID(id),
              let location = await locate(id) else { return nil }
        return Self.json(location)
    }

    /// What a watch compares to tell whether the answer to `current`
    /// changed: the tree and the display as they would be sent, with
    /// `hovered` left out, since the pointer moving is not a change a
    /// watch reports. It stays in this process.
    func signature() async -> String? {
        if let answer {
            let (root, words) = await answer()
            return Self.signature(root, words)
        }
        let root = await current()
        return Self.signature(root, await display?())
    }

    private static func signature(_ root: ContextElement, _ words: ContextDisplay?) -> String? {
        json(Signature(display: words?.sent, root: unhovered(root)))
    }

    private static func unhovered(_ element: ContextElement) -> ContextElement {
        var copy = element
        copy.hovered = false
        copy.children = element.children.map(unhovered)
        return copy
    }

    private struct Signature: Encodable {
        var display: ContextDisplay?
        var root: ContextElement
    }

    /// Applies the `check` setting to a provider's answer. False only
    /// under `refuse`, when the tree has an issue; the read then fails.
    private func inspect(_ root: ContextElement) -> Bool {
        if case .off = check { return true }
        let issues = ContextTree.check(root)
        for issue in issues where reported.isNew(issue) { report(issue) }
        if case .refuse = check { return issues.isEmpty }
        return true
    }

    /// The answer to `current`: these fields and no others. `display`
    /// is left out when the provider has none.
    private struct CurrentResult: Encodable {
        var `protocol`: String
        var instance: String
        var display: ContextDisplay?
        var root: ContextElement
    }

    /// A header value as the client meant it: MCP carries a value that is
    /// not plain ASCII as `=?base64?…?=`.
    static func decodedHeaderValue(_ value: String) -> String {
        let prefix = "=?base64?", suffix = "?="
        guard value.hasPrefix(prefix), value.hasSuffix(suffix), value.count >= prefix.count + suffix.count,
              let data = Data(base64Encoded: String(value.dropFirst(prefix.count).dropLast(suffix.count))),
              let decoded = String(data: data, encoding: .utf8) else { return value }
        return decoded
    }

    // MARK: JSON-RPC envelopes

    /// A request's id, which the response repeats as it came.
    enum RequestID: Equatable, Sendable {
        case string(String)
        case number(Int)

        init?(_ value: Any) {
            if let string = value as? String {
                self = .string(string)
            } else if let number = value as? NSNumber, CFGetTypeID(number) != CFBooleanGetTypeID() {
                self = .number(number.intValue)
            } else {
                return nil
            }
        }

        var value: Any {
            switch self {
            case .string(let string): string
            case .number(let number): number
            }
        }
    }

    /// One message on a watch's stream, as a server-sent event.
    static func event(_ message: [String: Any]) -> Data {
        Data("event: message\ndata: ".utf8) + data(message) + Data("\n\n".utf8)
    }

    /// The first message on a watch: what the provider agreed to tell.
    static func acknowledgment(_ id: RequestID) -> Data {
        event(["jsonrpc": "2.0", "method": "notifications/subscriptions/acknowledged", "params": [
            "_meta": [metaSubscription: id.value],
            "notifications": ["resourceSubscriptions": [currentURI]],
        ]])
    }

    /// The notice: the answer to `current` changed. It says no more.
    static func notice(_ id: RequestID) -> Data {
        event(["jsonrpc": "2.0", "method": "notifications/resources/updated", "params": [
            "_meta": [metaSubscription: id.value],
            "uri": currentURI,
        ]])
    }

    /// The answer to the watch request, which ends the watch.
    static func completion(_ id: RequestID) -> Data {
        event(["jsonrpc": "2.0", "id": id.value, "result": [
            "resultType": "complete",
            "_meta": [metaSubscription: id.value],
        ]])
    }

    private static func success(id: RequestID, legacy: Bool, result: [String: Any]) -> ContextHTTPResponse {
        var result = result
        if !legacy { result["resultType"] = "complete" }
        return ContextHTTPResponse(status: 200, body: data(["jsonrpc": "2.0", "id": id.value, "result": result]))
    }

    private static func failure(
        _ status: Int, id: RequestID?, code: Int, message: String, data: [String: Any]? = nil
    ) -> ContextHTTPResponse {
        var error: [String: Any] = ["code": code, "message": message]
        if let data { error["data"] = data }
        return ContextHTTPResponse(status: status, body: self.data([
            "jsonrpc": "2.0", "id": id?.value ?? NSNull(), "error": error,
        ]))
    }

    private static func data(_ object: [String: Any]) -> Data {
        (try? JSONSerialization.data(withJSONObject: object, options: [.sortedKeys, .withoutEscapingSlashes])) ?? Data("{}".utf8)
    }

    private static func json(_ value: some Encodable) -> String? {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
        return (try? encoder.encode(value)).flatMap { String(data: $0, encoding: .utf8) }
    }

    /// Compares without stopping at the first difference, so the time a
    /// refusal takes says nothing about how much of the token matched.
    private static func sameBytes(_ a: String, _ b: String) -> Bool {
        let left = Array(a.utf8), right = Array(b.utf8)
        var difference = UInt8(left.count == right.count ? 0 : 1)
        for index in 0..<min(left.count, right.count) { difference |= left[index] ^ right[index] }
        return difference == 0
    }
}

// MARK: - Descriptor

/// The app a provider answers for when it is not that app's own process
/// (RFC-0004, a draft): a helper the app started, such as the program a
/// browser runs for an extension.
public struct ContextTarget: Equatable, Sendable, Encodable {
    /// The bundle identifier of the app answered for.
    public var id: String
    /// That app's process id, which must be this provider's parent.
    public var pid: Int32

    public init(id: String, pid: Int32) {
        self.id = id
        self.pid = pid
    }
}

/// The file a running provider keeps so a host can find it.
public struct ContextDescriptor: Equatable, Sendable, Encodable {
    public var `protocol`: String
    public var app: ContextApp
    public var pid: Int32
    public var instance: String
    public var endpoint: String
    public var token: String
    public var started: String
    /// Set only by a provider that answers for another app. `app` and
    /// `pid` then describe the provider's own program and process.
    public var answersFor: ContextTarget?

    private enum CodingKeys: String, CodingKey {
        case `protocol`, app, pid, instance, endpoint, token, started
        case answersFor = "for"
    }

    /// - Parameters:
    ///   - endpoint: `http://127.0.0.1:<port><path>`, the path being the
    ///     one the responder answers.
    ///   - started: When the provider started, in UTC, ISO 8601.
    public init(
        protocol: String = ContextResponder.protocolVersion, app: ContextApp,
        pid: Int32 = ProcessInfo.processInfo.processIdentifier, instance: String, endpoint: String, token: String,
        started: String = ISO8601DateFormatter().string(from: Date()), answersFor: ContextTarget? = nil
    ) {
        self.protocol = `protocol`
        self.app = app
        self.pid = pid
        self.instance = instance
        self.endpoint = endpoint
        self.token = token
        self.started = started
        self.answersFor = answersFor
    }

    /// `~/Library/Application Support/AmbientContext/providers`.
    public static var defaultDirectory: URL {
        FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("AmbientContext", isDirectory: true)
            .appendingPathComponent("providers", isDirectory: true)
    }

    public static func fileName(bundleID: String, pid: Int32) -> String {
        "\(bundleID).\(pid).json"
    }

    /// The name of a descriptor that answers for another app: the app's
    /// identifier and process id first, so a host finds it by the app in
    /// front, then the provider's own process id.
    public static func fileName(answeringFor target: ContextTarget, pid: Int32) -> String {
        "\(target.id).\(target.pid).for.\(pid).json"
    }

    /// The name this descriptor is written under.
    public var fileName: String {
        answersFor.map { Self.fileName(answeringFor: $0, pid: pid) } ?? Self.fileName(bundleID: app.id, pid: pid)
    }

    /// Writes the file where only the user can read it, under a temporary
    /// name first so a host never reads half of it. Returns its address,
    /// which the caller removes when the provider stops. `ContextServer`
    /// calls it; so does an app that mounts a `ContextResponder` on its
    /// own listener, once that listener is up.
    @discardableResult
    public func write(to directory: URL = ContextDescriptor.defaultDirectory) throws -> URL {
        let files = FileManager.default
        try files.createDirectory(at: directory, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
        try files.setAttributes([.posixPermissions: 0o700], ofItemAtPath: directory.path)

        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]
        let data = try encoder.encode(self)

        let destination = directory.appendingPathComponent(fileName)
        let temporary = directory.appendingPathComponent(".\(UUID().uuidString).tmp")
        guard files.createFile(atPath: temporary.path, contents: data, attributes: [.posixPermissions: 0o600]) else {
            throw CocoaError(.fileWriteUnknown)
        }
        guard rename(temporary.path, destination.path) == 0 else {
            try? files.removeItem(at: temporary)
            throw CocoaError(.fileWriteUnknown)
        }
        return destination
    }

    /// Removes descriptors this app left behind: those naming a process
    /// that is no longer running, and any naming `pid` itself, which a
    /// crashed run with the same process id would have written.
    public static func removeStale(bundleID: String, pid: Int32, in directory: URL) {
        let files = FileManager.default
        guard let names = try? files.contentsOfDirectory(atPath: directory.path) else { return }
        let prefix = bundleID + "."
        for name in names where name.hasPrefix(prefix) && name.hasSuffix(".json") {
            let middle = name.dropFirst(prefix.count).dropLast(".json".count)
            guard let owner = Int32(middle) else { continue }
            let running = kill(owner, 0) == 0 || errno == EPERM
            if owner == pid || !running {
                try? files.removeItem(at: directory.appendingPathComponent(name))
            }
        }
    }
}

extension ContextDescriptor {
    /// The same for descriptors that answer for the app `bundleID`: those
    /// whose provider is no longer running, and any naming `pid` itself.
    public static func removeStale(answeringFor bundleID: String, pid: Int32, in directory: URL) {
        let files = FileManager.default
        guard let names = try? files.contentsOfDirectory(atPath: directory.path) else { return }
        let prefix = bundleID + "."
        for name in names where name.hasPrefix(prefix) && name.hasSuffix(".json") {
            // `<app pid>.for.<provider pid>` is what is left of the name.
            let parts = name.dropFirst(prefix.count).dropLast(".json".count).split(separator: ".")
            guard parts.count == 3, Int32(parts[0]) != nil, parts[1] == "for", let owner = Int32(parts[2]) else {
                continue
            }
            let running = kill(owner, 0) == 0 || errno == EPERM
            if owner == pid || !running {
                try? files.removeItem(at: directory.appendingPathComponent(name))
            }
        }
    }
}

// MARK: - Server

/// The listener and the descriptor. Start it and a host can find and
/// read the provider; stop it and both are gone.
@MainActor
public final class ContextServer {
    /// The app's own provider, or nil for one that answers for another
    /// app and is read through `delegated`.
    private let provider: (any ContextProvider)?
    private let delegated: (@Sendable () async -> ContextElement)?
    private let app: ContextResponder.App
    private let answersFor: ContextTarget?
    private let directory: URL
    private var listener: NWListener?
    private var descriptorURL: URL?
    private let queue: DispatchQueue
    private let watches: ContextWatches

    /// The endpoint, once the listener is up.
    public private(set) var endpoint: URL?
    public private(set) var token: String?
    public private(set) var instance: String?

    public var isRunning: Bool { listener != nil }

    public init(provider: any ContextProvider, app: ContextApp, directory: URL = ContextDescriptor.defaultDirectory) {
        self.provider = provider
        self.delegated = nil
        self.app = app
        self.answersFor = nil
        self.directory = directory
        let queue = DispatchQueue(label: "org.humanitas.ambient-context.server")
        self.queue = queue
        self.watches = ContextWatches(queue: queue)
    }

    /// A provider that answers for another app, which started it
    /// (RFC-0004, a draft). `app` names this program; `answersFor` names
    /// the app whose context it reports. Such a provider gets its answer
    /// from the app each time it is asked, so `current` may wait; it must
    /// come back well inside a host's time limit, with the application
    /// alone if the app did not answer.
    public init(
        app: ContextApp, answersFor: ContextTarget, directory: URL = ContextDescriptor.defaultDirectory,
        current: @escaping @Sendable () async -> ContextElement
    ) {
        self.provider = nil
        self.delegated = current
        self.app = app
        self.answersFor = answersFor
        self.directory = directory
        let queue = DispatchQueue(label: "org.humanitas.ambient-context.server")
        self.queue = queue
        self.watches = ContextWatches(queue: queue)
    }

    /// Tells any host that is watching that the answer to `current` may
    /// have changed. Call it from the app's own events: the selection
    /// changed, the focus moved, a document opened or closed, a title
    /// changed. Not from a timer, and not for the pointer moving, which
    /// is not a change a watch reports.
    ///
    /// An app whose `current()` reads `@Observable` state need not call
    /// it for that state: the server observes what the provider reads.
    /// It is for everything else, such as a text view's selection.
    ///
    /// It costs nothing when no host is watching, and may be called as
    /// often as the app likes and from any thread: calls are gathered
    /// into at most one notice in 250 milliseconds, the last change
    /// always tells, and a call after which the answer is the same as
    /// before tells nothing.
    public nonisolated func contextDidChange() {
        watches.changed()
    }

    /// The watches hosts hold open now.
    var watchCount: Int { watches.count }

    /// For tests: the least time between two notices on one watch, and
    /// how long a watch may stay quiet before a keep-alive. Set before
    /// `start()`.
    var watchTiming: (interval: TimeInterval, keepAlive: TimeInterval) {
        get { watches.timing }
        set { watches.timing = newValue }
    }

    /// Opens the listener on the loopback interface, on a port the
    /// system picks, and writes the descriptor once it is ready. A new
    /// token and instance are made on every start.
    public func start() {
        guard listener == nil else { return }
        let token = Self.random(bytes: 32)
        let instance = Self.random(bytes: 6)
        let pid = ProcessInfo.processInfo.processIdentifier
        if let answersFor {
            ContextDescriptor.removeStale(answeringFor: answersFor.id, pid: pid, in: directory)
        } else {
            ContextDescriptor.removeStale(bundleID: app.id, pid: pid, in: directory)
        }

        let parameters = NWParameters.tcp
        parameters.requiredLocalEndpoint = .hostPort(host: .ipv4(.loopback), port: .any)
        parameters.acceptLocalOnly = true
        guard let listener = try? NWListener(using: parameters) else { return }

        var responder: ContextResponder
        if let provider {
            // Only a provider that is also a locator answers `locate`.
            var locate: (@Sendable (String) async -> ContextLocation?)?
            if let locator = provider as? any ContextLocator {
                locate = { await locator.locate($0) }
            }
            responder = ContextResponder(
                app: app, instance: instance, token: token,
                current: { await provider.current() },
                locate: locate
            )
            // One turn on the main actor for both, so the words describe the
            // tree they are sent with.
            // Whatever `@Observable` state the provider reads to answer is
            // observed as it is read, so a change to it is a change the
            // server hears of without the app calling `contextDidChange()`.
            let watches = watches
            responder.answer = {
                await MainActor.run {
                    withObservationTracking {
                        (provider.current(), provider.display())
                    } onChange: {
                        watches.changed()
                    }
                }
            }
        } else if let delegated {
            // A provider for another app asks that app each time, so there
            // is nothing here to observe: it calls `contextDidChange()` when
            // the app tells it something moved.
            responder = ContextResponder(app: app, instance: instance, token: token, current: delegated)
        } else {
            return
        }
        responder.watches = watches
        let answering = responder
        watches.signature = { await answering.signature() }
        let queue = queue
        listener.newConnectionHandler = { connection in
            ContextConnection(connection, responder: answering).start(on: queue)
        }
        listener.stateUpdateHandler = { [weak self, weak listener] state in
            guard case .ready = state, let port = listener?.port?.rawValue else { return }
            Task { @MainActor in self?.listenerIsReady(listener, port: port, pid: pid) }
        }
        self.listener = listener
        self.token = token
        self.instance = instance
        // An app that allows sudden termination is killed on quit without
        // `applicationWillTerminate`, which would leave the descriptor
        // behind; hold that off for as long as there is one to remove.
        ProcessInfo.processInfo.disableSuddenTermination()
        listener.start(queue: queue)
    }

    private func listenerIsReady(_ ready: NWListener?, port: UInt16, pid: Int32) {
        guard let ready, ready === listener, let token, let instance, descriptorURL == nil else { return }
        let endpoint = "http://127.0.0.1:\(port)\(ContextResponder.endpointPath)"
        self.endpoint = URL(string: endpoint)
        let descriptor = ContextDescriptor(
            protocol: ContextResponder.protocolVersion,
            app: app,
            pid: pid,
            instance: instance,
            endpoint: endpoint,
            token: token,
            started: ISO8601DateFormatter().string(from: Date()),
            answersFor: answersFor
        )
        descriptorURL = try? descriptor.write(to: directory)
    }

    /// Ends every watch, closes the listener and removes the descriptor.
    public func stop() {
        let wasRunning = listener != nil
        watches.endAll()
        listener?.cancel()
        listener = nil
        if let descriptorURL { try? FileManager.default.removeItem(at: descriptorURL) }
        descriptorURL = nil
        endpoint = nil
        token = nil
        instance = nil
        // Last: once sudden termination is allowed again, a quit already
        // under way kills the process at this line.
        if wasRunning { ProcessInfo.processInfo.enableSuddenTermination() }
    }

    /// Random bytes as URL-safe text: what `ContextServer` uses for the
    /// token (32 bytes) and the instance (6). For an app that mounts a
    /// `ContextResponder` itself and needs both.
    public nonisolated static func random(bytes count: Int) -> String {
        var generator = SystemRandomNumberGenerator()
        let data = Data((0..<count).map { _ in UInt8.random(in: .min ... .max, using: &generator) })
        return data.base64EncodedString()
            .replacingOccurrences(of: "+", with: "-")
            .replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: "=", with: "")
    }
}

/// One accepted connection: reads a request, answers it, closes; or,
/// for a watch, answers with a stream and holds it open. All of its
/// state is touched only on the server's queue.
private final class ContextConnection: @unchecked Sendable {
    private let connection: NWConnection
    private let responder: ContextResponder
    private var buffer = Data()
    private var watching = false

    init(_ connection: NWConnection, responder: ContextResponder) {
        self.connection = connection
        self.responder = responder
    }

    func start(on queue: DispatchQueue) {
        connection.start(queue: queue)
        // A client that connects and says nothing is dropped. A watch is
        // meant to stay.
        queue.asyncAfter(deadline: .now() + 10) { [weak self] in
            guard let self, !self.watching else { return }
            self.connection.cancel()
        }
        receive(on: queue)
    }

    private func receive(on queue: DispatchQueue) {
        connection.receive(minimumIncompleteLength: 1, maximumLength: 64 * 1024) { [self] data, _, finished, error in
            if let data { buffer.append(data) }
            switch ContextHTTP.parse(buffer) {
            case .request(let request):
                let responder = responder
                Task { [self] in
                    let route = await responder.route(request)
                    queue.async { [self] in
                        switch route {
                        case .response(let response): send(response)
                        case .watch(let id): watch(id)
                        }
                    }
                }
            case .malformed:
                send(ContextHTTPResponse(status: 400))
            case .tooLarge:
                send(ContextHTTPResponse(status: 413))
            case .incomplete:
                if finished || error != nil { connection.cancel() } else { receive(on: queue) }
            }
        }
    }

    private func send(_ response: ContextHTTPResponse) {
        let connection = connection
        connection.send(content: response.serialized, completion: .contentProcessed { _ in connection.cancel() })
    }

    /// Answers with an event stream and hands the connection to the
    /// watches, which write to it from here on.
    private func watch(_ id: ContextResponder.RequestID) {
        guard let watches = responder.watches else { return connection.cancel() }
        watching = true
        let head = "HTTP/1.1 200 OK\r\nCache-Control: no-store\r\nConnection: close\r\n"
            + "Content-Type: text/event-stream\r\nX-Accel-Buffering: no\r\n\r\n"
        let watch = ContextWatch(connection: connection, id: id)
        watch.write(Data(head.utf8) + ContextResponder.acknowledgment(id))
        watches.add(watch)
        listenForTheEnd(of: watch, in: watches)
    }

    /// A host ends a watch by closing the connection. Nothing more is
    /// read from it; anything it sends is dropped.
    private func listenForTheEnd(of watch: ContextWatch, in watches: ContextWatches) {
        connection.receive(minimumIncompleteLength: 1, maximumLength: 64 * 1024) { [self] _, _, finished, error in
            if finished || error != nil {
                watches.remove(watch)
                connection.cancel()
            } else {
                listenForTheEnd(of: watch, in: watches)
            }
        }
    }
}

/// One watch: a connection held open, and the id of the request that
/// opened it, which every message on it carries.
final class ContextWatch: @unchecked Sendable {
    let connection: NWConnection
    let id: ContextResponder.RequestID
    var lastWrite = DispatchTime.now()

    init(connection: NWConnection, id: ContextResponder.RequestID) {
        self.connection = connection
        self.id = id
    }

    func write(_ data: Data) {
        lastWrite = .now()
        connection.send(content: data, completion: .contentProcessed { _ in })
    }

    /// The completion result, then the close.
    func end() {
        let connection = connection
        connection.send(content: ContextResponder.completion(id), completion: .contentProcessed { _ in connection.cancel() })
    }
}

/// The watches open on one `ContextServer`, and when each is told. Its
/// state is touched only on the server's queue.
final class ContextWatches: @unchecked Sendable {
    /// How many watches are held at once. One more ends the oldest.
    static let limit = 8

    private let queue: DispatchQueue
    private var open: [ContextWatch] = []
    /// The answer last given to a read or last announced.
    private var last: String?
    private var lastNotice: DispatchTime?
    private var scheduled = false
    private var computing = false
    private var changedMeanwhile = false
    private var keepAliveTimer: DispatchSourceTimer?
    private var interval: TimeInterval = 0.25
    private var keepAlive: TimeInterval = 10
    private var answer: (@Sendable () async -> String?)?

    init(queue: DispatchQueue) {
        self.queue = queue
    }

    var count: Int { queue.sync { open.count } }

    var timing: (interval: TimeInterval, keepAlive: TimeInterval) {
        get { queue.sync { (interval, keepAlive) } }
        set { queue.sync { (interval, keepAlive) = newValue } }
    }

    /// How the answer to `current` is had, as text to compare.
    var signature: (@Sendable () async -> String?)? {
        get { queue.sync { answer } }
        set { queue.sync { answer = newValue } }
    }

    /// A read was answered with this.
    func remember(_ signature: String?) {
        guard let signature else { return }
        queue.async { [self] in last = signature }
    }

    func add(_ watch: ContextWatch) {
        dispatchPrecondition(condition: .onQueue(queue))
        open.append(watch)
        if open.count > Self.limit { open.removeFirst().end() }
        startKeepAlive()
        // The host read before it asked to watch. If the answer moved in
        // between, it is told now.
        if last != nil { schedule() }
    }

    func remove(_ watch: ContextWatch) {
        dispatchPrecondition(condition: .onQueue(queue))
        open.removeAll { $0 === watch }
        if open.isEmpty { stopKeepAlive() }
    }

    /// Ends every watch as the protocol asks: the completion result,
    /// then the close.
    func endAll() {
        queue.sync {
            for watch in open { watch.end() }
            open.removeAll()
            stopKeepAlive()
            last = nil
        }
    }

    /// The app says its answer may have changed.
    func changed() {
        queue.async { [self] in schedule() }
    }

    /// At most one look, and so one notice, in any `interval`; a change
    /// that arrives while waiting or looking is not lost.
    private func schedule() {
        guard !open.isEmpty else { return }
        if computing { changedMeanwhile = true; return }
        guard !scheduled else { return }
        scheduled = true
        var wait = 0.0
        if let lastNotice {
            let since = Double(DispatchTime.now().uptimeNanoseconds - lastNotice.uptimeNanoseconds) / 1e9
            wait = max(0, interval - since)
        }
        queue.asyncAfter(deadline: .now() + wait) { [self] in look() }
    }

    private func look() {
        scheduled = false
        guard !open.isEmpty, let answer else { return }
        computing = true
        Task { [self] in
            let now = await answer()
            queue.async { [self] in
                computing = false
                if let now, now != last {
                    last = now
                    lastNotice = .now()
                    for watch in open { watch.write(ContextResponder.notice(watch.id)) }
                }
                if changedMeanwhile {
                    changedMeanwhile = false
                    schedule()
                }
            }
        }
    }

    private func startKeepAlive() {
        guard keepAliveTimer == nil else { return }
        let timer = DispatchSource.makeTimerSource(queue: queue)
        let tick = keepAlive / 2
        timer.schedule(deadline: .now() + tick, repeating: tick)
        timer.setEventHandler { [self] in
            let quietSince = DispatchTime.now().uptimeNanoseconds
            for watch in open where Double(quietSince - watch.lastWrite.uptimeNanoseconds) / 1e9 >= keepAlive / 2 {
                watch.write(Data(": keep-alive\n\n".utf8))
            }
        }
        timer.resume()
        keepAliveTimer = timer
    }

    private func stopKeepAlive() {
        keepAliveTimer?.cancel()
        keepAliveTimer = nil
    }
}
