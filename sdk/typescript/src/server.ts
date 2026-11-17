import { createHash, randomBytes, randomUUID, timingSafeEqual } from "node:crypto";
import { chmodSync, mkdirSync, readdirSync, renameSync, rmSync, writeFileSync } from "node:fs";
import { createServer } from "node:net";
import type { AddressInfo, Server, Socket } from "node:net";
import { homedir } from "node:os";
import { join } from "node:path";

import type { ContextContent, ContextDisplay, ContextElement, ContextLocation, ContextProvider, ContextRect } from "./provider.ts";
import { ContextTree } from "./tree.ts";
import type { ContextIssue } from "./tree.ts";

// A provider for the Ambient Context Protocol, version 0.2.1: a small MCP
// server on the loopback interface that answers `current` and `locate`
// as two resources, and the descriptor file that tells a host where it
// is. It is handed a `ContextProvider` and knows nothing else about the
// app it runs in.
//
// Three layers, each usable alone: `ContextHTTP` turns bytes into a
// request, `ContextResponder` turns a request into a response, and
// `ContextServer` owns the listener and the descriptor. An app with no
// server of its own uses `ContextServer`. An app that already runs one on
// the loopback interface mounts a `ContextResponder` at a path of its
// choosing and writes the descriptor with `ContextDescriptor` (RFC-0002).
// `ContextHTTP` is open to the package's tests.

// MARK: - HTTP

export interface ContextHTTPRequest {
  method: string;
  /** The request target without its query. */
  path: string;
  /** Header values by lowercased name. */
  headers: Map<string, string>;
  body: Buffer;
}

export interface ContextHTTPResponse {
  status: number;
  headers: Record<string, string>;
  body: Buffer;
}

function response(status: number, headers: Record<string, string> = {}, body: Buffer = Buffer.alloc(0)): ContextHTTPResponse {
  return { status, headers, body };
}

function reason(status: number): string {
  switch (status) {
    case 200: return "OK";
    case 202: return "Accepted";
    case 400: return "Bad Request";
    case 401: return "Unauthorized";
    case 403: return "Forbidden";
    case 404: return "Not Found";
    case 405: return "Method Not Allowed";
    case 413: return "Content Too Large";
    default: return "Error";
  }
}

export type ContextHTTPParse =
  /** More bytes are needed. */
  | { kind: "incomplete" }
  | { kind: "malformed" }
  | { kind: "tooLarge" }
  | { kind: "request"; request: ContextHTTPRequest };

const maxInt64 = 2n ** 63n - 1n;

function strictUTF8(bytes: Uint8Array): string | undefined {
  try {
    return new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(bytes);
  } catch {
    return undefined;
  }
}

