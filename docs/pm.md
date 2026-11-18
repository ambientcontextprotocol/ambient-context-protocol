# Ambient Context Protocol · Product Model

Last updated: `2026.11.18`

> A protocol by which a desktop app tells an ambient agent host what the user has open, what they have selected, and where an element is on screen. Version `0.2.4`; requirements are marked with the versions they hold in. First provider: Paper. First host: Sirius.

**Structure.** Domains, Features, Requirements and Verifications; each Requirement restates the [specification](spec/index.md) as something an outside check can test.

## Contents

1. [Ontology](#1-ontology)
2. [Domains](#2-domains)
3. [Features and requirements](#3-features-and-requirements)
   - [3.1 — Context](#31--context)
   - [3.2 — Identity](#32--identity)
   - [3.3 — Location](#33--location)
   - [3.4 — Discovery](#34--discovery)
   - [3.5 — Binding](#35--binding)
   - [3.6 — Compatibility](#36--compatibility)
   - [3.7 — Security](#37--security)
   - [3.8 — Host](#38--host)
4. [Verifications](#4-verifications)
5. [Coverage](#5-coverage)

---

## Principles

1. *The app says where; the host decides what.* A provider reports items and their positions. It never names what the host draws there.
2. *A shared language for how a thing is shown, the app's own word for what it is.* Every element has a role from a short fixed list; what the thing is to the app goes in its subrole and attributes. A text editor, a task tracker and a design tool all fit without the protocol knowing what a task or a frame is. (In 0.1: an envelope, not a domain model.)
3. *Pulled on the user's action, and kept current while the user is looking.* A host asks for context when the user does something that calls for it. While it is showing the user what it read, it may ask the provider to say when that changes. A provider sends nothing a host did not ask for, and a host does not poll.
4. *It is ordinary MCP.* A provider is an MCP server and the two answers are MCP resources. A client that has never heard of the protocol can still list and read them.

---

## 1. Ontology

Four levels. The first three are structure; the fourth says how a requirement is checked.

| Level | ID | What it is |
|---|---|---|
| **Domain** | abbreviation | An area of the protocol that groups related Features. |
| **Feature** | `F-xxn` | A coherent capability, identifiable for planning. Has a priority and one or more Requirements. |
| **Requirement** | `PR-nnn` | A specific, testable condition the product must satisfy. Specifies one Feature. |
| **Verification** | `V-nnn` | A defined way of establishing whether one Requirement is met. It does not record that it was run or that it passed. |

```
Domain: Security
└── Feature: F-SE1 Access control (P0)
    ├── PR-032 "A provider refuses a request that lacks the token."
    │   └── V-010 "POST to the endpoint with no Authorization header; expect a refusal."
    └── PR-033 "A provider refuses any request carrying an Origin header."
        └── V-011 "POST with a valid token and an Origin header; expect a refusal."
```

**Priority.** `P0` is in the version named in "Since". `P1` is next. `P2` and below are named so the design leaves room, and are not built.

**Who must satisfy it.** Each Requirement binds a provider, a host, or both. The "On" column says which.

---

## 2. Domains

| Domain | Abbrev | What it covers |
|---|---|---|
| **Context** | `CX` | What the user has open and in focus, and the shape it is reported in |
| **Identity** | `ID` | How an item is named so it can be referred to later |
| **Location** | `LO` | Where an item is on screen |
| **Discovery** | `DI` | How a host finds a running provider |
| **Binding** | `BI` | How the protocol is expressed over a concrete protocol; first MCP |
| **Compatibility** | `CO` | Versions, declaration and how the two sides tolerate differences |
| **Security** | `SE` | Who may call a provider |
| **Host** | `HO` | What a host may do with context once it has it |

---

## 3. Features and requirements

Each Feature is followed by the Requirements that specify it. "On" says who must satisfy the Requirement. "Verified by" points to [§4](#4-verifications); a dash means no Verification is defined yet.

**Versions.** "Since" is the first protocol version a Requirement holds in. "Until" is the last; a dash means it still holds. "RFC" names the proposal that added it. A Requirement is never reworded when the protocol changes: it is retired and a new one takes its place, so the list for any version can be read back exactly. `python3 tools/requirements.py 0.2.0` prints the Requirements of a version. In Requirements that date from 0.1, "item" means what 0.2.0 calls an element.

### 3.1 — Context

**F-CX1 — Current context** · P0. A provider reports the items the user has open and which are in focus.

| Requirement | Statement | On | Priority | Verified by | Since | Until | RFC |
|---|---|---|---|---|---|---|---|
| **PR-001** — Current | On request, a provider returns in one response the items the user has open in the app and the focus. | Provider | P0 | V-001 | 0.1 | 0.1 | — |
| **PR-002** — Item shape | Every item has `id`, `type` and `title`. An item may have `content`, `url`, `parent`, `locatable` and `payload`. | Provider | P0 | — | 0.1 | 0.1 | — |
| **PR-003** — Focus | The response names the focus as an ordered list of item ids. A selection is an item whose `parent` is the item it was made in. | Provider | P0 | — | 0.1 | 0.1 | — |
| **PR-004** — Response time | A provider answers a request for current context from state it already holds, without waiting on disk or network. A host sets its own time limit and proceeds without context when the limit passes. | Both | P0 | V-002 | 0.1 | — | — |
| **PR-047** — Current as a tree | On request, a provider returns in one response an object with exactly `protocol`, `instance` and `root`. `root` is one tree of elements holding everything the provider reports. Replaces PR-001. | Provider | P0 | — | 0.2.0 | 0.2.0 | [0001](rfcs/0001-element-model.md) |
| **PR-048** — Element shape | Every element has `id` and `role`. An element may have `subrole`, `title`, `content`, `url`, `selected`, `focused`, `visible`, `hovered`, `children` and `attributes`. An empty `children` list is not sent. Replaces PR-002. | Provider | P0 | — | 0.2.0 | — | [0001](rfcs/0001-element-model.md) |
| **PR-049** — Role language | Every `role` is one of the thirteen in the specification, §5.2. The root is an `Application` and no other element is. A provider does not report controls, menus, indicators or window furniture. | Provider | P0 | — | 0.2.0 | — | [0001](rfcs/0001-element-model.md) |
| **PR-050** — State said once | A provider states `selected`, `focused`, `visible` and `hovered` only on the element they describe. `selected`, `focused` and `hovered` are sent only when true. | Provider | P0 | — | 0.2.0 | — | [0001](rfcs/0001-element-model.md) |
| **PR-051** — Focus path | `focused` is set on every element on the path from a child of the root to the user's position, with no gaps. No two siblings are focused, and no element below the root's children is focused unless its parent is. Replaces PR-003. | Provider | P0 | — | 0.2.0 | — | [0001](rfcs/0001-element-model.md) |
| **PR-052** — Absent states | A host reads an absent `selected`, `focused` or `hovered` as false and an absent `visible` as the parent's value, with the root visible. | Host | P0 | — | 0.2.0 | — | [0001](rfcs/0001-element-model.md) |
| **PR-053** — Hover is one element | At most one element in an answer has `hovered` true: the innermost reported element under the pointer. No ancestor or descendant of it is marked. | Provider | P0 | — | 0.2.0 | — | [0003](rfcs/0003-hovered-state.md) |
| **PR-054** — Hover is true | An element marked `hovered` is the one under the pointer when the provider answers. A provider creates no element in order to mark it. | Provider | P0 | — | 0.2.0 | — | [0003](rfcs/0003-hovered-state.md) |
| **PR-055** — Absent hover | A host infers nothing from `hovered` being absent everywhere. | Host | P0 | — | 0.2.0 | — | [0003](rfcs/0003-hovered-state.md) |
| **PR-072** — Current as a tree, with display | On request, a provider returns in one response an object with `protocol`, `instance` and `root`, optionally `display`, and nothing else. `root` is one tree of elements holding everything the provider reports. Replaces PR-047. | Provider | P0 | — | 0.2.1 | 0.2.3 | [0005](rfcs/0005-display-and-favicon.md) |
| **PR-074** — Display shape | `display`, when sent, is an object. Its `title` and `detail`, when sent, are strings of plain text on one line, each of 80 characters or fewer. | Provider | P0 | — | 0.2.1 | — | [0005](rfcs/0005-display-and-favicon.md) |
| **PR-075** — Display says no more than the tree | `display` describes the same moment and the same tree as the answer it is in. It holds no content the provider does not report as an element and names nothing from an element the provider left out. | Provider | P0 | — | 0.2.1 | — | [0005](rfcs/0005-display-and-favicon.md) |
| **PR-080** — Watch offered | A provider that offers `watch` declares `"resources": {"subscribe": true}` and answers `subscriptions/listen` whose `resourceSubscriptions` names `ambient://current` with an event stream. The first message on it is `notifications/subscriptions/acknowledged`, naming that address and no other. | Provider | P1 | — | 0.2.2 | — | [0006](rfcs/0006-watching.md) |
| **PR-081** — Watch not offered | A provider that does not offer `watch` declares no `subscribe` and answers `subscriptions/listen` as a method it does not implement: HTTP `404` with error `-32601`. | Provider | P0 | — | 0.2.2 | — | [0006](rfcs/0006-watching.md) |
| **PR-082** — Notice shape | A notice is `notifications/resources/updated` with `uri` `ambient://current` and the subscription id, and nothing from the app. A provider sends no notification type or address the host did not ask for. | Provider | P0 | — | 0.2.2 | — | [0006](rfcs/0006-watching.md) |
| **PR-083** — Notices are coalesced | A provider sends at most one notice in any 250 milliseconds on one watch, and the last change always produces a notice. | Provider | P0 | — | 0.2.2 | — | [0006](rfcs/0006-watching.md) |
| **PR-084** — Hover alone is no change | A change in `hovered` alone produces no notice. Any other change to the answer to `current`, `display` included, does. | Provider | P0 | — | 0.2.2 | — | [0006](rfcs/0006-watching.md) |
| **PR-085** — Quiet watches are kept alive | On a watch with nothing to say, a provider sends an SSE comment line at least every 15 seconds. | Provider | P1 | — | 0.2.2 | — | [0006](rfcs/0006-watching.md) |
| **PR-086** — Watches end with the provider | A provider ends every watch when it quits and when the user turns it off. It may limit the watches it holds at once, to no fewer than four, and may end any watch at any time. | Provider | P0 | — | 0.2.2 | — | [0006](rfcs/0006-watching.md) |
| **PR-099** — Current as a tree, with display and sensitive | On request, a provider returns in one response an object with `protocol`, `instance` and `root`, optionally `display` and `sensitive`, and nothing else. `root` is one tree of elements holding everything the provider reports. Replaces PR-072. | Provider | P0 | — | 0.2.4 | — | [0007](rfcs/0007-sensitive-context.md) |
| **PR-100** — Sensitive is true | `sensitive`, when sent, is the boolean `true`. A provider with no reason to mark an answer leaves the field out and never sends `false`. It is sent on the answer and is not in the descriptor. | Provider | P0 | — | 0.2.4 | — | [0007](rfcs/0007-sensitive-context.md) |

**F-CX2 — Content** · P0. An item carries its content in a form any agent can read.

| Requirement | Statement | On | Priority | Verified by | Since | Until | RFC |
|---|---|---|---|---|---|---|---|
| **PR-005** — Content blocks | `content` is a list of MCP content blocks, unchanged from the MCP specification. | Provider | P0 | — | 0.1 | — | — |
| **PR-006** — Open types | `type` is an open string and `payload` is app-defined. The protocol defines no item types beyond the envelope. | Both | P0 | — | 0.1 | 0.1 | — |
| **PR-046** — Limits | A provider stays within stated bounds on the size of an item's content, the number of items in one answer and the number of ids it keeps alive. The bounds are not set yet (protocol §13, question 3). | Provider | P1 | — | 0.1 | — | — |
| **PR-056** — Open subrole and attributes | `subrole` is an open string and `attributes` is app-defined. A provider puts its own word for a thing in `subrole`, never in `role`, and gives a subrole to each thing that is the app's own kind. Replaces PR-006. | Both | P0 | — | 0.2.0 | — | [0001](rfcs/0001-element-model.md) |
| **PR-057** — Relations | A link between two elements that is not containment is expressed in the `related` attribute. | Provider | P1 | — | 0.2.0 | — | [0001](rfcs/0001-element-model.md) |
| **PR-058** — Author | A provider sends the `author` attribute only where the app already shows the author. | Provider | P0 | — | 0.2.0 | — | [0001](rfcs/0001-element-model.md) |

**F-CX3 — Changes since** · P2. A provider reports what changed since a given point.

| Requirement | Statement | On | Priority | Verified by | Since | Until | RFC |
|---|---|---|---|---|---|---|---|
| **PR-007** — Changes since | A provider returns the items added, changed and removed since a point the host names. | Provider | P2 | — | 0.1 | — | — |

### 3.2 — Identity

**F-ID1 — Item ids** · P0. Every item has a short id that keeps meaning the same thing.

| Requirement | Statement | On | Priority | Verified by | Since | Until | RFC |
|---|---|---|---|---|---|---|---|
| **PR-008** — Opaque ids | An id is a short string minted by the provider, such as `sel-23`. A host does not parse it. | Both | P0 | — | 0.1 | — | — |
| **PR-009** — Stable under edits | An id keeps referring to the same item after the surrounding content is edited. | Provider | P0 | V-003, V-019 | 0.1 | — | — |
| **PR-010** — No reuse | A provider does not reuse an id while it is running. When the item no longer exists, the provider says it is gone. | Provider | P0 | — | 0.1 | — | — |
| **PR-059** — Id form and uniqueness | An id is 1 to 128 letters, digits, hyphens and underscores, and is unique within one answer. The same thing shown twice is two elements with two ids. | Provider | P0 | — | 0.2.0 | — | [0001](rfcs/0001-element-model.md) |

**F-ID2 — Provider instance** · P0. An id is tied to the provider that issued it and to one run of that provider.

| Requirement | Statement | On | Priority | Verified by | Since | Until | RFC |
|---|---|---|---|---|---|---|---|
| **PR-040** — Instance value | A provider mints a random `instance` value each time it starts, returns it with current context and writes it in its descriptor. | Provider | P0 | V-013 | 0.1 | — | — |
| **PR-041** — Provider kept with the id | A host records which provider and which `instance` issued every id it passes to an agent. It resolves an id only with that provider and only while the instance is unchanged, and otherwise treats the item as gone. It never looks an id up again by app name or process id. | Host | P0 | V-014 | 0.1 | — | — |

### 3.3 — Location

**F-LO1 — Locate** · P0. Given an id, a provider says where the item is on screen.

| Requirement | Statement | On | Priority | Verified by | Since | Until | RFC |
|---|---|---|---|---|---|---|---|
| **PR-011** — Locate | Given an id, a provider returns a location: `state` (`visible`, `offscreen` or `gone`), `rects` and `window`. | Provider | P0 | — | 0.1 | — | — |
| **PR-012** — Coordinates | Rectangles are in global screen coordinates, in points, with the origin at the top left of the primary display. | Provider | P0 | V-021 | 0.1 | — | — |
| **PR-013** — Accuracy | Rectangles agree, within 2 points, with what the platform accessibility API reports for the same item. | Provider | P0 | V-004, V-020 | 0.1 | — | — |
| **PR-014** — Placement hints | A location may carry `avoid` (a rectangle the host should not cover) and `edge` (the side the provider prefers). A host may ignore both. | Both | P0 | — | 0.1 | — | — |
| **PR-060** — An element that cannot be placed | A provider that cannot place a particular element answers `locate` for it as for an id it never issued. Whether an element can be located is not declared in advance. | Provider | P0 | — | 0.2.0 | — | [0001](rfcs/0001-element-model.md) |
| **PR-015** — No host UI in the protocol | No message names a host interface element. A provider cannot ask a host to draw anything. | Both | P0 | — | 0.1 | — | — |

**F-LO2 — Watch** · P3. A provider tells the host when an item moves.

| Requirement | Statement | On | Priority | Verified by | Since | Until | RFC |
|---|---|---|---|---|---|---|---|
| **PR-016** — Watch | A provider notifies the host when a located item moves, scrolls out of view or is removed. | Provider | P3 | — | 0.1 | — | — |

### 3.4 — Discovery

**F-DI1 — Announce** · P0. A running provider writes a descriptor file a host can read.

| Requirement | Statement | On | Priority | Verified by | Since | Until | RFC |
|---|---|---|---|---|---|---|---|
| **PR-017** — Descriptor | While it is running and enabled, a provider keeps a descriptor file named `<app-id>.<pid>.json` in the descriptor folder its platform's profile gives (specification 8.1); on macOS, `~/Library/Application Support/AmbientContext/providers/<bundle-id>.<pid>.json`. | Provider | P0 | V-005 | 0.1 | — | — |
| **PR-018** — Descriptor fields | The descriptor holds `protocol`, `app`, `pid`, `instance`, `endpoint`, `token` and `started`. | Provider | P0 | — | 0.1 | — | — |
| **PR-019** — Descriptor permissions | The providers folder is mode `0700` and each descriptor is mode `0600`. | Provider | P0 | V-006 | 0.1 | — | — |
| **PR-020** — Descriptor removal | A provider removes its descriptor when it quits. A host ignores a descriptor whose `pid` is not running. | Both | P0 | V-007, V-016 | 0.1 | — | — |
| **PR-021** — Off means absent | When the user has turned the provider off, it writes no descriptor and opens no listener. | Provider | P0 | V-008 | 0.1 | — | — |
| **PR-042** — Atomic write | A provider writes its descriptor after its listener is up, to a temporary name in the same folder, then renames it into place. | Provider | P0 | — | 0.1 | — | — |
| **PR-043** — Endpoint check | Before using a descriptor, a host checks that the endpoint's address is `127.0.0.1` and that the process listening on its port is the process the descriptor names. It does not follow redirects, and it ignores an answer whose `instance` differs from the descriptor's. | Host | P0 | V-015 | 0.1 | — | — |
| **PR-061** — Answer version | A host ignores an answer whose `protocol` differs from the descriptor's. | Host | P0 | — | 0.2.0 | — | — |
| **PR-078** — Favicon place | An app that ships a favicon for hosts ships one SVG or PNG image at the place its platform's profile gives (specification 8.1); on macOS, `Contents/Resources/favicon.svg` in the app's bundle, or `favicon.png` there when there is no SVG. A PNG is at least 32 by 32 pixels. No descriptor or answer names or carries it. | Provider | P1 | — | 0.2.1 | — | [0005](rfcs/0005-display-and-favicon.md) |
| **PR-079** — Favicon found by the host | A host reads an app's favicon only from the profile's place in the installed app whose process it identified as in front, never from a path, URL or bytes a provider or descriptor names. It bounds the size it reads and treats a file that is missing, too large or not a readable image as absent. | Host | P0 | — | 0.2.1 | — | [0005](rfcs/0005-display-and-favicon.md) |
| **PR-093** — Answering for the app that started it | A provider writes `for` only when the app it names is its parent process, names its descriptor `<for.id>.<for.pid>.for.<pid>.json`, and removes it when that app closes its connection or quits. | Provider | P0 | — | 0.2.3 | — | [0004](rfcs/0004-a-provider-started-by-the-app.md) |
| **PR-094** — A helper is accepted only from its app | A host looks for a provider that answers for the front app only when that app has no descriptor of its own. It accepts one only when `for` names the front app and its process, the provider passes every check an app's own provider passes, and the front app is the provider's direct parent; it refuses one whose parent is any other process. | Host | P0 | — | 0.2.3 | — | [0004](rfcs/0004-a-provider-started-by-the-app.md) |
| **PR-095** — Several helpers | When more than one provider answers for the front app, a host uses the answer whose tree has a focus path, or the first to answer if none has. It may bound how many it reads. | Host | P1 | — | 0.2.3 | — | [0004](rfcs/0004-a-provider-started-by-the-app.md) |

**F-DI2 — Discovery without a descriptor** · P2. A provider that cannot announce itself with a descriptor is still found.

| Requirement | Statement | On | Priority | Verified by | Since | Until | RFC |
|---|---|---|---|---|---|---|---|
| **PR-022** — Discovery without a descriptor | A provider that cannot write to the shared folder (a sandboxed Mac app) or cannot listen (a web page) can still be found and read. The mechanism is not designed; connecting out to the host is one candidate. | Both | P2 | — | 0.1 | — | — |

### 3.5 — Binding

**F-BI1 — MCP binding** · P0. The protocol's operations are MCP resources on a local MCP server.

| Requirement | Statement | On | Priority | Verified by | Since | Until | RFC |
|---|---|---|---|---|---|---|---|
| **PR-023** — MCP server | A provider is an MCP server reached by `POST /mcp` at the descriptor's `endpoint`. | Provider | P0 | — | 0.1 | 0.1 | — |
| **PR-024** — Two resources | The provider offers `current` as the resource `ambient://current` and `locate` as the resource template `ambient://location/{id}`. Each is read with `resources/read` and returns one JSON document. The host's code reads them; the model does not call them. | Provider | P0 | — | 0.1 | — | — |
| **PR-025** — Any MCP client | An MCP client with no knowledge of this protocol can list and read both resources, given only the endpoint and token. | Provider | P0 | V-009 | 0.1 | — | — |
| **PR-026** — MCP versions | The provider speaks MCP `2026-07-28`. It should also serve clients that use the older `initialize` handshake, following that revision's rules for requests, results and errors. | Provider | P0 | — | 0.1 | — | — |
| **PR-044** — Request metadata | A host sends `protocolVersion` and `clientCapabilities` in `_meta` on every request, as MCP `2026-07-28` requires. A provider refuses a request missing either with HTTP `400` and error `-32602`. | Both | P0 | V-017 | 0.1 | 0.1 | — |
| **PR-062** — Endpoint path | A provider is an MCP server reached by `POST` at the descriptor's `endpoint`. The path is the provider's choice, begins with `/` and has no query or fragment; a host uses it as given. Replaces PR-023. | Both | P0 | — | 0.2.0 | — | [0002](rfcs/0002-shared-listener.md) |
| **PR-063** — Shared listener | On a listener the app shares with other routes, the token and `Origin` checks are enforced on the endpoint's path before any other handling. The path does not answer a cross-origin preflight with permission, and no response from it carries an `Access-Control-Allow-*` header. | Provider | P0 | — | 0.2.0 | — | [0002](rfcs/0002-shared-listener.md) |
| **PR-064** — Request metadata by revision | A host sends `protocolVersion` and `clientCapabilities` in `_meta` on every request, as MCP `2026-07-28` requires. A provider refuses a request that names `2026-07-28` and lacks either, with HTTP `400` and error `-32602`. A request that names no MCP version is served as an older client. Replaces PR-044. | Both | P0 | — | 0.2.0 | — | — |
| **PR-065** — Refusals | A provider answers an HTTP method other than `POST` with `405`, an oversized request with `413`, and a required MCP header that is missing or disagrees with the body with `400` and error `-32020`. | Provider | P0 | — | 0.2.0 | — | — |

### 3.6 — Compatibility

**F-CO1 — Versioning** · P0. Both sides know which version the other speaks and degrade safely.

| Requirement | Statement | On | Priority | Verified by | Since | Until | RFC |
|---|---|---|---|---|---|---|---|
| **PR-027** — Declared version | A provider declares the protocol and its version as an MCP extension: `"org.humanitas/ambient-context": {"version": "0.1"}`. | Provider | P0 | — | 0.1 | 0.1 | — |
| **PR-028** — Version in the descriptor | The descriptor's `protocol` field carries the same version, so a host can decide before connecting. | Provider | P0 | — | 0.1 | — | — |
| **PR-029** — Unknown fields | Both sides ignore fields they do not recognize. | Both | P0 | — | 0.1 | — | — |
| **PR-030** — Unsupported version | A host that does not support a provider's version treats the app as if it were not a provider. | Host | P0 | — | 0.1 | — | — |
| **PR-066** — Declared version, three places | A provider gives the same version, `0.2.0`, in the MCP extension `"io.github.ambientcontextprotocol/context": {"version": "0.2.0"}`, in the descriptor and in the `current` answer. Replaces PR-027. | Provider | P0 | — | 0.2.0 | 0.2.0 | [0001](rfcs/0001-element-model.md) |
| **PR-067** — Version agreement | Before 1.0 a host and a provider work together only if they agree on the major and minor parts of the version. A patch version only adds. | Both | P0 | — | 0.2.0 | — | [0001](rfcs/0001-element-model.md) |
| **PR-068** — Unknown role | A receiver treats a role it does not know as `Group`. | Both | P0 | — | 0.2.0 | — | [0001](rfcs/0001-element-model.md) |
| **PR-092** — Declared version, three places | A provider gives the same version, `0.2.2`, in the MCP extension `"io.github.ambientcontextprotocol/context": {"version": "0.2.2"}`, in the descriptor and in the `current` answer. Replaces PR-073. | Provider | P0 | — | 0.2.2 | 0.2.2 | [0006](rfcs/0006-watching.md) |
| **PR-098** — Declared version, three places | A provider gives the same version, `0.2.3`, in the MCP extension `"io.github.ambientcontextprotocol/context": {"version": "0.2.3"}`, in the descriptor and in the `current` answer. Replaces PR-092. | Provider | P0 | — | 0.2.3 | 0.2.3 | [0004](rfcs/0004-a-provider-started-by-the-app.md) |
| **PR-106** — Declared version, three places | A provider gives the same version, `0.2.4`, in the MCP extension `"io.github.ambientcontextprotocol/context": {"version": "0.2.4"}`, in the descriptor and in the `current` answer. Replaces PR-098. | Provider | P0 | — | 0.2.4 | — | [0007](rfcs/0007-sensitive-context.md) |
| **PR-073** — Declared version, three places | A provider gives the same version, `0.2.1`, in the MCP extension `"io.github.ambientcontextprotocol/context": {"version": "0.2.1"}`, in the descriptor and in the `current` answer. Replaces PR-066. | Provider | P0 | — | 0.2.1 | 0.2.1 | [0005](rfcs/0005-display-and-favicon.md) |

### 3.7 — Security

**F-SE1 — Access control** · P0. Only a local process that can read the user's descriptor can call a provider. A hostile program already running as the user is outside what version 0.1 defends against: it can read the token, and the user's documents, without this protocol. The token shows that a caller can read the user's files, not that the user approved the caller.

| Requirement | Statement | On | Priority | Verified by | Since | Until | RFC |
|---|---|---|---|---|---|---|---|
| **PR-031** — Loopback only | A provider listens on `127.0.0.1` only. | Provider | P0 | — | 0.1 | — | — |
| **PR-032** — Token required | A provider refuses a request that lacks `Authorization: Bearer <token>` with the descriptor's token. | Provider | P0 | V-010 | 0.1 | — | — |
| **PR-033** — No browser origin | A provider refuses any request that carries an `Origin` header. A host does not send one. | Both | P0 | V-011 | 0.1 | — | — |
| **PR-034** — Token lifetime | A provider mints a new token at each launch and stores it nowhere but the descriptor. | Provider | P0 | — | 0.1 | — | — |
| **PR-069** — Token for this endpoint only | The token is not a credential the app's server accepts anywhere else. | Provider | P0 | — | 0.2.0 | — | [0002](rfcs/0002-shared-listener.md) |
| **PR-070** — Nothing in logs | A provider writes neither its token nor anything from an answer to a log. | Provider | P0 | — | 0.2.0 | — | [0002](rfcs/0002-shared-listener.md) |
| **PR-087** — Watch behind the same checks | The watch request is refused without the token (`401`) and with an `Origin` header (`403`) before any stream opens. | Provider | P0 | — | 0.2.2 | — | [0006](rfcs/0006-watching.md) |
| **PR-096** — Second-hand is said | A provider that answers for another app sets `via` among the root's attributes, a short lowercase word for how it learned what it reports (`browser-extension` for a browser extension's helper). | Provider | P0 | — | 0.2.3 | — | [0004](rfcs/0004-a-provider-started-by-the-app.md) |
| **PR-097** — Sites never read | A provider that can report any site keeps a list of sites whose pages it does not read, which the user can see and change, starting with sign-in and password sites. For a listed site it reports nothing in the page. Not checkable from outside: an inspection of the provider. | Provider | P0 | — | 0.2.3 | — | [0004](rfcs/0004-a-provider-started-by-the-app.md) |
| **PR-101** — Marking is not leaving out | A provider that marks an answer sensitive still leaves out what it must never report. Not checkable from outside: a provider's own test. | Provider | P0 | — | 0.2.4 | — | [0007](rfcs/0007-sensitive-context.md) |
| **PR-107** — Redaction is the provider's | A provider removes or masks private details inside what it reports, reports only what should leave the app, and does not rely on a host to inspect, classify or redact an answer. No host is required to. Not checkable from outside: a provider's own test. | Provider | P0 | — | 0.2.4 | — | [0007](rfcs/0007-sensitive-context.md) |

### 3.8 — Host

**F-HO1 — Consent** · P0. The user sees what context will be sent and can remove it.

| Requirement | Statement | On | Priority | Verified by | Since | Until | RFC |
|---|---|---|---|---|---|---|---|
| **PR-035** — User action | A host requests context only in response to an action by the user. | Host | P0 | — | 0.1 | 0.2.1 | — |
| **PR-036** — Shown and removable | Before context is sent to an agent, the host shows the user what will be sent and lets them remove it. | Host | P0 | — | 0.1 | — | — |
| **PR-045** — Removed means removed | If the user removes context, or sends the message, while a provider's answer is still on its way, the host discards the late answer. | Host | P0 | V-018 | 0.1 | — | — |

**F-HO2 — Scope** · P0. A host limits how much context it takes and from which apps.

| Requirement | Statement | On | Priority | Verified by | Since | Until | RFC |
|---|---|---|---|---|---|---|---|
| **PR-037** — Front app in full | A host takes full context from the frontmost app only. | Host | P0 | — | 0.1 | — | — |
| **PR-038** — Other apps in one line | For each other visible app that is a provider, a host may include one line naming the app and its focused item. | Host | P1 | — | 0.1 | — | — |
| **PR-039** — No provider, no change | With an app in front that is not a provider, a host behaves exactly as it would without the protocol. | Host | P0 | V-012 | 0.1 | — | — |
| **PR-071** — Hover is weaker | A host presents `hovered` to an agent as where the pointer is, distinct from and weaker than `selected`, and sends no more of an element's content because it is hovered. | Host | P0 | — | 0.2.0 | — | [0003](rfcs/0003-hovered-state.md) |
| **PR-076** — Display read leniently | A host uses `display` only when its `title` is a non-empty string. It reads a `display` that is not an object, or a `title` or `detail` that is not a string, as absent, and never refuses an answer because of it. | Host | P0 | — | 0.2.1 | — | [0005](rfcs/0005-display-and-favicon.md) |
| **PR-077** — Display drawn as plain text | A host draws `display` as plain text on one line, cut to a length of its choosing, with control characters removed and no markup or links interpreted. It remains a label: the user can still remove the context it names. | Host | P0 | — | 0.2.1 | — | [0005](rfcs/0005-display-and-favicon.md) |
| **PR-088** — Read on an action or a notice | A host reads `current` only in response to an action by the user or to a notice on a watch it holds. Replaces PR-035. | Host | P0 | — | 0.2.2 | — | [0006](rfcs/0006-watching.md) |
| **PR-089** — One watch, in view | A host opens a watch only on the provider it has just read on the user's action, and only while it is showing the user that provider's context. It holds one at a time and ends it when the message is sent, the context is removed or its interface closes. | Host | P0 | — | 0.2.2 | — | [0006](rfcs/0006-watching.md) |
| **PR-090** — A notice is not context | A host learns the new state only by reading `current`, with every check a read has. It never has two reads outstanding: a notice that arrives during a read causes one more read after it. | Host | P0 | — | 0.2.2 | — | [0006](rfcs/0006-watching.md) |
| **PR-091** — A lost watch is silence | When a watch's stream ends or fails, a host carries on with what it last read, shows the user no error, and tries to open the watch again at most once. It still reads at send. | Host | P0 | — | 0.2.2 | — | [0006](rfcs/0006-watching.md) |
| **PR-102** — Sensitive read leniently | A host reads only the JSON value `true` as sensitive. It reads `false`, a missing field and a value of any other type as absent, and never refuses an answer because of it. | Host | P0 | — | 0.2.4 | — | [0007](rfcs/0007-sensitive-context.md) |
| **PR-103** — Confirm before sending | A host does not send context from an answer marked sensitive to an agent, or anywhere off the device, until the user has confirmed that send knowing which app it came from, or has earlier told the host not to ask for that app. That choice is kept per app, for the app answered for when a helper answers, and can be undone. | Host | P0 | — | 0.2.4 | — | [0007](rfcs/0007-sensitive-context.md) |
| **PR-104** — No way to ask | A host with no way to ask the user leaves context marked sensitive out and tells the user it did. | Host | P0 | — | 0.2.4 | — | [0007](rfcs/0007-sensitive-context.md) |
| **PR-105** — Absence is not safety | A host never treats the absence of `sensitive`, or `"sensitive": false`, as a reason to skip a warning it would otherwise give. Not checkable from outside: an inspection of the host. | Host | P0 | — | 0.2.4 | — | [0007](rfcs/0007-sensitive-context.md) |

---

## 4. Verifications

Each Verification checks one Requirement; a Requirement may have several. The "Plan" column numbers the line of the original implementation plan each came from; a dash marks one added later.

| Verification | Description | Verifies | Plan |
|---|---|---|---|
| **V-001** — Current returns open items | With two documents open and a sentence selected, read `ambient://current`. The response lists both documents and the selection, and the focus names the selection. | PR-001 | 3 |
| **V-002** — Current is fast | Read `ambient://current` 100 times with a 1,000-word document open, then with 50,000 words, then with 500,000. No call exceeds the time limit of the host under test, and the median time at the largest size is within a small factor of the median at the smallest. | PR-004 | 3 |
| **V-003** — Id survives edits | Select a passage and record its id. Type a paragraph above it. Reading its location with that id returns the same passage at its new position. | PR-009 | 5 |
| **V-004** — Locate matches Accessibility | Select a passage. Compare the rectangles from its location with the bounds the platform accessibility API reports for the same range. They agree within 2 points. The Accessibility reading does not pass through the provider's protocol code. | PR-013 | 4 |
| **V-005** — Descriptor exists | Launch the provider with its setting on. A descriptor with all seven fields exists in the providers folder. | PR-017 | 1 |
| **V-006** — Descriptor is private | Read the modes of the providers folder and the descriptor. They are `0700` and `0600`. | PR-019 | 1 |
| **V-007** — Descriptor is removed on quit | Quit the provider. Its descriptor is gone. | PR-020 | 1 |
| **V-008** — Off means absent | Launch the provider with its setting off. No descriptor exists and no port is open. | PR-021 | 9 |
| **V-009** — A foreign MCP client works | With a stock MCP client that is not the host, given only `endpoint` and `token`, list the resources and the template and read both. Both return results. | PR-025 | 6 |
| **V-010** — Token is required | Send a request with no `Authorization` header, then one with a wrong token. Both are refused. | PR-032 | 2 |
| **V-011** — Origin is refused | Send a request with a valid token and an `Origin` header. It is refused. | PR-033 | 2 |
| **V-012** — No provider, no change | Put an app that is not a provider in front and use the host. Its behavior and the agent's message match those of a host with the protocol disabled. | PR-039 | 9 |
| **V-013** — Instance changes per launch | Read `ambient://current` and the descriptor: both carry the same `instance`. Quit and relaunch the provider. Both now carry a different value. | PR-040 | — |
| **V-014** — An old id is gone after restart | Give the host an id from a provider. Restart the provider and make it issue the same id for a different item. Ask the host to locate the id. It reports the item as gone and does not return the new item's position. Repeat with two providers that issue the same id: the host asks only the one that issued it. | PR-041 | — |
| **V-015** — A false endpoint is ignored | Write a descriptor that names a running app's process but points at a server run by another process. Then one whose endpoint is not `127.0.0.1`, and one whose server answers with a redirect. The host uses none of them. | PR-043 | — |
| **V-016** — A stale descriptor is ignored | Kill the provider so that its descriptor stays behind. The host ignores the file. Start another process that receives the same process id where the test can arrange it; the host still ignores the file, because the bundle identifier does not match. | PR-020 | — |
| **V-017** — Request metadata is required | Send a request without `clientCapabilities` in `_meta`, then one without `protocolVersion`. Both are refused with HTTP `400` and error `-32602`. | PR-044 | — |
| **V-018** — A late answer is discarded | With a provider that delays its answer, request context, then remove it before the answer arrives; in a second run, send the message instead. In neither run does the late context reach the agent or reappear in the host. | PR-045 | — |
| **V-019** — Id survives harder edits | Record a selection's id. Replace text above it, undo and redo, type through an input method that composes characters, and insert characters outside the Basic Multilingual Plane above it. After each, its location returns the same passage. | PR-009 | — |
| **V-020** — Locate on hard layouts | Repeat V-004 for a selection partly scrolled out of view, a selection that spans hidden Markdown syntax, and one that wraps across lines. Rectangles cover only what is visible and agree within 2 points. | PR-013 | — |
| **V-021** — Coordinates across displays | Locate a selection in a window on a display left of or above the primary display, where coordinates are negative, and on a display with a different scale factor. Rectangles match the item's position in global points. | PR-012 | — |

---

## 5. Coverage

*Version 0.2.4.* 93 Requirements hold: RFC-0007 retired PR-072 and PR-098 and added PR-099 to PR-107, for an app that says its context is sensitive and for redaction as the provider's job. The outside check covers PR-099, PR-100 and PR-106 and the schema is `schema/current-0.2.4.json`; PR-102 to PR-104 are tested in the host, PR-105 is an inspection, and PR-101 and PR-107 are a provider's own tests.

*Version 0.2.3.* 86 Requirements hold: RFC-0004 retired PR-092 and added PR-093 to PR-098, for a provider started by the app it answers for. The outside check covers PR-093, PR-096 and PR-098 when run on a descriptor; PR-094 and PR-095 are tested in the host, and PR-097 is an inspection.

*Version 0.2.2.* 81 Requirements hold: RFC-0006 retired PR-035 and PR-073 and added PR-080 to PR-092, for watching `current`.

*Version 0.2.1.* 70 Requirements hold, 63 of them at P0: RFC-0005 retired PR-047 and PR-066 and added PR-072 to PR-079, of which the outside check covers PR-072, PR-073 and PR-074 and the schema is `schema/current-0.2.1.json`.

*Version 0.2.0.* 64 Requirements hold, 58 of them at P0, and 16 of those have a Verification. None of the 24 P0 Requirements added in 0.2.0 has one yet: most are checks on the shape of an answer, which the schema (`schema/current-0.2.0.json`) and the outside check (ACP-0001) define, and their Verifications are added with that work. The rest of this section was written for 0.1 and is kept as the record of that version.

Eighteen of the 41 Requirements at P0 have a Verification. The 23 without one:

| Domain | Unverified at P0 |
|---|---|
| Context | PR-002, PR-003, PR-005, PR-006 |
| Identity | PR-008, PR-010 |
| Location | PR-011, PR-014, PR-015 |
| Discovery | PR-018, PR-042 |
| Binding | PR-023, PR-024, PR-026 |
| Compatibility | PR-027, PR-028, PR-029, PR-030 |
| Security | PR-031, PR-034 |
| Host | PR-035, PR-036, PR-037 |

Most of the provider-side gaps close with one schema check: validate a `current` and a `locate` response against a published JSON Schema (PR-002, PR-003, PR-005, PR-011, PR-018, PR-024, PR-027). That check is the start of a conformance suite another app's author could run, which matters if this is to become a standard.

The review of 2026.11.09 recommended building that suite's other half first: a fake provider that a host is tested against, covering both MCP revisions, stale and colliding ids (V-014), false and stale descriptors (V-015, V-016) and delayed answers (V-018). It needs no editor integration, so it can run before the first real provider exists.

The three Host gaps (PR-035 to PR-037) are the hardest to verify from outside. A protocol cannot enforce what a host does with context it has received; these are rules of conduct a host claims to follow. I recommend keeping them as Requirements and marking their Verifications as inspections of the host, not automated checks.
