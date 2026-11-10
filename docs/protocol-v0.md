# Ambient Context Protocol

Version `0.1` · Draft of `2026.11.09` · Not stable. Everything here may change, every name is a placeholder, and nothing has shipped.

> The Ambient Context Protocol lets a desktop app tell an ambient agent what the user is looking at, so that "this" means something when the user asks a question. It also lets the agent's interface appear beside the thing in question. An app answers two questions: what is open and selected, and where a listed thing is on screen. Version 0.1 is defined as an extension to the Model Context Protocol (MCP): both answers are MCP resources.

## Contents

1. [The problem](#1-the-problem)
2. [An example](#2-an-example)
3. [Roles and principles](#3-roles-and-principles)
4. [Operations](#4-operations)
   - [4.1 — current](#41--current)
   - [4.2 — locate](#42--locate)
5. [Items](#5-items)
6. [Locations](#6-locations)
7. [The MCP binding](#7-the-mcp-binding)
   - [7.1 — The server](#71--the-server)
   - [7.2 — Declaring the extension](#72--declaring-the-extension)
   - [7.3 — The two resources](#73--the-two-resources)
   - [7.4 — Errors and refusals](#74--errors-and-refusals)
   - [7.5 — An optional tool](#75--an-optional-tool)
   - [7.6 — Older MCP clients](#76--older-mcp-clients)
8. [Discovery](#8-discovery)
9. [Rules](#9-rules)
   - [9.1 — For providers](#91--for-providers)
   - [9.2 — For hosts](#92--for-hosts)
10. [Versioning](#10-versioning)
11. [Implementing a provider](#11-implementing-a-provider)
12. [Not in version 0.1](#12-not-in-version-01)
13. [Open questions](#13-open-questions)
14. [MCP details this draft relies on](#14-mcp-details-this-draft-relies-on)

## 1. The problem

An ambient agent is one you can call from anywhere on your computer: press a key, ask a question, get an answer without switching apps.

The question you ask is usually about what is in front of you. "Is this claim true?" "Move this to tomorrow." "Why is this failing?" The agent can't answer unless it knows what "this" is. Today that takes a screenshot, a paste, or a paragraph of explanation.

The app in front already knows the answer. It knows which documents are open, which one has focus and what is selected. It also knows where each of those things is on screen, which matters when the agent wants to show its answer next to the passage and not in a corner of the display.

This protocol is how the app says so. It is deliberately small. It does not describe documents, tasks or layers. It gives every app the same way to say "here is what the user has open, here is what they are pointing at, and here is where it is."

## 2. An example

A user has two Markdown files open in an editor. They select a sentence in one, call the agent, and type "is this claim actually true?"

**Step 1.** The agent's host sees which app is in front, finds that app's descriptor file ([section 8](#8-discovery)), and reads the current context from the address the file gives:

```http
POST /mcp HTTP/1.1
Host: 127.0.0.1:53124
Authorization: Bearer q7Jm…
Content-Type: application/json
Accept: application/json, text/event-stream
MCP-Protocol-Version: 2026-07-28
Mcp-Method: resources/read
Mcp-Name: ambient://current

{
  "jsonrpc": "2.0",
  "id": 7,
  "method": "resources/read",
  "params": {
    "uri": "ambient://current",
    "_meta": { "io.modelcontextprotocol/protocolVersion": "2026-07-28" }
  }
}
```

**Step 2.** The editor answers. The resource's text is a JSON document:

```json
{
  "jsonrpc": "2.0",
  "id": 7,
  "result": {
    "resultType": "complete",
    "contents": [
      {
        "uri": "ambient://current",
        "mimeType": "application/json",
        "text": "{ \"app\": …, \"focus\": …, \"items\": … }"
      }
    ]
  }
}
```

Decoded, the text is:

```json
{
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
```

**Step 3.** The host shows the user what it picked up, so they can remove it, and passes it to the agent with the question. How a host words this for its agent is the host's business.

**Step 4.** The agent decides its answer belongs beside the sentence. It tells the host which item, by id: `sel-23`. How an agent says this is also the host's business. The agent never calls the provider.

**Step 5.** The host asks the editor where that item is, by reading `ambient://location/sel-23` the same way as in step 1.

**Step 6.** The editor answers, and the host places its own interface. Decoded:

```json
{
  "id": "sel-23",
  "state": "visible",
  "rects": [{ "x": 425, "y": 233, "w": 480, "h": 20 }],
  "window": 9120,
  "avoid": { "x": 400, "y": 80, "w": 620, "h": 900 },
  "edge": "right"
}
```

The editor never learned what the host showed, and the agent never saw a coordinate.

## 3. Roles and principles

**Provider.** An app that answers these questions about itself: an editor, a task manager, a design tool, a terminal. In MCP's terms it is a server.

**Host.** The ambient agent's own app. It reads from providers, shows the user what it collected, passes context to an agent, and draws its own interface. In MCP's terms it is a client.

**Agent.** The model behind the host. It is not a party to this protocol. It sees whatever the host chooses to pass on.

Four principles shape everything else:

1. *The app says where; the host decides what.* A provider reports items and their positions. It never names what the host draws there.
2. *An envelope, not a domain model.* The protocol fixes a handful of fields every item has. What an item is, and anything specific to it, is the provider's to define. A language model can read any payload, so there is nothing to gain from standardizing "document" or "task."
3. *Pulled on the user's action.* A host asks for context when the user does something that calls for it. A provider does not push, and a host does not poll. Provisional: this holds for version 0.1 and may change.
4. *It is ordinary MCP.* A provider is an MCP server and the two answers are MCP resources. A client that has never heard of this protocol can still list and read them.

## 4. Operations

The protocol has two operations. This section defines them apart from any carrier; [section 7](#7-the-mcp-binding) says how MCP carries them.

Both are reads. The host's application code performs them, not the model: the host reads `current` when the user invokes the agent, and reads `locate` when it needs to place something. This is why the MCP binding uses resources, which MCP defines as application-driven, and not tools, which it defines as model-controlled.

### 4.1 — current

Asks what the user has open and what they are pointing at, right now. Takes no input.

Result:

| Field | Type | Required | Meaning |
|---|---|---|---|
| `app` | object | yes | `id` (the app's bundle identifier) and `name`. |
| `items` | array | yes | The [items](#5-items) currently open or selected. May be empty. |
| `focus` | array of strings | no | The ids of the most specific items the user is pointing at: the selection if there is one, otherwise the front document or view. More than one when several things are selected together. Absent or empty when nothing has focus. |

### 4.2 — locate

Asks where an item is on screen.

Input:

| Field | Type | Required | Meaning |
|---|---|---|---|
| `id` | string | yes | An item id the provider returned earlier. |

The result is a [location](#6-locations). An id the provider issued and whose item no longer exists is not an error: the provider answers with `state: "gone"`. An id the provider never issued is an error.

## 5. Items

An item is one thing the user has open or selected.

| Field | Type | Required | Meaning |
|---|---|---|---|
| `id` | string | yes | Short, opaque, unique within the provider, made of letters, digits, hyphens and underscores. See the lifetime rule in 9.1. |
| `type` | string | yes | A name the provider chooses, such as `document`, `selection`, `task`, `layer`. Hosts use it for grouping and display only. |
| `title` | string | yes | One line a person could read, such as a file name or a task's name. |
| `content` | array of content blocks | no | What the item contains, for the agent to read or see. See below. |
| `url` | string | no | An address for the thing, when it has one: a `file://` URL, a web URL, or a link the app itself opens. |
| `parent` | string | no | The id of the item this one sits inside, such as a selection's document. |
| `locatable` | boolean | no | Whether `locate` can answer for this item. Defaults to `false`. |
| `payload` | object | no | Anything else the provider wants an agent to have. Free-form. |

A provider decides how much to list. An editor with forty open files might list them all, since each costs one line. A task manager would list the open view and the selected tasks, not its whole database.

**Content blocks.** `content` uses MCP's `ContentBlock` type unchanged, so a host can hand the blocks to an agent without translating them. The block types, as of MCP schema `2026-07-28`:

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

Identity and position work the same as for text: the id is opaque, and `locate` returns the frame's bounding box as a list of one rectangle.

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

**Coordinates.** Version 0.1 is specified for macOS. Rectangles are in global display coordinates, in points, with the origin at the top-left corner of the primary display and y increasing downward. This is the space the macOS Accessibility API and Core Graphics use. AppKit's own coordinates have a bottom-left origin and must be converted.

**Hints.** `avoid` and `edge` are requests. A host should honor them when it can and may ignore them.

A location describes one moment. A host that needs to know whether an item moved asks again.

## 7. The MCP binding

A provider is an MCP server. The two operations are MCP resources. Everything in this section follows MCP revision `2026-07-28`; the details relied on are listed with their sources in [section 14](#14-mcp-details-this-draft-relies-on).

### 7.1 — The server

- **Address.** The provider listens on `127.0.0.1` only, on a port the system assigns at launch.
- **Transport.** MCP's Streamable HTTP transport: each JSON-RPC request is one HTTP `POST` to a single path. The provider may answer every request with a single JSON object (`Content-Type: application/json`); it does not need to stream.
- **Authentication.** Every request must carry `Authorization: Bearer <token>`. The token is random, made at launch, and published only in the descriptor file.
- **Browser protection.** The provider refuses any request that carries an `Origin` header. Only browsers send one, and no web page should be calling this server.
- **Required MCP methods.** `server/discover`, `resources/list`, `resources/templates/list` and `resources/read`. Nothing else is required.

### 7.2 — Declaring the extension

The provider lists the extension in its capabilities, which a client gets from `server/discover`:

```json
{
  "resultType": "complete",
  "supportedVersions": ["2026-07-28"],
  "capabilities": {
    "resources": {},
    "extensions": {
      "org.humanitas/ambient-context": { "version": "0.1" }
    }
  },
  "_meta": {
    "io.modelcontextprotocol/serverInfo": { "name": "Editor", "version": "2.3.0" }
  }
}
```

The settings object has one field, `version`, the version of this protocol the provider speaks. A client that does not know the extension ignores it and sees an ordinary server with two resources.

### 7.3 — The two resources

| Operation | Resource | Listed by |
|---|---|---|
| `current` | `ambient://current` | `resources/list` |
| `locate` | `ambient://location/{id}` | `resources/templates/list` |

A host performs an operation with `resources/read` on the address. For `locate`, the host puts the item's id in place of `{id}`.

The result's `contents` array holds exactly one entry: the `uri` that was read, `mimeType` `application/json`, and `text` holding the operation's result ([4.1](#41--current) or a [location](#6-locations)) as a JSON document.

`resources/list` returns:

```json
{
  "resultType": "complete",
  "resources": [
    {
      "uri": "ambient://current",
      "name": "current",
      "title": "Current context",
      "description": "What the user has open and selected in this app, right now.",
      "mimeType": "application/json"
    }
  ]
}
```

`resources/templates/list` returns:

```json
{
  "resultType": "complete",
  "resourceTemplates": [
    {
      "uriTemplate": "ambient://location/{id}",
      "name": "location",
      "title": "Location of an item",
      "description": "Where an item from the current context is on screen.",
      "mimeType": "application/json"
    }
  ]
}
```

A provider that cannot report positions leaves the template out. Its context still reaches the agent; the host places its own interface by default.

### 7.4 — Errors and refusals

| Case | Response |
|---|---|
| No `Authorization` header, or the wrong token | HTTP `401` |
| An `Origin` header is present | HTTP `403` |
| `locate` for an id whose item is gone | A normal result with `state: "gone"` |
| `locate` for an id the provider never issued | JSON-RPC error `-32602`, as MCP requires for a resource that does not exist |
| A method the provider does not implement | HTTP `404` with JSON-RPC error `-32601` |
| A protocol version the provider does not support | HTTP `400` with MCP's `UnsupportedProtocolVersionError` (`-32022`) |

### 7.5 — An optional tool

An agent connected straight to a provider, with no host between them, cannot read a resource on its own initiative in every MCP client. A provider may therefore also offer one tool, `context_current`, which takes no arguments and returns the `current` result as structured content, with the same JSON as a text block. It is a convenience for that case. A host never uses it, and a provider is complete without it.

### 7.6 — Older MCP clients

MCP revisions up to `2025-11-25` open with an `initialize` handshake, which `2026-07-28` removed. A provider should also answer that handshake, so that clients which have not moved yet can connect. MCP allows a server to support both.

## 8. Discovery

A host has to find the provider for the app in front. Version 0.1 defines one way, for apps that can write a file in the user's Library folder.

A running provider writes one descriptor file and removes it at quit.

- **Folder.** `~/Library/Application Support/AmbientContext/providers/`, created with permissions `0700`.
- **File.** `<bundle-id>.<pid>.json`, permissions `0600`.

```json
{
  "protocol": "0.1",
  "app": { "id": "org.example.editor", "name": "Editor", "version": "2.3.0" },
  "pid": 48211,
  "endpoint": "http://127.0.0.1:53124/mcp",
  "token": "q7Jm…",
  "started": "2026-11-09T21:14:03Z"
}
```

| Field | Meaning |
|---|---|
| `protocol` | The version of this protocol the provider speaks. The same value it declares in 7.2. |
| `app` | The app's bundle identifier, name and version. |
| `pid` | The provider's process id. |
| `endpoint` | The MCP endpoint. |
| `token` | The bearer token for this run. |
| `started` | When the provider started, in UTC. |

A provider writes the file after its listener is up. At launch it removes any descriptor left by an earlier run of itself that did not exit cleanly. When the user has turned the provider off, it writes no file and opens no listener.

**What the host does:**

1. When the user invokes it, take the front app's process id from the operating system.
2. Look for a descriptor with that process id. Ignore a file whose process is no longer running, whose bundle identifier does not match the process, or whose `protocol` the host does not support.
3. Read `ambient://current` with the token and a time limit of the host's choosing. On any failure, carry on with no context.
4. To place something beside an item, read `ambient://location/<id>`.

**Trust.** Any program running as the user can read the token. That is the same level of protection other local integrations of this kind use. A host can additionally check the provider's code signature from its process id without any change to the format.

**Apps that cannot do this.** A sandboxed app cannot write to a shared folder, and a web page cannot listen at all. Both can make an outgoing connection on the local machine. A later version will define a second mode in which the provider connects to the host and the same resources are read over that connection.

## 9. Rules

### 9.1 — For providers

- **Answer only when asked.** Send nothing unprompted.
- **Answer from what you already hold.** `current` is answered from state the app has in memory, without waiting on disk or network.
- **Keep ids meaningful.** An id refers to the thing it was minted for, for as long as that thing exists and the app is running. An id for a text selection keeps referring to that passage after the user selects something else, and follows the passage through edits where it can. A provider does not reuse an id while it is running. When the thing is gone, answer `gone`.
- **Expose what the user would expect.** The provider chooses what to list. It leaves out anything the user would be surprised to see handed to an agent, such as the contents of a password field or a private window.

### 9.2 — For hosts

- **Ask on the user's action.** Read `current` when the user invokes the agent, not on a timer.
- **Ask the front app only.** Which app is in front is the host's knowledge, from the operating system; `focus` in a provider's answer says what has focus inside that app. A host passes the front app's context in full. A user asking about a paragraph in an editor does not expect their mail to go along.
- **Show what was collected.** Before a message is sent, the user must be able to see which context will go with it, and remove it.
- **Pass ids through unchanged.** When an agent names an item, use exactly the id the provider issued.
- **Never wait on a provider.** Set a time limit. If a provider does not answer, or answers `offscreen` or `gone`, carry on without the context or the placement.

## 10. Versioning

The protocol has a version of the form `major.minor`, sent as a string. This draft is `0.1`.

- **Where it appears.** In the descriptor's `protocol` field, and in the extension's settings object in the provider's capabilities.
- **While the major version is 0,** any minor version may change or remove anything. A host and a provider work together only if they agree on the exact version. A host that does not support a provider's version treats the app as if it were not a provider.
- **From 1.0,** a minor version only adds: new optional fields, new resources, new values a receiver may ignore. Anything that would break an existing implementation takes a new major version.
- **Unknown fields are ignored.** A receiver must not fail on a field, an item `type` or a `payload` key it does not recognize.
- **MCP's version is separate.** Each request names the MCP revision it uses, and MCP's own rules settle that. This protocol's version says nothing about it, except that content blocks follow the MCP schema this version names (`2026-07-28` for `0.1`). A host skips block types it cannot handle.

Every change to this document that alters behavior bumps the version and is listed in the changelog at the end.

## 11. Implementing a provider

A provider has four jobs:

1. **Listen** on the loopback interface and answer the four MCP methods in 7.1, checking the token and refusing `Origin`.
2. **Write the descriptor** when the listener is up, and remove it at quit.
3. **Answer `current`:** list what is open and selected, mint an id for each, and name the focus.
4. **Answer `locate`:** look up an id and return the screen rectangles of what it refers to.

An app already has the information for the third in its window and selection state. It has the information for the fourth in the code that draws and hit-tests its content. The work is exposing it.

## 12. Not in version 0.1

- **What changed.** A request for what changed since a point the host names ("a task was moved to tomorrow"), so an agent can resolve "what I just did."
- **Watching.** A provider telling the host when context or a location changes. MCP resources already support subscriptions, so this needs no new mechanism, only a decision to allow it.
- **Other visible apps.** One line of context for each visible app that is not in front.
- **Actions.** A provider declaring operations an agent can run on an item.
- **Dial-in.** The second discovery mode in section 8.
- **Other platforms.** Coordinates and the descriptor folder are defined for macOS only.

## 13. Open questions

1. Whether an agent can ask to locate something the provider did not list, such as lines 40 to 42 of an open file. This would need a way to mint an id for an address.
2. How long ids must stay valid after the app quits and reopens, if at all.
3. Whether `content` needs size limits, and what a provider does with a very large selection or image.
4. Web apps: the page knows where an element is in the page, and only the browser knows where the page is on screen. Either the browser is the provider or something bridges the two.
5. The token in a file is not MCP's own authorization scheme, which is built on OAuth. Whether a local provider should offer that as well.
6. The final names: the extension identifier, the `ambient` address scheme, the descriptor folder and the protocol itself.

## 14. MCP details this draft relies on

Read from the MCP specification's source pages for revision `2026-07-28` (repository `modelcontextprotocol/modelcontextprotocol`, folder `docs/specification/2026-07-28/`, copied 2026.11.09).

| Detail | What the specification says | Page |
|---|---|---|
| Resources are for the application, tools for the model | Resources are "application-driven"; tools are "model-controlled" | `server/index.mdx`, `server/resources.mdx`, `server/tools.mdx` |
| Reading a resource | `resources/read` with `params.uri`; the result has `resultType` and `contents`, each entry with `uri`, `mimeType` and `text` or `blob` | `server/resources.mdx` |
| Parameterized resources | `resources/templates/list` returns `resourceTemplates`, each with a `uriTemplate` | `server/resources.mdx` |
| A resource that does not exist | JSON-RPC error `-32602`; never an empty `contents` | `server/resources.mdx` |
| Custom address schemes | Allowed, and must follow RFC 3986 | `server/resources.mdx` |
| Resource capability | A server offering resources declares `"resources": {}`; `subscribe` and `listChanged` are optional | `server/resources.mdx` |
| No handshake | Every request carries its protocol version in `_meta` under `io.modelcontextprotocol/protocolVersion`; a server must implement `server/discover` | `basic/versioning.mdx`, `server/discover.mdx` |
| Extensions | Advertised under `capabilities.extensions`, a map from identifier to settings object; identifiers take a vendor prefix in reverse DNS form; prefixes whose second label is `modelcontextprotocol` or `mcp` are reserved | `basic/versioning.mdx`, `basic/index.mdx` |
| HTTP transport | One endpoint accepting `POST`; a request is answered with one JSON object or an event stream; the client's `Accept` lists both | `basic/transports/streamable-http.mdx` |
| Required headers | `MCP-Protocol-Version` and `Mcp-Method` on every request; `Mcp-Name` carrying the address on `resources/read`; a mismatch with the body is refused with `400` and error `-32020` | `basic/transports/streamable-http.mdx` |
| Local servers | Must validate `Origin` and answer `403` when it is invalid; should bind to `127.0.0.1`; should authenticate | `basic/transports/streamable-http.mdx` |
| Unknown method and version | `404` with `-32601`; `400` with `-32022` | `basic/transports/streamable-http.mdx`, `basic/versioning.mdx` |
| Tool names | Letters, digits, underscore, hyphen and dot; 1 to 128 characters | `server/tools.mdx` |
| Older clients | A server may support both the `initialize` handshake and per-request metadata | `basic/versioning.mdx` |

## Changelog

- `0.1` · `2026.11.09` · First version. Two operations, `current` and `locate`; items with MCP content blocks; locations. Carried as an MCP extension: two resources on a loopback MCP server, found through a descriptor file.