export const ContextHTTP = {
  headerLimit: 16 * 1024,
  bodyLimit: 1024 * 1024,

  /**
   * Reads one request from the start of `buffer`. Only a body with a
   * `Content-Length` is understood; that is what every JSON-RPC client
   * sends for a body it holds in memory.
   */
  parse(buffer: Buffer): ContextHTTPParse {
    const end = buffer.indexOf("\r\n\r\n");
    if (end < 0) {
      return { kind: buffer.length > ContextHTTP.headerLimit ? "tooLarge" : "incomplete" };
    }
    if (end > ContextHTTP.headerLimit) return { kind: "malformed" };
    const head = strictUTF8(buffer.subarray(0, end));
    if (head === undefined) return { kind: "malformed" };

    const lines = head.split("\r\n");
    const requestLine = (lines.shift() ?? "").split(" ");
    const [verb, target, version] = requestLine;
    if (requestLine.length !== 3 || verb === undefined || target === undefined || version === undefined
      || !version.startsWith("HTTP/1.") || verb === "" || !target.startsWith("/")) {
      return { kind: "malformed" };
    }

    const headers = new Map<string, string>();
    for (const line of lines) {
      const colon = line.indexOf(":");
      if (colon < 0) return { kind: "malformed" };
      const name = line.slice(0, colon).toLowerCase();
      if (name === "" || name.includes(" ")) return { kind: "malformed" };
      headers.set(name, line.slice(colon + 1).replace(/^[\t\p{Zs}]+|[\t\p{Zs}]+$/gu, ""));
    }
    if (headers.has("transfer-encoding")) return { kind: "malformed" };

    let length = 0;
    const declared = headers.get("content-length");
    if (declared !== undefined) {
      if (!/^[+-]?[0-9]+$/.test(declared)) return { kind: "malformed" };
      const value = BigInt(declared);
      if (value < 0n || value > maxInt64) return { kind: "malformed" };
      if (value > BigInt(ContextHTTP.bodyLimit)) return { kind: "tooLarge" };
      length = Number(value);
    }
    const bodyStart = end + 4;
    if (buffer.length - bodyStart < length) return { kind: "incomplete" };

    const query = target.indexOf("?");
    return {
      kind: "request",
      request: {
        method: verb,
        path: query < 0 ? target : target.slice(0, query),
        headers,
        body: Buffer.from(buffer.subarray(bodyStart, bodyStart + length)),
      },
    };
  },

  /**
   * The response as bytes. Every response closes its connection, so the
   * server never has to tell one request from the next.
   */
  serialize(response: ContextHTTPResponse): Buffer {
    const all: Record<string, string> = { ...response.headers };
    all["Content-Length"] = String(response.body.length);
    all["Connection"] = "close";
    if (response.body.length > 0 && all["Content-Type"] === undefined) all["Content-Type"] = "application/json";
    let head = `HTTP/1.1 ${response.status} ${reason(response.status)}\r\n`;
    for (const name of Object.keys(all).sort()) head += `${name}: ${all[name] ?? ""}\r\n`;
    head += "\r\n";
    return Buffer.concat([Buffer.from(head, "utf8"), response.body]);
  },
};

// MARK: - MCP

/**
 * The app a provider speaks for: its bundle identifier, the name people
 * know it by, and its version.
 */
export interface ContextApp {
  id: string;
  name: string;
  version: string;
}

type JSONObject = Record<string, unknown>;
type RequestID = string | number;

function isObject(value: unknown): value is JSONObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** JSON with every object's keys in order, as the Swift package writes it. */
function sortedJSON(value: unknown, indent?: number): string {
  return JSON.stringify(value, (_key, inner: unknown) => {
    if (!isObject(inner)) return inner;
    const sorted: JSONObject = Object.create(null) as JSONObject;
    for (const key of Object.keys(inner).sort()) sorted[key] = inner[key];
    return sorted;
  }, indent);
}

// Only the protocol's own fields are sent, and a field an element does
// not have is left out, not sent as null.

function encodeContent(block: ContextContent): unknown {
  switch (block.type) {
    case "text": return { type: block.type, text: block.text };
    case "image": return { type: block.type, data: block.data, mimeType: block.mimeType };
    case "resource_link": return { type: block.type, uri: block.uri, name: block.name };
    default: return block;
  }
}

// `selected`, `focused` and `hovered` are false when absent, so only true
// is sent. `visible` is the parent's value when absent, so either value a
// provider gave is sent.
/** The longest line of a `display` the protocol allows, in characters. */
const displayLineLimit = 80;

/**
 * One line of plain text: line breaks and control characters become
 * spaces, runs of spaces become one, and a line over the limit is cut and
 * ends in an ellipsis. Undefined when nothing is left or it is no string.
 */
function displayLine(text: unknown): string | undefined {
  if (typeof text !== "string") return undefined;
  const line = text.replace(/[\p{Cc}\u2028\u2029]/gu, " ").split(" ").filter((word) => word !== "").join(" ");
  if (line === "") return undefined;
  const characters = Array.from(line);
  return characters.length <= displayLineLimit ? line : characters.slice(0, displayLineLimit - 1).join("") + "…";
}

/**
 * What is sent for a provider's `display`: nothing without a title, since
 * a host uses `display` only when it has one.
 */
