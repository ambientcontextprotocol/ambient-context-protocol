# Ambient Context for TypeScript

Makes a desktop app built on Node, such as an Electron app, a provider of the Ambient Context Protocol, version 0.2.4: it runs the local server, answers the protocol's requests and keeps the descriptor file a host finds the app by. The app writes one thing, a tree of what the user has open and selected.

Version 0.2.4 is the [specification](../../docs/spec/index.md), shaped by seven accepted proposals: [the element model](../../docs/rfcs/0001-element-model.md), [the shared listener](../../docs/rfcs/0002-shared-listener.md), [the hovered state](../../docs/rfcs/0003-hovered-state.md), [a provider started by the app it answers for](../../docs/rfcs/0004-a-provider-started-by-the-app.md), [display and the favicon](../../docs/rfcs/0005-display-and-favicon.md), [watching](../../docs/rfcs/0006-watching.md) and [sensitive context](../../docs/rfcs/0007-sensitive-context.md). Discovery, transport and trust are in [discovery](../../docs/spec/discovery.md) and [security](../../docs/spec/security.md).

It uses Node's standard library only and has no dependencies. It is plain TypeScript with no build step: Node 22.18 or later runs the source directly, and a bundler takes it as it is. Like the protocol's discovery, it is for macOS. It began as a port of the [Swift package](../swift/README.md), name for name, and both are at 0.2.4.

## Add it

The package is used by local path for now. Import the source from the app's main process and let the app's bundler compile it:

```ts
import { ContextServer } from "../../ambient-context-protocol/sdk/typescript/src/index.ts";
```

The sources import each other with `.ts` extensions, so a project that type-checks them with `tsc` needs `allowImportingTsExtensions`.

## Say what is open

```ts
import type { ContextProvider } from "ambient-context-provider";

const notesContext: ContextProvider = {
  current() {
    return {
      id: "app", role: "Application", title: "Notes",
      children: [{
        id: "w-1", role: "Window", focused: true,
        children: [{
          id: "note-1", role: "Document", subrole: "note", title: "Groceries", focused: true,
          content: [{ type: "text", text: "Eggs, rice, limes" }],
          children: [{ id: "sel-1", role: "Text", selected: true, content: [{ type: "text", text: "rice" }] }],
        }],
      }],
    };
  },
};
```

`current()` is called each time a host asks, and should answer from state already in memory. It may return the tree or a promise of it. The package adds the protocol version and the run's instance.

Everything is an element, and the root is the application. What an element says about itself:

| Field | Meaning |
|---|---|
| `id` | Letters, digits, hyphens and underscores. Unique in one answer and the same for as long as the thing is shown in this run. It names one appearance: a thread open in two panes is two elements with two ids |
| `role` | How the thing is shown. One of thirteen words, below |
| `subrole` | What the thing is, in the app's own word: `note`, `task`, `thread`, `pane`. Any string |
| `title` | One line a person could read |
| `content` | Text, an image or a link, as MCP content blocks |
| `url` | An address for the thing |
| `selected` | The user selected this |
| `focused` | The keyboard or cursor is here. Mark every element on the way down to where the user is, with no gaps: the window, the document in it, the row in that |
| `hovered` | The pointer is over this. On one element at most, the innermost one reported, and not on what contains it. Leave it out if the app does not track the pointer |
| `visible` | Drawn on screen now. Left out, it is the parent's value. `false` on a tab that is open but not showing |
| `children` | The elements inside this one, in the app's order |
| `attributes` | Anything else, as plain JSON values: `attributes: { ref: "T-12", done: false }`. Two names are reserved: `author`, a string, and `related`, a list of links that are not containment, each with a relation name and another element's `id` or an address |

The roles, spelled exactly so (`contextRoles` lists them):

| Kind | Roles |
|---|---|
| The app and its windows | `Application`, `Window` |
| Containers | `Group`, `List`, `Table` |
| Entries | `Row`, `Cell` |
| Text | `Text`, `Heading`, `Link` |
| Pictures and pages | `Image`, `Page` |
| A whole document | `Document` |

The role says how a thing is shown and the subrole what it is: a task in a list is a `Row` with subrole `task`, and the same task on a board is a `Cell` with subrole `task`. A tab or a pane is a `Window` that says so in its subrole. Selected text is a `Text` with `selected: true`, inside the element it was selected in. When no role plainly fits, use `Group`. Do not report controls, menus or window furniture.

Report what is useful to someone asking about what is in front of the user, not everything the app has loaded. Send `author` only where the app already shows it.

## Serve it

```ts
import { ContextServer } from "ambient-context-provider";

const server = new ContextServer({
  provider: notesContext,
  app: { id: "org.example.notes", name: "Notes", version: "1.0" },
});
await server.start();   // when the user turns the feature on
server.stop();          // when they turn it off, and when the app is about to quit
```

