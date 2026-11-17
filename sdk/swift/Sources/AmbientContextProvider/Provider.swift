import Foundation

// The Ambient Context Protocol's types, version 0.2.2 (RFC-0001, the
// element model; RFC-0003, the hovered state; RFC-0005, display), and the interface an app
// implements to be a provider: `ContextProvider` to say what the user
// has open and selected, and `ContextLocator` as well if it can also say
// where an element is on screen.

/// One block of an element's content, in MCP's `ContentBlock` form.
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

/// A free-form value for an element's `attributes`.
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

// An attribute reads as the JSON it becomes: `["ref": "T-12", "done": false]`.
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

/// The role language: how a thing is shown. Thirteen words, spelled on
/// the wire with a capital, as in the specification. What the thing is,
/// in the app's own word, goes in `subrole`.
public enum ContextRole: String, Equatable, Sendable, Encodable, CaseIterable {
    case application = "Application"
    case window = "Window"
    case group = "Group"
    case list = "List"
    case table = "Table"
    case row = "Row"
    case cell = "Cell"
    case text = "Text"
    case heading = "Heading"
    case link = "Link"
    case image = "Image"
    case page = "Page"
    case document = "Document"
}

/// One thing the user has open, and what is inside it. A provider answers
/// with one tree of these, rooted at an `application`.
public struct ContextElement: Equatable, Sendable, Encodable {
    /// Letters, digits, hyphens and underscores, 1 to 128 of them. Unique
    /// within one answer and stable for one run. Names one appearance:
    /// the same thing shown twice is two elements.
    public var id: String
    public var role: ContextRole
    /// The app's own word for what the thing is.
    public var subrole: String?
    /// One line a person could read.
    public var title: String?
    public var content: [ContextContent]?
    public var url: String?
    /// The user selected this.
    public var selected: Bool
    /// The keyboard or cursor is here. Set on every element of the path
    /// from the root's children down to the user's position, with no
    /// gaps.
    public var focused: Bool
    /// The pointer is over this element now. On at most one element: the
    /// innermost reported one under the pointer, never its ancestors.
    public var hovered: Bool
    /// Drawn on screen now. Nil means the parent's value; the root is
    /// visible.
    public var visible: Bool?
    /// The elements inside this one, in the app's order.
    public var children: [ContextElement]
    /// Anything else, by name. Two names are reserved: `author`, who
    /// wrote the thing, as a string, sent only where the app already
    /// shows it; and `related`, a list of links that are not containment.
    public var attributes: [String: ContextValue]?

    public init(
        id: String, role: ContextRole, subrole: String? = nil, title: String? = nil,
        content: [ContextContent]? = nil, url: String? = nil,
        selected: Bool = false, focused: Bool = false, hovered: Bool = false, visible: Bool? = nil,
        attributes: [String: ContextValue]? = nil, children: [ContextElement] = []
    ) {
        self.id = id
        self.role = role
        self.subrole = subrole
        self.title = title
        self.content = content
        self.url = url
        self.selected = selected
        self.focused = focused
        self.hovered = hovered
        self.visible = visible
        self.attributes = attributes
        self.children = children
    }

    private enum Key: String, CodingKey {
        case id, role, subrole, title, content, url, selected, focused, hovered, visible, children, attributes
    }

    /// `selected`, `focused` and `hovered` are sent only when true, and
    /// an empty `children` list is not sent.
    public func encode(to encoder: Encoder) throws {
        var values = encoder.container(keyedBy: Key.self)
        try values.encode(id, forKey: .id)
        try values.encode(role, forKey: .role)
        try values.encodeIfPresent(subrole, forKey: .subrole)
        try values.encodeIfPresent(title, forKey: .title)
        try values.encodeIfPresent(content, forKey: .content)
        try values.encodeIfPresent(url, forKey: .url)
        if selected { try values.encode(true, forKey: .selected) }
        if focused { try values.encode(true, forKey: .focused) }
        if hovered { try values.encode(true, forKey: .hovered) }
        try values.encodeIfPresent(visible, forKey: .visible)
        if !children.isEmpty { try values.encode(children, forKey: .children) }
        try values.encodeIfPresent(attributes, forKey: .attributes)
    }
}

/// The app's own words for what an answer holds, for the line a host
/// shows the user: `release-runbook.md · lines 12–18`. Optional. A host
/// that gets none words the line itself from the tree.
///
/// It labels the answer it is sent with: it names nothing the tree does
/// not hold. The picture a host draws beside it is not sent; it is the
/// file `Contents/Resources/favicon.svg` (or `favicon.png`) in the app's
/// bundle, which the host finds itself.
public struct ContextDisplay: Equatable, Sendable, Encodable {
    /// The longest line the protocol allows, in characters.
    public static let lineLimit = 80

    /// What is open: the document, the view, the thread.
    public var title: String?
    /// What is selected or in focus within it: `lines 12–18`, `3 tasks`.
    public var detail: String?

    public init(title: String? = nil, detail: String? = nil) {
        self.title = title
        self.detail = detail
    }

