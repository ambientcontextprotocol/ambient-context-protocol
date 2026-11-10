import assert from "node:assert/strict";
import { existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { request as httpRequest } from "node:http";
import { connect } from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import type { TestContext } from "node:test";

import { createServer } from "node:http";
import type { AddressInfo } from "node:net";

import { ContextContent, ContextDescriptor, ContextResponder, ContextServer, ContextTree, contextRoles } from "../src/index.ts";
import type { ContextElement, ContextHTTPRequest, ContextProvider, ContextValue } from "../src/index.ts";

// The package as an app uses it: only the public interface, over a real
// socket, found through the descriptor file as a host finds it. Ported
// from the Swift package's `PublicInterfaceTests.swift` at draft 0.1 and
// carried to version 0.2.0; the tests after the first three are this
// package's own.

type JSONObject = Record<string, any>;

const notes: ContextProvider = {
  current: () => ({
    id: "app", role: "Application", title: "Notes",
    children: [{ id: "w-1", role: "Window", focused: true, children: [
      { id: "note-1", role: "Document", subrole: "note", title: "Groceries", focused: true, content: [ContextContent.text("Eggs, rice")] },
    ] }],
  }),
};

const locatedNotes: ContextProvider = {
  // A provider may answer with a promise.
  current: async () => ({
    id: "app", role: "Application",
    children: [{ id: "note-1", role: "Document", subrole: "note", title: "Groceries", focused: true }],
  }),
  locate: (id) => (id === "note-1" ? { id, state: "visible", rects: [{ x: 10, y: 20, w: 300, h: 40 }] } : undefined),
};

interface Started {
  server: ContextServer;
  descriptor: ContextDescriptor;
  file: string;
  directory: string;
}

async function started(t: TestContext, provider: ContextProvider): Promise<Started> {
  const directory = join(mkdtempSync(join(tmpdir(), "acp-")), "providers");
  const app = { id: "org.example.notes", name: "Notes", version: "1.0" };
  const server = new ContextServer({ provider, app, directory });
  t.after(() => {
    server.stop();
    rmSync(join(directory, ".."), { recursive: true, force: true });
  });
  await server.start();
  const file = join(directory, ContextDescriptor.fileName(app.id, process.pid));
  const descriptor = JSON.parse(readFileSync(file, "utf8")) as ContextDescriptor;
  return { server, descriptor, file, directory };
}

interface Answer {
  status: number;
  headers: Record<string, string | string[] | undefined>;
  body: string;
}

function post(endpoint: string, headers: Record<string, string>, body: string, method = "POST"): Promise<Answer> {
  return new Promise((resolve, reject) => {
    const outgoing = httpRequest(endpoint, { method, headers: { ...headers, "Content-Length": Buffer.byteLength(body) } }, (incoming) => {
      const chunks: Buffer[] = [];
      incoming.on("data", (chunk: Buffer) => chunks.push(chunk));
      incoming.on("end", () => resolve({
        status: incoming.statusCode ?? 0, headers: incoming.headers, body: Buffer.concat(chunks).toString("utf8"),
      }));
    });
    outgoing.on("error", reject);
    outgoing.end(body);
  });
}

function message(method: string, uri?: string): { headers: Record<string, string>; body: string } {
  const params: JSONObject = {
    _meta: {
      "io.modelcontextprotocol/protocolVersion": "2026-07-28",
      "io.modelcontextprotocol/clientCapabilities": {},
    },
  };
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "MCP-Protocol-Version": "2026-07-28",
    "Mcp-Method": method,
  };
  if (uri !== undefined) {
    params["uri"] = uri;
    headers["Mcp-Name"] = uri;
  }
  return { headers, body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }) };
}

async function call(descriptor: ContextDescriptor, method: string, uri?: string): Promise<JSONObject> {
  const { headers, body } = message(method, uri);
  const answer = await post(descriptor.endpoint, { ...headers, Authorization: `Bearer ${descriptor.token}` }, body);
  return JSON.parse(answer.body);
}

function documentOf(answer: JSONObject): JSONObject {
  const text = answer["result"]?.contents?.[0]?.text;
  assert.equal(typeof text, "string");
  return JSON.parse(text);
}

test("attributesAreWrittenAsLiterals", async (t) => {
  const attributes: { [key: string]: ContextValue } = {
    ref: "T-12", done: false, order: 3, weight: 0.5,
    tags: ["home", "week"], lines: { start: 3, end: 4 },
    author: "Ada", related: [{ relation: "blocks", id: "task-2" }, { relation: "source", url: "https://example.org/list" }],
  };
  const task: ContextElement = { id: "task-1", role: "Row", subrole: "task", title: "Shop", attributes };
  const root: ContextElement = { id: "app", role: "Application", children: [task, { id: "task-2", role: "Row", subrole: "task" }] };
  const { descriptor } = await started(t, { current: () => root });
  const current = documentOf(await call(descriptor, "resources/read", "ambient://current"));
  assert.deepEqual(current["root"].children[0].attributes, attributes);
  // An element with nothing in focus, selected or hovered says none of them.
  assert.deepEqual(Object.keys(current["root"].children[1]).sort(), ["id", "role", "subrole"]);
});

