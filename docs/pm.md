# Ambient Context Protocol · Product Model

Last updated: `2026.11.09`

> A protocol by which a desktop app tells an ambient agent host what the user has open, what they have selected, and where an item is on screen. Version `0.1`. First provider: Paper. First host: Sirius. Task: SIR-0105.

**Status.** Draft for Andrew's review. Nothing here is in the graph. The structure uses the product ontology as edited on 2026.11.09 (Domain, Feature, Requirement, Verification; the Product level is left out because this repository holds one product). The requirements restate the design in the [plan](../../paper/.plan/ambient-context-provider.md) and the [protocol draft](spec/index.md); most of their wording is Claude's and unconfirmed. All method, field and path names are placeholders.

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
2. *An envelope, not a domain model.* The protocol fixes the shape of an item and leaves its type and payload to the app. A text editor, a task tracker and a design tool all fit without the protocol knowing what a document, a task or a frame is.
3. *Pulled on the user's action.* A host asks for context when the user does something that calls for it. A provider does not push, and a host does not poll. Provisional: this holds for version 0.1 and may change.
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

**Priority.** `P0` is in version 0.1. `P1` is next. `P2` and below are named so the design leaves room, and are not built.

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

### 3.1 — Context

**F-CX1 — Current context** · P0. A provider reports the items the user has open and which are in focus.

| Requirement | Statement | On | Priority | Verified by |
|---|---|---|---|---|
| **PR-001** — Current | On request, a provider returns in one response the items the user has open in the app and the focus. | Provider | P0 | V-001 |
| **PR-002** — Item shape | Every item has `id`, `type` and `title`. An item may have `content`, `url`, `parent`, `locatable` and `payload`. | Provider | P0 | — |
| **PR-003** — Focus | The response names the focus as an ordered list of item ids. A selection is an item whose `parent` is the item it was made in. | Provider | P0 | — |
| **PR-004** — Response time | A provider answers a request for current context from state it already holds, without waiting on disk or network. A host sets its own time limit and proceeds without context when the limit passes. | Both | P0 | V-002 |

**F-CX2 — Content** · P0. An item carries its content in a form any agent can read.

| Requirement | Statement | On | Priority | Verified by |
|---|---|---|---|---|
| **PR-005** — Content blocks | `content` is a list of MCP content blocks, unchanged from the MCP specification. | Provider | P0 | — |
| **PR-006** — Open types | `type` is an open string and `payload` is app-defined. The protocol defines no item types beyond the envelope. | Both | P0 | — |
| **PR-046** — Limits | A provider stays within stated bounds on the size of an item's content, the number of items in one answer and the number of ids it keeps alive. The bounds are not set yet (protocol §13, question 3). | Provider | P1 | — |

**F-CX3 — Changes since** · P2. A provider reports what changed since a given point.

| Requirement | Statement | On | Priority | Verified by |
|---|---|---|---|---|
| **PR-007** — Changes since | A provider returns the items added, changed and removed since a point the host names. | Provider | P2 | — |

### 3.2 — Identity

**F-ID1 — Item ids** · P0. Every item has a short id that keeps meaning the same thing.

| Requirement | Statement | On | Priority | Verified by |
|---|---|---|---|---|
| **PR-008** — Opaque ids | An id is a short string minted by the provider, such as `sel-23`. A host does not parse it. | Both | P0 | — |
| **PR-009** — Stable under edits | An id keeps referring to the same item after the surrounding content is edited. | Provider | P0 | V-003, V-019 |
| **PR-010** — No reuse | A provider does not reuse an id while it is running. When the item no longer exists, the provider says it is gone. | Provider | P0 | — |

**F-ID2 — Provider instance** · P0. An id is tied to the provider that issued it and to one run of that provider.

