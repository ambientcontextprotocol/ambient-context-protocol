// The smallest provider: a notes app with one window, one note open and a
// few words selected in it. Run it, and a host that looks for
// `org.example.notes` finds it; stop it with Ctrl-C and the descriptor
// goes with it.
//
//   node examples/minimal.ts            the real descriptor folder
//   node examples/minimal.ts /tmp/acp   a folder of your choosing
import { ContextServer } from "../src/index.ts";
import type { ContextElement, ContextProvider } from "../src/index.ts";

const notes: ContextProvider = {
  current(): ContextElement {
    return {
      id: "app", role: "Application", title: "Notes",
      children: [{
        id: "w-1", role: "Window", title: "Groceries", focused: true,
        children: [{
          id: "note-1", role: "Document", subrole: "note", title: "Groceries", focused: true,
          url: "file:///Users/ada/notes/groceries.md",
          content: [{ type: "text", text: "Eggs, rice, limes" }],
          children: [{ id: "sel-1", role: "Text", selected: true, content: [{ type: "text", text: "rice" }] }],
        }],
      }],
    };
  },
};

const directory = process.argv[2];
const server = new ContextServer({
  provider: notes,
  app: { id: "org.example.notes", name: "Notes", version: "1.0" },
  ...(directory ? { directory } : {}),
});
await server.start();
if (!server.isRunning) {
  console.error("the listener did not open");
  process.exit(1);
}
console.log(`answering on ${server.endpoint?.href ?? ""}; Ctrl-C to stop`);

for (const signal of ["SIGINT", "SIGTERM"] as const) {
  process.on(signal, () => {
    server.stop();
    process.exit(0);
  });
}