test("theRoleLanguageIsThirteenWords", () => {
  assert.equal(contextRoles.length, 13);
  assert.equal(new Set(contextRoles).size, 13);
  for (const role of contextRoles) assert.match(role, /^[A-Z][a-z]+$/);
});

test("aProviderThatOnlySaysWhatIsOpen", async (t) => {
  const { server, descriptor, file } = await started(t, notes);
  assert.equal(descriptor.pid, process.pid);
  assert.equal(server.isRunning, true);

  const current = documentOf(await call(descriptor, "resources/read", "ambient://current"));
  assert.equal(current["instance"], descriptor.instance);
  assert.equal(current["protocol"], "0.2.0");
  assert.equal(current["root"].role, "Application");
  assert.equal(current["root"].children[0].children[0].title, "Groceries");
  assert.deepEqual(ContextTree.check(current["root"]), []);

  const templates = await call(descriptor, "resources/templates/list");
  assert.deepEqual(templates["result"].resourceTemplates, []);

  const location = await call(descriptor, "resources/read", "ambient://location/note-1");
  assert.equal(location["error"].code, -32602);

  server.stop();
  assert.equal(existsSync(file), false);
  assert.equal(server.isRunning, false);
});

test("aProviderThatAlsoSaysWhere", async (t) => {
  const { server, descriptor } = await started(t, locatedNotes);
  const templates = await call(descriptor, "resources/templates/list");
  assert.equal(templates["result"].resourceTemplates.length, 1);

  const location = documentOf(await call(descriptor, "resources/read", "ambient://location/note-1"));
  assert.equal(location["state"], "visible");
  assert.deepEqual(location["rects"], [{ x: 10, y: 20, w: 300, h: 40 }]);
  server.stop();
});

// MARK: - The listener and the descriptor, which Swift's tests leave to the two above

test("theDescriptorNamesALoopbackListenerThatIsAlreadyUp", async (t) => {
  const { server, descriptor, file, directory } = await started(t, notes);
  assert.match(descriptor.endpoint, /^http:\/\/127\.0\.0\.1:[0-9]+\/mcp$/);
  assert.equal(server.endpoint?.href, descriptor.endpoint);
  assert.equal(server.token, descriptor.token);
  assert.equal(server.instance, descriptor.instance);
  assert.equal(descriptor.protocol, "0.2.0");
  assert.match(descriptor.started, /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$/);
  assert.equal(statSync(directory).mode & 0o777, 0o700);
  assert.equal(statSync(file).mode & 0o777, 0o600);
  assert.deepEqual(readdirSync(directory), [ContextDescriptor.fileName("org.example.notes", process.pid)]);

  // Stopped, the port no longer answers; started again, the run is new.
  const before = { ...descriptor };
  server.stop();
  assert.equal(server.endpoint, undefined);
  await assert.rejects(call(before, "resources/list"));
  await server.start();
  assert.notEqual(server.token, before.token);
  assert.notEqual(server.instance, before.instance);
  assert.equal(existsSync(file), true);
});

test("aLeftoverDescriptorOfThisAppIsRemovedAtStart", async (t) => {
  const directory = join(mkdtempSync(join(tmpdir(), "acp-")), "providers");
  t.after(() => rmSync(join(directory, ".."), { recursive: true, force: true }));
  const app = { id: "org.example.notes", name: "Notes", version: "1.0" };
  // Stand in for a crashed run: a descriptor naming a process that is gone.
  mkdirSync(directory, { recursive: true });
  writeFileSync(join(directory, ContextDescriptor.fileName(app.id, 99_999_999)), "{}");

  const server = new ContextServer({ provider: notes, app, directory });
  t.after(() => server.stop());
  await server.start();
  assert.deepEqual(readdirSync(directory), [ContextDescriptor.fileName(app.id, process.pid)]);
});

test("refusalsHoldOverTheSocket", async (t) => {
  const { descriptor } = await started(t, notes);
  const { headers, body } = message("resources/list");
  const authorized = { ...headers, Authorization: `Bearer ${descriptor.token}` };

  const origin = await post(descriptor.endpoint, { ...authorized, Origin: "http://localhost:3000" }, body);
  assert.equal(origin.status, 403);
  assert.equal(origin.body, "");

  const wrong = await post(descriptor.endpoint, { ...headers, Authorization: "Bearer wrong" }, body);
  assert.equal(wrong.status, 401);
  assert.equal(wrong.headers["www-authenticate"], "Bearer");
  assert.equal((await post(descriptor.endpoint, headers, body)).status, 401);

  const get = await post(descriptor.endpoint, authorized, "", "GET");
  assert.equal(get.status, 405);
  assert.equal(get.headers["allow"], "POST");

  const ok = await post(descriptor.endpoint, authorized, body);
  assert.equal(ok.status, 200);
  assert.equal(ok.headers["connection"], "close");
  assert.equal(ok.headers["content-type"], "application/json");
});

