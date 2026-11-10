import Foundation

// The Ambient Context Protocol's types, draft 0.1, and the interface an
// app implements to be a provider: `ContextProvider` to say what the user
// has open and selected, and `ContextLocator` as well if it can also say
// where an item is on screen.

/// One block of an item's content, in MCP's `ContentBlock` form.
public enum ContextContent: Equatable, Sendable, Encodable {
    case text(String)
    case image(data: Data, mimeType: String)
    case resourceLink(uri: String, name: String)

    private enum Key: String, CodingKey { case type, text, data, mimeType, uri, name }

    public func encode(to encoder: Encoder) throws {
        var values = encoder.container(keyedBy: Key.self)
        switch self {
        case .text(let text):
            try values.encode("text", forKey: .type)
            try values.encode(text, forKey: .text)
        case .image(let data, let mimeType):
            try values.encode("image", forKey: .type)
            try values.encode(data.base64EncodedString(), forKey: .data)
            try values.encode(mimeType, forKey: .mimeType)
        case .resourceLink(let uri, let name):
            try values.encode("resource_link", forKey: .type)
            try values.encode(uri, forKey: .uri)
            try values.encode(name, forKey: .name)
        }
    }
}

/// A free-form value for an item's `payload`.
public enum ContextValue: Equatable, Sendable, Encodable {
    case string(String)
    case number(Double)
    case integer(Int)
    case bool(Bool)
    case array([ContextValue])
    case object([String: ContextValue])

    public func encode(to encoder: Encoder) throws {
        var value = encoder.singleValueContainer()
        switch self {
        case .string(let string): try value.encode(string)
        case .number(let number): try value.encode(number)
        case .integer(let integer): try value.encode(integer)
        case .bool(let bool): try value.encode(bool)
        case .array(let array): try value.encode(array)
        case .object(let object): try value.encode(object)
        }
    }
}

// A payload reads as the JSON it becomes: `["ref": "T-12", "done": false]`.
extension ContextValue: ExpressibleByStringLiteral, ExpressibleByBooleanLiteral, ExpressibleByIntegerLiteral,
    ExpressibleByFloatLiteral, ExpressibleByArrayLiteral, ExpressibleByDictionaryLiteral {
    public init(stringLiteral value: String) { self = .string(value) }
    public init(booleanLiteral value: Bool) { self = .bool(value) }
    public init(integerLiteral value: Int) { self = .integer(value) }
    public init(floatLiteral value: Double) { self = .number(value) }
    public init(arrayLiteral elements: ContextValue...) { self = .array(elements) }
    public init(dictionaryLiteral elements: (String, ContextValue)...) {
        self = .object(Dictionary(elements, uniquingKeysWith: { _, last in last }))
    }
}

/// One thing the user has open or selected.
public struct ContextItem: Equatable, Sendable, Encodable {
    public var id: String
    public var type: String
    public var title: String
    public var content: [ContextContent]?
    public var url: String?
    public var parent: String?
    public var locatable: Bool?
    public var payload: [String: ContextValue]?

    public init(
        id: String, type: String, title: String, content: [ContextContent]? = nil, url: String? = nil,
        parent: String? = nil, locatable: Bool? = nil, payload: [String: ContextValue]? = nil
    ) {
        self.id = id
        self.type = type
        self.title = title
        self.content = content
        self.url = url
        self.parent = parent
        self.locatable = locatable
        self.payload = payload
    }
}

/// The provider's answer to `current`, before the server adds the app
/// and the instance.
public struct ContextCurrent: Equatable, Sendable {
    public var focus: [String] = []
    public var items: [ContextItem] = []

    public init(focus: [String] = [], items: [ContextItem] = []) {
        self.focus = focus
        self.items = items
    }
}

/// A rectangle in global display coordinates: points, origin at the top
/// left of the primary display, y increasing downward.
public struct ContextRect: Equatable, Sendable, Encodable {
    public var x: Double
    public var y: Double
    public var w: Double
    public var h: Double

    public init(x: Double, y: Double, w: Double, h: Double) {
        self.x = x
        self.y = y
        self.w = w
        self.h = h
    }
}

/// Where an item is on screen, at one moment.
public struct ContextLocation: Equatable, Sendable, Encodable {
    public enum State: String, Sendable, Encodable { case visible, offscreen, gone }
    public enum Edge: String, Sendable, Encodable { case left, right, top, bottom }

    public var id: String
    public var state: State
    public var rects: [ContextRect]?
    public var window: Int?
    public var avoid: ContextRect?
    public var edge: Edge?

    public init(
        id: String, state: State, rects: [ContextRect]? = nil, window: Int? = nil,
        avoid: ContextRect? = nil, edge: Edge? = nil
    ) {
        self.id = id
        self.state = state
        self.rects = rects
        self.window = window
        self.avoid = avoid
        self.edge = edge
    }

    public static func gone(_ id: String) -> ContextLocation {
        ContextLocation(id: id, state: .gone)
    }
}

/// What an app implements to be a provider.
@MainActor
public protocol ContextProvider: AnyObject, Sendable {
    /// What the user has open and in focus, from state already in memory.
    func current() -> ContextCurrent
}

/// A provider that can also say where an item is on screen. Optional: a
/// provider that is not a locator offers no location resource, and a host
/// places its own interface by default.
@MainActor
public protocol ContextLocator: ContextProvider {
    /// Where the item is, or nil for an id this run never issued. An item
    /// that was issued and no longer exists is a location whose state is
    /// `gone`.
    func locate(_ id: String) -> ContextLocation?
}
