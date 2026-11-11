# Ambient Context Protocol · Items

> Part of the [specification](index.md), version `0.1`.

## 5. Items

An item is one thing the user has open or selected.

| Field | Type | Required | Meaning |
|---|---|---|---|
| `id` | string | yes | Short, opaque, made of letters, digits, hyphens and underscores. Unique within one run of one provider, and no further. See below and the lifetime rule in 9.1. |
| `type` | string | yes | A name the provider chooses, such as `document`, `selection`, `task`, `layer`. Hosts use it for grouping and display only. |
| `title` | string | yes | One line a person could read, such as a file name or a task's name. |
| `content` | array of content blocks | no | What the item contains, for the agent to read or see. See below. |
| `url` | string | no | An address for the thing, when it has one: a `file://` URL, a web URL, or a link the app itself opens. |
| `parent` | string | no | The id of the item this one sits inside, such as a selection's document. |
| `locatable` | boolean | no | Whether `locate` can answer for this item. Defaults to `false`. |
| `payload` | object | no | Anything else the provider wants an agent to have. Free-form. |

**Ids and instances.** An id means something only together with the provider that issued it and that provider's `instance`. Two providers may both issue `sel-23`, and a provider that restarts may issue it again for something else. The full name of an item is therefore the provider, its instance and the id. Keeping the three together is the host's job ([9.2](security.md#92--for-hosts)); an agent sees only the id.

A provider decides how much to list. An editor with forty open files might list them all, since each costs one line. A task manager would list the open view and the selected tasks, not its whole database.

**Content blocks.** `content` uses MCP's `ContentBlock` type unchanged, so a host can hand the blocks to an agent without translating them. The block types, as of MCP schema `2026-07-28`:

| `type` | Required fields | Use here |
|---|---|---|
| `text` | `text` | Selected text, or a short description of the item. |
| `image` | `data` (base64), `mimeType` | A small rendering of something visual: a frame, a chart, a region of a canvas. |
| `audio` | `data` (base64), `mimeType` | Rarely needed. |
| `resource_link` | `uri`, `name` | A pointer to the full thing, for the agent to fetch if it needs it. |
| `resource` | `resource` (a `uri` with `text` or `blob`) | The full thing, embedded. |

An item that is text sends a `text` block. An item that is not text sends an image, a link, or both. A selected frame in a design tool:

```json
{
  "id": "node-7",
  "type": "frame",
  "title": "Checkout / Payment form",
  "url": "https://design.example.com/file/AbC123?node=160-34",
  "parent": "page-2",
  "locatable": true,
  "content": [
    { "type": "image", "data": "iVBORw0KGgo…", "mimeType": "image/png" },
    { "type": "resource_link", "uri": "https://design.example.com/file/AbC123?node=160-34", "name": "Checkout / Payment form" }
  ],
  "payload": { "width": 390, "height": 844, "children": 14 }
}
```

Identity and position work the same as for text: the id is opaque, and `locate` returns the frame's bounding box as a list of one rectangle.

A provider should keep `content` small: a selection's text, a thumbnail and not a full-resolution export. Anything large belongs behind a `resource_link`.