`start()` returns a promise that resolves once the listener is up and the descriptor is written; `endpoint`, `token`, `instance` and `isRunning` say what is running. `app.id` is the app's identifier on its platform (on macOS, its bundle identifier), which the caller supplies: an Electron app in development runs under Electron's bundle and not its own. A third option, `directory`, puts the descriptor somewhere other than `ContextDescriptor.defaultDirectory`, for tests.

Three things an app should do around it:

- Keep the feature off until the user turns it on, and say plainly what it does: while it is on, any program running as the user can ask what is open and selected.
- Call `ContextDescriptor.removeStale(bundleID, process.pid, ContextDescriptor.defaultDirectory)` at launch, whether or not the feature is on, so a descriptor left by a crash does not outlive it.
- Call `stop()` before the app exits: in Electron, on `will-quit`. While it runs, the server also removes its descriptor when the process exits normally, but not when it is killed.

## When the tree is wrong

A tree can be wrong in ways a host cannot repair: an id used twice, a root that is not an `Application`, a focused element whose parent is not focused, two elements hovered. Each time it answers, the package checks the tree for the mistakes that can be told from the tree alone, and reports each distinct one once:

```
ambient context: error: element 'c-3': focused, but an element between it and the root is not: the focused path has a gap
```

A role outside the thirteen is a warning, not an error, because a host reads it as `Group`.

The `check` option, on `ContextServer` and `ContextResponder`, says what happens next:

| `check` | What it does |
|---|---|
| `"warn"` (default) | Reports through `report`, which defaults to `console.warn`, and answers anyway |
| `"refuse"` | Also fails the read when an issue is an error. For the app's own tests |
| `"off"` | Does not look |

`ContextTree.check(root)` runs the same check directly and returns the issues, for a unit test of the function that builds the tree.

## On a server the app already has

An app that already runs a local server does not need a second port. It mounts the answering part, `ContextResponder`, at a path of its own and writes the descriptor itself:

```ts
import { ContextDescriptor, ContextResponder, ContextServer } from "ambient-context-provider";

const app = { id: "org.example.editor", name: "Editor", version: "3.0" };
const token = ContextServer.random(32);    // new on every launch, for this path only
const instance = ContextServer.random(6);
const responder = new ContextResponder({
  app, instance, token, path: "/ambient",
  current: () => editorContext.current(),
});

// In the app's server, before any other handling of that path:
//   const answer = await responder.respond({ method, path, headers, body });
// `headers` is a Map of values by lowercased name, `body` a Buffer.
// Send answer.status, answer.headers and answer.body as they are.

// Once the listener is up:
const file = ContextDescriptor.write({
  protocol: ContextResponder.protocolVersion, app, pid: process.pid, instance, token,
  endpoint: `http://127.0.0.1:${port}/ambient`,
  started: new Date().toISOString().replace(/\.\d+Z$/, "Z"),
}, ContextDescriptor.defaultDirectory);
// At quit, or when the user turns the feature off: remove `file`.
```

The responder refuses any request that carries an `Origin` header, a preflight included, and any without the token, before it looks at anything else. What stays with the app, because the package cannot see it:

- *The listener is on `127.0.0.1` only.* A server bound to all interfaces must not carry this path: the token would be all that stands between the user's selection and the local network.
- *Nothing adds cross-origin headers to this path.* A framework that puts `Access-Control-Allow-Origin` on every response, or answers every preflight itself, undoes the refusal, and a test with a client that is not a browser will not show it. Route the path to the responder before such middleware.
- *The token is used nowhere else.* It is written to the descriptor file, so it must not be a credential the server accepts for anything but this path.
- *Neither the token nor a response's body is logged.* The body is what the user has selected.

## Word the line a host shows

A host shows the user what it read before anything is sent: a small picture, what is open, what is selected. Left alone, it words that line itself from the tree. An app can word it better, in its own nouns, with one more function:

```ts
const notesContext: ContextProvider = {
  current() { /* the tree */ },
  display() {
    return { title: "Groceries", detail: "1 word" };
  },
};
```

`title` is what is open and `detail` is what is selected or in focus within it. Both are plain text; the package puts each on one line and cuts it at 80 characters, and sends nothing when there is no `title`. `display()` is called straight after `current()` and must describe the same tree: it names nothing the tree does not hold. Return nothing to let the host word the line.

The picture is not sent. Ship it as a file in the app, `Contents/Resources/favicon.svg` in the bundle on macOS, or `favicon.png` (at least 32 by 32 pixels) when there is no SVG. The host finds it there itself. Draw a simple shape in one light color: it is shown at about 16 points, often on a dark surface. In an Electron app, add the file to the packager's extra resources so that it lands directly in `Contents/Resources`.

## Say that it is sensitive (optional)

An app that mostly shows private things, such as mail, messages or a bank's pages, can say so, and a host then asks the user before sending that context to an agent ([RFC-0007](../../docs/rfcs/0007-sensitive-context.md)). One more function:

```ts
const mailContext: ContextProvider = {
  current() { /* the tree */ },
  sensitive() {
    return true;
  },
};
```

When it answers `true`, the answer to `current` carries `"sensitive": true`. When it answers anything else, or the function is left out, the field is not sent: the package never sends `false`, because no mark does not mean safe. It is called straight after `current()` and describes the same tree, so an app can mark some views and not others. With a `ContextResponder`, pass `sensitive` beside `current`. A helper that answers for another app marks its answer the same way.

Marking is not redacting. Removing or masking private details inside what `current()` reports is the provider's job: the app knows which of its content is private, and it reports only what should leave it. No host is required to inspect or clean an answer, and a host written before 0.2.4 ignores the mark, so what should never be reported is still left out of the tree.

## Say when it changes (optional)

A host reads the context once, when the user asks for it, and shows the user what it read. A watch is one request the host then holds open while that line is on screen, on which the provider says "changed", with no content, so the host can read again and the line stays true.

The package holds the watch. The app adds one call, wherever what `current()` would answer may have changed:

```ts
server.contextDidChange();
```

In an Electron app the tree is usually built from state the renderer owns, so the call comes from the renderer's own events, relayed to the main process where the server runs: the selection changed, the focus moved, the user navigated, a document, tab or window opened or closed.

```ts
// Renderer, through the preload script's bridge:
document.addEventListener("selectionchange", () => bridge.contextChanged());

