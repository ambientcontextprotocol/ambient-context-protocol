# Ambient Context Protocol · Locations

> Part of the [specification](index.md), version `0.1`.

## 6. Locations

A location is the answer to "where is this item on screen?" It has the same shape for every kind of item.

| Field | Type | Required | Meaning |
|---|---|---|---|
| `id` | string | yes | The item asked about. |
| `state` | string | yes | `visible`, `offscreen` or `gone`. |
| `rects` | array | when visible | One or more rectangles covering the item, each `{x, y, w, h}`. |
| `window` | number | no | The system window number of the window the item is in. |
| `avoid` | rect | no | A region the provider would prefer the host not cover, such as its text column. |
| `edge` | string | no | The side the provider would prefer things attached to: `left`, `right`, `top` or `bottom`. |

**States.** `visible`: at least part of the item is drawn on screen. `offscreen`: the item exists but is not drawn, because it is scrolled away, in a background tab or in a minimized window. `gone`: the item was deleted or the id has expired.

**Rectangles.** A list, because some items are not one rectangle: a text selection that wraps has one per line. Most items send a list of one.

**Coordinates.** Version 0.1 is specified for macOS. Rectangles are in global display coordinates, in points, with the origin at the top-left corner of the primary display and y increasing downward. This is the space the macOS Accessibility API and Core Graphics use. AppKit's own coordinates have a bottom-left origin and must be converted.

**Hints.** `avoid` and `edge` are requests. A host should honor them when it can and may ignore them.

A location describes one moment. A host that needs to know whether an item moved asks again.
