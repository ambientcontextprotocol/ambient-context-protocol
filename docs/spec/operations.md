# Ambient Context Protocol · Operations

> Part of the [specification](index.md), version `0.2.2`.

## 4. Operations

The protocol has three operations: two reads, and a watch on the first of them. This section defines them apart from any carrier; [section 7](binding.md#7-the-mcp-binding) says how MCP carries them.

The host's application code performs them, not the model: the host reads `current` when the user invokes the agent, reads `locate` when it needs to place something, and may watch `current` while it is showing the user what it read. This is why the MCP binding uses resources, which MCP defines as application-driven, and not tools, which it defines as model-controlled.

### 4.1 — current

Asks what the user has open and what they are pointing at, right now. Takes no input.

Result, an object with these fields and no others:

| Field | Type | Required | Meaning |
|---|---|---|---|
| `protocol` | string | yes | The version of this protocol the answer follows: `"0.2.2"`. The same value as in the descriptor and the extension declaration ([section 10](versioning.md#10-versioning)). |
| `instance` | string | yes | A random value the provider mints each time it starts. It identifies this run of the provider. See [ids and instances](elements.md#54--ids-and-instances). |
| `root` | [element](elements.md#5-elements) | yes | The app, as an element with role `Application`. Everything the provider reports is inside it. |
| `display` | object | no | The app's own words for what this answer holds, for the host to show the user. See [4.3](#43--display). |

The app's name is the root's `title`. Its identifier is in the descriptor ([section 8](discovery.md#8-discovery)), not in the answer.

The result's shape is also given as a JSON Schema, [`schema/current-0.2.2.json`](../../schema/current-0.2.2.json). The schema checks what a schema can; unique ids, the focus path and the single hovered element are rules of [section 5](elements.md#5-elements) it cannot state.

What the user is pointing at is not a separate field. It is stated on the elements themselves, as the states `selected`, `focused` and `hovered` ([5.3](elements.md#53--states)).

### 4.2 — locate

Asks where an element is on screen.

Input:

| Field | Type | Required | Meaning |
|---|---|---|---|
| `id` | string | yes | An element id the provider returned earlier. |

The result is a [location](locations.md#6-locations). An id the provider issued and whose element no longer exists is not an error: the provider answers with `state: "gone"`. An id the provider never issued in this run is an error.

Whether an element can be located is asked, not declared in advance. A provider that cannot place a particular element answers as it does for an id it never issued, and the host carries on without the placement. A provider that cannot report positions at all does not offer the operation ([7.3](binding.md#73--the-two-resources)).

### 4.3 — display

A host shows the user which context will go with a message ([9.2](security.md#92--for-hosts)). `display` lets the app word that line, as a web page's title and description word the card a site draws for a link to it. It is optional. A provider with nothing particular to say leaves it out, and the host words the line itself from the tree.

```json
"display": { "title": "release-runbook.md", "detail": "lines 12–18" }
```

| Field | Type | Required | Meaning |
|---|---|---|---|
| `title` | string | no | What is open: the document, the view, the thread. |
| `detail` | string | no | What is selected or in focus within it: `lines 12–18`, `3 tasks`, a row's name. |

Rules for a provider:

- Each string is plain text on one line: no markup, no line breaks. It is written for a person, in the app's own nouns.
- Each is 80 characters or fewer.
- `display` describes the same moment and the same tree as the answer it is in. It names nothing the tree does not hold ([9.1](security.md#91--for-providers)).
- It is sent on every answer it applies to, because it changes with the selection. It is not in the descriptor.

Rules for a host:

- A host uses `display` only when `title` is a non-empty string. A `detail` with no `title` is ignored.
- A `display` that is not an object, or a `title` or `detail` that is not a string, is read as absent. The rest of the answer is used as if it were not there: a malformed `display` is never a reason to refuse an answer.
- A host draws the strings as plain text, cuts each to one line and to a length of its choosing, and removes control characters. It does not interpret markup or links in them.
- `display` is a label for the user. It is not the context: what goes to the agent is the tree, and a host that lets the user inspect what will be sent shows the tree.

The picture a host may draw beside these words is not in the answer. It is a file the app ships ([8.2](discovery.md#82--the-apps-favicon)).

### 4.4 — watch

Asks the provider to say when its answer to `current` changes. Takes no input. It is optional for a provider, and a host works without it.

A host that shows the user what it read ([9.2](security.md#92--for-hosts)) is showing a moment that passes: the user selects something else in the app and the line still names the old selection. `watch` lets the host keep that line true without asking again and again. The provider says only that the answer changed. The host then reads `current` as it always does.

The operation has no result while it lasts. For as long as it is open, the provider sends a notice each time its answer to `current` would differ from the one it last gave to a read or last announced. A notice carries no content: nothing of the tree, nothing of `display`, not what changed. The operation ends when the host ends it, when the provider ends it, or when the connection between them is lost.

**What counts as a change.** Anything that would alter the answer to `current`, `display` included, with one exception: a change in `hovered` alone is not a change. The pointer moves constantly, and a notice for each movement would report the user's attention and little else. A host that wants the pointer's state reads it when the user acts.

**The order of things.** A host reads `current` on the user's action, then opens the watch. If the answer changed between that read and the watch opening, the provider says so as soon as the watch is open, so the host never needs to read twice to be sure.

Rules for a provider are in [9.1](security.md#91--for-providers): it gathers changes into at most one notice in any 250 milliseconds, never drops the last one, and learns of changes from the app's own events. Rules for a host are in [9.2](security.md#92--for-hosts): one watch, on the provider it has just read, only while it is showing that provider's context. How MCP carries the operation is in [7.7](binding.md#77--watching).
