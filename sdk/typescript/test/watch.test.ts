import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { request as httpRequest } from "node:http";
import type { ClientRequest } from "node:http";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import type { TestContext } from "node:test";

import { ContextDescriptor, ContextResponder, ContextServer } from "../src/index.ts";
import type { ContextElement, ContextHTTPRequest, ContextProvider } from "../src/index.ts";

// Watching `current` (RFC-0006), over a real socket, as a host does it:
// one request held open, the acknowledgment, a notice with no content for
// each change, and the ways a watch ends. The intervals are shortened so
// the tests are quick; the rules they check do not depend on the numbers.

type JSONObject = Record<string, any>;

const subscriptionID = "io.modelcontextprotocol/subscriptionId";
const coalesce = 40;
const sleep = (ms: number): Promise<void> => new Promise((resolve) => setTimeout(resolve, ms));

async function until(condition: () => boolean, what: string, timeout = 2000): Promise<void> {
  const deadline = Date.now() + timeout;
  while (!condition()) {
    if (Date.now() > deadline) assert.fail(`timed out waiting for ${what}`);
    await sleep(2);
  }
}

/** An app whose selection, pointer and wording a test can move. */
class Notes implements ContextProvider {
  selected = "note-1";
  hovered: string | undefined;
  detail = "1 word";
  asked = 0;

  current(): ContextElement {
    this.asked += 1;
    const note = (id: string): ContextElement => ({
      id, role: "Row", subrole: "note", title: id,
      ...(this.selected === id ? { selected: true } : {}),
      ...(this.hovered === id ? { hovered: true } : {}),
    });
    return { id: "app", role: "Application", title: "Notes", children: [note("note-1"), note("note-2"), note("note-3")] };
  }

  display(): { title: string; detail: string } {
    return { title: "Notes", detail: this.detail };
  }
}

interface Started {
  server: ContextServer;
  descriptor: ContextDescriptor;
  notes: Notes;
}

async function started(t: TestContext, options: { keepAlive?: number } = {}): Promise<Started> {
  const directory = join(mkdtempSync(join(tmpdir(), "acp-")), "providers");
  const app = { id: "org.example.notes", name: "Notes", version: "1.0" };
  const notes = new Notes();
  const server = new ContextServer({
    provider: notes, app, directory, _coalesceInterval: coalesce,
    ...(options.keepAlive === undefined ? {} : { _keepAliveInterval: options.keepAlive }),
  });
  t.after(() => {
    server.stop();
    rmSync(join(directory, ".."), { recursive: true, force: true });
  });
  await server.start();
  const file = join(directory, ContextDescriptor.fileName(app.id, process.pid));
  return { server, descriptor: JSON.parse(readFileSync(file, "utf8")) as ContextDescriptor, notes };
}

interface Sent {
  id?: string | number;
  token?: string | null;
  headers?: Record<string, string>;
  params?: JSONObject;
  /** Null for a client of an earlier revision, which names none in the body. */
  version?: string | null;
}

function message(method: string, sent: Sent = {}): { headers: Record<string, string>; body: string } {
  const version = sent.version === undefined ? "2026-07-28" : sent.version;
  const params: JSONObject = { ...sent.params };
  const headers: Record<string, string> = { "Content-Type": "application/json", Accept: "application/json, text/event-stream" };
  if (version !== null) {
    params["_meta"] = {
      "io.modelcontextprotocol/protocolVersion": version,
      "io.modelcontextprotocol/clientCapabilities": {},
    };
    headers["MCP-Protocol-Version"] = version;
    headers["Mcp-Method"] = method;
    if (typeof params["uri"] === "string") headers["Mcp-Name"] = params["uri"];
  }
  return { headers: { ...headers, ...sent.headers }, body: JSON.stringify({ jsonrpc: "2.0", id: sent.id ?? 1, method, params }) };
}

interface Stream {
  status: number;
  headers: Record<string, string | string[] | undefined>;
  /** Everything received after the head, as it came. */
  raw: () => string;
  /** The JSON-RPC messages received so far, with when each arrived. */
  events: JSONObject[];
  arrived: number[];
  notices: () => JSONObject[];
  ended: () => boolean;
  /** Ends the watch as a host does: by closing the connection. */
  close: () => void;
}

