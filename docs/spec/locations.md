# Ambient Context Protocol · Locations

> Part of the [specification](index.md), version `0.2.3`.

## 6. Locations

A location is the answer to "where is this element on screen?" It has the same shape for every kind of element.

| Field | Type | Required | Meaning |
|---|---|---|---|
| `id` | string | yes | The element asked about. |
| `state` | string | yes | `visible`, `offscreen` or `gone`. |
| `rects` | array | when visible | One or more rectangles covering the element, each `{x, y, w, h}`. |
| `window` | number | no | The system window number of the window the element is in. |
| `avoid` | rect | no | A region the provider would prefer the host not cover, such as its text column. |
| `edge` | string | no | The side the provider would prefer things attached to: `left`, `right`, `top` or `bottom`. |

**States.** `visible`: at least part of the element is drawn on screen. `offscreen`: the element exists but is not drawn, because it is scrolled away, in a background tab or in a minimized window. `gone`: the element was deleted or the id has expired. These are a location's states and are separate from an element's `visible` state ([5.3](elements.md#53--states)), which is what the provider said when it answered `current`; a location says what is true when `locate` is answered.

**Rectangles.** A list, because some elements are not one rectangle: a text selection that wraps has one per line. Most elements send a list of one.

**Coordinates.** Rectangles are in the platform's global display coordinates, the space in which a host places its own windows. The platform's profile defines that space, its unit and its origin ([8.1](discovery.md#81--platform-profiles)).

**Hints.** `avoid` and `edge` are requests. A host should honor them when it can and may ignore them.

A location describes one moment. A host that needs to know whether an element moved asks again.
