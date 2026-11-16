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
    /// when it said nothing in time, or when the window it reports is not
    /// the browser's front one (`inFront`, from `FrontWindow`). A window
    /// that is reported is where the user is in the browser, so the focus
    /// path runs through it.
    public mutating func tree(_ state: PageState?, inFront: Bool = true) -> ContextElement {
        var root = ContextElement(
            id: "app", role: .application, title: appName, attributes: ["via": "browser-extension"]
        )
        guard let state else {
            root.attributes?["state"] = "no-answer"
            return root
        }
        guard inFront, let window = state.window, let tab = state.tab else { return root }

        var page = ContextElement(
            id: "t-\(tab.id)", role: .document, subrole: "page", title: Self.line(tab.title), url: tab.url,
            focused: true
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
                id: id, role: .text, content: [.text(text)], selected: true, focused: true,
                attributes: cut ? ["cut": true] : nil
            )]
        }
        root.children = [
            ContextElement(id: "w-\(window.id)", role: .window, focused: true, children: [page]),
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

/// Whether the window the extension reports is the browser's front one.
///
/// The extension sees only the windows it is allowed in. With a private
/// window in front it still reports the last ordinary one, marked as not
/// having the keyboard, and that page must not be handed over as what the
/// user is looking at. The same mark is on an ordinary window whenever
/// another app has the keyboard, which is exactly when a host asks. What
/// tells the two apart is whether the browser is the app in front: a
/// window without the keyboard while the browser has it means some
/// window the extension cannot see is in front. That is remembered, since
/// it stays true after the user turns to another app.
public struct FrontWindow: Equatable, Sendable {
    /// A window the extension cannot see is the browser's front one.
    /// Until the first look nothing is known, and unknown is treated as
    /// hidden: a page is reported only once it has been seen in front.
    public private(set) var hidden: Bool

    public init(hidden: Bool = true) {
        self.hidden = hidden
    }

    /// Takes one look, and says whether the reported window may be
    /// passed on.
    /// - Parameters:
    ///   - focused: The extension says its window has the keyboard.
    ///   - browserActive: The browser is the app in front.
    public mutating func look(focused: Bool, browserActive: Bool) -> Bool {
        if focused {
            hidden = false
        } else if browserActive {
            hidden = true
        }
        return focused || (!browserActive && !hidden)
    }
}
