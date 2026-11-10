# Plan: Paper as the first Ambient Context provider

Last updated: `2026.11.09` · Task: SIR-0105 · Revision 2, by claude, awaiting Andrew's approval. Nothing in this plan has been started. Protocol draft: [labs/projects/ambient-context-protocol/.plan/protocol-v0.md](protocol-v0.md).

> While it is open, Paper runs a small MCP server on this machine and announces it with a file in a known folder. The server answers two questions: what is open and selected, and where a listed item is on screen. Sirius finds the front app's server through that folder, reads the first answer when the composer opens, and uses the second to open an aside beside the selection. Paper's side is built and verified first, on its own.

Revision 1 bound the protocol to a command in the app's bundle. Andrew, 2026.11.09: "i'm wondering if this CLI approach is really the way to do this across the board? discovery seems weird to me in that case. i'm just very concerned / focused on wanting this to become a standard". This revision replaces that binding. The reasons are in section 2.

## Contents

1. [Outcome](#1-outcome)
2. [The binding](#2-the-binding)
   - [2.1 — Why this shape](#21--why-this-shape)
   - [2.2 — The server](#22--the-server)
   - [2.3 — The two tools](#23--the-two-tools)
   - [2.4 — The descriptor file](#24--the-descriptor-file)
   - [2.5 — What the host does](#25--what-the-host-does)
   - [2.6 — Later: dial-in](#26--later-dial-in)
3. [Tasks](#3-tasks)
   - [3.1 — Protocol](#31--protocol)
   - [3.2 — Paper](#32--paper)
   - [3.3 — Sirius](#33--sirius)
   - [3.4 — End to end](#34--end-to-end)
4. [Dependencies and order](#4-dependencies-and-order)
5. [Files touched](#5-files-touched)
6. [Uncertainties](#6-uncertainties)
7. [Approvals needed](#7-approvals-needed)

## 1. Outcome

**Scope.** Version `0.1` of the protocol, defined as an MCP extension with announce-mode discovery. Andrew, 2026.11.09: "i'd consider this version 0.1". The earlier draft was never implemented, so it is rewritten in place and keeps the number. Paper as a provider. Sirius as a host: context in the message, a context chip in the composer, an `--anchor` option on `display aside`, and aside placement from `locate`.

**Out of scope.** Dial-in mode for sandboxed and web providers (2.6). An aside that follows scrolling. Margin marks and reopening an aside from the document. One-line context for other visible apps. A reusable provider library as its own package. Shipping either app.

**Done when:**

1. With Paper running and the setting on, a descriptor file for Paper exists in the providers folder, readable only by the user, and is gone after Paper quits.
2. A request to Paper's endpoint without the token, or with an `Origin` header, is refused.
3. Calling the `current` tool returns the open documents and the selection, matching the draft, in under 50 ms.
4. Calling the `locate` tool returns rectangles that agree, within 2 points, with what the macOS Accessibility API reports for the same range. This is an independent check: the Accessibility probe used during design reads positions without going through Paper's new code.
5. An id minted for a selection still locates the same passage after text is typed above it.
6. An MCP client that is not Sirius lists and calls both tools, given only the endpoint and token from the descriptor. This is the evidence for "any MCP client can use it."
7. In Sirius, selecting text in Paper, pressing the hotkey and pressing ⌘Return opens the aside beside the selection, and the agent's turn contains the `<context>` block.
8. An agent's `sirius display aside --anchor <id> "<brief>"` opens the aside beside that item, and falls back to the default spot when the id is gone.
9. With Paper's setting off, or with an app that is not a provider in front, Sirius behaves exactly as it does today.
10. Both test suites pass.

## 2. The binding

### 2.1 — Why this shape

Two background research agents surveyed the field on 2026.11.09. I have not read their sources myself; the claims that most deserve an independent check are marked in section 6.

- **Nobody has standardized this.** No published protocol covers an app reporting its selection and on-screen positions to an outside agent. Agents that read other apps today use Accessibility and screenshots.
- **MCP is the only cross-platform carrier.** Windows has an operating-system registry of local MCP servers, in preview. Apple uses App Intents for its own assistant and exposes nothing to third parties. The web proposal covers tools only. Apps that do cooperate with an agent (editor integrations, Figma's desktop server) use a local MCP server.
- **The proven way to find a running app is a descriptor file.** The app listens on a local port and writes a file with the port and a one-time token into a known per-user folder. Jupyter does this. Claude Code's editor integration does this, and five other editors reimplemented it with no standards body involved. It works on macOS, Windows and Linux, and several hosts can read the same folder.
- **A bundled command does not generalize.** It is tied to one platform's bundle format, a web page cannot ship one, and for sandboxed apps it is unverified.
- **Sandboxed Mac apps and web pages can only connect outward.** That needs a second mode, described in 2.6 and left for later. Paper is not sandboxed.

So the standard has three layers: the model (items, content blocks, locations), MCP as the carrier, and a discovery convention with two modes that share one wire format. This plan builds the first mode.

### 2.2 — The server

- **Address.** `127.0.0.1` only, on a port the system assigns at launch.
- **Transport.** MCP's HTTP transport: JSON-RPC in an HTTP `POST` to one path, `/mcp`.
- **MCP version.** The current one, `2026-07-28`, which is plain request and response with no connection handshake. The server also answers the older `initialize` handshake, so clients that have not moved yet can connect (task T5).
- **Authentication.** Every request carries `Authorization: Bearer <token>`. The token is random, made at launch, and published only in the descriptor file.
- **Browser protection.** Any request with an `Origin` header is refused. Only browsers send one, and no browser page should be calling this server.
- **Extension declaration.** The server lists the extension in its capabilities: `"extensions": { "org.humanitas/ambient-context": { "version": "0.1" } }`. The identifier is a placeholder until the protocol has a home.
- **No library.** The MCP Swift SDK does not open sockets and does not yet support the current MCP version, so it would save little. The server is written by hand on Apple's Network framework, as Sirius's own MCP server already is.

### 2.3 — The two tools

| Tool | Input | Result |
|---|---|---|
| `context_current` | none | The draft's `current` result: `app`, `items`, `focus` |
| `context_locate` | `{ "id": string }` | The draft's location: `state`, `rects`, `window`, `avoid`, `edge` |

Each returns its result as MCP structured content, with the same JSON as a text block for clients that only read text. Each declares an output schema. An unknown id is not an error; `context_locate` answers `state: "gone"`.

Tools, not custom methods: the MCP specification does not say whether an extension may add method names, and every MCP client already knows how to list and call tools.

### 2.4 — The descriptor file

A running provider writes one file and removes it at quit.

- **Folder.** `~/Library/Application Support/AmbientContext/providers/`, created with permissions `0700`. The folder name is a placeholder. Windows and Linux locations are for the protocol document to define.
- **File.** `<bundle-id>.<pid>.json`, permissions `0600`.

```json
{
  "protocol": "0.1",
  "app": { "id": "org.humanitas.paper", "name": "Paper", "version": "0.9.4" },
  "pid": 48211,
  "endpoint": "http://127.0.0.1:53124/mcp",
  "token": "q7Jm…",
  "started": "2026-11-09T21:14:03Z"
}
```

**Trust.** Any program running as the user can read the token. That is the same level as Claude Code's editor integration and Jupyter. Checking the provider's code signature from its process id can be added on top without changing the format.

### 2.5 — What the host does

1. When the user invokes it, take the front app's process id from the operating system.
2. Look for a descriptor with that process id. Ignore files whose process is no longer running or whose bundle id does not match the process.
3. Call `context_current` with the token, with a 150 ms limit. On any failure, carry on with no context.
4. To place something, call `context_locate` with the item's id.

### 2.6 — Later: dial-in

Sandboxed Mac App Store apps cannot write to a shared folder or offer a socket to another developer's app, and a web page cannot listen at all. Both can make an outgoing connection to the local machine. In the second mode the provider connects to the host and the same two tools are called over that connection. It is not designed here. SIR-0052 (the transport spike with a sandboxed test app) becomes the test of it.

## 3. Tasks

**Tracker.** Sync, project `sirius`, as subtasks of SIR-0105. The ids below are placeholders; real ids exist once the tasks are created, which needs approval (section 7).

### 3.1 — Protocol

| Id | Task | Verified by |
|---|---|---|
| T1 | **Pin the MCP details from the specification itself.** Read the `2026-07-28` pages for the HTTP transport, tools, structured results, capability discovery and the older handshake. Record the exact request and response shapes the server must produce, and correct section 2 where it is wrong. | A short table of shapes with source links, added to the protocol draft. |
| T2 | **Rewrite the protocol draft as `0.1`.** Replace `initialize`, the three methods and the transport section with: the extension identifier, the two tools, the descriptor file, the host procedure, and dial-in as a named future mode. The changelog's single `0.1` entry describes this version. | Andrew reads it. |

### 3.2 — Paper

| Id | Task | Verified by |
|---|---|---|
| T3 | **Tracked ranges and screen rectangles.** A registry that mints an id for a character range and keeps the range correct as text is inserted or deleted before or inside it. A function returning the screen rectangles for a range, one per line, in top-left global coordinates. | Unit tests: the range shifts on edits above, shrinks on edits inside, reports `gone` when fully deleted. A rectangle test against a known layout. |
| T4 | **The server.** A loopback listener, a minimal HTTP `POST` handler, the token and `Origin` checks, and JSON-RPC dispatch for capability discovery, tool listing and tool calls. Written so it knows nothing about Paper: it is handed a provider object that answers `current` and `locate`. | Unit tests over the request handler with canned requests: good call, missing token, `Origin` present, unknown method, malformed body. |
| T5 | **The older handshake.** Answer `initialize` so clients on the previous MCP version can connect. | Criterion 6 with a client on the older version. |
| T6 | **Paper's provider.** Answers `current` from the open documents, the front window and the selection, minting ids through T3. Answers `locate` from T3. | Unit tests with a fake document list. Criteria 3 to 5 against the built app. |
| T7 | **Descriptor and lifecycle.** Write the descriptor after the listener is up; remove it at quit; remove a stale one from a crashed run at launch. Start and stop with the setting. | Criterion 1. Kill Paper and relaunch: one descriptor, correct process id. |
| T8 | **Setting.** `ambient.context` in Paper's config file. Documented in the guide. | Config test. With it off: no listener, no descriptor. |
| T9 | **Changelog and architecture note** in Paper's docs. | Read-through. |

### 3.3 — Sirius

| Id | Task | Verified by |
|---|---|---|
| T10 | **Provider client.** Find the descriptor for a process id, validate it, call the two tools over HTTP with the token and a time limit, decode the results. New file; no changes to existing ones. | Unit tests with a fake descriptor folder and a stub server: timeout, bad token, stale descriptor, mismatched bundle id. |
| T11 | **Context on the message.** `Message` gains an optional `context`; the renderer writes the `<context>` block for ordinary and aside turns; protocol types and docs updated. | Renderer tests: block present, absent when there is no context, escaping. |
| T12 | **Composer.** On open, ask the front app's provider in the background; show one chip for the focused item (app icon, title, first words), removable; send the context with the message. | Composer snapshot with a chip. Manual run against Paper. |
| T13 | **`--anchor` on `display aside`.** The option in the `sirius` command and Sirius's MCP tool, validation, protocol docs, and one sentence in each harness's bundled instructions saying when to use it. | Protocol tests: accepted on aside, rejected on other kinds. |
| T14 | **Placement.** `AsideController` takes an optional item to anchor to, calls `locate`, and places the window beside the rectangles, honoring `avoid` and `edge` when it can and staying on screen. ⌘Return anchors to the focused item. Falls back to today's placement on `offscreen`, `gone`, timeout or no provider. | Unit tests on the placement function with fixed rectangles and screen sizes. Criteria 7 to 9. |

### 3.4 — End to end

| Id | Task | Verified by |
|---|---|---|
| T15 | Run all ten criteria in section 1 with both apps built, on one display and with Paper on a second display. Record the results in this plan. | The recorded results. |

## 4. Dependencies and order

```
T1 ──► T2 ──┬──► T4 ──► T5 ──┐
            │     │           │
            │     ▼           ▼
            │    T6 ──► T7 ──► T8 ──► T9
            │     ▲
            │    T3
            │
            └──► T10 ──► T11 ──► T12 ──┐
                          │             ├──► T14 ──► T15
                         T13 ───────────┘             ▲
                                                      │
                              T7 ─────────────────────┘
```

- **T1 and T2 first.** They fix the request shapes, the tool names and the descriptor format, which both sides code against. T1 comes before any code because section 2 rests on a research agent's reading of the MCP specification, not mine.
- **T3 has no prerequisites** and can start alongside T1.
- **Paper (T3 to T9) and Sirius (T10 to T14) are independent** once T2 is settled. They meet only at T15.
- **Paper goes first in practice.** Almost every Sirius file this plan touches has uncommitted changes from the session building asides. T10 is a new file and can start any time. T11 to T14 wait until that work is committed, or are handed to that session.
- **Paper can be fully verified without Sirius:** `curl` against the endpoint for criteria 1 to 5, and an off-the-shelf MCP client for criterion 6.

## 5. Files touched

**Paper** (`labs/projects/paper`, on a new branch from `master`):

| Path | Change |
|---|---|
| `Paper/Context/ContextServer.swift` | New: listener, HTTP, MCP dispatch, descriptor file. Knows nothing about Paper. |
| `Paper/Context/ContextProvider.swift` | New: the protocol's types and the provider interface the server calls |
| `Paper/Context/PaperContext.swift` | New: Paper's answers to `current` and `locate` |
| `Paper/Editor/TrackedRanges.swift` | New: the id registry |
| `Paper/Editor/PaperTextView.swift` | Edit: feed edits to the registry; screen rectangles for a range |
| `Paper/App/AppDelegate.swift` | Edit: start and stop the server |
| `Paper/Config/Configuration.swift` | Edit: the `ambient.context` setting |
| `PaperTests/ContextServerTests.swift`, `TrackedRangesTests.swift`, `PaperContextTests.swift` | New |
| `CHANGELOG.md`, `docs/architecture.md`, `docs/guide.md` | Edit |

`ContextServer.swift` and `ContextProvider.swift` are kept free of Paper so they can later be lifted out as the provider library other apps drop in.

**Protocol** (`labs/projects/ambient-context-protocol`):

| Path | Change |
|---|---|
| `.plan/protocol-v0.md` | Edit: rewritten as `0.1` (T1, T2) |

**Sirius** (`labs/projects/sirius`):

| Path | Change |
|---|---|
| `Sources/SiriusCore/AmbientContext.swift` | New: descriptor lookup, provider client, context types |
| `Sources/SiriusProtocol/Message.swift`, `Methods.swift`, `Validation.swift` | Edit: context on the message, anchor on display |
| `Sources/SiriusCore/MessageRenderer.swift` | Edit: the `<context>` block |
| `Sources/SiriusApp/Composer/ComposerController.swift`, `ComposerPanel.swift` | Edit: fetch on open, chip |
| `Sources/SiriusApp/Aside/AsideController.swift` | Edit: anchored placement |
| `Sources/SiriusApp/AppCommandQueue.swift`, `main.swift` | Edit: pass the anchor through |
| `Sources/sirius/Commands.swift`, `Sources/sirius-mcp/Tools.swift`, `Schemas.swift` | Edit: `--anchor` |
| `packaging/agent/*/tools.md` | Edit: one sentence each |
| `docs/asides.md`, `docs/protocol/proto.ts`, `docs/architecture.md` | Edit |
| Tests beside each | New and edited |

## 6. Uncertainties

1. **The MCP details are second-hand.** The request shapes, the extension declaration, structured results and the older handshake come from research agents' reports. T1 exists to read the specification directly before code depends on it.
2. **Which MCP version existing clients speak.** If common clients are still on the previous version, T5 is what makes criterion 6 pass, and it moves from "small" to "required." Unknown until tested.
3. **A hand-written HTTP handler.** It only needs `POST` with a body length, but hand-written HTTP is where bugs and security mistakes hide. The handler is kept minimal, refuses anything it does not expect, and is the most heavily tested piece.
4. **A listening port in a text editor.** Binding to `127.0.0.1` should not trigger the macOS firewall prompt or the local network permission, but I have not tested that on a signed build.
5. **Rectangles in Paper.** Paper hides Markdown punctuation outside the active paragraph, so a range's rectangles depend on which paragraph is revealed. Criterion 4 checks the visible result; it needs testing.
6. **The chip's design.** SIR-0009 holds the open design questions for context chips. T12 builds the plainest version that works and does not settle them.
7. **Sandbox and browser claims behind 2.6.** That sandboxed Mac apps can only connect outward, and that browsers allow a page to reach a local port after a prompt, come from one research report citing Apple developer forum answers and browser documentation. They decide the shape of dial-in mode and should be checked independently before it is designed.
8. **Names.** The extension identifier, the tool names, the folder name and the setting name are placeholders.

## 7. Approvals needed

Nothing below has been done.

1. **This plan**, including the binding in section 2.
2. **Create tasks T1 to T15 in Sync** under SIR-0105, and add a note to SIR-0052 that it now tests dial-in mode.
3. **Edit the protocol draft** at `labs/projects/ambient-context-protocol/.plan/protocol-v0.md` (T1, T2).
4. **A git worktree for Paper** at `labs/projects/paper-context`, on a new branch `ambient-context` from `master`, so the uncommitted work on `task-check-contrast` is untouched.
5. **The Paper file changes** in section 5.
6. **The Sirius file changes** in section 5, and whether I make them after the aside work is committed or hand them to that session.
7. **Paper's default:** `ambient.context` off (my choice while the protocol is a draft) or on (the better demo).
