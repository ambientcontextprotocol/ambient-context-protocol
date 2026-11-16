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

    @Test func aWindowWithoutTheKeyboardHasNoFocusPath() {
        var builder = PageTree(appName: "Google Chrome")
        let root = builder.tree(state(focused: false, selection: "words"))
        let window = root.children[0]
        #expect(!window.focused && !window.children[0].focused && !window.children[0].children[0].focused)
        #expect(window.children[0].children[0].selected)
        #expect(ContextTree.check(root).isEmpty)
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