/** Sends a request and resolves at the response's head, leaving the body to arrive. */
function open(descriptor: ContextDescriptor, method: string, sent: Sent = {}): Promise<Stream> {
  const { headers, body } = message(method, sent);
  const token = sent.token === undefined ? descriptor.token : sent.token;
  if (token !== null) headers["Authorization"] = `Bearer ${token}`;
  return new Promise((resolve, reject) => {
    const outgoing: ClientRequest = httpRequest(descriptor.endpoint, {
      method: "POST", headers: { ...headers, "Content-Length": Buffer.byteLength(body) }, agent: false,
    }, (incoming) => {
      let raw = "", parsed = 0, ended = false;
      const events: JSONObject[] = [], arrived: number[] = [];
      incoming.setEncoding("utf8");
      incoming.on("data", (chunk: string) => {
        raw += chunk;
        for (;;) {
          const end = raw.indexOf("\n\n", parsed);
          if (end < 0) break;
          const lines = raw.slice(parsed, end).split("\n");
          parsed = end + 2;
          if (lines[0]?.startsWith(":")) continue;
          assert.equal(lines.length, 2);
          assert.equal(lines[0], "event: message");
          assert.ok(lines[1]?.startsWith("data: "));
          events.push(JSON.parse((lines[1] ?? "").slice(6)));
          arrived.push(performance.now());
        }
      });
      incoming.on("end", () => { ended = true; });
      incoming.on("error", () => { ended = true; });
      resolve({
        status: incoming.statusCode ?? 0, headers: incoming.headers, raw: () => raw, events, arrived,
        notices: () => events.filter((event) => event["method"] === "notifications/resources/updated"),
        ended: () => ended,
        close: () => outgoing.destroy(),
      });
    });
    outgoing.on("error", reject);
    outgoing.end(body);
  });
}

/** A request answered in the ordinary way: the whole response. */
async function post(descriptor: ContextDescriptor, method: string, sent: Sent = {}): Promise<{ status: number; headers: Stream["headers"]; body: string }> {
  const stream = await open(descriptor, method, sent);
  await until(stream.ended, "the response to end");
  return { status: stream.status, headers: stream.headers, body: stream.raw() };
}

const listen = (resources: unknown = ["ambient://current"], more: JSONObject = {}): JSONObject => ({
  notifications: { resourceSubscriptions: resources, ...more },
});

async function watch(t: TestContext, descriptor: ContextDescriptor, sent: Sent = {}): Promise<Stream> {
  const stream = await open(descriptor, "subscriptions/listen", { id: 7, params: listen(), ...sent });
  t.after(() => stream.close());
  assert.equal(stream.status, 200);
  await until(() => stream.events.length > 0, "the acknowledgment");
  return stream;
}

async function read(descriptor: ContextDescriptor): Promise<JSONObject> {
  const answer = await post(descriptor, "resources/read", { params: { uri: "ambient://current" } });
  assert.equal(answer.status, 200);
  return JSON.parse(JSON.parse(answer.body)["result"].contents[0].text);
}

/** Long enough for a notice that was owed to have come. */
const settle = (): Promise<void> => sleep(coalesce * 4);

// MARK: - Opening a watch

test("aWatchOpensWithTheAcknowledgmentNamingOnlyCurrent", async (t) => {
  const { descriptor, server } = await started(t);
  // Asked for more than is served: only `current` is acknowledged.
  const stream = await watch(t, descriptor, {
    id: "listen-1",
    params: listen(["ambient://current", "ambient://location/note-1"], { toolsListChanged: true, resourcesListChanged: true }),
  });
  assert.equal(stream.headers["content-type"], "text/event-stream");
  assert.equal(stream.headers["cache-control"], "no-store");
  assert.equal(stream.headers["x-accel-buffering"], "no");
  assert.equal(stream.headers["content-length"], undefined);
  assert.deepEqual(stream.events, [{
    jsonrpc: "2.0",
    method: "notifications/subscriptions/acknowledged",
    params: {
      _meta: { [subscriptionID]: "listen-1" },
      notifications: { resourceSubscriptions: ["ambient://current"] },
    },
  }]);
  assert.equal(stream.ended(), false);
  assert.equal(server._watchCount, 1);
});

