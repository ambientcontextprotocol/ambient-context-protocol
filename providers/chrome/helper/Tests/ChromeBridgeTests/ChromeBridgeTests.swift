import AmbientContextProvider
import Foundation
import Testing
@testable import ChromeBridge

struct NativeMessageTests {
    @Test func aMessageIsItsLengthThenItsBody() throws {
        let framed = try #require(NativeMessage.frame(Data("{\"a\":1}".utf8)))
        #expect(Array(framed.prefix(4)) == [7, 0, 0, 0])
        #expect(String(decoding: framed.dropFirst(4), as: UTF8.self) == "{\"a\":1}")
    }

    @Test func aBodyTheBrowserWouldRefuseIsNotFramed() {
        #expect(NativeMessage.frame(Data(count: NativeMessage.maxToBrowser + 1)) == nil)
        #expect(NativeMessage.frame(Data(count: NativeMessage.maxToBrowser)) != nil)
    }

    @Test func messagesAreReadHoweverTheBytesArrive() throws {
        let one = try #require(NativeMessage.frame(Data("first".utf8)))
        let two = try #require(NativeMessage.frame(Data("second".utf8)))
        let stream = one + two
        var reader = NativeMessage.Reader()
        var read: [String] = []
        // One byte at a time: a length and a body both arrive in pieces.
        for byte in stream {
            reader.append(Data([byte]))
            while let body = try reader.next() { read.append(String(decoding: body, as: UTF8.self)) }
        }
        #expect(read == ["first", "second"])

        var whole = NativeMessage.Reader()
        whole.append(stream)
        #expect(try whole.next().map { String(decoding: $0, as: UTF8.self) } == "first")
        #expect(try whole.next().map { String(decoding: $0, as: UTF8.self) } == "second")
        #expect(try whole.next() == nil)
    }

    @Test func anImpossibleLengthStopsTheReader() {
        var reader = NativeMessage.Reader()
        reader.append(Data([0xFF, 0xFF, 0xFF, 0xFF, 1, 2]))
        #expect(throws: NativeMessage.Failure.tooLong(Int(UInt32.max))) { try reader.next() }
    }
}

struct PageTreeTests {
    private func state(
        focused: Bool = true, tab: Int = 44, selection: String? = nil, cut: Bool? = nil, readable: Bool? = nil
    ) -> PageState {
        PageState(
            window: .init(id: 8, focused: focused),
            tab: .init(id: tab, title: "RFC 3986", url: "https://www.rfc-editor.org/rfc/rfc3986"),
            selection: selection, cut: cut, readable: readable
        )
    }

    @Test func aPageWithASelection() {
        var builder = PageTree(appName: "Google Chrome")
        let root = builder.tree(state(selection: "a hierarchical sequence"))
        #expect(root.role == .application)
        #expect(root.title == "Google Chrome")
        #expect(root.attributes?["via"] == "browser-extension")
        #expect(ContextTree.check(root).isEmpty)

        let window = root.children[0]
        #expect(window.id == "w-8" && window.role == .window && window.focused)
        let page = window.children[0]
        #expect(page.id == "t-44" && page.role == .document && page.subrole == "page" && page.focused)
        #expect(page.title == "RFC 3986")
        #expect(page.url == "https://www.rfc-editor.org/rfc/rfc3986")
        let selection = page.children[0]
        #expect(selection.role == .text && selection.selected && selection.focused)
        #expect(selection.content == [.text("a hierarchical sequence")])
        #expect(selection.attributes == nil)
    }

    @Test func nothingSelectedIsThePageAlone() {
        var builder = PageTree(appName: "Google Chrome")
        let page = builder.tree(state()).children[0].children[0]
        #expect(page.children.isEmpty)
        #expect(builder.tree(state(selection: "")).children[0].children[0].children.isEmpty)
    }

    @Test func aReportedWindowIsWhereTheUserIsInTheBrowser() {
        // Another app has the keyboard, as when a host's own window is
        // open: the page is still the browser's front one.
        var builder = PageTree(appName: "Google Chrome")
        let root = builder.tree(state(focused: false, selection: "words"))
        let window = root.children[0]
        #expect(window.focused && window.children[0].focused && window.children[0].children[0].focused)
        #expect(ContextTree.check(root).isEmpty)
    }

    @Test func aWindowThatIsNotInFrontIsNotReported() {
        var builder = PageTree(appName: "Google Chrome")
        let root = builder.tree(state(focused: false, selection: "words"), inFront: false)
        #expect(root.children.isEmpty)
        #expect(root.attributes?["state"] == nil)
    }

    @Test func noAnswerIsTheApplicationAloneAndSaysSo() {
        var builder = PageTree(appName: "Google Chrome")
        let root = builder.tree(nil)
        #expect(root.children.isEmpty)
        #expect(root.attributes?["state"] == "no-answer")
        // The extension answered, with no window it may report: a private
        // window in front, or none open.
        let empty = builder.tree(PageState())
        #expect(empty.children.isEmpty)
        #expect(empty.attributes?["state"] == nil)
    }