function encodeDisplay(display: ContextDisplay | null | undefined): unknown {
  const title = displayLine(display?.title);
  if (title === undefined) return undefined;
  return { title, detail: displayLine(display?.detail) };
}

function encodeElement(element: ContextElement): unknown {
  return {
    id: element.id,
    role: element.role,
    subrole: element.subrole ?? undefined,
    title: element.title ?? undefined,
    content: element.content?.map(encodeContent),
    url: element.url ?? undefined,
    selected: element.selected === true ? true : undefined,
    focused: element.focused === true ? true : undefined,
    hovered: element.hovered === true ? true : undefined,
    visible: typeof element.visible === "boolean" ? element.visible : undefined,
    children: element.children && element.children.length > 0 ? element.children.map(encodeElement) : undefined,
    attributes: element.attributes ?? undefined,
  };
}

function encodeRect(rect: ContextRect): unknown {
  return { x: rect.x, y: rect.y, w: rect.w, h: rect.h };
}

function encodeLocation(location: ContextLocation): unknown {
  return {
    id: location.id,
    state: location.state,
    rects: location.rects?.map(encodeRect),
    window: location.window ?? undefined,
    avoid: location.avoid ? encodeRect(location.avoid) : undefined,
    edge: location.edge ?? undefined,
  };
}

const metaVersion = "io.modelcontextprotocol/protocolVersion";
const metaCapabilities = "io.modelcontextprotocol/clientCapabilities";
const metaServerInfo = "io.modelcontextprotocol/serverInfo";

export interface ContextResponderOptions {
  app: ContextApp;
  instance: string;
  token: string;
  /** The tree, rooted at an `Application`. */
  current: () => ContextElement | Promise<ContextElement>;
  /**
   * The app's own words for what `current` holds. Absent, or answering
   * nothing, leaves the wording to the host.
   */
  display?: (() => ContextDisplay | null | undefined | Promise<ContextDisplay | null | undefined>) | undefined;
  /**
   * Absent for a provider that does not report positions: the location
   * template is then not offered and no location can be read.
   */
  locate?: ((id: string) => ContextLocation | null | undefined | Promise<ContextLocation | null | undefined>) | undefined;
  /**
   * The one path this responder answers. Defaults to `/mcp`, which is
   * what `ContextServer` listens on. An app that mounts the responder on
   * its own server names the path it mounted it at.
   */
  path?: string;
  /**
   * What to do when the provider's tree breaks a rule that can be told
   * from the tree (`ContextTree.check`). `warn`, the default, reports
   * each distinct issue once through `report` and answers anyway.
   * `refuse` answers with an error when an issue is an error, for an
   * app's own tests. `off` does not look.
   */
  check?: "warn" | "refuse" | "off";
  /** Where issues go. Defaults to `console.warn`. */
  report?: (issue: ContextIssue) => void;
}

/**
 * Answers one HTTP request as an MCP server offering the protocol's two
 * resources: one request in, one response out, with the `Origin` refusal
 * and the token checked here. Everything it needs arrives with the
 * request, and the two functions reach the app.
 *
 * On a server the app already has, hand it every request for its path
 * before any other handling, and send its response as it is: it never
 * carries an `Access-Control-Allow-*` header, and nothing else may add
 * one. The token is for this path only. Neither it nor a response's body
 * belongs in a log.
 */
export class ContextResponder {
  static readonly protocolVersion = "0.2.1";
  static readonly extensionID = "io.github.ambientcontextprotocol/context";
  /** The path used when none is given. */
  static readonly endpointPath = "/mcp";
  static readonly currentURI = "ambient://current";
  static readonly locationPrefix = "ambient://location/";
  static readonly locationTemplate = "ambient://location/{id}";
  /** The MCP revision this server is written for. */
  static readonly mcpVersion = "2026-07-28";
  /** Earlier revisions, which open with `initialize`, served as well. */
  static readonly legacyVersions: readonly string[] = ["2025-11-25", "2025-06-18", "2025-03-26"];

