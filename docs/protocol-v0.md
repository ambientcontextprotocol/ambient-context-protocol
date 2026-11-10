# Ambient Context Protocol

Version `0.1` · Draft of `2026.11.09` · Not stable. Everything here may change, and nothing has shipped.

> The Ambient Context Protocol lets a desktop app tell an ambient agent what the user is looking at, so that "this" means something when the user asks a question. It also lets the agent's interface appear beside the thing in question. An app implements two requests: one that lists what is open and selected, and one that says where a listed thing is on screen.

## Contents

1. [The problem](#1-the-problem)
2. [An example](#2-an-example)
3. [Roles and principles](#3-roles-and-principles)
4. [Messages](#4-messages)
   - [4.1 — initialize](#41--initialize)
   - [4.2 — context/current](#42--contextcurrent)
   - [4.3 — context/locate](#43--contextlocate)
5. [Items](#5-items)
6. [Locations](#6-locations)
7. [Rules](#7-rules)
   - [7.1 — For providers](#71--for-providers)
   - [7.2 — For hosts](#72--for-hosts)
8. [Versioning](#8-versioning)
9. [Transport](#9-transport)
10. [Implementing a provider](#10-implementing-a-provider)
11. [Not in version 0](#11-not-in-version-0)
12. [Open questions](#12-open-questions)

## 1. The problem

An ambient agent is one you can call from anywhere on your computer: press a key, ask a question, get an answer without switching apps. Sirius is one such agent.

The question you ask is usually about what is in front of you. "Is this claim true?" "Move this to tomorrow." "Why is this failing?" The agent can't answer unless it knows what "this" is. Today that takes a screenshot, a paste, or a paragraph of explanation.

The app in front already knows the answer. It knows which documents are open, which one has focus and what is selected. It also knows where each of those things is on screen, which matters when the agent wants to show its answer next to the passage and not in a corner of the display.

This protocol is how the app says so. It is deliberately small. It does not describe documents, tasks or layers. It gives every app the same way to say "here is what the user has open, here is what they are pointing at, and here is where it is."

## 2. An example

A user has two Markdown files open in an editor. They select a sentence in one, call the agent, and type "is this claim actually true?"

**Step 1.** The agent's host asks the editor what is current:

```json
{ "jsonrpc": "2.0", "id": 7, "method": "context/current" }
```

**Step 2.** The editor answers:

```json
{
  "jsonrpc": "2.0",
  "id": 7,
  "result": {
    "app": { "id": "org.example.editor", "name": "Editor" },
    "focus": ["sel-23"],
    "items": [
      {
        "id": "doc-1",
        "type": "document",
        "title": "draft.md",
        "url": "file:///Users/ada/essays/draft.md"
      },
      {
        "id": "doc-2",
        "type": "document",
        "title": "notes.md",
        "url": "file:///Users/ada/essays/notes.md"
      },
      {
        "id": "sel-23",
        "type": "selection",
        "parent": "doc-1",
        "title": "Selection in draft.md",
        "content": [
          { "type": "text", "text": "The command line lasted thirty years as the main way people used computers." }
        ],
        "locatable": true,
        "payload": { "lines": [31, 31] }
      }
    ]
  }
}
```

**Step 3.** The host shows the user what it picked up, so they can remove it, and passes it to the agent with the question. How a host words this for its agent is the host's business. Sirius would write something like:

```
is this claim actually true?

<context app="org.example.editor" name="Editor" front="true">
  <document id="doc-1" path="/Users/ada/essays/draft.md"/>
  <document id="doc-2" path="/Users/ada/essays/notes.md"/>
  <selection id="sel-23" in="doc-1" focus="true" locatable="true">
The command line lasted thirty years as the main way people used computers.
  </selection>
</context>
<context app="org.example.browser" name="Browser" title="History of the graphical user interface"/>
```

The editor is in front, so its context is passed in full. The browser has a visible window behind it and gets one line.

**Step 4.** The agent decides to answer in a window beside the sentence. It tells the host which item to attach to, by id. In Sirius:

```
sirius display aside --anchor sel-23 "Check the dates in this claim"
```

**Step 5.** The host asks the editor where that item is:

```json
{ "jsonrpc": "2.0", "id": 8, "method": "context/locate", "params": { "id": "sel-23" } }
```

**Step 6.** The editor answers, and the host places its window:

```json
{
  "jsonrpc": "2.0",
  "id": 8,
  "result": {
    "id": "sel-23",
    "state": "visible",
    "rects": [{ "x": 425, "y": 233, "w": 480, "h": 20 }],
    "window": 48211,
    "avoid": { "x": 400, "y": 80, "w": 620, "h": 900 },
    "edge": "right"
  }
}
```

The editor never learned what the host showed, and the agent never saw a coordinate.

## 3. Roles and principles

**Provider.** An app that answers these requests about itself: an editor, a task manager, a design tool, a terminal.

**Host.** The ambient agent's own app. It calls providers, shows the user what it collected, passes context to an agent, and draws its own interface.

**Agent.** The model behind the host. It is not a party to this protocol. It sees whatever the host chooses to pass on.

Four principles shape everything else:

1. **An envelope, not a domain model.** The protocol fixes a handful of fields every item has. What an item is, and anything specific to it, is the provider's to define. A language model can read any payload, so there is nothing to gain from standardizing "document" or "task."
2. **Ids are opaque.** A provider mints a short id for each item. Only the provider knows what it refers to. The host and the agent pass it back unchanged.
3. **The provider says where; the host decides what.** A provider reports where an item is on screen. It does not know or care what the host draws there. Nothing in the protocol names a host's windows.
4. **Pull, on the user's action.** A host asks for context when the user invokes it. A provider sends nothing on its own.

## 4. Messages

Messages are JSON-RPC 2.0 requests and responses. The host sends requests; the provider responds. Version 0 has three methods and no notifications.

### 4.1 — initialize

Sent once when a host connects.

Request `params`:

| Field | Type | Required | Meaning |
|---|---|---|---|
| `protocol` | string | yes | The newest protocol version the host speaks. `"0.1"` for this draft. See [Versioning](#8-versioning). |
| `host` | object | yes | `name` and `version` of the host. |

Result:

| Field | Type | Required | Meaning |
|---|---|---|---|
| `protocol` | string | yes | The version the provider will speak. |
| `app` | object | yes | `id` (the app's bundle identifier), `name`, `version`. |
| `capabilities` | object | yes | `locate`: boolean, whether the provider answers `context/locate` at all. |

### 4.2 — context/current

Asks what the user has open and what they are pointing at, right now. Takes no parameters.

Result:

| Field | Type | Required | Meaning |
|---|---|---|---|
| `app` | object | yes | `id` and `name`, as in `initialize`. |
| `items` | array | yes | The [items](#5-items) currently open or selected. May be empty. |
| `focus` | array of strings | no | The ids of the most specific items the user is pointing at: the selection if there is one, otherwise the front document or view. More than one when several things are selected together. Absent or empty when nothing has focus. |

### 4.3 — context/locate

Asks where an item is on screen.

Request `params`:

| Field | Type | Required | Meaning |
|---|---|---|---|
| `id` | string | yes | An item id the provider returned earlier. |

The result is a [location](#6-locations). An id the provider no longer recognizes is not an error: the provider answers with `state: "gone"`.

## 5. Items

An item is one thing the user has open or selected.

| Field | Type | Required | Meaning |
|---|---|---|---|
| `id` | string | yes | Short, opaque, unique within the provider. See the lifetime rule in 7.1. |
| `type` | string | yes | A name the provider chooses, such as `document`, `selection`, `task`, `layer`. Hosts use it for grouping and display only. |
| `title` | string | yes | One line a person could read, such as a file name or a task's name. |
| `content` | array of content blocks | no | What the item contains, for the agent to read or see. See below. |
| `url` | string | no | An address for the thing, when it has one: a `file://` URL, a web URL, or a link the app itself opens. |
| `parent` | string | no | The id of the item this one sits inside, such as a selection's document. |
| `locatable` | boolean | no | Whether `context/locate` can answer for this item. Defaults to `false`. |
| `payload` | object | no | Anything else the provider wants an agent to have. Free-form. |

A provider decides how much to list. An editor with forty open files might list them all, since each costs one line. A task manager would list the open view and the selected tasks, not its whole database.

**Content blocks.** `content` uses the Model Context Protocol's `ContentBlock` type unchanged, so a host can hand the blocks to an agent without translating them. The block types, as of MCP schema `2026-07-28`:

| `type` | Required fields | Use here |
|---|---|---|
| `text` | `text` | Selected text, or a short description of the item. |
| `image` | `data` (base64), `mimeType` | A small rendering of something visual: a frame, a chart, a region of a canvas. |
| `audio` | `data` (base64), `mimeType` | Rarely needed. |
| `resource_link` | `uri`, `name` | A pointer to the full thing, for the agent to fetch if it needs it. |
| `resource` | `resource` (a `uri` with `text` or `blob`) | The full thing, embedded. |

An item that is text sends a `text` block. An item that is not text sends an image, a link, or both. A selected frame in a design tool:

```json
{
  "id": "node-7",
  "type": "frame",
  "title": "Checkout / Payment form",
  "url": "https://design.example.com/file/AbC123?node=160-34",
  "parent": "page-2",
  "locatable": true,
  "content": [
    { "type": "image", "data": "iVBORw0KGgo…", "mimeType": "image/png" },
    { "type": "resource_link", "uri": "https://design.example.com/file/AbC123?node=160-34", "name": "Checkout / Payment form" }
  ],
  "payload": { "width": 390, "height": 844, "children": 14 }
}
```

Identity and position work the same as for text: the id is opaque, and `context/locate` returns the frame's bounding box as a list of one rectangle.

A provider should keep `content` small: a selection's text, a thumbnail and not a full-resolution export. Anything large belongs behind a `resource_link`.

## 6. Locations

A location is the answer to "where is this item on screen?" It has the same shape for every kind of item.

| Field | Type | Required | Meaning |
|---|---|---|---|
| `id` | string | yes | The item asked about. |
| `state` | string | yes | `visible`, `offscreen` or `gone`. |
| `rects` | array | when visible | One or more rectangles covering the item, each `{x, y, w, h}`. |
| `window` | number | no | The system window number of the window the item is in. |
| `avoid` | rect | no | A region the provider would prefer the host not cover, such as its text column. |
| `edge` | string | no | The side the provider would prefer things attached to: `left`, `right`, `top` or `bottom`. |

**States.** `visible`: at least part of the item is drawn on screen. `offscreen`: the item exists but is not drawn, because it is scrolled away, in a background tab or in a minimized window. `gone`: the item was deleted or the id has expired.

**Rectangles.** A list, because some items are not one rectangle: a text selection that wraps has one per line. Most items send a list of one.

**Coordinates.** Version 0 is specified for macOS. Rectangles are in global display coordinates, in points, with the origin at the top-left corner of the primary display and y increasing downward. This is the space the macOS Accessibility API and Core Graphics use. AppKit's own coordinates have a bottom-left origin and must be converted.

**Hints.** `avoid` and `edge` are requests. A host should honor them when it can and may ignore them.

A location describes one moment. A host that needs to know whether an item moved asks again.

## 7. Rules

### 7.1 — For providers

- **Answer only when asked.** Send nothing unprompted.
- **Answer quickly.** `context/current` should return within about 150 ms. A host will proceed without the context if it doesn't.
- **Keep ids meaningful.** An id refers to the thing it was minted for, for as long as that thing exists and the app is running. An id for a text selection keeps referring to that passage after the user selects something else, and should follow the passage through edits where it can. When the thing is gone, answer `gone`.
- **Expose what the user would expect.** The provider chooses what to list. It should leave out anything the user would be surprised to see handed to an agent, such as the contents of a password field or a private window.

### 7.2 — For hosts

- **Ask on the user's action.** Call `context/current` when the user invokes the agent, not on a timer.
- **Ask the front app, and only mention the rest.** Which app is in front is the host's knowledge, from the operating system; `focus` in a provider's answer says what has focus inside that app. A host should pass the front app's context in full, and for each other app with a visible window pass one line at most (its name and window title). It should pass nothing for hidden or minimized apps. If the agent needs more from another app, the host calls that provider then. A user asking about a paragraph in an editor does not expect their mail to go along.
- **Show what was collected.** Before a message is sent, the user must be able to see which context will go with it, and remove it.
- **Pass ids through unchanged.** When an agent names an item, send the provider exactly the id it issued.
- **Fail soft.** If a provider does not answer, or answers `offscreen` or `gone`, carry on without the context or the placement. Never block the user's message on a provider.

## 8. Versioning

The protocol has a version of the form `major.minor`, sent as a string. This draft is `0.1`.

- **While the major version is 0,** any minor version may change or remove anything. A host and a provider work together only if they agree on the exact version.
- **From 1.0,** a minor version only adds: new optional fields, new methods, new values a receiver may ignore. Anything that would break an existing implementation takes a new major version.
- **Negotiation.** The host sends the newest version it speaks in `initialize`. The provider answers with that version if it speaks it, and otherwise with the newest version it does speak. If the host can't use the answer, it closes the connection and treats the app as having no provider.
- **Unknown fields are ignored.** A receiver must not fail on a field, an item `type` or a `payload` key it does not recognize. This is what lets minor versions add things.
- **Content blocks follow MCP's version, not this one.** A provider may send any block type from the MCP schema this version names (`2026-07-28` for `0.1`). A host skips block types it cannot handle.

Every change to this document that alters behavior bumps the version and is listed in a changelog at the end.

## 9. Transport

Version 0 does not fix a transport. The messages above work over any channel that carries JSON-RPC between two local processes.

The first implementation will use a Unix domain socket, and that choice is provisional. Three questions are open, and all three matter most for sandboxed apps from the Mac App Store:

- **Discovery.** How a host finds the providers that are running.
- **Trust.** How a host confirms a provider is the app it claims to be, and how a provider confirms a host is one the user approved. Code signature checks on the peer are the likely answer.
- **Sandboxing.** Which channel a sandboxed app can offer without entitlements that App Store review would refuse. Candidates are a socket in the app's container, XPC, and HTTP on the loopback interface.

## 10. Implementing a provider

A provider has three jobs:

1. **Listen** for a host and answer `initialize`.
2. **Answer `context/current`:** list what is open and selected, mint an id for each, and name the focus.
3. **Answer `context/locate`:** look up an id and return the screen rectangles of what it refers to.

An app already has the information for the first two in its window and selection state. It has the information for the third in the code that draws and hit-tests its content. The work is exposing it.

A provider that cannot report positions leaves `capabilities.locate` false and implements only the first two. Its context still reaches the agent; the host places its own interface by default.

## 11. Not in version 0

- **What changed.** A request for events since a cursor ("a task was moved to tomorrow"), so an agent can resolve "what I just did."
- **Actions.** A provider declaring operations an agent can run on an item.
- **Push.** A provider telling the host when context or a location changes. A host that wants to track a moving item calls `context/locate` again.
- **Previews.** A host asking a provider for a card describing an item.
- **Other platforms.** Coordinates are defined for macOS only.

## 12. Open questions

1. The transport, discovery and trust model (section 9).
2. Whether an agent can ask to locate something the provider did not list, such as lines 40 to 42 of an open file. This would need a request that mints an id for an address.
3. How long ids must stay valid after the app quits and reopens, if at all.
4. Whether `content` needs size limits, and what a provider does with a very large selection or image.
5. Web apps: the page knows where an element is in the page, and only the browser knows where the page is on screen. Either the browser is the provider or something bridges the two.
6. Whether this should be expressed as an extension of the Model Context Protocol instead of a protocol of its own. Items already carry MCP content blocks. MCP has a mechanism for third-party extensions, declared under `capabilities.extensions` with an identifier in the form `com.example/extension-name`.

## Changelog

- `0.1` · `2026.11.09` · First draft: `initialize`, `context/current`, `context/locate`; items with MCP content blocks; locations.
