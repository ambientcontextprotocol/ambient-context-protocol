import AmbientContextProvider
import Foundation

// What the extension reports when asked, and the tree made of it. The
// extension reports the window in front and its active tab only.

/// The extension's answer to one question.
public struct PageState: Decodable, Equatable, Sendable {
    public struct Window: Decodable, Equatable, Sendable {
        public var id: Int
        /// Whether the browser says this window has the keyboard.
        public var focused: Bool

        public init(id: Int, focused: Bool) {
            self.id = id
            self.focused = focused
        }
    }

    public struct Tab: Decodable, Equatable, Sendable {
        public var id: Int
        public var title: String?
        public var url: String?

        public init(id: Int, title: String? = nil, url: String? = nil) {
            self.id = id
            self.title = title
            self.url = url
        }
    }

    public var window: Window?
    public var tab: Tab?
    /// The text selected in the page, already shortened by the extension.
    public var selection: String?
    /// The selection was longer than the extension sends.
    public var cut: Bool?
    /// False when the browser would not let the page be read: its own
    /// pages, the extension store, some document viewers.
    public var readable: Bool?

    public init(
        window: Window? = nil, tab: Tab? = nil, selection: String? = nil, cut: Bool? = nil, readable: Bool? = nil
    ) {
        self.window = window
        self.tab = tab
        self.selection = selection
        self.cut = cut
        self.readable = readable
    }
}

/// A message from the extension. Anything else it sends is ignored.
public struct ExtensionMessage: Decodable, Equatable, Sendable {
    public var type: String
    public var id: Int?
    public var state: PageState?
}

/// Builds the tree a host reads, and keeps the ids meaningful across
/// answers: a window and a tab keep the browser's own ids, and a
/// selection keeps its id for as long as the same passage is selected in
/// the same tab. A new selection gets a new id; none is used twice.
public struct PageTree: Sendable {
    /// The most selected text one answer carries, in Unicode scalars: what
    /// a host passes on at most. The extension cuts first; this holds if
    /// it does not.
    public static let maxSelection = 20_000

    public var appName: String
    private var selectionCount = 0
    private var last: (tab: Int, text: String, id: String)?

    public init(appName: String) {
        self.appName = appName
    }

    /// The tree for what the extension said, or the application alone
    /// when it said nothing in time.
    public mutating func tree(_ state: PageState?) -> ContextElement {
        var root = ContextElement(
            id: "app", role: .application, title: appName, attributes: ["via": "browser-extension"]
        )
        guard let state else {
            root.attributes?["state"] = "no-answer"
            return root
        }
        guard let window = state.window, let tab = state.tab else { return root }

        var page = ContextElement(
            id: "t-\(tab.id)", role: .document, subrole: "page", title: Self.line(tab.title), url: tab.url,
            focused: window.focused
        )
        if state.readable == false { page.attributes = ["readable": false] }

        if let selected = state.selection, !selected.isEmpty {
            var text = selected
            var cut = state.cut == true
            if text.unicodeScalars.count > Self.maxSelection {
                var kept = String.UnicodeScalarView()
                kept.append(contentsOf: text.unicodeScalars.prefix(Self.maxSelection))
                text = String(kept)
                cut = true
            }
            let id: String
            if let last, last.tab == tab.id, last.text == text {
                id = last.id
            } else {
                selectionCount += 1
                id = "sel-\(tab.id)-\(selectionCount)"
                last = (tab.id, text, id)
            }
            page.children = [ContextElement(
                id: id, role: .text, content: [.text(text)], selected: true, focused: window.focused,
                attributes: cut ? ["cut": true] : nil
            )]
        }
        root.children = [
            ContextElement(id: "w-\(window.id)", role: .window, focused: window.focused, children: [page]),
        ]
        return root
    }

    // A title is one line; a page's can be anything.
    private static func line(_ title: String?) -> String? {
        guard let title else { return nil }
        let flat = title.split(whereSeparator: \.isNewline).joined(separator: " ")
        return flat.isEmpty ? nil : String(flat.prefix(300))
    }
}