  app: ContextApp;
  instance: string;
  token: string;
  current: ContextResponderOptions["current"];
  display: ContextResponderOptions["display"];
  locate: ContextResponderOptions["locate"];
  path: string;
  check: "warn" | "refuse" | "off";
  report: (issue: ContextIssue) => void;
  #reported = new Set<string>();

  constructor(options: ContextResponderOptions) {
    this.app = options.app;
    this.instance = options.instance;
    this.token = options.token;
    this.current = options.current;
    this.display = options.display;
    this.locate = options.locate;
    this.path = options.path ?? ContextResponder.endpointPath;
    if (!this.path.startsWith("/") || this.path.includes("?") || this.path.includes("#")) {
      throw new TypeError(`ContextResponder: the path '${this.path}' must start with '/' and carry no query or fragment`);
    }
    this.check = options.check ?? "warn";
    this.report = options.report ?? ((issue) => {
      console.warn(`ambient context: ${issue.severity}: element '${issue.element}': ${issue.message}`);
    });
  }

  async respond(request: ContextHTTPRequest): Promise<ContextHTTPResponse> {
    // A browser attaches Origin to a page's requests, and no page
    // should be calling this server. Refused before the token is
    // looked at, so a page learns nothing about it.
    if (request.headers.has("origin")) return response(403);

    const authorization = request.headers.get("authorization");
    if (authorization === undefined || !sameBytes(authorization, `Bearer ${this.token}`)) {
      return response(401, { "WWW-Authenticate": "Bearer" });
    }
    if (request.path !== this.path) return response(404);
    if (request.method !== "POST") return response(405, { Allow: "POST" });

    let message: unknown;
    try {
      const text = strictUTF8(request.body);
      message = text === undefined ? undefined : JSON.parse(text);
    } catch {
      message = undefined;
    }
    if (!isObject(message)) return failure(400, undefined, -32700, "Parse error");

    const id = requestID(message["id"]);
    const method = message["method"];
    if (message["jsonrpc"] !== "2.0" || typeof method !== "string") {
      return failure(400, id, -32600, "Invalid request");
    }
    // A notification asks for nothing.
    if (id === undefined) return response(202);

    const params = isObject(message["params"]) ? message["params"] : {};
    const meta = isObject(params["_meta"]) ? params["_meta"] : {};
    const header = request.headers.get("mcp-protocol-version");
    const declared = typeof meta[metaVersion] === "string" ? meta[metaVersion] : undefined;

    // An older client names its revision in the header alone, or not
    // at all, and never in the body.
    const legacy = method === "initialize"
      || (declared === undefined && (header === undefined || ContextResponder.legacyVersions.includes(header)));

    if (!legacy) {
      const refusal = validate(request, method, params, meta, id);
      if (refusal) return refusal;
    }
    try {
      return await this.dispatch(method, params, id, legacy);
    } catch {
      // The app's own function threw; the Swift interface cannot.
      return failure(500, id, -32603, "Internal error");
    }
  }