| Requirement | Statement | On | Priority | Verified by |
|---|---|---|---|---|
| **PR-040** — Instance value | A provider mints a random `instance` value each time it starts, returns it with current context and writes it in its descriptor. | Provider | P0 | V-013 |
| **PR-041** — Provider kept with the id | A host records which provider and which `instance` issued every id it passes to an agent. It resolves an id only with that provider and only while the instance is unchanged, and otherwise treats the item as gone. It never looks an id up again by app name or process id. | Host | P0 | V-014 |

### 3.3 — Location

**F-LO1 — Locate** · P0. Given an id, a provider says where the item is on screen.

| Requirement | Statement | On | Priority | Verified by |
|---|---|---|---|---|
| **PR-011** — Locate | Given an id, a provider returns a location: `state` (`visible`, `offscreen` or `gone`), `rects` and `window`. | Provider | P0 | — |
| **PR-012** — Coordinates | Rectangles are in global screen coordinates, in points, with the origin at the top left of the primary display. | Provider | P0 | V-021 |
| **PR-013** — Accuracy | Rectangles agree, within 2 points, with what the platform accessibility API reports for the same item. | Provider | P0 | V-004, V-020 |
| **PR-014** — Placement hints | A location may carry `avoid` (a rectangle the host should not cover) and `edge` (the side the provider prefers). A host may ignore both. | Both | P0 | — |
| **PR-015** — No host UI in the protocol | No message names a host interface element. A provider cannot ask a host to draw anything. | Both | P0 | — |

**F-LO2 — Watch** · P3. A provider tells the host when an item moves.

| Requirement | Statement | On | Priority | Verified by |
|---|---|---|---|---|
| **PR-016** — Watch | A provider notifies the host when a located item moves, scrolls out of view or is removed. | Provider | P3 | — |

### 3.4 — Discovery

**F-DI1 — Announce** · P0. A running provider writes a descriptor file a host can read.

| Requirement | Statement | On | Priority | Verified by |
|---|---|---|---|---|
| **PR-017** — Descriptor | While it is running and enabled, a provider keeps a descriptor file at `~/Library/Application Support/AmbientContext/providers/<bundle-id>.<pid>.json`. | Provider | P0 | V-005 |
| **PR-018** — Descriptor fields | The descriptor holds `protocol`, `app`, `pid`, `instance`, `endpoint`, `token` and `started`. | Provider | P0 | — |
| **PR-019** — Descriptor permissions | The providers folder is mode `0700` and each descriptor is mode `0600`. | Provider | P0 | V-006 |
| **PR-020** — Descriptor removal | A provider removes its descriptor when it quits. A host ignores a descriptor whose `pid` is not running. | Both | P0 | V-007, V-016 |
| **PR-021** — Off means absent | When the user has turned the provider off, it writes no descriptor and opens no listener. | Provider | P0 | V-008 |
| **PR-042** — Atomic write | A provider writes its descriptor after its listener is up, to a temporary name in the same folder, then renames it into place. | Provider | P0 | — |
| **PR-043** — Endpoint check | Before using a descriptor, a host checks that the endpoint's address is `127.0.0.1` and that the process listening on its port is the process the descriptor names. It does not follow redirects, and it ignores an answer whose `instance` differs from the descriptor's. | Host | P0 | V-015 |

**F-DI2 — Discovery without a descriptor** · P2. A provider that cannot announce itself with a descriptor is still found.

| Requirement | Statement | On | Priority | Verified by |
|---|---|---|---|---|
| **PR-022** — Discovery without a descriptor | A provider that cannot write to the shared folder (a sandboxed Mac app) or cannot listen (a web page) can still be found and read. The mechanism is not designed; connecting out to the host is one candidate. | Both | P2 | — |

### 3.5 — Binding

**F-BI1 — MCP binding** · P0. The protocol's operations are MCP resources on a local MCP server.