    @Test func aSelectionKeepsItsIdAndANewOneGetsANewId() {
        var builder = PageTree(appName: "Google Chrome")
        func id(_ state: PageState) -> String? { builder.tree(state).children[0].children[0].children.first?.id }
        let first = id(state(selection: "one"))
        #expect(first == "sel-44-1")
        #expect(id(state(selection: "one")) == first)
        let second = id(state(selection: "two"))
        #expect(second == "sel-44-2")
        // The first passage selected again is a new selection: its id was
        // given to something that has since gone.
        #expect(id(state(selection: "one")) == "sel-44-3")
        // The same words in another tab are another passage.
        #expect(id(state(tab: 45, selection: "one")) == "sel-45-4")
    }

    @Test func aLongSelectionIsCutAndSaysSo() {
        var builder = PageTree(appName: "Google Chrome")
        let long = String(repeating: "é", count: PageTree.maxSelection + 5)
        let selection = builder.tree(state(selection: long)).children[0].children[0].children[0]
        guard case .text(let text)? = selection.content?.first else {
            Issue.record("no text")
            return
        }
        #expect(text.unicodeScalars.count == PageTree.maxSelection)
        #expect(selection.attributes?["cut"] == true)
        // Cut by the extension already.
        let marked = builder.tree(state(selection: "short", cut: true)).children[0].children[0].children[0]
        #expect(marked.attributes?["cut"] == true)
    }

    @Test func aPageTheBrowserWillNotReadSaysSo() {
        var builder = PageTree(appName: "Google Chrome")
        let page = builder.tree(state(readable: false)).children[0].children[0]
        #expect(page.attributes?["readable"] == false)
        #expect(page.children.isEmpty)
    }

    @Test func whatIsInViewIsThePagesTextAndItsChildren() {
        var builder = PageTree(appName: "Google Chrome")
        var seen = state(selection: "picked")
        seen.text = "The seven vices\nFirst paragraph in view."
        seen.page = "k3f9x2"
        seen.elements = [
            .init(n: 1, kind: "link", title: "Issues", url: "https://site.example/issues"),
            .init(n: 2, kind: "heading", title: "The seven vices", level: 1),
            .init(n: 3, kind: "image", title: "A gin palace", url: "https://site.example/p.jpg", width: 1200, height: 800),
        ]
        let root = builder.tree(seen)
        #expect(ContextTree.check(root).isEmpty)
        let page = root.children[0].children[0]
        #expect(page.content == [.text("The seven vices\nFirst paragraph in view.")])
        #expect(page.attributes == nil)
        // The selection first, then what is in view in the page's order.
        #expect(page.children.map(\.role) == [.text, .link, .heading, .image])
        #expect(page.children.map(\.id) == ["sel-44-1", "e-44-k3f9x2-1", "e-44-k3f9x2-2", "e-44-k3f9x2-3"])
        let heading = page.children[2]
        #expect(heading.title == "The seven vices" && heading.attributes?["level"] == 1)
        let image = page.children[3]
        #expect(image.title == "A gin palace" && image.url == "https://site.example/p.jpg")
        #expect(image.attributes?["width"] == 1200 && image.attributes?["height"] == 800)
        // Only the selection is selected, and nothing in view is focused.
        #expect(page.children.dropFirst().allSatisfy { !$0.selected && !$0.focused })
        // The same page read again gives the same ids.
        #expect(builder.tree(seen).children[0].children[0].children.map(\.id) == page.children.map(\.id))
    }

    @Test func whatIsMalformedInViewIsLeftOut() {
        var builder = PageTree(appName: "Google Chrome")
        var seen = state()
        seen.page = "k3f9x2"
        seen.elements = [
            .init(n: 1, kind: "link", title: "No address"),
            .init(n: 2, kind: "link", title: "Script", url: "javascript:alert(1)"),
            .init(n: 3, kind: "link", title: "File", url: "file:///etc/passwd"),
            .init(n: 4, kind: "heading", title: "  "),
            .init(n: 5, kind: "video", title: "Unknown kind", url: "https://e.org/v"),
            .init(n: 6, kind: "image"),
            .init(n: 7, kind: "link", title: "Good", url: "https://e.org/a"),
            .init(n: 7, kind: "link", title: "Same number", url: "https://e.org/b"),
            .init(n: 0, kind: "link", title: "No number", url: "https://e.org/c"),
            .init(n: 8, kind: "heading", title: "Odd level", level: 9),
            .init(n: 9, kind: "image", title: "Data picture", url: "data:image/png;base64,AAAA"),
        ]
        let page = builder.tree(seen).children[0].children[0]
        #expect(page.children.map(\.title) == ["Good", "Odd level", "Data picture"])
        #expect(page.children[1].attributes == nil)
        #expect(page.children[2].url == nil)
        #expect(ContextTree.check(builder.tree(seen)).isEmpty)

        // Without the page's word, or with one that is not an id, the
        // numbers mean nothing and no element is made.
        seen.page = nil
        #expect(builder.tree(seen).children[0].children[0].children.isEmpty)
        seen.page = "not an id!"
        #expect(builder.tree(seen).children[0].children[0].children.isEmpty)
    }