test("aBodyOverTheLimitIsRefusedOverTheSocket", async (t) => {
  const { descriptor } = await started(t, notes);
  const port = Number(new URL(descriptor.endpoint).port);
  const raw = (text: string): Promise<string> => new Promise((resolve, reject) => {
    const socket = connect(port, "127.0.0.1", () => socket.write(text));
    const chunks: Buffer[] = [];
    socket.on("data", (chunk: Buffer) => chunks.push(chunk));
    socket.on("close", () => resolve(Buffer.concat(chunks).toString("utf8")));
    socket.on("error", reject);
  });
  const large = await raw(`POST /mcp HTTP/1.1\r\nAuthorization: Bearer ${descriptor.token}\r\nContent-Length: ${1024 * 1024 + 1}\r\n\r\n`);
  assert.ok(large.startsWith("HTTP/1.1 413 Content Too Large\r\n"));
  const malformed = await raw("nonsense\r\n\r\n");
  assert.ok(malformed.startsWith("HTTP/1.1 400 Bad Request\r\n"));
});

test("aProviderThatThrowsIsAnErrorNotACrash", async (t) => {
  const { descriptor } = await started(t, { current: () => { throw new Error("no window"); } });
  const answer = await call(descriptor, "resources/read", "ambient://current");
  assert.equal(answer["error"].code, -32603);
  assert.equal((await call(descriptor, "resources/list"))["result"].resources.length, 1);
});

// MARK: - On a server the app already has (RFC-0002)

test("anAppWithItsOwnServerMountsTheResponderAndWritesTheDescriptor", async (t) => {
  const directory = join(mkdtempSync(join(tmpdir(), "acp-")), "providers");
  const app = { id: "org.example.editor", name: "Editor", version: "3.0" };
  const token = ContextServer.random(32), instance = ContextServer.random(6);
  const responder = new ContextResponder({ app, instance, token, path: "/ambient", current: () => notes.current() });

  // The app's server: its own routes answer as before, and one path is
  // handed to the responder before anything else looks at it.
  const server = createServer((incoming, outgoing) => {
    const chunks: Buffer[] = [];
    incoming.on("data", (chunk: Buffer) => chunks.push(chunk));
    incoming.on("end", () => {
      const path = (incoming.url ?? "/").split("?")[0] ?? "/";
      if (path !== "/ambient") {
        outgoing.writeHead(200, { "Access-Control-Allow-Origin": "*" }).end("the app's own route");
        return;
      }
      const headers = new Map<string, string>();
      for (const [name, value] of Object.entries(incoming.headers)) {
        if (value !== undefined) headers.set(name, Array.isArray(value) ? value.join(", ") : value);
      }
      const request: ContextHTTPRequest = { method: incoming.method ?? "", path, headers, body: Buffer.concat(chunks) };
      void responder.respond(request).then((answer) => outgoing.writeHead(answer.status, answer.headers).end(answer.body));
    });
  });
  await new Promise<void>((resolve) => server.listen({ host: "127.0.0.1", port: 0 }, resolve));
  const port = (server.address() as AddressInfo).port;
  const file = ContextDescriptor.write({
    protocol: ContextResponder.protocolVersion, app, pid: process.pid, instance, token,
    endpoint: `http://127.0.0.1:${port}/ambient`, started: new Date().toISOString().replace(/\.\d+Z$/, "Z"),
  }, directory);
  t.after(() => {
    server.close();
    rmSync(join(directory, ".."), { recursive: true, force: true });
  });

  // A host finds it as it finds any provider.
  const descriptor = JSON.parse(readFileSync(file, "utf8")) as ContextDescriptor;
  assert.equal(descriptor.endpoint, `http://127.0.0.1:${port}/ambient`);
  assert.equal(statSync(file).mode & 0o777, 0o600);
  const current = documentOf(await call(descriptor, "resources/read", "ambient://current"));
  assert.equal(current["root"].children[0].children[0].title, "Groceries");

  // The rules hold on that path whatever the rest of the server does.
  const { headers, body } = message("resources/list");
  const authorized = { ...headers, Authorization: `Bearer ${token}` };
  const answers = [
    await post(descriptor.endpoint, headers, body),
    await post(descriptor.endpoint, { ...authorized, Origin: "http://localhost:3000" }, body),
    await post(descriptor.endpoint, { Origin: "http://localhost:3000", "Access-Control-Request-Method": "POST" }, "", "OPTIONS"),
    await post(descriptor.endpoint, authorized, body),
  ];
  assert.deepEqual(answers.map((answer) => answer.status), [401, 403, 403, 200]);
  for (const answer of answers) {
    assert.deepEqual(Object.keys(answer.headers).filter((name) => name.startsWith("access-control-")), []);
  }
  // The app's other routes are untouched, and need no token.
  const other = await post(`http://127.0.0.1:${port}/`, {}, "", "GET");
  assert.equal(other.body, "the app's own route");
});