    /// What is sent: each string on one line of at most 80 characters,
    /// or nil when there is no title, since a host uses `display` only
    /// when it has one.
    var sent: ContextDisplay? {
        guard let title = title.flatMap(Self.line) else { return nil }
        return ContextDisplay(title: title, detail: detail.flatMap(Self.line))
    }

    /// One line of plain text: line breaks and control characters become
    /// spaces, runs of spaces become one, and a line over the limit is
    /// cut and ends in an ellipsis. Nil when nothing is left.
    static func line(_ text: String) -> String? {
        let spaced = String(String.UnicodeScalarView(text.unicodeScalars.map { scalar in
            scalar.properties.generalCategory == .control || scalar == "\u{2028}" || scalar == "\u{2029}" ? " " : scalar
        }))
        let line = spaced.split(separator: " ", omittingEmptySubsequences: true).joined(separator: " ")
        if line.isEmpty { return nil }
        return line.count <= lineLimit ? line : String(line.prefix(lineLimit - 1)) + "…"
    }

    private enum Key: String, CodingKey { case title, detail }

    public func encode(to encoder: Encoder) throws {
        var values = encoder.container(keyedBy: Key.self)
        try values.encodeIfPresent(title, forKey: .title)
        try values.encodeIfPresent(detail, forKey: .detail)
    }
}

/// Something wrong with a tree that can be told from the tree alone.
public struct ContextIssue: Equatable, Sendable {
    /// An `error` is an answer a host may refuse or misread.
    public enum Severity: String, Sendable { case error, warning }

    public var severity: Severity
    /// The element's `id`.
    public var element: String
    public var message: String
}

/// The rules a tree must keep that its type does not enforce (RFC-0001
/// section 7, RFC-0003). The server runs this on a provider's answer so
/// an app's author hears of a mistake from the app, not from a host that
/// reads it oddly.
public enum ContextTree {
    /// Letters, digits, hyphens and underscores, as the protocol allows.
    public static func isElementID(_ id: String) -> Bool {
        !id.isEmpty && id.utf8.count <= 128 && id.utf8.allSatisfy { byte in
            (byte >= 0x30 && byte <= 0x39) || (byte >= 0x41 && byte <= 0x5A)
                || (byte >= 0x61 && byte <= 0x7A) || byte == 0x2D || byte == 0x5F
        }
    }

    /// Everything wrong with the tree under `root`, in the order met;
    /// empty for a tree with nothing to report.
    public static func check(_ root: ContextElement) -> [ContextIssue] {
        var issues: [ContextIssue] = []
        var seen = Set<String>()
        var hovered = 0
        func note(_ element: ContextElement, _ message: String) {
            issues.append(ContextIssue(severity: .error, element: element.id, message: message))
        }
        if root.role != .application {
            note(root, "the root's role is '\(root.role.rawValue)', not 'Application'")
        }
        // `onPath` is whether the parent lies on the focused path; the
        // root does, whether or not it is marked.
        func visit(_ element: ContextElement, onPath: Bool, depth: Int) {
            if !isElementID(element.id) {
                note(element, "the id is not 1 to 128 letters, digits, hyphens or underscores")
            } else if !seen.insert(element.id).inserted {
                note(element, "the id is used by more than one element")
            }
            if element.role == .application, depth > 0 {
                note(element, "only the root is an 'Application'")
            }
            if element.focused, !onPath {
                note(element, "focused, but an element between it and the root is not: the focused path has a gap")
            }
            if element.hovered {
                hovered += 1
                if hovered == 2 {
                    note(element, "hovered, and so is an earlier element: at most one element is hovered")
                }
            }
            let focused = element.children.filter(\.focused)
            if focused.count > 1 {
                note(focused[1], "focused, and so is an earlier element beside it: the focused path forks")
            }
            let here = depth == 0 || (onPath && element.focused)
            for child in element.children { visit(child, onPath: here, depth: depth + 1) }
        }
        visit(root, onPath: true, depth: 0)
        return issues
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

/// Where an element is on screen, at one moment.
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
    /// What the user has open, as one tree rooted at an `application`,
    /// from state already in memory. The server adds the protocol
    /// version and the instance.
    func current() -> ContextElement

    /// The app's own words for what `current()` holds, or nil to let the
    /// host word it. Called on the main actor straight after `current()`,
    /// with nothing in between, so the two describe the same moment.
    /// Optional: the default is nil.
    func display() -> ContextDisplay?
}

extension ContextProvider {
    public func display() -> ContextDisplay? { nil }
}

/// A provider that can also say where an element is on screen. Optional:
/// a provider that is not a locator offers no location resource, and a
/// host places its own interface by default.
@MainActor
public protocol ContextLocator: ContextProvider {
    /// Where the element is, or nil for an id this run never issued or
    /// an element that cannot be placed. An element that was issued and
    /// no longer exists is a location whose state is `gone`.
    func locate(_ id: String) -> ContextLocation?
}
