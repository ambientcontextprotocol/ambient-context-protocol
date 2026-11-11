# Ambient Context Protocol · Overview

> Part of the [specification](index.md), version `0.1`.

## 1. The problem

An ambient agent is one you can call from anywhere on your computer: press a key, ask a question, get an answer without switching apps.

The question you ask is usually about what is in front of you. "Is this claim true?" "Move this to tomorrow." "Why is this failing?" The agent can't answer unless it knows what "this" is. Today that takes a screenshot, a paste, or a paragraph of explanation.

The app in front already knows the answer. It knows which documents are open, which one has focus and what is selected. It also knows where each of those things is on screen, which matters when the agent wants to show its answer next to the passage and not in a corner of the display.

This protocol is how the app says so. It is deliberately small. It does not describe documents, tasks or layers. It gives every app the same way to say "here is what the user has open, here is what they are pointing at, and here is where it is."

## 2. An example

A user has two Markdown files open in an editor. They select a sentence in one, call the agent, and type "is this claim actually true?"

**Step 1.** The agent's host sees which app is in front, finds that app's descriptor file ([section 8](discovery.md#8-discovery)), and reads the current context from the address the file gives:

```http
POST /mcp HTTP/1.1
Host: 127.0.0.1:53124
Authorization: Bearer q7Jm…
Content-Type: application/json
Accept: application/json, text/event-stream
MCP-Protocol-Version: 2026-07-28
Mcp-Method: resources/read
Mcp-Name: ambient://current

{
  "jsonrpc": "2.0",
  "id": 7,
  "method": "resources/read",
  "params": {
    "uri": "ambient://current",
    "_meta": {
      "io.modelcontextprotocol/protocolVersion": "2026-07-28",
      "io.modelcontextprotocol/clientCapabilities": {}
    }
  }
}
```

**Step 2.** The editor answers. The resource's text is a JSON document:

```json
{
  "jsonrpc": "2.0",
  "id": 7,
  "result": {
    "resultType": "complete",
    "contents": [
      {
        "uri": "ambient://current",
        "mimeType": "application/json",
        "text": "{ \"app\": …, \"instance\": …, \"focus\": …, \"items\": … }"
      }
    ]
  }
}
```

Decoded, the text is:

```json
{
  "app": { "id": "org.example.editor", "name": "Editor" },
  "instance": "k3f9x2",
  "focus": ["sel-23"],
  "items": [
    {
      "id": "doc-1",
      "type": "document",
      "title": "draft.md",
      "url": "file:///Users/ada/essays/draft.md"
    },
    {
      "id": "doc-2",
      "type": "document",
      "title": "notes.md",
      "url": "file:///Users/ada/essays/notes.md"
    },
    {
      "id": "sel-23",
      "type": "selection",
      "parent": "doc-1",
      "title": "Selection in draft.md",
      "content": [
        { "type": "text", "text": "The command line lasted thirty years as the main way people used computers." }
      ],
      "locatable": true,
      "payload": { "lines": [31, 31] }
    }
  ]
}
```

**Step 3.** The host shows the user what it picked up, so they can remove it, and passes it to the agent with the question. How a host words this for its agent is the host's business.

**Step 4.** The agent decides its answer belongs beside the sentence. It tells the host which item, by id: `sel-23`. How an agent says this is also the host's business. The agent never calls the provider. The host remembers which provider, and which run of it, issued `sel-23`.

**Step 5.** The host asks the editor where that item is, by reading `ambient://location/sel-23` the same way as in step 1.

**Step 6.** The editor answers, and the host places its own interface. Decoded:

```json
{
  "id": "sel-23",
  "state": "visible",
  "rects": [{ "x": 425, "y": 233, "w": 480, "h": 20 }],
  "window": 9120,
  "avoid": { "x": 400, "y": 80, "w": 620, "h": 900 },
  "edge": "right"
}
```

The editor never learned what the host showed, and the agent never saw a coordinate.

## 3. Roles and principles

**Provider.** An app that answers these questions about itself: an editor, a task manager, a design tool, a terminal. In MCP's terms it is a server.

**Host.** The ambient agent's own app. It reads from providers, shows the user what it collected, passes context to an agent, and draws its own interface. In MCP's terms it is a client.

**Agent.** The model behind the host. It is not a party to this protocol. It sees whatever the host chooses to pass on.

Four principles shape everything else:

1. *The app says where; the host decides what.* A provider reports items and their positions. It never names what the host draws there.
2. *An envelope, not a domain model.* The protocol fixes a handful of fields every item has. What an item is, and anything specific to it, is the provider's to define. A language model can read any payload, so there is nothing to gain from standardizing "document" or "task."
3. *Pulled on the user's action.* A host asks for context when the user does something that calls for it. A provider does not push, and a host does not poll. Provisional: this holds for version 0.1 and may change.
4. *It is ordinary MCP.* A provider is an MCP server and the two answers are MCP resources. A client that has never heard of this protocol can still list and read them.
