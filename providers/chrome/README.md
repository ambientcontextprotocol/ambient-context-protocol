# Ambient Context for Chrome

> A provider of the [Ambient Context Protocol](../../docs/spec/index.md) for Chrome and other Chromium browsers: an extension and a small helper program that together tell a host which page is in front, what of it is in view and what text is selected on it. It depends on [RFC-0004](../../docs/rfcs/0004-a-provider-started-by-the-app.md), which is a draft, so it is experimental.

## What it is

Chrome cannot be a provider by itself: nobody but its maker can add a listener to its process. So there are two parts.

- **The extension** (`extension/`) knows the tabs and can read the selection in a page. It keeps one connection open to the helper and sends nothing unless asked.
- **The helper** (`helper/`) is the provider. Chrome starts it for the extension and talks to it over standard input and output. It runs the local server and keeps the descriptor file, using the [Swift package](../../sdk/swift/README.md). Each time a host reads `ambient://current`, it asks the extension and builds the tree from the answer.

The helper names the app it answers for from its own parent process, so it holds nothing specific to one browser.

## What a host receives

```json
{
  "id": "app", "role": "Application", "title": "Google Chrome",
  "attributes": { "via": "browser-extension" },
  "children": [
    { "id": "w-812", "role": "Window", "focused": true, "children": [
      { "id": "t-4411", "role": "Document", "subrole": "page", "title": "RFC 3986", "url": "https://www.rfc-editor.org/rfc/rfc3986", "focused": true,
        "content": [{ "type": "text", "text": "…the text of the page that is inside the window…" }],
        "children": [
          { "id": "sel-4411-1", "role": "Text", "selected": true, "focused": true, "content": [{ "type": "text", "text": "A URI is a sequence of characters." }] },
          { "id": "e-4411-k3f9x2-1", "role": "Heading", "title": "Uniform Resource Identifier (URI): Generic Syntax", "attributes": { "level": 1 } },
          { "id": "e-4411-k3f9x2-2", "role": "Image", "title": "The parts of a URI", "url": "https://www.rfc-editor.org/uri.png", "attributes": { "width": 600, "height": 200 } },
          { "id": "e-4411-k3f9x2-3", "role": "Link", "title": "RFC 2396", "url": "https://www.rfc-editor.org/rfc/rfc2396" }
        ] }
    ] }
  ]
}
```

- The window in front and its active tab only. Other tabs are not reported.
- A window and a tab keep Chrome's own ids. A selection keeps its id while the same passage stays selected in the same tab.
- Selected text is cut at 20,000 characters, and the element then carries `cut: true`.
- What is in view: the page's `content` is the text inside the window, up to 6,000 characters, and its children are the headings (up to 10), images (up to 10) and links (up to 20) in view, in the page's order. An image has its caption or alt text as its title and its address; no image bytes are sent. Links in the page's own content are taken before those in its header and footer. Only the top page is read for this, not frames inside it.
- An element in view keeps its id while its page is open, and the id is not used again after.
- A page on the user's never-read list is reported with its title and address and `read: "never"`, and nothing in it is looked at.
- A page Chrome will not let an extension read (its own pages, the Web Store, some document viewers) is reported with its title and address and `readable: false`.
- The reported window is the browser's front one, so the focus path runs through it even while another app, such as the host's own window, has the keyboard.
- With a window the extension cannot see in front (Incognito, or another profile's), the answer is the application alone.
- If the extension does not answer within 150 ms, the answer is the application alone with `state: "no-answer"`.
- Positions are not reported, so there is no `locate`.

## What it reads, and when

The extension asks for access to all sites, because a host's key is pressed outside Chrome, where Chrome's narrower "this tab, when clicked" permission never applies. It runs in a page only when a host asks. It reads the selection and what is inside the window; it reads nothing typed into a form field, nothing scrolled out of view, and no password box. Its options page has a switch for what is in view and a list of sites never to read, which starts with a few sign-in, password-manager and mail sites. It is not enabled in Incognito windows unless the user allows it there, and it reports nothing for one. Chrome still tells the extension about the last ordinary window when an Incognito one is in front, so the helper keeps track of whether a window the extension cannot see is the browser's front one, and then reports the application alone. For this the extension tells the helper when the keyboard moves between windows, and nothing else unasked. Nothing is stored, and nothing leaves the Mac from the extension or the helper; what a host does with the answer is the host's business.

Any program on the Mac that can read the descriptor's token can ask the helper, as for every provider ([section 8](../../docs/spec/discovery.md)). For a browser that reaches further than for an editor, and it is not yet answered.

## Trying it

It is not on the Chrome Web Store. To run it from this folder:

1. Build the helper: `swift build -c release --package-path providers/chrome/helper`.
2. In Chrome, open `chrome://extensions`, switch on Developer mode, choose "Load unpacked" and pick `providers/chrome/extension`. Its id should be `ablpecmggklfelddalonopnjdkcfhdpe`.
3. Register the helper with Chrome: `providers/chrome/register.sh`. This writes one file, `io.github.ambientcontextprotocol.chrome.json`, into Chrome's `NativeMessagingHosts` folder. `register.sh --remove` takes it away.
4. Within half a minute a descriptor named `com.google.Chrome.<pid>.for.<pid>.json` appears in `~/Library/Application Support/AmbientContext/providers/`. Check it from outside with `python3 tools/conformance/check.py <that file>`.

A host must implement RFC-0004 to use it.

## Testing the helper alone

```sh
swift test --package-path providers/chrome/helper
python3 providers/chrome/tools/fake_browser.py providers/chrome/helper/.build/debug/ambient-context-chrome --check
node --test providers/chrome/tests/*.test.mjs
```

The second starts the helper as a browser would, answers its questions with one fixed page, and runs the outside check against it. The descriptor goes in a temporary folder. The third tests the extension: its plain functions, and the function that reads a page, run against a fixture in a headless Chrome with a temporary profile of its own.