// Main process:
ipcMain.on("context-changed", () => server.contextDidChange());
win.on("focus", () => server.contextDidChange());
win.webContents.on("did-navigate-in-page", () => server.contextDidChange());
```

Update the state `current()` answers from before making the call, or in the same turn. If `display()` words the line from something the tree does not show, make the call when that changes too.

Calling often is fine. With no host watching, the call does nothing. With one, the package waits out a burst (at most one notice in 250 milliseconds, and the last change always gets one), then asks for `current()` and `display()` and sends the notice only if that answer differs from the one the host last read or was last told of. A call with nothing changed sends nothing.

The pointer needs no call. A change in `hovered` alone is not a change a host is told of, and a call made for one sends nothing; the next read carries the hovered element as always.

A place the app forgets is a line that goes stale with no error anywhere, so do not make up for one by calling on a timer: that is polling moved into the app. The package holds at most eight watches and ends them all at `stop()`.

Only `ContextServer` offers this. A `ContextResponder` on the app's own server does not offer it yet: it answers a watch request as a method it does not have, and a host falls back to reading when the user asks.

## Say where it is (optional)

A provider that can report where an element is on screen also has `locate`. A host can then place its own interface beside it.

```ts
const notesContext: ContextProvider = {
  current() { /* as above */ },
  locate(id) {
    const frame = screenFrame(id);
    if (!frame) return undefined;
    return { id, state: "visible", rects: [frame], edge: "right" };
  },
};
```

Return nothing for an id this run never issued, and `ContextLocation.gone(id)` for an element that was issued and no longer exists. Rectangles are in global display coordinates: points, origin at the top left of the primary display, y increasing downward. Elements do not declare in advance whether they can be located; a host asks. A provider without `locate` offers no location resource, and nothing else changes.

## For an app that started this program

A helper an app starts, such as a browser's native-messaging host, can answer for that app ([RFC-0004](../../docs/rfcs/0004-a-provider-started-by-the-app.md)). Pass `answersFor` with the app's identifier and process id, which must be this process's parent; `app` then names the helper. Put `via` on the root, such as `browser-extension`, and call `contextDidChange()` only if the app tells the helper of changes.

```ts
const server = new ContextServer({
  provider,
  app: { id: "org.example.helper", name: "Helper", version: "1.0.0" },
  answersFor: { id: "com.google.Chrome", pid: process.ppid },
});
```

The descriptor is written as `<app-id>.<app-pid>.for.<pid>.json`. A host accepts it only if the app in front started this process.

## Try it

```sh
npm test                    # the server, the tree check, the descriptor and the public interface over a real socket
node examples/minimal.ts    # a provider a host can find, until Ctrl-C
```

The tests run on the source with `node --test` and keep their descriptors in a temporary folder.

The package has no dependencies, development ones included, so it carries no TypeScript compiler. To type-check it, run a `tsc` you already have against its own settings, pointing it at a folder that holds `@types/node`:

```sh
/path/to/node_modules/.bin/tsc -p . --typeRoots /path/to/node_modules/@types
```