test("aContextServerDeclaresSubscribeAndABareResponderDoesNot", async (t) => {
  const { descriptor } = await started(t);
  const discovered = JSON.parse((await post(descriptor, "server/discover")).body);
  assert.deepEqual(discovered["result"].capabilities.resources, { subscribe: true });

  // The earlier handshake is as it was, and an earlier client has no such method.
  const initialized = JSON.parse((await post(descriptor, "initialize", { version: null, params: { protocolVersion: "2025-11-25" } })).body);
  assert.deepEqual(initialized["result"].capabilities.resources, {});
  const legacy = await post(descriptor, "subscriptions/listen", { version: null, params: listen() });
  assert.equal(legacy.status, 200);
  assert.equal(legacy.headers["content-type"], "application/json");
  assert.equal(JSON.parse(legacy.body)["error"].code, -32601);

  // On an app's own server: not offered yet.
  const responder = new ContextResponder({
    app: { id: "org.example.editor", name: "Editor", version: "3.0" }, instance: "k3f9x2", token: "test-token",
    current: () => ({ id: "app", role: "Application" }),
  });
  const ask = (method: string, params: JSONObject = {}): ContextHTTPRequest => {
    const { headers, body } = message(method, { params });
    const lowered = new Map(Object.entries(headers).map(([name, value]) => [name.toLowerCase(), value]));
    lowered.set("authorization", "Bearer test-token");
    return { method: "POST", path: "/mcp", headers: lowered, body: Buffer.from(body) };
  };
  const bare = await responder.respond(ask("server/discover"));
  assert.deepEqual(JSON.parse(bare.body.toString("utf8"))["result"].capabilities.resources, {});
  const refused = await responder.respond(ask("subscriptions/listen", listen()));
  assert.equal(refused.status, 404);
  assert.equal(JSON.parse(refused.body.toString("utf8"))["error"].code, -32601);
});

test("aWatchIsRefusedBeforeAnyStreamOpens", async (t) => {
  const { descriptor, server } = await started(t);
  const params = listen();

  const noToken = await post(descriptor, "subscriptions/listen", { params, token: null });
  assert.equal(noToken.status, 401);
  assert.equal(noToken.body, "");
  const wrongToken = await post(descriptor, "subscriptions/listen", { params, token: "wrong" });
  assert.equal(wrongToken.status, 401);

  // Refused even with the token, and before it is looked at.
  for (const token of [descriptor.token, null]) {
    const origin = await post(descriptor, "subscriptions/listen", { params, token, headers: { Origin: "http://localhost:3000" } });
    assert.equal(origin.status, 403);
    assert.equal(origin.body, "");
    assert.notEqual(origin.headers["content-type"], "text/event-stream");
  }

  // The checks every request gets come first as well.
  const mismatch = await post(descriptor, "subscriptions/listen", { params, headers: { "Mcp-Method": "resources/read" } });
  assert.equal(mismatch.status, 400);
  assert.equal(JSON.parse(mismatch.body)["error"].code, -32020);

  assert.equal(server._watchCount, 0);
});

test("aFilterWithoutCurrentIsRefused", async (t) => {
  const { descriptor, server } = await started(t);
  const filters: JSONObject[] = [
    listen(["ambient://location/note-1"]),
    listen([]),
    listen("ambient://current"),
    { notifications: { resourcesListChanged: true } },
    { notifications: "ambient://current" },
    {},
  ];
  for (const params of filters) {
    const answer = await post(descriptor, "subscriptions/listen", { params });
    assert.equal(answer.status, 400);
    assert.equal(answer.headers["content-type"], "application/json");
    assert.equal(JSON.parse(answer.body)["error"].code, -32602);
  }
  assert.equal(server._watchCount, 0);
});

// MARK: - Notices

test("aChangeProducesExactlyOneNoticeWithNoContent", async (t) => {
  const { descriptor, server, notes } = await started(t);
  assert.equal((await read(descriptor))["root"].children[0].selected, true);
  const stream = await watch(t, descriptor);

  notes.selected = "note-2";
  server.contextDidChange();
  await until(() => stream.notices().length === 1, "the notice");
  await settle();
  assert.deepEqual(stream.events.slice(1), [{
    jsonrpc: "2.0",
    method: "notifications/resources/updated",
    params: { _meta: { [subscriptionID]: 7 }, uri: "ambient://current" },
  }]);
  // The host learns the new state by reading, as ever.
  assert.equal((await read(descriptor))["root"].children[1].selected, true);

  // What the app words is part of the answer too.
  notes.detail = "2 words";
  server.contextDidChange();
  await until(() => stream.notices().length === 2, "the notice for display");
});

