# Ambient Context Protocol · Operations

> Part of the [specification](index.md), version `0.2.0`.

## 4. Operations

The protocol has two operations. This section defines them apart from any carrier; [section 7](binding.md#7-the-mcp-binding) says how MCP carries them.

Both are reads. The host's application code performs them, not the model: the host reads `current` when the user invokes the agent, and reads `locate` when it needs to place something. This is why the MCP binding uses resources, which MCP defines as application-driven, and not tools, which it defines as model-controlled.

### 4.1 — current

Asks what the user has open and what they are pointing at, right now. Takes no input.

Result, an object with exactly these three fields:

| Field | Type | Required | Meaning |
|---|---|---|---|
| `protocol` | string | yes | The version of this protocol the answer follows: `"0.2.0"`. The same value as in the descriptor and the extension declaration ([section 10](versioning.md#10-versioning)). |
| `instance` | string | yes | A random value the provider mints each time it starts. It identifies this run of the provider. See [ids and instances](elements.md#54--ids-and-instances). |
| `root` | [element](elements.md#5-elements) | yes | The app, as an element with role `Application`. Everything the provider reports is inside it. |

The app's name is the root's `title`. Its bundle identifier is in the descriptor ([section 8](discovery.md#8-discovery)), not in the answer.

What the user is pointing at is not a separate field. It is stated on the elements themselves, as the states `selected`, `focused` and `hovered` ([5.3](elements.md#53--states)).

### 4.2 — locate

Asks where an element is on screen.

Input:

| Field | Type | Required | Meaning |
|---|---|---|---|
| `id` | string | yes | An element id the provider returned earlier. |

The result is a [location](locations.md#6-locations). An id the provider issued and whose element no longer exists is not an error: the provider answers with `state: "gone"`. An id the provider never issued in this run is an error.

Whether an element can be located is asked, not declared in advance. A provider that cannot place a particular element answers as it does for an id it never issued, and the host carries on without the placement. A provider that cannot report positions at all does not offer the operation ([7.3](binding.md#73--the-two-resources)).