  private async dispatch(method: string, params: JSONObject, id: RequestID, legacy: boolean): Promise<ContextHTTPResponse> {
    const versions = ContextResponder.legacyVersions;
    const extension = { [ContextResponder.extensionID]: { version: ContextResponder.protocolVersion } };
    const serverInfo = { name: this.app.name, version: this.app.version };

    if (method === "initialize") {
      const asked = params["protocolVersion"];
      const version = typeof asked === "string" && versions.includes(asked) ? asked : versions[0];
      return success(id, true, {
        protocolVersion: version,
        capabilities: { resources: {}, experimental: extension },
        serverInfo,
      });
    }
    if (method === "ping") return success(id, legacy, {});
    if (method === "server/discover" && !legacy) {
      return success(id, false, {
        supportedVersions: [ContextResponder.mcpVersion, ...versions],
        capabilities: { resources: {}, extensions: extension },
        _meta: { [metaServerInfo]: serverInfo },
      });
    }
    if (method === "resources/list") {
      return success(id, legacy, {
        resources: [{
          uri: ContextResponder.currentURI,
          name: "current",
          title: "Current context",
          description: "What the user has open and selected in this app, right now.",
          mimeType: "application/json",
        }],
      });
    }
    if (method === "resources/templates/list") {
      const templates = this.locate ? [{
        uriTemplate: ContextResponder.locationTemplate,
        name: "location",
        title: "Location of an element",
        description: "Where an element from the current context is on screen.",
        mimeType: "application/json",
      }] : [];
      return success(id, legacy, { resourceTemplates: templates });
    }
    if (method === "resources/read") {
      const uri = params["uri"];
      if (typeof uri !== "string") return failure(200, id, -32602, "Missing uri");
      const text = await this.read(uri);
      if (text === undefined) {
        // Earlier revisions used their own code for this.
        return failure(200, id, legacy ? -32002 : -32602, "Resource not found", { uri });
      }
      return success(id, legacy, { contents: [{ uri, mimeType: "application/json", text }] });
    }
    return failure(legacy ? 200 : 404, id, -32601, "Method not found");
  }

  /**
   * The JSON document a resource holds, or undefined when there is no
   * such resource.
   */
  private async read(uri: string): Promise<string | undefined> {
    if (uri === ContextResponder.currentURI) {
      const root = await this.current();
      const display = this.display ? await this.display() : undefined;
      this.#inspect(root);
      return sortedJSON({
        protocol: ContextResponder.protocolVersion,
        instance: this.instance,
        display: encodeDisplay(display),
        root: encodeElement(root),
      });
    }
    if (!this.locate || !uri.startsWith(ContextResponder.locationPrefix)) return undefined;
    let id: string;
    try {
      id = decodeURIComponent(uri.slice(ContextResponder.locationPrefix.length));
    } catch {
      return undefined;
    }
    if (!ContextTree.isElementID(id)) return undefined;
    const location = await this.locate(id);
    return location ? sortedJSON(encodeLocation(location)) : undefined;
  }