| Requirement | Statement | On | Priority | Verified by |
|---|---|---|---|---|
| **PR-023** — MCP server | A provider is an MCP server reached by `POST /mcp` at the descriptor's `endpoint`. | Provider | P0 | — |
| **PR-024** — Two resources | The provider offers `current` as the resource `ambient://current` and `locate` as the resource template `ambient://location/{id}`. Each is read with `resources/read` and returns one JSON document. The host's code reads them; the model does not call them. | Provider | P0 | — |
| **PR-025** — Any MCP client | An MCP client with no knowledge of this protocol can list and read both resources, given only the endpoint and token. | Provider | P0 | V-009 |
| **PR-026** — MCP versions | The provider speaks MCP `2026-07-28`. It should also serve clients that use the older `initialize` handshake, following that revision's rules for requests, results and errors. | Provider | P0 | — |
| **PR-044** — Request metadata | A host sends `protocolVersion` and `clientCapabilities` in `_meta` on every request, as MCP `2026-07-28` requires. A provider refuses a request missing either with HTTP `400` and error `-32602`. | Both | P0 | V-017 |

### 3.6 — Compatibility

**F-CO1 — Versioning** · P0. Both sides know which version the other speaks and degrade safely.

| Requirement | Statement | On | Priority | Verified by |
|---|---|---|---|---|
| **PR-027** — Declared version | A provider declares the protocol and its version as an MCP extension: `"org.humanitas/ambient-context": {"version": "0.1"}`. | Provider | P0 | — |
| **PR-028** — Version in the descriptor | The descriptor's `protocol` field carries the same version, so a host can decide before connecting. | Provider | P0 | — |
| **PR-029** — Unknown fields | Both sides ignore fields they do not recognize. | Both | P0 | — |
| **PR-030** — Unsupported version | A host that does not support a provider's version treats the app as if it were not a provider. | Host | P0 | — |

### 3.7 — Security

**F-SE1 — Access control** · P0. Only a local process that can read the user's descriptor can call a provider. A hostile program already running as the user is outside what version 0.1 defends against: it can read the token, and the user's documents, without this protocol. The token shows that a caller can read the user's files, not that the user approved the caller.

| Requirement | Statement | On | Priority | Verified by |
|---|---|---|---|---|
| **PR-031** — Loopback only | A provider listens on `127.0.0.1` only. | Provider | P0 | — |
| **PR-032** — Token required | A provider refuses a request that lacks `Authorization: Bearer <token>` with the descriptor's token. | Provider | P0 | V-010 |
| **PR-033** — No browser origin | A provider refuses any request that carries an `Origin` header. A host does not send one. | Both | P0 | V-011 |
| **PR-034** — Token lifetime | A provider mints a new token at each launch and stores it nowhere but the descriptor. | Provider | P0 | — |

### 3.8 — Host

**F-HO1 — Consent** · P0. The user sees what context will be sent and can remove it.

| Requirement | Statement | On | Priority | Verified by |
|---|---|---|---|---|
| **PR-035** — User action | A host requests context only in response to an action by the user. | Host | P0 | — |
| **PR-036** — Shown and removable | Before context is sent to an agent, the host shows the user what will be sent and lets them remove it. | Host | P0 | — |
| **PR-045** — Removed means removed | If the user removes context, or sends the message, while a provider's answer is still on its way, the host discards the late answer. | Host | P0 | V-018 |

**F-HO2 — Scope** · P0. A host limits how much context it takes and from which apps.

| Requirement | Statement | On | Priority | Verified by |
|---|---|---|---|---|
| **PR-037** — Front app in full | A host takes full context from the frontmost app only. | Host | P0 | — |
| **PR-038** — Other apps in one line | For each other visible app that is a provider, a host may include one line naming the app and its focused item. | Host | P1 | — |
| **PR-039** — No provider, no change | With an app in front that is not a provider, a host behaves exactly as it would without the protocol. | Host | P0 | V-012 |

---

## 4. Verifications

Each Verification checks one Requirement; a Requirement may have several. The "Plan" column gives the "Done when" line in the [plan](../../paper/.plan/ambient-context-provider.md) §1 that it came from. Lines there that covered several Requirements are split. A dash marks a Verification added after the adversarial review of 2026.11.09, with no line in the plan yet.

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
