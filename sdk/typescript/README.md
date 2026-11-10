# Ambient Context for TypeScript

Makes a desktop app built on Node, such as an Electron app, a provider of the [Ambient Context Protocol](../../docs/protocol-v0.md), draft 0.1: it runs the local server, answers the protocol's requests and keeps the descriptor file a host finds the app by. The app writes one thing, a description of what the user has open and selected.

It is a port of the [Swift package](../swift/README.md), name for name, and answers every request as that one does. It uses Node's standard library only and has no dependencies. It is plain TypeScript with no build step: Node 22.18 or later runs the source directly, and a bundler takes it as it is. Like the protocol's discovery, it is for macOS.

## Add it

The package is used by local path for now. Import the source from the app's main process and let the app's bundler compile it:

```ts
import { ContextServer } from "../../ambient-context-protocol/sdk/typescript/src/index.ts";
```

The sources import each other with `.ts` extensions, so a project that type-checks them with `tsc` needs `allowImportingTsExtensions`.

## Say what is open

```ts
import type { ContextProvider } from "@ambient-context/provider";

const notesContext: ContextProvider = {
  current() {
    return {
      focus: ["note-1"],
      items: [{ id: "note-1", type: "note", title: "Groceries", content: [{ type: "text", text: "Eggs, rice, limes" }] }],
    };
  },
};
```

An item's `payload` takes plain JSON values: `payload: { ref: "T-12", done: false }`.

`current()` is called each time a host asks, and should answer from state already in memory. It may return its answer or a promise of it. `focus` lists the ids of the items the user is working on now; `items` is everything open. An id is letters, digits, hyphens and underscores, and stays the same for as long as the item exists in this run of the app.

## Serve it

```ts
import { ContextServer } from "@ambient-context/provider";

const server = new ContextServer({
  provider: notesContext,
  app: { id: "org.example.notes", name: "Notes", version: "1.0" },
});
await server.start();   // when the user turns the feature on
server.stop();          // when they turn it off, and when the app is about to quit
```

`start()` returns a promise that resolves once the listener is up and the descriptor is written; `endpoint`, `token`, `instance` and `isRunning` say what is running. `app.id` is the app's bundle identifier, which the caller supplies: an Electron app in development runs under Electron's bundle and not its own. A third option, `directory`, puts the descriptor somewhere other than `ContextDescriptor.defaultDirectory`, for tests.

Three things an app should do around it:

- Keep the feature off until the user turns it on, and say plainly what it does: while it is on, any program running as the user can ask what is open and selected.
- Call `ContextDescriptor.removeStale(bundleID, process.pid, ContextDescriptor.defaultDirectory)` at launch, whether or not the feature is on, so a descriptor left by a crash does not outlive it.
- Call `stop()` before the app exits: in Electron, on `will-quit`. While it runs, the server also removes its descriptor when the process exits normally, but not when it is killed.

## Say where it is (optional)

A provider that can report where an item is on screen also has `locate`. A host can then place its own interface beside the item.

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

Return nothing for an id this run never issued, and `ContextLocation.gone(id)` for an item that was issued and no longer exists. Rectangles are in global display coordinates: points, origin at the top left of the primary display, y increasing downward. Mark an item `locatable: true` in `current()` only if `locate` can answer for it. A provider without `locate` offers no location resource, and nothing else changes.

## Try it

```sh
npm test   # the server, the descriptor and the public interface over a real socket
```

The tests run on the source with `node --test` and keep their descriptors in a temporary folder.