  /**
   * Applies the `check` setting to a provider's answer. Throws only under
   * `refuse`, and then the read fails as any error in the app's own
   * function does.
   */
  #inspect(root: ContextElement): void {
    if (this.check === "off") return;
    const issues = ContextTree.check(root);
    for (const issue of issues) {
      const key = `${issue.severity}\u0000${issue.element}\u0000${issue.message}`;
      if (this.#reported.has(key)) continue;
      // An app whose ids change every answer would otherwise fill this.
      if (this.#reported.size >= 1000) this.#reported.clear();
      this.#reported.add(key);
      this.report(issue);
    }
    if (this.check === "refuse" && issues.some((issue) => issue.severity === "error")) {
      throw new Error("the provider's tree breaks the protocol's rules");
    }
  }

  /**
   * A header value as the client meant it: MCP carries a value that is
   * not plain ASCII as `=?base64?…?=`.
   */
  static decodedHeaderValue(value: string): string {
    const prefix = "=?base64?", suffix = "?=";
    if (!value.startsWith(prefix) || !value.endsWith(suffix) || value.length < prefix.length + suffix.length) return value;
    const inner = value.slice(prefix.length, value.length - suffix.length);
    if (!/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(inner)) return value;
    return strictUTF8(Buffer.from(inner, "base64")) ?? value;
  }
}

/**
 * The checks revision 2026-07-28 puts on every request: the version and
 * the client's capabilities in the body, and headers that agree with the
 * body.
 */
function validate(
  request: ContextHTTPRequest, method: string, params: JSONObject, meta: JSONObject, id: RequestID,
): ContextHTTPResponse | undefined {
  const declared = meta[metaVersion];
  if (typeof declared !== "string") {
    return failure(400, id, -32602, `Missing ${metaVersion} in _meta`);
  }
  const header = request.headers.get("mcp-protocol-version");
  if (header === undefined) {
    return failure(400, id, -32020, "Header mismatch: MCP-Protocol-Version header is missing");
  }
  if (header !== declared) {
    return failure(400, id, -32020, `Header mismatch: MCP-Protocol-Version header value '${header}' does not match body value '${declared}'`);
  }
  if (declared !== ContextResponder.mcpVersion) {
    return failure(400, id, -32022, "Unsupported protocol version", {
      supported: [ContextResponder.mcpVersion, ...ContextResponder.legacyVersions],
      requested: declared,
    });
  }
  if (!isObject(meta[metaCapabilities])) {
    return failure(400, id, -32602, `Missing ${metaCapabilities} in _meta`);
  }
  const named = request.headers.get("mcp-method");
  if (named === undefined) {
    return failure(400, id, -32020, "Header mismatch: Mcp-Method header is missing");
  }
  if (named !== method) {
    return failure(400, id, -32020, `Header mismatch: Mcp-Method header value '${named}' does not match body value '${method}'`);
  }
  const uri = params["uri"];
  if (method === "resources/read" && typeof uri === "string") {
    const raw = request.headers.get("mcp-name");
    if (raw === undefined) {
      return failure(400, id, -32020, "Header mismatch: Mcp-Name header is missing");
    }
    const name = ContextResponder.decodedHeaderValue(raw);
    if (name !== uri) {
      return failure(400, id, -32020, `Header mismatch: Mcp-Name header value '${name}' does not match body value '${uri}'`);
    }
  }
  return undefined;
}

// MARK: JSON-RPC envelopes

/** A request's id, which the response repeats as it came. */
function requestID(value: unknown): RequestID | undefined {
  if (typeof value === "string") return value;
  if (typeof value === "number") return Math.trunc(value);
  return undefined;
}

function success(id: RequestID, legacy: boolean, result: JSONObject): ContextHTTPResponse {
  const full = legacy ? result : { ...result, resultType: "complete" };
  return response(200, {}, Buffer.from(sortedJSON({ jsonrpc: "2.0", id, result: full }), "utf8"));
}

function failure(status: number, id: RequestID | undefined, code: number, message: string, data?: JSONObject): ContextHTTPResponse {
  const error: JSONObject = { code, message };
  if (data) error["data"] = data;
  return response(status, {}, Buffer.from(sortedJSON({ jsonrpc: "2.0", id: id ?? null, error }), "utf8"));
}

/**
 * Compares in time that does not depend on where the two differ, so the
 * time a refusal takes says nothing about how much of the token matched.
 */
function sameBytes(a: string, b: string): boolean {
  const left = createHash("sha256").update(a, "utf8").digest();
  const right = createHash("sha256").update(b, "utf8").digest();
  return timingSafeEqual(left, right);
}

// MARK: - Descriptor

/** The file a running provider keeps so a host can find it. */
export interface ContextDescriptor {
  protocol: string;
  app: ContextApp;
  pid: number;
  instance: string;
  endpoint: string;
  token: string;
  started: string;
}

export const ContextDescriptor = {
  /** `~/Library/Application Support/AmbientContext/providers`. */
  get defaultDirectory(): string {
    return join(homedir(), "Library", "Application Support", "AmbientContext", "providers");
  },

  fileName(bundleID: string, pid: number): string {
    return `${bundleID}.${pid}.json`;
  },

  /**
   * Writes the file where only the user can read it, under a temporary
   * name first so a host never reads half of it. Returns its path, which
   * the caller removes when the provider stops. `ContextServer` calls it;
   * so does an app that mounts a `ContextResponder` on its own listener,
   * once that listener is up, with `endpoint` naming the mounted path.
   */
  write(descriptor: ContextDescriptor, directory: string): string {
    mkdirSync(directory, { recursive: true, mode: 0o700 });
    chmodSync(directory, 0o700);

    const data = sortedJSON({
      protocol: descriptor.protocol,
      app: { id: descriptor.app.id, name: descriptor.app.name, version: descriptor.app.version },
      pid: descriptor.pid,
      instance: descriptor.instance,
      endpoint: descriptor.endpoint,
      token: descriptor.token,
      started: descriptor.started,
    }, 2);

    const destination = join(directory, ContextDescriptor.fileName(descriptor.app.id, descriptor.pid));
    const temporary = join(directory, `.${randomUUID().toUpperCase()}.tmp`);
    try {
      writeFileSync(temporary, data, { mode: 0o600, flag: "wx" });
      chmodSync(temporary, 0o600);
      renameSync(temporary, destination);
    } catch (error) {
      rmSync(temporary, { force: true });
      throw error;
    }
    return destination;
  },

  /**
   * Removes descriptors this app left behind: those naming a process
   * that is no longer running, and any naming `pid` itself, which a
   * crashed run with the same process id would have written.
   */
  removeStale(bundleID: string, pid: number, directory: string): void {
    let names: string[];
    try {
      names = readdirSync(directory);
    } catch {
      return;
    }
    const prefix = `${bundleID}.`, suffix = ".json";
    for (const name of names) {
      if (!name.startsWith(prefix) || !name.endsWith(suffix) || name.length < prefix.length + suffix.length) continue;
      const middle = name.slice(prefix.length, name.length - suffix.length);
      if (!/^[+-]?[0-9]{1,10}$/.test(middle)) continue;
      const owner = Number(middle);
      if (owner < -(2 ** 31) || owner > 2 ** 31 - 1) continue;
      if (owner === pid || !isRunning(owner)) rmSync(join(directory, name), { force: true });
    }
  },
};

function isRunning(pid: number): boolean {
  // Zero and below name process groups, not one process; left alone.
  if (pid <= 0) return true;
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return (error as NodeJS.ErrnoException).code === "EPERM";
  }
}

