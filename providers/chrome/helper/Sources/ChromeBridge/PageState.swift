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

    /// A heading, image or link in view.
    public struct Element: Decodable, Equatable, Sendable {
        /// The extension's number for it, the same each time the same
        /// page is read.
        public var n: Int
        /// `heading`, `image` or `link`. Any other kind is left out.
        public var kind: String
        public var title: String?
        public var url: String?
        public var level: Int?
        public var width: Int?
        public var height: Int?

        public init(
            n: Int, kind: String, title: String? = nil, url: String? = nil, level: Int? = nil,
            width: Int? = nil, height: Int? = nil
        ) {
            self.n = n
            self.kind = kind
            self.title = title
            self.url = url
            self.level = level
            self.width = width
            self.height = height
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
    /// The site is one the user has said never to read: the page is
    /// named and nothing in it was looked at.
    public var never: Bool?
    /// The text of the page that is inside the window.
    public var text: String?
    public var textCut: Bool?
    /// A word for this page that no other page shares, which makes the
    /// elements' numbers into ids that are never used twice.
    public var page: String?
    /// The headings, images and links in view, in the page's order.
    public var elements: [Element]?

    public init(
        window: Window? = nil, tab: Tab? = nil, selection: String? = nil, cut: Bool? = nil, readable: Bool? = nil,
        never: Bool? = nil, text: String? = nil, textCut: Bool? = nil, page: String? = nil,
        elements: [Element]? = nil
    ) {
        self.window = window
        self.tab = tab
        self.selection = selection
        self.cut = cut
        self.readable = readable
        self.never = never
        self.text = text
        self.textCut = textCut
        self.page = page
        self.elements = elements
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
    /// The most of the page's visible text one answer carries, and the
    /// most headings, images and links. The extension keeps to the same
    /// limits; these hold if it does not.
    public static let maxText = 6_000
    public static let maxHeadings = 10
    public static let maxImages = 10
    public static let maxLinks = 20

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
        if state.never == true {
            // Named and not read. Whatever else the message holds is
            // not passed on.
            page.attributes = ["read": "never"]
            root.children = [ContextElement(id: "w-\(window.id)", role: .window, focused: true, children: [page])]
            return root
        }
        if let visible = state.text, !visible.isEmpty {
            let (text, cut) = Self.shortened(visible, to: Self.maxText)
            page.content = [.text(text)]
            if cut || state.textCut == true { page.attributes = (page.attributes ?? [:]).merging(["cut": true]) { $1 } }
        }

        if let selected = state.selection, !selected.isEmpty {
            let (text, shortened) = Self.shortened(selected, to: Self.maxSelection)
            let cut = shortened || state.cut == true
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
        page.children += Self.inView(state, tab: tab.id)
        root.children = [
            ContextElement(id: "w-\(window.id)", role: .window, focused: true, children: [page]),
        ]
        return root
    }

    // The headings, images and links in view, each kind up to its limit.
    // An id is the tab, the page's word and the extension's number, so it
    // stays with one thing while its page is open and is not used again
    // after. Anything malformed is left out.
    private static func inView(_ state: PageState, tab: Int) -> [ContextElement] {
        guard let word = state.page, ContextTree.isElementID(word), word.count <= 16 else { return [] }
        var left = ["heading": maxHeadings, "image": maxImages, "link": maxLinks]
        var numbers: Set<Int> = []
        var found: [ContextElement] = []
        for element in state.elements ?? [] {
            guard let room = left[element.kind], room > 0, element.n > 0, !numbers.contains(element.n) else {
                continue
            }
            let title = line(element.title)
            let url = address(element.url)
            let id = "e-\(tab)-\(word)-\(element.n)"
            var made: ContextElement
            switch element.kind {
            case "heading":
                guard title != nil else { continue }
                made = ContextElement(id: id, role: .heading, title: title)
                if let level = element.level, (1...6).contains(level) { made.attributes = ["level": .integer(level)] }
            case "image":
                guard title != nil || url != nil else { continue }
                made = ContextElement(id: id, role: .image, title: title, url: url)
                if let width = element.width, let height = element.height, width > 0, height > 0 {
                    made.attributes = ["width": .integer(width), "height": .integer(height)]
                }
            default:
                guard title != nil, url != nil else { continue }
                made = ContextElement(id: id, role: .link, title: title, url: url)
            }
            left[element.kind] = room - 1
            numbers.insert(element.n)
            found.append(made)
        }
        return found
    }

    // An address a host can pass on: the web's two schemes only.
    private static func address(_ text: String?) -> String? {
        guard let text, text.count <= 2_000, let url = URL(string: text),
              let scheme = url.scheme?.lowercased(), scheme == "http" || scheme == "https"
        else { return nil }
        return text
    }

    private static func shortened(_ text: String, to limit: Int) -> (String, Bool) {
        guard text.unicodeScalars.count > limit else { return (text, false) }
        var kept = String.UnicodeScalarView()
        kept.append(contentsOf: text.unicodeScalars.prefix(limit))
        return (String(kept), true)
    }

    // A title is one line; a page's can be anything.
    private static func line(_ title: String?) -> String? {
        guard let title else { return nil }
        let flat = title.split(whereSeparator: \.isWhitespace).joined(separator: " ")
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
