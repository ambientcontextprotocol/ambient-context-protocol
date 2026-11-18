# Ambient Context Protocol · Elements

> Part of the [specification](index.md), version `0.2.4`.

## 5. Elements

An element is one thing the app shows: the app itself, a window, a document, a list, a row in it, a run of text. Everything a provider reports is an element, and the elements form one tree rooted at the app. Containment in the tree says how things relate: selected words are inside the comment they were selected in, which is inside its thread, which is inside its pane.

A notes-and-threads app with words selected inside a comment, and a second thread in another pane:

```json
{
  "protocol": "0.2.4",
  "instance": "k3f9x2",
  "root": {
    "id": "app", "role": "Application", "title": "Example",
    "children": [
      { "id": "w-1", "role": "Window", "subrole": "pane", "focused": true, "children": [
        { "id": "th-2", "role": "List", "subrole": "thread", "title": "Launch plan", "focused": true, "children": [
          { "id": "c-3", "role": "Row", "subrole": "comment", "title": "Comment by Ada", "focused": true, "children": [
            { "id": "sel-4", "role": "Text", "selected": true,
              "content": [{ "type": "text", "text": "what it shows" }] }
          ] }
        ] }
      ] },
      { "id": "w-2", "role": "Window", "subrole": "pane", "children": [
        { "id": "th-7", "role": "List", "subrole": "thread", "title": "Budget" }
      ] }
    ]
  }
}
```

### 5.1 — Fields