// MARK: - Server

export interface ContextServerOptions {
  provider: ContextProvider;
  app: ContextApp;
  /** Where the descriptor is kept. Defaults to `ContextDescriptor.defaultDirectory`. */
  directory?: string;
  /** As `ContextResponderOptions.check`. */
  check?: "warn" | "refuse" | "off";
  /** As `ContextResponderOptions.report`. */
  report?: (issue: ContextIssue) => void;
}

/**
 * The listener and the descriptor. Start it and a host can find and read
 * the provider; stop it and both are gone.
 */
export class ContextServer {
  #provider: ContextProvider;
  #app: ContextApp;
  #directory: string;
  #check: ContextServerOptions["check"];
  #report: ContextServerOptions["report"];
  #listener: Server | undefined;
  #ready: Promise<void> | undefined;
  #descriptorPath: string | undefined;
  #endpoint: URL | undefined;
  #token: string | undefined;
  #instance: string | undefined;
  #stopAtExit = (): void => this.stop();

  constructor(options: ContextServerOptions) {
    this.#provider = options.provider;
    this.#app = { id: options.app.id, name: options.app.name, version: options.app.version };
    this.#directory = options.directory ?? ContextDescriptor.defaultDirectory;
    this.#check = options.check;
    this.#report = options.report;
  }