    @Test func eachKindInViewHasItsLimit() {
        var builder = PageTree(appName: "Google Chrome")
        var seen = state()
        seen.page = "p"
        seen.elements = (1...30).map { .init(n: $0, kind: "link", title: "L\($0)", url: "https://e.org/\($0)") }
            + (31...50).map { .init(n: $0, kind: "heading", title: "H\($0)") }
            + (51...70).map { .init(n: $0, kind: "image", title: "I\($0)") }
        let children = builder.tree(seen).children[0].children[0].children
        #expect(children.filter { $0.role == .link }.count == PageTree.maxLinks)
        #expect(children.filter { $0.role == .heading }.count == PageTree.maxHeadings)
        #expect(children.filter { $0.role == .image }.count == PageTree.maxImages)

        seen.elements = nil
        seen.text = String(repeating: "a", count: PageTree.maxText + 10)
        let page = builder.tree(seen).children[0].children[0]
        guard case .text(let text)? = page.content?.first else {
            Issue.record("no text")
            return
        }
        #expect(text.count == PageTree.maxText)
        #expect(page.attributes?["cut"] == true)
    }

    @Test func aSiteNeverToReadIsNamedAndNothingMore() {
        var builder = PageTree(appName: "Google Chrome")
        // Even if the extension were to send more, none of it is passed on.
        var seen = state(selection: "should not be here")
        seen.never = true
        seen.text = "nor this"
        seen.page = "p"
        seen.elements = [.init(n: 1, kind: "heading", title: "nor this")]
        let root = builder.tree(seen)
        let page = root.children[0].children[0]
        #expect(page.title == "RFC 3986" && page.url == "https://www.rfc-editor.org/rfc/rfc3986")
        #expect(page.content == nil && page.children.isEmpty)
        #expect(page.attributes?["read"] == "never")
        #expect(root.children[0].focused && page.focused)
        #expect(ContextTree.check(root).isEmpty)
    }

    @Test func aTitleIsOneLine() {
        var builder = PageTree(appName: "Google Chrome")
        var odd = state()
        odd.tab?.title = "two\nlines"
        #expect(builder.tree(odd).children[0].children[0].title == "two lines")
        odd.tab?.title = ""
        #expect(builder.tree(odd).children[0].children[0].title == nil)
    }

    @Test func theExtensionsMessageIsRead() throws {
        let json = #"{"type":"state","id":7,"state":{"window":{"id":8,"focused":true},"tab":{"id":44,"title":"T","url":"https://e.org/"},"selection":"x","readable":true,"extra":1}}"#
        let message = try JSONDecoder().decode(ExtensionMessage.self, from: Data(json.utf8))
        #expect(message.type == "state" && message.id == 7)
        #expect(message.state?.tab?.url == "https://e.org/")
        #expect(message.state?.selection == "x")
        let hello = try JSONDecoder().decode(ExtensionMessage.self, from: Data(#"{"type":"hello"}"#.utf8))
        #expect(hello.state == nil)
    }
}

struct FrontWindowTests {
    @Test func nothingIsReportedUntilAWindowHasBeenSeenInFront() {
        var front = FrontWindow()
        // Another app in front, and no look yet at what the browser shows.
        let look1 = front.look(focused: false, browserActive: false)
        #expect(!look1)
        let look2 = front.look(focused: true, browserActive: true)
        #expect(look2)
        let look3 = front.look(focused: false, browserActive: false)
        #expect(look3)
    }

    @Test func anotherAppInFrontLeavesThePageReported() {
        var front = FrontWindow()
        let look4 = front.look(focused: true, browserActive: true)
        #expect(look4)
        // The host's own window takes the keyboard, and asks again later.
        let look5 = front.look(focused: false, browserActive: false)
        #expect(look5)
        let look6 = front.look(focused: false, browserActive: false)
        #expect(look6)
    }

    @Test func aWindowTheExtensionCannotSeeHidesThePage() {
        var front = FrontWindow()
        let look7 = front.look(focused: true, browserActive: true)
        #expect(look7)
        // A private window comes to the front: the browser has the
        // keyboard and the reported window does not.
        let look8 = front.look(focused: false, browserActive: true)
        #expect(!look8)
        #expect(front.hidden)
        // The user turns to another app with the private window still
        // the browser's front one.
        let look9 = front.look(focused: false, browserActive: false)
        #expect(!look9)
        // Back to an ordinary window.
        let look10 = front.look(focused: true, browserActive: true)
        #expect(look10)
        let look11 = front.look(focused: false, browserActive: false)
        #expect(look11)
    }

    @Test func aStandInBrowserStartsWithNothingHidden() {
        var front = FrontWindow(hidden: false)
        let look12 = front.look(focused: false, browserActive: false)
        #expect(look12)
    }
}
