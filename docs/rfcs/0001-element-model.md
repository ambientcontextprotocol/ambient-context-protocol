# RFC-0001 — The element model

> Replace the flat list of items with one tree of elements, each with a role from a shared language, an optional subrole in the app's own words, and its state said once. Version 0.2.0.

| Field | Value |
|---|---|
| Author | The protocol session, for Andrew Jones |
| Status | Draft |
| Created | `2026.11.10` |
| Decided | — |
| Discussion | Not yet opened as a pull request |
| Specification sections | 2 (example), 4 (operations), 5 (items), 9 (rules), 10 (versioning) |
| Version effect | Breaking: `0.1` to `0.2.0` |
| Supersedes or amends | None |
| Released in | — |

## 1. Summary

Everything a provider reports becomes an element. Elements form one tree rooted at the application. Each element has a `role` taken from a general language (the role names of Apple's Accessibility that describe content and structure, plus `Document`), an optional `subrole` that is the app's own word for the thing, and three states, `selected`, `focused` and `visible`, stated on the element itself. The version number gains a third part.

## 2. Motivation

Version 0.1 returns a flat list of items and a `focus` list of ids. Three problems appeared as soon as a second and third app used it:

1. *An agent cannot tell how things relate.* A thread open in the front pane and another in a side pane arrive as two identical items. Which comment the selected words belong to is only implied by `parent`.
2. *`type` is any word,* so a host or a checking tool cannot write a rule that holds across apps: "never send a password field", "keep the document and the selection when trimming".
3. *A host that reads apps through the operating system's accessibility interface,* for apps that are not providers, has to translate that tree into a different shape.

## 3. Proposal

A provider answers with one tree. A notes-and-threads app with words selected inside a comment, and a second thread in another pane:

```json
{
  "protocol": "0.2.0",
  "instance": "k3f9x2",
  "root": {
    "id": "app", "role": "Application", "title": "Example",
    "children": [
      { "id": "w-1", "role": "Window", "subrole": "pane", "focused": true, "children": [
        { "id": "th-2", "role": "List", "subrole": "thread", "title": "Launch plan", "children": [
          { "id": "c-3", "role": "Row", "subrole": "comment", "title": "Comment by Ada", "focused": true, "children": [
            { "id": "sel-4", "role": "StaticText", "selected": true,
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

The role says how a thing is shown; the subrole says what it is. A task in a list is a `Row` with subrole `task`; the same task on a board is a `Cell` with subrole `task`. When no role plainly fits, the provider uses `Group`.

Out of scope: notifications when context changes, actions on an element, search over things that are not open, and any change to discovery, transport or trust.

## 4. Specification changes

### 4.1 The element (replaces section 5, Items)

| Field | Required | Meaning |
|---|---|---|
| `id` | yes | Opaque; unique within one answer and stable for one run of the provider. Names one appearance: the same thing shown twice is two elements |
| `role` | yes | A word from the role language in 4.2 |
| `subrole` | no | The app's own word for what the thing is. Any string; an app defines these freely |
| `title` | no | One line a person could read |
| `content` | no | MCP content blocks, unchanged from 0.1 |
| `url` | no | An address for the thing |
| `selected` | no | The user selected this. Absent means false |
| `focused` | no | The keyboard or cursor is here. May be set at each level; the user's position is found by following focused elements down from the root. Absent means false |
| `visible` | no | Drawn on screen now. Absent means the parent's value; the root is visible |
| `children` | no | The elements inside this one, in the app's order |
| `attributes` | no | Anything else, by name. `author` and `related` are reserved (4.3). Replaces `payload` |

`type`, `parent`, `locatable` and the answer's `focus` and `items` are removed. Selected text is an element with a text role and `selected` true, placed inside the element it was selected in.

### 4.2 The role language

A role is one of the following, spelled as shown.

| Kind | Roles |
|---|---|
| The app and its windows | Application, Window, Sheet, Drawer, Popover, TabGroup |
| Containers | Group, SplitGroup, ScrollArea, LayoutArea, List, Table, Outline, Browser, Grid |
| Entries | Row, Column, Cell, LayoutItem |
| Text | StaticText, TextField, TextArea, Heading, Link |
| Pictures and pages | Image, Page, WebArea |
| Added by this protocol | Document |

Rules: the root is an `Application`. A receiver treats a role it does not know as `Group`. A provider does not report controls, menus, indicators or window furniture.

### 4.3 Reserved attributes

- `author`: who wrote the thing, as a string.
- `related`: a list of links that are not containment, each with a relation name and another element's `id` or an address.

### 4.4 Operations (section 4)

`current` returns `{ protocol, instance, root }`. `locate` is unchanged in behavior and takes an element id; whether an element can be located is asked, not declared in advance.

### 4.5 Versioning (section 10)

Versions have three parts. Before 1.0 the minor part changes for a breaking change and the patch part for an additive one. This RFC makes the version `0.2.0`.

## 5. Compatibility

Breaking. Every provider and host changes: the specification, both packages, the three first-party providers, and the first-party host. A host can accept 0.1 and 0.2.0 side by side by the descriptor's `protocol` field for as long as it chooses. No implementation outside the maintainers' own is known, which is why the break is proposed now.

## 6. Privacy and security

No new information is requested: the same things are reported in a different shape. Two effects to weigh:

1. A tree invites a provider to report more of what is open than a list did. The rule that a provider reports what is useful, and a host sends only what the user's action warrants, is unchanged and should be restated beside the element definition.
2. A shared role language makes rules possible that 0.1 could not express, such as never reading a secure text field, or settings by kind. This is a gain.

`author` attaches a person's name to content; a provider should send it only where the app already shows it.

## 7. Conformance

Draft requirements, each to be added to the product model on acceptance:

| Draft | Requirement | Check from outside |
|---|---|---|
| R1 | A provider states `selected`, `focused` and `visible` only on the element they describe | Reject an answer that repeats state elsewhere |
| R2 | A host reads an absent `selected` or `focused` as false and an absent `visible` as the parent's value | A test of the host's reader on a fixed tree |
| R3 | A provider's roles all come from the role language, and its root is an `Application` | Reject any other role at the root; flag unknown roles |
| R4 | Each element's `id` is unique within an answer | Reject a repeat |
| R5 | A link that is not containment is expressed in `related` | Not checkable from outside |
| R6 | Every selected or focused element is reachable from the root | Walk the tree |
| R7 | A provider gives a `subrole` to each thing that is the app's own | Not checkable from outside |

## 8. Rationale, alternatives and prior art

*Prior art.* Apple's Accessibility describes every app on the Mac with one object type, a tree, a fixed role with an open subrole, and focus and selection as relations. Hosts can already read it for apps that are not providers, so sharing its vocabulary removes a translation. The web's ARIA makes the same split of roles and states.

*Alternatives considered.*

1. *Keep the flat list and add a relation word per item.* Smaller change; leaves the reader to rebuild the tree.
2. *A short invented role list* (application, window, document, section, entity, text, media). Tested on paper against twelve apps. Rejected: the invented words either said nothing (`entity`) or forced a judgment (`collection` or `record`), where "is it a row or a cell" is a fact about the screen.
3. *One open `role` field with a recommended vocabulary and no subrole.* Simpler, and close to 0.1's `type`. Not chosen because programs, unlike agents, can only apply rules written against words fixed in advance.

*Drawbacks.* The vocabulary is Apple's, and other platforms use different words for some roles. Layout roles change when the user changes view. A tree is more to build than a list. Apple has no role for audio or video.

## 9. Open questions

1. May a provider put its own word in `role` when none fits, in place of `Group` plus a subrole?
2. Should the role spelling follow Apple's capitalization, as here, or lower case?
3. Is `visible` needed in the first version, or only `selected` and `focused`?
4. Should text roles collapse to one for providers, keeping three only for what a host reads from the operating system?
5. Limits: the largest tree, depth and content size a provider may send.
6. Does `locate` remain a separate resource or become a question asked of an element?

## 10. Decision and outcome

Pending. The direction, an element tree using Apple's role names with app-defined subroles, was set by the maintainer in discussion on 2026.11.10; no revision of this RFC has been accepted.