test("aBurstIsOneNoticeAndTheLastChangeStillGetsOne", async (t) => {
  const { descriptor, server, notes } = await started(t);
  await read(descriptor);
  const stream = await watch(t, descriptor);

  for (let turn = 0; turn < 200; turn += 1) {
    notes.selected = turn % 2 === 0 ? "note-2" : "note-3";
    server.contextDidChange();
  }
  await until(() => stream.notices().length === 1, "the burst's notice");

  // More changes inside the same interval: held back, never dropped.
  for (const selected of ["note-1", "note-2", "note-1"]) {
    notes.selected = selected;
    server.contextDidChange();
    await sleep(2);
  }
  await until(() => stream.notices().length === 2, "the last change's notice");
  await settle();
  assert.equal(stream.notices().length, 2);
  const [, first, second] = stream.arrived;
  assert.ok(first !== undefined && second !== undefined);
  // A few milliseconds are allowed for the two clocks: the server's timer and this reader.
  assert.ok(second - first >= coalesce - 10, `two notices ${second - first} ms apart`);
  // Told of the last change, a host reads the last state.
  assert.equal((await read(descriptor))["root"].children[0].selected, true);
});

test("aChangeInHoveredAloneProducesNoNotice", async (t) => {
  const { descriptor, server, notes } = await started(t);
  await read(descriptor);
  const stream = await watch(t, descriptor);

  for (const hovered of ["note-2", "note-3", undefined, "note-1"]) {
    notes.hovered = hovered;
    server.contextDidChange();
    await settle();
  }
  assert.equal(stream.notices().length, 0);
  // The read still carries it, and reading a hovered tree owes no notice either.
  assert.equal((await read(descriptor))["root"].children[0].hovered, true);
  notes.hovered = "note-2";
  server.contextDidChange();
  await settle();
  assert.equal(stream.notices().length, 0);

  // A real change with the pointer somewhere new is one notice.
  notes.selected = "note-3";
  notes.hovered = "note-3";
  server.contextDidChange();
  await until(() => stream.notices().length === 1, "the notice");
});

test("anUnchangedTreeProducesNoNotice", async (t) => {
  const { descriptor, server, notes } = await started(t);
  await read(descriptor);
  const stream = await watch(t, descriptor);

  server.contextDidChange();
  await settle();
  server.contextDidChange();
  await settle();
  assert.equal(stream.notices().length, 0);

  // A host that has already read the new answer is not told of it.
  notes.selected = "note-2";
  await read(descriptor);
  server.contextDidChange();
  await settle();
  assert.equal(stream.notices().length, 0);

  // Changed and changed back before the answer is computed: nothing to tell.
  notes.selected = "note-3";
  server.contextDidChange();
  notes.selected = "note-2";
  server.contextDidChange();
  await settle();
  assert.equal(stream.notices().length, 0);
});

test("withNoWatchOpenNothingIsComputed", async (t) => {
  const { descriptor, server, notes } = await started(t);
  await read(descriptor);
  const asked = notes.asked;
  for (let turn = 0; turn < 50; turn += 1) server.contextDidChange();
  await settle();
  assert.equal(notes.asked, asked);

  // With one, a burst is computed once, and never on a timer of its own.
  const stream = await watch(t, descriptor);
  for (let turn = 0; turn < 50; turn += 1) server.contextDidChange();
  await settle();
  assert.equal(notes.asked, asked + 1);
  assert.equal(stream.notices().length, 0);
});

test("everyWatchIsToldWithItsOwnId", async (t) => {
  const { descriptor, server, notes } = await started(t);
  await read(descriptor);
  const one = await watch(t, descriptor, { id: 7 });
  const two = await watch(t, descriptor, { id: "second" });
  assert.equal(server._watchCount, 2);

  notes.selected = "note-2";
  server.contextDidChange();
  await until(() => one.notices().length === 1 && two.notices().length === 1, "both notices");
  assert.equal(one.notices()[0]?.["params"]._meta[subscriptionID], 7);
  assert.equal(two.notices()[0]?.["params"]._meta[subscriptionID], "second");
});

