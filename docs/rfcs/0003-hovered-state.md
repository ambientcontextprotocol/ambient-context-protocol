# RFC-0003 — A hovered state

> Add an optional fourth state to an element, `hovered`, saying the pointer is over it now.

| Field | Value |
|---|---|
| Author | The protocol session, for Andrew Jones |
| Status | Accepted |
| Created | `2026.11.10` |
| Decided | `2026.11.10` |
| Discussion | Not yet opened as a pull request |
| Specification sections | The element's fields and states (RFC-0001, 4.1); rules for hosts |
| Version effect | Additive |
| Supersedes or amends | Amends RFC-0001 |
| Released in | — |

## 1. Summary

RFC-0001 gives an element three states: `selected`, `focused` and `visible`. This RFC adds `hovered`: the pointer is over this element now. It is optional for a provider, and a host treats it as a weaker signal than selection.

## 2. Motivation

Resting the pointer on a thing is the cheapest way a person points at it. Someone looking at a row in a list says "what is this" or "move this to next week" without clicking or selecting anything. With the three states of RFC-0001 the agent has nothing to resolve "this" to. Spoken requests gain the most, because a person speaking has often selected nothing.

## 3. Proposal

A planner with the pointer resting on a task, and nothing selected:

```json
{ "id": "v-1", "role": "List", "subrole": "view", "focused": true, "children": [
  { "id": "t-104", "role": "Row", "subrole": "task", "title": "Launch plan review", "hovered": true },
  { "id": "t-105", "role": "Row", "subrole": "task", "title": "Book the venue" }
] }
```

The host tells the agent that the pointer is over "Launch plan review". If something were selected as well, the agent would be told both, with the selection first.

Scope and exclusions:

- A provider marks the innermost element it already reports under the pointer. It does not create new elements, such as one per word, in order to mark them.
- The state describes the moment the provider answers. It is not a stream of pointer movements.
- It says where the pointer is and nothing about clicks, dragging or how long the pointer has rested.

## 4. Specification changes

1. *The element's fields.* Add `hovered`, optional: the pointer is over this element now. Absent means false.
2. *Where it is set.* At most one element in an answer has `hovered` true: the innermost reported element under the pointer. Its ancestors are not marked; containment already says what holds it. This differs from `focused`, which is marked along the whole path, because focus has levels (a pane, then a row in it) and the pointer has one position.
3. *When it is absent everywhere.* The pointer is outside the app's windows, or over something the provider does not report, or the provider does not track the pointer. A receiver cannot tell these apart and must not infer anything from the absence.
4. *Rules for hosts.* A host presents `hovered` to an agent as where the pointer is, distinct from and weaker than `selected`. A host does not send more of an element's content because it is hovered than it would otherwise send.

## 5. Compatibility

Additive. A provider that never sets it is correct. A host that does not know the field ignores it, as with any field it does not know. It can be part of 0.2.0 at no cost to compatibility, since no implementation of 0.2.0 exists yet; after 0.2.0 is released it would be a patch version.

## 6. Privacy and security

1. *It is often not deliberate.* A selection is something the user did. The pointer is wherever it was last left, and may rest on something the user never meant to indicate. A provider that reports the hovered element therefore reports one more thing the user did not choose to share: which item the pointer happened to be on. Within an app whose open content is already reported this adds little, since the element is in the tree either way; the state adds only the pointer's position among them.
2. *It must not widen what is sent.* The risk is a host that treats hover like selection and sends the hovered thing's full content. Rule 4 forbids it.
3. *Callers are unchanged.* The same programs that can read `current` can read this.
4. *It reveals attention.* Read repeatedly, the state would trace what the user looks at. The existing rule that a host reads context only on the user's action covers it; nothing in this RFC allows polling.

## 7. Conformance

| Draft | Requirement | Check from outside |
|---|---|---|
| H1 | At most one element in an answer has `hovered` true | Count them in the answer |
| H2 | A hovered element has no hovered ancestor or descendant | Follows from H1 |
| H3 | A host reads an absent `hovered` as false and infers nothing from it | A test of the host's reader on a fixed tree |
| H4 | A host presents hover as distinct from and weaker than selection, and sends no more content because of it | An inspection of the host; not checkable from outside |
| H5 | The hovered element is the one actually under the pointer | Not checkable by request alone; a provider's own test places the pointer and reads the answer |

## 8. Rationale, alternatives and prior art

- *Why a state and not a separate question.* Apple's Accessibility has no hovered state on an element; it answers "which element is at this point on screen". A host can use that for apps that are not providers. For a provider, a state on the element is simpler: the host does not need positions, and the app already knows what its pointer is over.
- *Why only the innermost element.* Marking the path, as focus does, would repeat what the tree already says and make "at most one" impossible to check.
- *The host works it out from positions.* Possible where a provider reports locations, but it needs a location for every element and a second request per element. Rejected as far more work for the same answer.
- *Do nothing.* The user clicks or selects first. It works, and it is what every app requires today; the cost is that speech without a selection has nothing to point with.
- *Prior art.* The web separates the two the same way: hover is a pointer condition a page can observe, selection and focus are things the user did.

*Drawbacks.* A native app has to track the pointer over its elements, a few hours of work each. An agent may give an accidental hover more weight than it deserves, which rule 4 reduces and cannot remove.

## 9. Open questions

1. Should a provider report hover only when the pointer has rested for a moment, to filter out a pointer that is merely passing? I lean no: the provider reports the fact, and the host decides its weight.
2. On a device with no pointer, the state is simply never set. Is a touch-and-hold worth the same word later?

## 10. Decision and outcome

Accepted on 2026.11.10 by Andrew Jones, maintainer, for protocol version `0.2.0`, as an amendment to RFC-0001.

Why: pointing with the pointer is the cheapest way to indicate a thing, and speech without a selection has nothing else to resolve "this" to. It is optional and additive, and costs nothing in compatibility while no implementation of 0.2.0 exists. The open questions in section 9 stay open during implementation. Not yet implemented or released.
