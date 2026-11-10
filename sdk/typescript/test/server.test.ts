import assert from "node:assert/strict";
import { chmodSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { basename, dirname, join } from "node:path";
import { test } from "node:test";

import type { ContextItem } from "../src/provider.ts";
import { ContextLocation } from "../src/provider.ts";
import { ContextDescriptor, ContextHTTP, ContextResponder, ContextServer } from "../src/server.ts";
import type { ContextHTTPRequest, ContextHTTPResponse } from "../src/server.ts";

// The provider's server, without a socket: bytes to a request, a request
// to a response, and the descriptor file. Ported from the Swift package's
// `ServerTests.swift`, test for test and under the same names.

// MARK: - Fixtures

type JSONObject = Record<string, any>;

const token = "test-token";

const selection: ContextItem = {
  id: "sel-23", type: "selection", title: "Selection in draft.md",
  content: [{ type: "text", text: "The command line lasted thirty years." }],
  parent: "doc-1", locatable: true,
  payload: { lines: { start: 3, end: 3 } },
};
const draft: ContextItem = {
  id: "doc-1", type: "document", title: "draft.md", url: "file:///Users/ada/essays/draft.md",
};

function makeResponder(locate = true): ContextResponder {
  return new ContextResponder({
    app: { id: "org.example.editor", name: "Editor", version: "2.3.0" },
    instance: "k3f9x2",
    token,
    current: () => ({ focus: ["sel-23"], items: [draft, selection] }),
    locate: locate ? (id) => {
      switch (id) {
        case "sel-23":
          return { id, state: "visible", rects: [{ x: 425, y: 233, w: 480, h: 20 }], window: 48211, edge: "right" };
        case "sel-9": return ContextLocation.gone(id);
        default: return undefined;
      }
    } : undefined,
  });
}

const responder = makeResponder();

interface RequestOptions {
  params?: JSONObject;
  id?: unknown;
  token?: string | null;
  version?: string | null;
  headerVersion?: string | null;
  capabilities?: unknown;
  methodHeader?: string | null;
  nameHeader?: string | null;
  extraHeaders?: Record<string, string>;
  httpMethod?: string;
  path?: string;
}

/**
 * A request as a current client sends it; each option can be overridden
 * or, with null, left out.
 */
function request(method: string, options: RequestOptions = {}): ContextHTTPRequest {
  const or = <T>(value: T | null | undefined, fallback: T | null): T | null => (value === undefined ? fallback : value);
  const id = or(options.id, 1);
  const bearer = or(options.token, token);
  const version = or(options.version, "2026-07-28");
  const capabilities = or(options.capabilities, {});

  const meta: JSONObject = {};
  if (version !== null) meta["io.modelcontextprotocol/protocolVersion"] = version;
  if (capabilities !== null) meta["io.modelcontextprotocol/clientCapabilities"] = capabilities;
  const params: JSONObject = { ...options.params };
  if (Object.keys(meta).length > 0) params["_meta"] = meta;
  const message: JSONObject = { jsonrpc: "2.0", method, params };
  if (id !== null) message["id"] = id;

  const headers = new Map(Object.entries(options.extraHeaders ?? {}));
  if (bearer !== null) headers.set("authorization", `Bearer ${bearer}`);
  const headerVersion = or(options.headerVersion, version);
  if (headerVersion !== null) headers.set("mcp-protocol-version", headerVersion);
  const methodHeader = or(options.methodHeader, method);
  if (methodHeader !== null) headers.set("mcp-method", methodHeader);
  const nameHeader = or(options.nameHeader, typeof params["uri"] === "string" ? params["uri"] : null);
  if (nameHeader !== null) headers.set("mcp-name", nameHeader);
  return {
    method: options.httpMethod ?? "POST", path: options.path ?? "/mcp", headers,
    body: Buffer.from(JSON.stringify(message)),
  };
}

function json(response: ContextHTTPResponse): JSONObject {
  const value: unknown = JSON.parse(response.body.toString("utf8"));
  assert.ok(typeof value === "object" && value !== null && !Array.isArray(value));
  return value as JSONObject;
}

function result(response: ContextHTTPResponse): JSONObject {
  assert.equal(response.status, 200);
  const value = json(response)["result"];
  assert.ok(value);
  return value;
}

function errorCode(response: ContextHTTPResponse): number {
  const error = json(response)["error"];
  assert.ok(error);
  assert.equal(typeof error.code, "number");
  return error.code;
}

/** The JSON document inside a `resources/read` result. */
function documentOf(response: ContextHTTPResponse, uri: string): JSONObject {
  const value = result(response);
  assert.equal(value["resultType"], "complete");
  const contents = value["contents"];
  assert.equal(contents.length, 1);
  assert.equal(contents[0].uri, uri);
  assert.equal(contents[0].mimeType, "application/json");
  assert.equal(typeof contents[0].text, "string");
  return JSON.parse(contents[0].text);
}

const bytes = (text: string): Buffer => Buffer.from(text, "utf8");

// MARK: - HTTP

test("aWholeRequestParses", () => {
  const parsed = ContextHTTP.parse(bytes("POST /mcp?x=1 HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Length: 2\r\nAuthorization:  Bearer t \r\n\r\n{}"));
  assert.deepEqual(parsed, {
    kind: "request",
    request: {
      method: "POST", path: "/mcp",
      headers: new Map([["host", "127.0.0.1"], ["content-length", "2"], ["authorization", "Bearer t"]]),
      body: bytes("{}"),
    },
  });
});

test("aRequestSplitAcrossReadsWaitsForTheRest", () => {
  const whole = bytes("POST /mcp HTTP/1.1\r\nContent-Length: 10\r\n\r\n{\"a\":1234}");
  for (const cut of [5, 20, whole.length - 12, whole.length - 1]) {
    assert.deepEqual(ContextHTTP.parse(whole.subarray(0, cut)), { kind: "incomplete" });
  }
  const parsed = ContextHTTP.parse(whole);
  assert.equal(parsed.kind, "request");
  if (parsed.kind === "request") assert.deepEqual(parsed.request.body, bytes("{\"a\":1234}"));
});

test("aBufferThatIsASliceParses", () => {
  const padded = Buffer.concat([bytes("xxxx"), bytes("GET / HTTP/1.1\r\n\r\n")]);
  assert.deepEqual(ContextHTTP.parse(padded.subarray(4)), {
    kind: "request",
    request: { method: "GET", path: "/", headers: new Map(), body: Buffer.alloc(0) },
  });
});

test("malformedAndOversizedRequestsAreToldApart", () => {
  assert.equal(ContextHTTP.parse(bytes("nonsense\r\n\r\n")).kind, "malformed");
  assert.equal(ContextHTTP.parse(bytes("POST /mcp HTTP/1.1\r\nno colon\r\n\r\n")).kind, "malformed");
  assert.equal(ContextHTTP.parse(bytes("POST /mcp HTTP/1.1\r\nContent-Length: -1\r\n\r\n")).kind, "malformed");
  assert.equal(ContextHTTP.parse(bytes("POST /mcp HTTP/1.1\r\nTransfer-Encoding: chunked\r\n\r\n")).kind, "malformed");
  assert.equal(ContextHTTP.parse(bytes("POST /mcp HTTP/1.1\r\nContent-Length: 99999999\r\n\r\n")).kind, "tooLarge");
  assert.equal(ContextHTTP.parse(Buffer.alloc(ContextHTTP.headerLimit + 1, 0x41)).kind, "tooLarge");
});

test("aResponseSerializesWithItsLengthAndCloses", () => {
  const text = ContextHTTP.serialize({ status: 200, headers: {}, body: bytes("{}") }).toString("utf8");
  assert.equal(text, "HTTP/1.1 200 OK\r\nConnection: close\r\nContent-Length: 2\r\nContent-Type: application/json\r\n\r\n{}");
});

// MARK: - Reads

test("discoverDeclaresTheExtension", async () => {
  const value = result(await responder.respond(request("server/discover")));
  assert.equal(value["resultType"], "complete");
  assert.equal(value["supportedVersions"][0], "2026-07-28");
  assert.deepEqual(value["capabilities"].resources, {});
  assert.deepEqual(value["capabilities"].extensions["org.humanitas/ambient-context"], { version: "0.1" });
  assert.deepEqual(value["_meta"]["io.modelcontextprotocol/serverInfo"], { name: "Editor", version: "2.3.0" });
});

test("theResourceAndTheTemplateAreListed", async () => {
  const listed = result(await responder.respond(request("resources/list")));
  assert.deepEqual(listed["resources"].map((entry: JSONObject) => entry["uri"]), ["ambient://current"]);
  assert.equal(listed["resources"][0].mimeType, "application/json");

  const templates = result(await responder.respond(request("resources/templates/list")));
  assert.deepEqual(templates["resourceTemplates"].map((entry: JSONObject) => entry["uriTemplate"]), ["ambient://location/{id}"]);
});

test("currentReturnsTheAppTheInstanceAndTheItems", async () => {
  const uri = "ambient://current";
  const current = documentOf(await responder.respond(request("resources/read", { params: { uri } })), uri);
  assert.deepEqual(current["app"], { id: "org.example.editor", name: "Editor" });
  assert.equal(current["instance"], "k3f9x2");
  assert.deepEqual(current["focus"], ["sel-23"]);

  const items = current["items"];
  assert.equal(items.length, 2);
  assert.equal(items[0].id, "doc-1");
  assert.equal(items[0].url, "file:///Users/ada/essays/draft.md");
  // Fields an item does not have are left out, not sent as null.
  assert.deepEqual(Object.keys(items[0]).sort(), ["id", "title", "type", "url"]);

  assert.equal(items[1].parent, "doc-1");
  assert.equal(items[1].locatable, true);
  assert.deepEqual(items[1].content, [{ type: "text", text: "The command line lasted thirty years." }]);
  assert.deepEqual(items[1].payload, { lines: { start: 3, end: 3 } });
});

test("locateReturnsTheRectangles", async () => {
  const uri = "ambient://location/sel-23";
  const location = documentOf(await responder.respond(request("resources/read", { params: { uri } })), uri);
  assert.equal(location["id"], "sel-23");
  assert.equal(location["state"], "visible");
  assert.deepEqual(location["rects"], [{ x: 425, y: 233, w: 480, h: 20 }]);
  assert.equal(location["window"], 48211);
  assert.equal(location["edge"], "right");
  assert.equal("avoid" in location, false);
});

test("anItemThatIsGoneIsAnAnswerNotAnError", async () => {
  const uri = "ambient://location/sel-9";
  const location = documentOf(await responder.respond(request("resources/read", { params: { uri } })), uri);
  assert.equal(location["state"], "gone");
  assert.deepEqual(Object.keys(location).sort(), ["id", "state"]);
});

test("anIdNeverIssuedIsAnError", async () => {
  for (const uri of ["ambient://location/sel-404", "ambient://location/", "ambient://location/a%2Fb", "ambient://nothing", "file:///etc/passwd"]) {
    const response = await responder.respond(request("resources/read", { params: { uri } }));
    assert.equal(errorCode(response), -32602, uri);
    assert.equal(response.status, 200, uri);
  }
});

// MARK: - A provider that does not report positions

const withoutLocate = makeResponder(false);

test("aProviderWithoutLocateOffersNoTemplate", async () => {
  const templates = result(await withoutLocate.respond(request("resources/templates/list")));
  assert.deepEqual(templates["resourceTemplates"], []);
});

test("aProviderWithoutLocateStillAnswersCurrent", async () => {
  const uri = "ambient://current";
  const current = documentOf(await withoutLocate.respond(request("resources/read", { params: { uri } })), uri);
  assert.equal(current["items"].length, 2);
});

test("aProviderWithoutLocateHasNoLocations", async () => {
  const response = await withoutLocate.respond(request("resources/read", { params: { uri: "ambient://location/sel-23" } }));
  assert.equal(response.status, 200);
  assert.equal(errorCode(response), -32602);
});

test("aStringIdComesBackAsAString", async () => {
  const response = await responder.respond(request("resources/list", { id: "discover-1" }));
  assert.equal(json(response)["id"], "discover-1");
});

// MARK: - Refusals

test("aMissingOrWrongTokenIsRefused", async () => {
  assert.equal((await responder.respond(request("resources/list", { token: null }))).status, 401);
  assert.equal((await responder.respond(request("resources/list", { token: "wrong" }))).status, 401);
  assert.equal((await responder.respond(request("resources/list", { token: token + "x" }))).status, 401);
  const lowercase = request("resources/list");
  lowercase.headers.set("authorization", `bearer ${token}`);
  assert.equal((await responder.respond(lowercase)).status, 401);
});

test("anOriginIsRefusedEvenWithTheToken", async () => {
  const response = await responder.respond(request("resources/list", { extraHeaders: { origin: "http://localhost:3000" } }));
  assert.equal(response.status, 403);
  // And before the token is judged: a page learns nothing from it.
  const anonymous = await responder.respond(request("resources/list", { token: null, extraHeaders: { origin: "null" } }));
  assert.equal(anonymous.status, 403);
});

test("onlyPostToTheEndpointIsServed", async () => {
  assert.equal((await responder.respond(request("resources/list", { path: "/" }))).status, 404);
  const get = await responder.respond(request("resources/list", { httpMethod: "GET" }));
  assert.equal(get.status, 405);
  assert.equal(get.headers["Allow"], "POST");
});

test("aBodyThatIsNotARequestIsRefused", async () => {
  const broken = request("resources/list");
  broken.body = bytes("{not json");
  const parse = await responder.respond(broken);
  assert.equal(parse.status, 400);
  assert.equal(errorCode(parse), -32700);

  broken.body = bytes("{\"jsonrpc\":\"2.0\",\"id\":1}");
  const invalid = await responder.respond(broken);
  assert.equal(invalid.status, 400);
  assert.equal(errorCode(invalid), -32600);

  broken.body = bytes("[]");
  assert.equal((await responder.respond(broken)).status, 400);
});

test("aNotificationIsAcceptedWithNoBody", async () => {
  const response = await responder.respond(request("notifications/cancelled", { id: null }));
  assert.equal(response.status, 202);
  assert.equal(response.body.length, 0);
});

test("anUnknownMethodIsNotFound", async () => {
  const response = await responder.respond(request("tools/list"));
  assert.equal(response.status, 404);
  assert.equal(errorCode(response), -32601);
});

test("theClientCapabilitiesAreRequired", async () => {
  const response = await responder.respond(request("resources/list", { capabilities: null }));
  assert.equal(response.status, 400);
  assert.equal(errorCode(response), -32602);
});

test("theVersionInTheBodyIsRequiredOnceTheHeaderNamesThisRevision", async () => {
  const response = await responder.respond(request("resources/list", { version: null, headerVersion: "2026-07-28" }));
  assert.equal(response.status, 400);
  assert.equal(errorCode(response), -32602);
});

test("anUnsupportedVersionListsTheSupportedOnes", async () => {
  const response = await responder.respond(request("resources/list", { version: "1900-01-01" }));
  assert.equal(response.status, 400);
  const error = json(response)["error"];
  assert.equal(error.code, -32022);
  assert.equal(error.data.requested, "1900-01-01");
  assert.ok(error.data.supported.includes("2026-07-28"));
});

test("headersMustAgreeWithTheBody", async () => {
  const cases = [
    request("resources/list", { headerVersion: null }),
    request("resources/list", { headerVersion: "2025-11-25" }),
    request("resources/list", { methodHeader: null }),
    request("resources/list", { methodHeader: "resources/read" }),
    request("resources/read", { params: { uri: "ambient://current" }, nameHeader: null }),
    request("resources/read", { params: { uri: "ambient://current" }, nameHeader: "ambient://location/sel-23" }),
  ];
  for (const [index, mismatched] of cases.entries()) {
    const response = await responder.respond(mismatched);
    assert.equal(response.status, 400, `case ${index}`);
    assert.equal(errorCode(response), -32020, `case ${index}`);
  }
});

test("anEncodedNameHeaderIsDecodedBeforeComparing", async () => {
  const uri = "ambient://current";
  const encoded = `=?base64?${Buffer.from(uri).toString("base64")}?=`;
  const response = await responder.respond(request("resources/read", { params: { uri }, nameHeader: encoded }));
  assert.equal(response.status, 200);
  assert.equal(ContextResponder.decodedHeaderValue("plain"), "plain");
  assert.equal(ContextResponder.decodedHeaderValue("=?base64?!!!?="), "=?base64?!!!?=");
});

test("itemIdsAreLettersDigitsHyphensAndUnderscores", () => {
  assert.ok(ContextResponder.isItemID("sel-23"));
  assert.ok(ContextResponder.isItemID("Doc_1"));
  assert.ok(!ContextResponder.isItemID(""));
  assert.ok(!ContextResponder.isItemID("a/b"));
  assert.ok(!ContextResponder.isItemID("sél"));
  assert.ok(!ContextResponder.isItemID("a".repeat(129)));
});

// MARK: - Older clients

/**
 * A request as a client on an earlier revision sends it: nothing in
 * `_meta`, the revision in the header once it has been agreed.
 */
function legacy(method: string, params: JSONObject = {}, header: string | null = "2025-11-25"): ContextHTTPRequest {
  const headers = new Map([["authorization", `Bearer ${token}`]]);
  if (header !== null) headers.set("mcp-protocol-version", header);
  const message = { jsonrpc: "2.0", id: 7, method, params };
  return { method: "POST", path: "/mcp", headers, body: Buffer.from(JSON.stringify(message)) };
}

test("theOlderHandshakeIsAnswered", async () => {
  const response = await responder.respond(legacy("initialize", {
    protocolVersion: "2025-06-18", capabilities: {},
    clientInfo: { name: "old", version: "1" },
  }, null));
  const value = result(response);
  assert.equal(value["protocolVersion"], "2025-06-18");
  assert.deepEqual(value["serverInfo"], { name: "Editor", version: "2.3.0" });
  assert.equal("resultType" in value, false);
  assert.deepEqual(value["capabilities"].resources, {});
  assert.deepEqual(value["capabilities"].experimental, { "org.humanitas/ambient-context": { version: "0.1" } });

  // A revision this server does not know is answered with one it does.
  const unknown = result(await responder.respond(legacy("initialize", { protocolVersion: "2030-01-01" }, null)));
  assert.equal(unknown["protocolVersion"], "2025-11-25");

  const note = legacy("notifications/initialized");
  note.body = bytes("{\"jsonrpc\":\"2.0\",\"method\":\"notifications/initialized\"}");
  assert.equal((await responder.respond(note)).status, 202);
});

test("anOlderClientListsAndReadsBothResources", async () => {
  for (const header of ["2025-11-25", "2025-03-26", null]) {
    const listed = result(await responder.respond(legacy("resources/list", {}, header)));
    assert.equal("resultType" in listed, false);
    assert.equal(listed["resources"][0].uri, "ambient://current");

    const templates = result(await responder.respond(legacy("resources/templates/list", {}, header)));
    assert.equal(templates["resourceTemplates"].length, 1);

    const read = result(await responder.respond(legacy("resources/read", { uri: "ambient://location/sel-23" }, header)));
    assert.ok(read["contents"][0].text.includes("\"state\":\"visible\""));
  }
});

test("anOlderClientGetsThatRevisionsErrors", async () => {
  const missing = await responder.respond(legacy("resources/read", { uri: "ambient://location/sel-404" }));
  assert.equal(missing.status, 200);
  assert.equal(errorCode(missing), -32002);

  const unknown = await responder.respond(legacy("tools/list"));
  assert.equal(unknown.status, 200);
  assert.equal(errorCode(unknown), -32601);

  // `server/discover` belongs to the newer revision only.
  assert.equal(errorCode(await responder.respond(legacy("server/discover"))), -32601);
  // The token and Origin rules hold for every client.
  const noToken = legacy("resources/list");
  noToken.headers.delete("authorization");
  assert.equal((await responder.respond(noToken)).status, 401);
});

// MARK: - Descriptor

function temporaryDirectory(): string {
  return join(mkdtempSync(join(tmpdir(), "acp-context-")), "providers");
}

function descriptor(pid: number): ContextDescriptor {
  return {
    protocol: "0.1", app: { id: "org.example.editor", name: "Editor", version: "2.3.0" },
    pid, instance: "k3f9x2", endpoint: "http://127.0.0.1:53124/mcp", token: "secret",
    started: "2026-11-09T21:14:03Z",
  };
}

const permissions = (path: string): number => statSync(path).mode & 0o777;

test("theDescriptorIsWrittenPrivateWithItsSevenFields", (t) => {
  const directory = temporaryDirectory();
  t.after(() => rmSync(dirname(directory), { recursive: true, force: true }));
  const path = ContextDescriptor.write(descriptor(48211), directory);

  assert.equal(basename(path), "org.example.editor.48211.json");
  assert.equal(permissions(directory), 0o700);
  assert.equal(permissions(path), 0o600);
  // Nothing but the descriptor is left in the folder.
  assert.deepEqual(readdirSync(directory), ["org.example.editor.48211.json"]);

  const written = JSON.parse(readFileSync(path, "utf8"));
  assert.deepEqual(Object.keys(written).sort(), ["app", "endpoint", "instance", "pid", "protocol", "started", "token"]);
  assert.equal(written.protocol, "0.1");
  assert.equal(written.pid, 48211);
  assert.equal(written.endpoint, "http://127.0.0.1:53124/mcp");
  assert.deepEqual(written.app, { id: "org.example.editor", name: "Editor", version: "2.3.0" });
});

test("writingAgainReplacesTheFileAndTightensTheFolder", (t) => {
  const directory = temporaryDirectory();
  t.after(() => rmSync(dirname(directory), { recursive: true, force: true }));
  mkdirSync(directory, { recursive: true });
  chmodSync(directory, 0o755);
  ContextDescriptor.write(descriptor(1), directory);
  const path = ContextDescriptor.write({ ...descriptor(1), token: "newer" }, directory);
  assert.equal(permissions(directory), 0o700);
  assert.ok(readFileSync(path, "utf8").includes("newer"));
});

test("staleDescriptorsOfThisAppAreRemoved", (t) => {
  const directory = temporaryDirectory();
  t.after(() => rmSync(dirname(directory), { recursive: true, force: true }));
  const own = process.pid;
  // A process id no running process has: far above the system's limit.
  const dead = 99_999_999;
  ContextDescriptor.write(descriptor(dead), directory);
  ContextDescriptor.write(descriptor(own), directory);
  ContextDescriptor.write(descriptor(process.ppid), directory);
  const other = descriptor(dead);
  other.app.id = "org.example.other";
  ContextDescriptor.write(other, directory);

  ContextDescriptor.removeStale("org.example.editor", own, directory);
  // The dead one and a leftover under this process's own id go; a
  // running sibling's stays, and so does another app's.
  assert.deepEqual(readdirSync(directory).sort(), [`org.example.editor.${process.ppid}.json`, `org.example.other.${dead}.json`]);
});

test("tokensAreLongRandomAndSafeInAHeader", () => {
  const first = ContextServer.random(32), second = ContextServer.random(32);
  assert.notEqual(first, second);
  assert.equal(first.length, 43);
  assert.match(first, /^[A-Za-z0-9_-]+$/);
});
