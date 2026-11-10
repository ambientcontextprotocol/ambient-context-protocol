# Ambient Context Protocol :: Product Requirements

Last updated: `2026.11.09`

> A protocol by which a desktop app tells an ambient agent host what the user has open, what they have selected, and where an item is on screen. Version `0.1`. First provider: Paper. First host: Sirius. Task: SIR-0105.

**Status.** Draft for Andrew's review. Nothing here is in the graph. The structure uses the product ontology as edited on 2026.11.09 (Product, Domain, Feature, Requirement, Verification). The requirements restate the design in the [plan](../../paper/.plan/ambient-context-provider.md) and the [protocol draft](protocol-v0.md); most of their wording is Claude's and unconfirmed. All method, field and path names are placeholders.

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
6. [Outside this product](#6-outside-this-product)

---

## Principles

1. *The app says where; the host decides what.* A provider reports items and their positions. It never names what the host draws there.
2. *An envelope, not a domain model.* The protocol fixes the shape of an item and leaves its type and payload to the app. A text editor, a task tracker and a design tool all fit without the protocol knowing what a document, a task or a frame is.
3. *Pulled on the user's action.* A host asks for context when the user does something that calls for it. A provider does not push, and a host does not poll.
4. *Any MCP client can use it.* The first binding is ordinary MCP tools. A client that has never heard of the protocol can still call them.
5. *Costs an app a day, not a month.* A provider is a small local server, one file on disk and two tools. No SDK is required.

---

## 1. Ontology

Five levels. The first four are structure; the fifth says how a requirement is checked.

| Level | ID | What it is |
|---|---|---|
| **Product** | name | A coherent offering with a separable reason to use it. Here: the Ambient Context Protocol. |
| **Domain** | abbreviation | An area within the Product that groups related Features. |
| **Feature** | `F-xxn` | A coherent capability, identifiable for planning. Has a priority and one or more Requirements. |
| **Requirement** | `PR-nnn` | A specific, testable condition the product must satisfy. Specifies one Feature. |
| **Verification** | `V-nnn` | A defined way of establishing whether one Requirement is met. It does not record that it was run or that it passed. |

```
Product: Ambient Context Protocol
└── Domain: Security
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

**F-CX3 — Changes since** · P2. A provider reports what changed since a given point.

| Requirement | Statement | On | Priority | Verified by |
|---|---|---|---|---|
| **PR-007** — Changes since | A provider returns the items added, changed and removed since a point the host names. | Provider | P2 | — |

### 3.2 — Identity

**F-ID1 — Item ids** · P0. Every item has a short id that keeps meaning the same thing.

| Requirement | Statement | On | Priority | Verified by |
|---|---|---|---|---|
| **PR-008** — Opaque ids | An id is a short string minted by the provider, such as `sel-23`. A host does not parse it. | Both | P0 | — |
| **PR-009** — Stable under edits | An id keeps referring to the same item after the surrounding content is edited. | Provider | P0 | V-003 |
| **PR-010** — No reuse | A provider does not reuse an id while it is running. When the item no longer exists, the provider says it is gone. | Provider | P0 | — |

### 3.3 — Location

**F-LO1 — Locate** · P0. Given an id, a provider says where the item is on screen.

| Requirement | Statement | On | Priority | Verified by |
|---|---|---|---|---|
| **PR-011** — Locate | Given an id, a provider returns a location: `state` (`visible`, `offscreen` or `gone`), `rects` and `window`. | Provider | P0 | — |
| **PR-012** — Coordinates | Rectangles are in global screen coordinates, in points, with the origin at the top left of the primary display. | Provider | P0 | — |
| **PR-013** — Accuracy | Rectangles agree, within 2 points, with what the platform accessibility API reports for the same item. | Provider | P0 | V-004 |
| **PR-014** — Placement hints | A location may carry `avoid` (rectangles the host should not cover) and `edge` (the side the provider prefers). A host may ignore both. | Both | P0 | — |
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
| **PR-018** — Descriptor fields | The descriptor holds `protocol`, `app`, `pid`, `endpoint`, `token` and `started`. | Provider | P0 | — |
| **PR-019** — Descriptor permissions | The providers folder is mode `0700` and each descriptor is mode `0600`. | Provider | P0 | V-006 |
| **PR-020** — Descriptor removal | A provider removes its descriptor when it quits. A host ignores a descriptor whose `pid` is not running. | Both | P0 | V-007 |
| **PR-021** — Off means absent | When the user has turned the provider off, it writes no descriptor and opens no listener. | Provider | P0 | V-008 |

**F-DI2 — Dial-in** · P2. A provider that cannot listen connects out to the host.

| Requirement | Statement | On | Priority | Verified by |
|---|---|---|---|---|
| **PR-022** — Dial-in | A provider that cannot listen, such as a sandboxed app or a web page, connects out to the host and serves the same operations over that connection. | Both | P2 | — |

### 3.5 — Binding

**F-BI1 — MCP binding** · P0. The protocol's operations are MCP tools on a local MCP server.

| Requirement | Statement | On | Priority | Verified by |
|---|---|---|---|---|
| **PR-023** — MCP server | A provider is an MCP server reached by `POST /mcp` at the descriptor's `endpoint`. | Provider | P0 | — |
| **PR-024** — Two tools | The provider offers the tools `context_current` and `context_locate {id}`. Each returns structured content and the same data as a JSON text block. | Provider | P0 | — |
| **PR-025** — Any MCP client | An MCP client with no knowledge of this protocol can list and call both tools, given only the endpoint and token. | Provider | P0 | V-009 |
| **PR-026** — MCP versions | The provider speaks MCP `2026-07-28` and also answers the older `initialize` handshake. | Provider | P0 | — |

### 3.6 — Compatibility

**F-CO1 — Versioning** · P0. Both sides know which version the other speaks and degrade safely.

| Requirement | Statement | On | Priority | Verified by |
|---|---|---|---|---|
| **PR-027** — Declared version | A provider declares the protocol and its version as an MCP extension: `"org.humanitas/ambient-context": {"version": "0.1"}`. | Provider | P0 | — |
| **PR-028** — Version in the descriptor | The descriptor's `protocol` field carries the same version, so a host can decide before connecting. | Provider | P0 | — |
| **PR-029** — Unknown fields | Both sides ignore fields they do not recognize. | Both | P0 | — |
| **PR-030** — Unsupported version | A host that does not support a provider's version treats the app as if it were not a provider. | Host | P0 | — |

### 3.7 — Security

**F-SE1 — Access control** · P0. Only a local process that can read the user's descriptor can call a provider.

| Requirement | Statement | On | Priority | Verified by |
|---|---|---|---|---|
| **PR-031** — Loopback only | A provider listens on `127.0.0.1` only. | Provider | P0 | — |
| **PR-032** — Token required | A provider refuses a request that lacks `Authorization: Bearer <token>` with the descriptor's token. | Provider | P0 | V-010 |
| **PR-033** — No browser origin | A provider refuses any request that carries an `Origin` header. | Provider | P0 | V-011 |
| **PR-034** — Token lifetime | A provider mints a new token at each launch and stores it nowhere but the descriptor. | Provider | P0 | — |

### 3.8 — Host

**F-HO1 — Consent** · P0. The user sees what context will be sent and can remove it.

| Requirement | Statement | On | Priority | Verified by |
|---|---|---|---|---|
| **PR-035** — User action | A host requests context only in response to an action by the user. | Host | P0 | — |
| **PR-036** — Shown and removable | Before context is sent to an agent, the host shows the user what will be sent and lets them remove it. | Host | P0 | — |

**F-HO2 — Scope** · P0. A host limits how much context it takes and from which apps.

| Requirement | Statement | On | Priority | Verified by |
|---|---|---|---|---|
| **PR-037** — Front app in full | A host takes full context from the frontmost app only. | Host | P0 | — |
| **PR-038** — Other apps in one line | For each other visible app that is a provider, a host may include one line naming the app and its focused item. | Host | P1 | — |
| **PR-039** — No provider, no change | With an app in front that is not a provider, a host behaves exactly as it would without the protocol. | Host | P0 | V-012 |

---

## 4. Verifications

Each Verification checks one Requirement. The "Plan" column gives the "Done when" line in the [plan](../../paper/.plan/ambient-context-provider.md) §1 that it came from. Lines there that covered several Requirements are split.

| Verification | Description | Verifies | Plan |
|---|---|---|---|
| **V-001** — Current returns open items | With two documents open and a sentence selected, call `context_current`. The response lists both documents and the selection, and the focus names the selection. | PR-001 | 3 |
| **V-002** — Current is fast | Call `context_current` 100 times against a provider with a 50,000-word document open. No call exceeds the time limit of the host under test, and the response time does not grow with the size of the document. | PR-004 | 3 |
| **V-003** — Id survives edits | Select a passage and record its id. Type a paragraph above it. `context_locate` with that id returns the same passage at its new position. | PR-009 | 5 |
| **V-004** — Locate matches Accessibility | Select a passage. Compare the rectangles from `context_locate` with the bounds the platform accessibility API reports for the same range. They agree within 2 points. The Accessibility reading does not pass through the provider's protocol code. | PR-013 | 4 |
| **V-005** — Descriptor exists | Launch the provider with its setting on. A descriptor with all six fields exists in the providers folder. | PR-017 | 1 |
| **V-006** — Descriptor is private | Read the modes of the providers folder and the descriptor. They are `0700` and `0600`. | PR-019 | 1 |
| **V-007** — Descriptor is removed | Quit the provider. Its descriptor is gone. | PR-020 | 1 |
| **V-008** — Off means absent | Launch the provider with its setting off. No descriptor exists and no port is open. | PR-021 | 9 |
| **V-009** — A foreign MCP client works | With a stock MCP client that is not the host, given only `endpoint` and `token`, list the tools and call both. Both return results. | PR-025 | 6 |
| **V-010** — Token is required | Send a request with no `Authorization` header, then one with a wrong token. Both are refused. | PR-032 | 2 |
| **V-011** — Origin is refused | Send a request with a valid token and an `Origin` header. It is refused. | PR-033 | 2 |
| **V-012** — No provider, no change | Put an app that is not a provider in front and use the host. Its behavior and the agent's message match those of a host with the protocol disabled. | PR-039 | 9 |

---

## 5. Coverage

Twelve of the 35 Requirements at P0 have a Verification. The 23 without one:

| Domain | Unverified at P0 |
|---|---|
| Context | PR-002, PR-003, PR-005, PR-006 |
| Identity | PR-008, PR-010 |
| Location | PR-011, PR-012, PR-014, PR-015 |
| Discovery | PR-018 |
| Binding | PR-023, PR-024, PR-026 |
| Compatibility | PR-027, PR-028, PR-029, PR-030 |
| Security | PR-031, PR-034 |
| Host | PR-035, PR-036, PR-037 |

Most of the provider-side gaps close with one schema check: validate a `context_current` and a `context_locate` response against a published JSON Schema (PR-002, PR-003, PR-005, PR-011, PR-018, PR-024, PR-027). That check is the start of a conformance suite another app's author could run, which matters if this is to become a standard.

The three Host gaps (PR-035 to PR-037) are the hardest to verify from outside. A protocol cannot enforce what a host does with context it has received; these are rules of conduct a host claims to follow. I recommend keeping them as Requirements and marking their Verifications as inspections of the host, not automated checks.

---

## 6. Outside this product

Three lines from the plan's "Done when" list are not Requirements of the protocol.

| Plan line | What it says | Where it belongs |
|---|---|---|
| 7 | Selecting text in Paper, pressing the hotkey and pressing ⌘Return opens the aside beside the selection, and the agent's turn contains the `<context>` block | Sirius, as Features that consume the protocol: context in the message, the composer chip, aside placement |
| 8 | `sirius display aside --anchor <id> "<brief>"` opens the aside beside that item and falls back to the default spot when the id is gone | Sirius |
| 10 | Both test suites pass | A build gate for Paper and Sirius, not a Requirement |

Under the ontology these are Features of the Sirius Product, each with its own Requirements and Verifications. Paper's side is thinner: Paper adds one Feature of its own, the `ambient.context` setting, and otherwise is a provider that must satisfy the Requirements above.
