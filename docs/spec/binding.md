# Ambient Context Protocol · The MCP binding

> Part of the [specification](index.md), version `0.2.2`.

## 7. The MCP binding

A provider is an MCP server. The two operations are MCP resources. Everything in this section follows MCP revision `2026-07-28`; the details relied on are listed with their sources in [section 14](#14-mcp-details-this-draft-relies-on).

### 7.1 — The server

- **Address.** The provider listens on `127.0.0.1` only. It may open a listener for this protocol on a port the system assigns at launch, or use a listener the app already has. A listener bound to any other address, including all interfaces, must not carry the endpoint.
- **Path.** The endpoint is a single path, chosen by the provider and published in the descriptor: `/mcp` on a listener of its own, or a path such as `/ambient` on a shared one. It begins with `/` and has no query or fragment. A host uses it as given.
- **Transport.** MCP's Streamable HTTP transport: each JSON-RPC request is one HTTP `POST` to that path. The provider may answer every request with a single JSON object (`Content-Type: application/json`); it does not need to stream.
- **Authentication.** Every request must carry `Authorization: Bearer <token>`. The token is random, made at launch, and published only in the descriptor file. It is used for this endpoint only, and must not be a credential the app's server accepts anywhere else.
- **Browser protection.** The provider refuses any request that carries an `Origin` header. Browsers attach one to requests made by web pages, and no web page should be calling this server. This is stricter than MCP requires, and a host must not send the header.
- **Required MCP methods.** `server/discover`, `resources/list`, `resources/templates/list` and `resources/read`. A provider should also answer `ping` with an empty result, for clients that test a connection. Nothing else is required.

**On a shared listener.** An app that already runs a local HTTP or MCP server may serve the endpoint from it. The rules above then apply to the endpoint's path, with three additions:

1. The token and `Origin` checks are enforced on that path before any other handling the server applies to requests, including middleware that adds headers or answers preflights.
2. The provider does not answer a cross-origin preflight (`OPTIONS`) on that path with permission, and no response from that path carries an `Access-Control-Allow-*` header.
3. Neither the token nor anything from an answer is written to the server's logs.

A provider answered by a different process than the app, and a provider without a token, are not defined by this version.

### 7.2 — Declaring the extension

The provider lists the extension in its capabilities, which a client gets from `server/discover`:

```json
{
  "resultType": "complete",
  "supportedVersions": ["2026-07-28"],
  "capabilities": {
    "resources": {},
    "extensions": {
      "io.github.ambientcontextprotocol/context": { "version": "0.2.2" }
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

A host performs an operation with `resources/read` on the address. For `locate`, the host puts the element's id in place of `{id}`.

The result's `contents` array holds exactly one entry: the `uri` that was read, `mimeType` `application/json`, and `text` holding the operation's result ([4.1](operations.md#41--current) or a [location](locations.md#6-locations)) as a JSON document.

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
      "title": "Location of an element",
      "description": "Where an element from the current context is on screen.",
      "mimeType": "application/json"
    }
  ]
}
```

A provider that cannot report positions leaves the template out. Its context still reaches the agent; the host places its own interface by default.

### 7.4 — Errors and refusals

| Case | Response |
|---|---|
| An `Origin` header is present, on any HTTP method including `OPTIONS` | HTTP `403`, with no body. Checked first, so a web page learns nothing else |
| No `Authorization` header, or the wrong token | HTTP `401` |
| An HTTP method other than `POST` | HTTP `405` |
| A request body larger than the provider accepts | HTTP `413`. The limit is the provider's choice |
| A body that is not JSON, or not a JSON-RPC request | HTTP `400` with JSON-RPC error `-32700` or `-32600` |
| `locate` for an id whose element is gone | A normal result with `state: "gone"` |
| `locate` for an id the provider never issued, or an element it cannot place | JSON-RPC error `-32602`, as MCP requires for a resource that does not exist |
| A request that names MCP `2026-07-28` and lacks a `_meta` field MCP requires (`protocolVersion`, `clientCapabilities`) | HTTP `400` with JSON-RPC error `-32602` |
| A header MCP requires (`MCP-Protocol-Version`, `Mcp-Method`, `Mcp-Name`) that is missing or disagrees with the body | HTTP `400` with MCP's header-mismatch error (`-32020`) |
| A method the provider does not implement | HTTP `404` with JSON-RPC error `-32601` |
| A protocol version the provider does not support | HTTP `400` with MCP's `UnsupportedProtocolVersionError` (`-32022`) |

**A request that names no MCP version.** A request with no version in its body, and either no `MCP-Protocol-Version` header or one naming an older revision, is treated as coming from an older client ([7.6](#76--older-mcp-clients)), not refused. Refusing it would turn away the clients 7.6 asks a provider to serve, which never put a version in the body. The refusal in the table applies to a request whose header names `2026-07-28` or a revision the provider does not know.

### 7.5 — An optional tool

An agent connected straight to a provider, with no host between them, cannot read a resource on its own initiative in every MCP client. A provider may therefore also offer one tool, `context_current`, which takes no arguments and returns the `current` result ([4.1](operations.md#41--current)) as structured content, with the same JSON as a text block. It is a convenience for that case. A host never uses it, and a provider is complete without it.

### 7.6 — Older MCP clients

MCP revisions up to `2025-11-25` open with an `initialize` handshake, which `2026-07-28` removed. A provider should also answer that handshake, so that clients which have not moved yet can connect. MCP allows a server to support both. Doing so is more than one extra method: requests, results and errors differ between the two revisions, and a provider that supports both follows each revision's rules for the clients that use it. Two differences matter here. The provider declares this protocol to those clients under `capabilities.experimental` in its `initialize` result, with the same identifier and settings object. And a resource that does not exist, or a method the provider does not implement, is answered to those clients with HTTP `200` carrying the JSON-RPC error (`-32002` and `-32601`), as those revisions define.

## 11. Implementing a provider

A provider has four jobs:

1. **Listen** on the loopback interface and answer the four MCP methods in 7.1, checking the token and refusing `Origin`.
2. **Write the descriptor** when the listener is up, and remove it at quit.
3. **Answer `current`:** build the tree of what is open, mint an id for each element, and mark what is selected, focused and, if the app tracks it, hovered.
4. **Answer `locate`:** look up an id and return the screen rectangles of what it refers to.

An app already has the information for the third in its window and selection state. It has the information for the fourth in the code that draws and hit-tests its content. The work is exposing it.

There are two ways to do the first job:

- **A listener of its own.** The provider opens a port the system assigns and serves only this endpoint on it. This is the simplest to get right, because nothing else shares the listener.
- **A route on a server the app already has.** The app adds one path and hands every request on it to code that checks `Origin` and the token and answers the four methods: one request in, one response out. The extra rules for a shared listener in [7.1](#71--the-server) apply. The descriptor is written the same way, with `endpoint` naming that path.

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
| Required request metadata | `protocolVersion` and `clientCapabilities` are required in `_meta` on every request; a request missing either is refused with `400` and `-32602` | `basic/index.mdx` |
| Authorization | Optional for MCP implementations | `basic/authorization/index.mdx` |
| Extensions | Advertised under `capabilities.extensions`, a map from identifier to settings object; identifiers take a vendor prefix in reverse DNS form; prefixes whose second label is `modelcontextprotocol` or `mcp` are reserved | `basic/versioning.mdx`, `basic/index.mdx` |
| HTTP transport | One endpoint accepting `POST`; a request is answered with one JSON object or an event stream; the client's `Accept` lists both | `basic/transports/streamable-http.mdx` |
| Required headers | `MCP-Protocol-Version` and `Mcp-Method` on every request; `Mcp-Name` carrying the address on `resources/read`; a mismatch with the body is refused with `400` and error `-32020` | `basic/transports/streamable-http.mdx` |
| Local servers | Must validate `Origin` and answer `403` when it is invalid; should bind to `127.0.0.1`; should authenticate | `basic/transports/streamable-http.mdx` |
| Unknown method and version | `404` with `-32601`; `400` with `-32022` | `basic/transports/streamable-http.mdx`, `basic/versioning.mdx` |
| Tool names | Letters, digits, underscore, hyphen and dot; 1 to 128 characters | `server/tools.mdx` |
| Older clients | A server may support both the `initialize` handshake and per-request metadata | `basic/versioning.mdx` |