  /** The endpoint, once the listener is up. */
  get endpoint(): URL | undefined { return this.#endpoint; }
  get token(): string | undefined { return this.#token; }
  get instance(): string | undefined { return this.#instance; }
  get isRunning(): boolean { return this.#listener !== undefined; }

  /**
   * Opens the listener on the loopback interface, on a port the system
   * picks, and writes the descriptor once it is ready. A new token and
   * instance are made on every start. The promise resolves when the
   * descriptor has been written, or when the listener failed or was
   * stopped first; it never rejects.
   */
  start(): Promise<void> {
    if (this.#listener) return this.#ready ?? Promise.resolve();
    const token = ContextServer.random(32);
    const instance = ContextServer.random(6);
    const pid = process.pid;
    ContextDescriptor.removeStale(this.#app.id, pid, this.#directory);

    const provider = this.#provider;
    // Only a provider with `locate` answers it.
    const locate = typeof provider.locate === "function" ? (id: string) => provider.locate?.(id) : undefined;
    const responder = new ContextResponder({
      app: this.#app, instance, token,
      current: () => provider.current(),
      display: typeof provider.display === "function" ? () => provider.display?.() : undefined,
      locate,
      ...(this.#check ? { check: this.#check } : {}),
      ...(this.#report ? { report: this.#report } : {}),
    });

    const listener = createServer({ allowHalfOpen: true }, (socket) => serve(socket, responder));
    this.#listener = listener;
    this.#token = token;
    this.#instance = instance;
    this.#ready = new Promise((resolve) => {
      listener.once("listening", () => {
        this.#listenerIsReady(listener, pid);
        resolve();
      });
      // A listener that could not open is not running: clear the state so
      // `isRunning` says so and a later `start()` tries again.
      listener.once("error", () => {
        if (this.#listener === listener) this.stop();
        resolve();
      });
      listener.once("close", () => resolve());
    });
    // A process that exits without `stop()` would leave the descriptor
    // behind; remove it on the way out for as long as there is one.
    process.once("exit", this.#stopAtExit);
    listener.listen({ host: "127.0.0.1", port: 0, exclusive: true });
    return this.#ready;
  }

  #listenerIsReady(ready: Server, pid: number): void {
    const token = this.#token, instance = this.#instance;
    if (ready !== this.#listener || token === undefined || instance === undefined || this.#descriptorPath !== undefined) return;
    const address = ready.address() as AddressInfo | null;
    if (!address || typeof address !== "object") return;
    const endpoint = `http://127.0.0.1:${address.port}${ContextResponder.endpointPath}`;
    this.#endpoint = new URL(endpoint);
    try {
      this.#descriptorPath = ContextDescriptor.write({
        protocol: ContextResponder.protocolVersion,
        app: this.#app,
        pid,
        instance,
        endpoint,
        token,
        started: new Date().toISOString().replace(/\.\d+Z$/, "Z"),
      }, this.#directory);
    } catch {
      // No descriptor: the listener runs and no host can find it.
    }
  }

  /** Closes the listener and removes the descriptor. */
  stop(): void {
    const listener = this.#listener;
    this.#listener = undefined;
    this.#ready = undefined;
    if (listener) {
      listener.close();
      process.off("exit", this.#stopAtExit);
    }
    if (this.#descriptorPath !== undefined) {
      try {
        rmSync(this.#descriptorPath, { force: true });
      } catch {
        // Nothing more to do about a file that will not go.
      }
    }
    this.#descriptorPath = undefined;
    this.#endpoint = undefined;
    this.#token = undefined;
    this.#instance = undefined;
  }

  /** Random bytes as URL-safe text. */
  static random(bytes: number): string {
    return randomBytes(bytes).toString("base64url");
  }
}

/** One accepted connection: reads a request, answers it, closes. */
function serve(socket: Socket, responder: ContextResponder): void {
  let chunks: Buffer = Buffer.alloc(0);
  let answered = false;

  // A client that connects and says nothing is dropped.
  const timer = setTimeout(() => socket.destroy(), 10_000);
  socket.on("close", () => clearTimeout(timer));
  socket.on("error", () => socket.destroy());

  const send = (answer: ContextHTTPResponse): void => {
    if (socket.destroyed) return;
    socket.end(ContextHTTP.serialize(answer), () => socket.destroy());
  };

  socket.on("data", (data: Buffer) => {
    if (answered) return;
    chunks = Buffer.concat([chunks, data]);
    const parsed = ContextHTTP.parse(chunks);
    if (parsed.kind === "incomplete") return;
    answered = true;
    if (parsed.kind === "request") {
      responder.respond(parsed.request).then(send, () => socket.destroy());
    } else {
      send(response(parsed.kind === "malformed" ? 400 : 413));
    }
  });
  socket.on("end", () => {
    if (!answered) socket.destroy();
  });
}
