# Ambient Context Protocol · Operations

> Part of the [specification](index.md), version `0.1`.

## 4. Operations

The protocol has two operations. This section defines them apart from any carrier; [section 7](binding.md#7-the-mcp-binding) says how MCP carries them.

Both are reads. The host's application code performs them, not the model: the host reads `current` when the user invokes the agent, and reads `locate` when it needs to place something. This is why the MCP binding uses resources, which MCP defines as application-driven, and not tools, which it defines as model-controlled.

### 4.1 — current

Asks what the user has open and what they are pointing at, right now. Takes no input.

Result:

| Field | Type | Required | Meaning |
|---|---|---|---|
| `app` | object | yes | `id` (the app's bundle identifier) and `name`. |
| `instance` | string | yes | A random value the provider mints each time it starts. It identifies this run of the provider. See [ids and instances](elements.md#5-items). |
| `items` | array | yes | The [items](elements.md#5-items) currently open or selected. May be empty. |
| `focus` | array of strings | no | The ids of the most specific items the user is pointing at: the selection if there is one, otherwise the front document or view. More than one when several things are selected together. Absent or empty when nothing has focus. |

### 4.2 — locate

Asks where an item is on screen.

Input:

| Field | Type | Required | Meaning |
|---|---|---|---|
| `id` | string | yes | An item id the provider returned earlier. |

The result is a [location](locations.md#6-locations). An id the provider issued and whose item no longer exists is not an error: the provider answers with `state: "gone"`. An id the provider never issued in this run is an error.