| Field | Type | Required | Meaning |
|---|---|---|---|
| `id` | string | yes | Opaque. 1 to 128 characters: letters, digits, hyphens and underscores. Unique within one answer and stable for one run of the provider. See [5.4](#54--ids-and-instances). |
| `role` | string | yes | How the thing is shown: a word from the role language in [5.2](#52--roles). |
| `subrole` | string | no | What the thing is, in the app's own word: `task`, `comment`, `pane`, `markdown`. Any string; an app defines these freely. |
| `title` | string | no | One line a person could read, such as a file name or a task's name. |
| `content` | array of content blocks | no | What the element contains, for the agent to read or see. See [5.5](#55--content). |
| `url` | string | no | An address for the thing, when it has one: a `file://` URL, a web URL, or a link the app itself opens. |
| `selected` | boolean | no | The user selected this. See [5.3](#53--states). |
| `focused` | boolean | no | The keyboard or cursor is here, or inside here. See [5.3](#53--states). |
| `visible` | boolean | no | Drawn on screen now. See [5.3](#53--states). |
| `hovered` | boolean | no | The pointer is over this now. See [5.3](#53--states). |
| `children` | array of elements | no | The elements inside this one, in the app's order. An empty list is not sent. |
| `attributes` | object | no | Anything else the provider wants an agent to have, by name. See [5.6](#56--attributes). |

Selected text is a `Text` element with `selected` true, placed inside the element it was selected in.

### 5.2 — Roles

A role is one of the following thirteen words, spelled as shown.

| Kind | Roles |
|---|---|
| The app and its windows | `Application`, `Window` |
| Containers | `Group`, `List`, `Table` |
| Entries | `Row`, `Cell` |
| Text | `Text`, `Heading`, `Link` |
| Pictures and pages | `Image`, `Page` |
| Added by this protocol | `Document` |

The roles are this protocol's own and mean the same on every platform. Eleven of the names are taken from Apple's Accessibility roles; `Text` stands for its three text roles, and `Document` is new here. Two roles are kept apart only where an agent or a host would act differently on seeing one or the other. A provider whose platform has more roles reports the nearest of these. The examples below use Apple's role names, and a provider on another platform maps its own roles in the same way:

| Role | Also covers |
|---|---|
| `Window` | Sheet, Drawer, Popover, TabGroup. A tab or pane says so in the subrole. |
| `Document` | WebArea |
| `Group` | SplitGroup, ScrollArea, LayoutArea, LayoutItem |
| `List` | Outline, Browser. Nesting shows the hierarchy. |
| `Table` | Grid. A table is rows of cells; a column is not an element. |
| `Text` | StaticText, TextField, TextArea |

The role says how a thing is shown; the subrole says what it is. A task in a list is a `Row` with subrole `task`; the same task on a board is a `Cell` with subrole `task`. When no role plainly fits, the provider uses `Group`.

Rules:

1. The root is an `Application`, and no other element is.
2. A provider's own word goes in `subrole`, never in `role`.
3. A receiver treats a role it does not know as `Group`. A role added to this list later is therefore not a breaking change.
4. A provider does not report controls, menus, indicators or window furniture: no buttons, scroll bars or toolbars.
5. A provider gives a `subrole` to each thing that is the app's own kind: its tasks, comments, panes. A plain window or a plain run of text needs none.

### 5.3 — States

Four states say what the user is pointing at and what is on screen. Each is stated once, on the element it describes, and nowhere else in the answer.

| State | Meaning | When absent | How many |
|---|---|---|---|
| `selected` | The user selected this element. | False | Any number |
| `focused` | The keyboard or cursor is in this element. | False | One path, see below |
| `visible` | The element is drawn on screen now. | The parent's value; the root is visible | Any number |
| `hovered` | The pointer is over this element now. | False | At most one |

A provider sends `selected`, `focused` and `hovered` only when true. `visible` is sent with either value where it differs from the parent's.

**Focus is a path.** `focused` is set on every element on the path from a child of the root down to the user's position, with no gaps, so the position is found by following focused elements down from the root. The root itself need not be marked. Two focused siblings are an error, and so is a focused element whose parent, below the root, is not focused.

**Hover is one element.** At most one element in an answer has `hovered` true: the innermost reported element under the pointer. Its ancestors are not marked; containment already says what holds it. A provider does not create elements, such as one per word, in order to mark them. The state describes the moment the provider answers and says nothing about clicks, dragging or how long the pointer has rested. It is optional: a provider that never sets it is correct.

**When `hovered` is absent everywhere,** the pointer is outside the app's windows, or over something the provider does not report, or the provider does not track the pointer. A receiver cannot tell these apart and must not infer anything from the absence.

**Visible is about drawing, not focus.** A document in a background tab, a pane scrolled out of view and a minimized window are not visible. An element can be visible without being focused, and several windows can be visible at once.

### 5.4 — Ids and instances

An id names one appearance of a thing: the same task shown in two panes is two elements with two ids.

An id means something only together with the provider that issued it and that provider's `instance`. Two providers may both issue `sel-23`, and a provider that restarts may issue it again for something else. The full name of an element is therefore the provider, its instance and the id. Keeping the three together is the host's job ([9.2](security.md#92--for-hosts)); an agent sees only the id.

Within one run, an id keeps referring to the thing it was minted for ([9.1](security.md#91--for-providers)). The form is restricted to letters, digits, hyphens and underscores because `locate` puts the id in an address.

### 5.5 — Content

`content` uses MCP's `ContentBlock` type unchanged, so a host can hand the blocks to an agent without translating them. The block types, as of MCP schema `2026-07-28`:

| `type` | Required fields | Use here |
|---|---|---|
| `text` | `text` | Selected text, or a short description of the element. |
| `image` | `data` (base64), `mimeType` | A small rendering of something visual: a frame, a chart, a region of a canvas. |
| `audio` | `data` (base64), `mimeType` | Rarely needed. |
| `resource_link` | `uri`, `name` | A pointer to the full thing, for the agent to fetch if it needs it. |
| `resource` | `resource` (a `uri` with `text` or `blob`) | The full thing, embedded. |

An element that is text sends a `text` block. An element that is not text sends an image, a link, or both. A selected frame in a design tool, which is neither a row nor a cell and so is a `Group`:

```json
{
  "id": "node-7",
  "role": "Group",
  "subrole": "frame",
  "title": "Checkout / Payment form",
  "url": "https://design.example.com/file/AbC123?node=160-34",
  "selected": true,
  "content": [
    { "type": "image", "data": "iVBORw0KGgo…", "mimeType": "image/png" },
    { "type": "resource_link", "uri": "https://design.example.com/file/AbC123?node=160-34", "name": "Checkout / Payment form" }
  ],
  "attributes": { "width": 390, "height": 844, "layers": 14 }
}
```

Identity and position work the same as for text: the id is opaque, and `locate` returns the frame's bounding box as a list of one rectangle.

A provider should keep `content` small: a selection's text, a thumbnail and not a full-resolution export. Anything large belongs behind a `resource_link`.

### 5.6 — Attributes

`attributes` is an object of named values the app defines freely: line numbers, a due date, a status. A receiver ignores names it does not know.

Three names are reserved:

| Name | Value | Meaning |
|---|---|---|
| `author` | string | Who wrote the thing. A provider sends it only where the app already shows it. |
| `related` | array | Links that are not containment. Each entry has a relation name and another element's `id` or an address. |
| `via` | string | On the root only: how a provider that answers for another app learned what it reports, such as `browser-extension` ([9.1](security.md#91--for-providers)). |

A link between two things that is not containment is expressed in `related`, not by placing one element inside the other.

### 5.7 — What to report

A provider decides how much of the app to report. The tree is not a copy of everything the app holds, or of its whole interface. It carries what the user has open and is pointing at: the windows, the documents or views in them, and what is selected, focused or hovered. An editor with forty open files might report them all, since each costs one line. A task manager would report the open view and the selected tasks, not its whole database.

A tree makes it easy to report more than a list did. The rule is unchanged: a provider reports what is useful and what the user would expect ([9.1](security.md#91--for-providers)), and a host sends an agent only what the user's action warrants ([9.2](security.md#92--for-hosts)).

Limits on the size of a tree, its depth and an element's content are not yet set ([section 13](versioning.md#13-open-questions)).