test("aProviderThatThrowsSendsNoNoticeAndKeepsTheWatch", async (t) => {
  const { descriptor, server, notes } = await started(t);
  await read(descriptor);
  const stream = await watch(t, descriptor);
  const current = notes.current.bind(notes);
  notes.current = () => { throw new Error("no window"); };
  server.contextDidChange();
  await settle();
  assert.equal(stream.notices().length, 0);
  assert.equal(stream.ended(), false);

  notes.current = current;
  notes.selected = "note-2";
  server.contextDidChange();
  await until(() => stream.notices().length === 1, "the notice");
});

// MARK: - Quiet watches and how a watch ends

test("aQuietWatchCarriesKeepAliveComments", async (t) => {
  const { descriptor, server, notes } = await started(t, { keepAlive: 25 });
  await read(descriptor);
  const stream = await watch(t, descriptor);
  const comments = (): number => stream.raw().split("\n\n").filter((event) => event === ": keep-alive").length;
  await until(() => comments() >= 3, "three keep-alive comments");
  // Comments are not messages, and the watch still works after them.
  assert.equal(stream.events.length, 1);
  notes.selected = "note-2";
  server.contextDidChange();
  await until(() => stream.notices().length === 1, "the notice");
  assert.equal(stream.ended(), false);
});

test("stopEndsEveryWatchWithTheCompletionResult", async (t) => {
  const { descriptor, server } = await started(t);
  const one = await watch(t, descriptor, { id: 7 });
  const two = await watch(t, descriptor, { id: "second" });
  server.stop();
  await until(() => one.ended() && two.ended(), "both streams to end");
  assert.deepEqual(one.events.at(-1), {
    jsonrpc: "2.0", id: 7, result: { resultType: "complete", _meta: { [subscriptionID]: 7 } },
  });
  assert.deepEqual(two.events.at(-1), {
    jsonrpc: "2.0", id: "second", result: { resultType: "complete", _meta: { [subscriptionID]: "second" } },
  });
  assert.equal(one.events.length, 2);
  assert.equal(server._watchCount, 0);
  // Stopped, a change is nothing.
  server.contextDidChange();
});

test("closingTheConnectionRemovesTheWatch", async (t) => {
  const { descriptor, server, notes } = await started(t);
  await read(descriptor);
  const gone = await watch(t, descriptor);
  const kept = await watch(t, descriptor, { id: 8 });
  assert.equal(server._watchCount, 2);

  gone.close();
  await until(() => server._watchCount === 1, "the watch to be removed");
  notes.selected = "note-2";
  server.contextDidChange();
  await until(() => kept.notices().length === 1, "the notice on the watch that is left");

  kept.close();
  await until(() => server._watchCount === 0, "the last watch to be removed");
  const asked = notes.asked;
  notes.selected = "note-3";
  server.contextDidChange();
  await settle();
  assert.equal(notes.asked, asked);
});

test("aNinthWatchEndsTheOldest", async (t) => {
  const { descriptor, server, notes } = await started(t);
  await read(descriptor);
  const streams: Stream[] = [];
  for (let id = 1; id <= 9; id += 1) streams.push(await watch(t, descriptor, { id }));
  const [oldest, ...rest] = streams;
  assert.ok(oldest);
  await until(oldest.ended, "the oldest watch to end");
  assert.deepEqual(oldest.events.at(-1), {
    jsonrpc: "2.0", id: 1, result: { resultType: "complete", _meta: { [subscriptionID]: 1 } },
  });
  assert.equal(server._watchCount, 8);
  assert.ok(rest.every((stream) => !stream.ended()));

  notes.selected = "note-2";
  server.contextDidChange();
  await until(() => rest.every((stream) => stream.notices().length === 1), "a notice on each of the eight");
  assert.equal(oldest.notices().length, 0);
});

test("aChangeBetweenTheReadAndTheWatchIsToldWhenTheWatchOpens", async (t) => {
  const { descriptor, server, notes } = await started(t);
  await read(descriptor);
  // No watch is open yet, so this call does nothing.
  notes.selected = "note-2";
  server.contextDidChange();

  const stream = await watch(t, descriptor);
  await until(() => stream.notices().length === 1, "the notice for the change before the watch");
  assert.equal((stream.events[0] as JSONObject)["method"], "notifications/subscriptions/acknowledged");
});
