# RFC-0003 — Object references: search and read

> Two optional operations that let a host list a provider's objects matching what the user typed, and fetch the one the user picked, so a person can refer to a thing in an app that is not in front.

| Field | Value |
|---|---|
| Author | The protocol session, for Andrew Jones |
| Status | Draft |
| Created | `2026.11.10` |
| Decided | — |
| Discussion | Not yet opened as a pull request |
| Specification sections | 4 (operations), 7.2 and 7.3 (the MCP binding), 9 (rules) |
| Version effect | Additive |
| Supersedes or amends | None. Written against RFC-0001's element; depends on it |
| Released in | — |

## 1. Summary

Today a provider answers one question: what does the user have open. This RFC adds two more, both optional. *Search* returns the provider's elements that match a short query. *Read* returns one element by id, with its content. A host uses them to offer a menu of things to mention, across every running provider, and to send the agent the thing the user chose.

## 2. Motivation

A person writing to an agent wants to say "this task" without first bringing the task's app to the front. In a composer that means typing `@`, a few letters, and picking from a menu. The menu has to list objects from several apps, and no host can know every app's objects. Current context cannot serve this: it reports only what is open, and only for the app in front.

The same two operations serve voice, where there is no menu: the agent resolves "the launch task in the planner" by searching.

## 3. Proposal

The user types `@lau`. The host asks each running provider that offers search for matches to `lau`, with a short time limit. A planner answers:

```json
{
  "instance": "k3f9x2",
  "elements": [
    { "id": "t-104", "role": "Row", "subrole": "task", "title": "Launch plan review", "url": "planner://task/104" },
    { "id": "g-7", "role": "Row", "subrole": "goal", "title": "Launch" }
  ]
}
```

The host shows the answers grouped by app. The user picks one. The host reads `t-104` from that provider and gets the same element with its `content`, which it gives to the agent together with the app's name.

Scope and exclusions:

- Results are elements as RFC-0001 defines them, without `children` and without the three states: a result is a thing, not a place on screen.
- The provider ranks. It knows what is recent and what matters; the host does not reorder within one provider's answer.
- Apps that are not running do not answer. Starting a provider on demand is not part of this RFC.
- Nothing here lets a host change anything in an app.

## 4. Specification changes

1. *Section 4, new operation `search`.* Input: `query`, a string of at least one character, and an optional `limit`. Output: `instance` and `elements`, best match first, at most `limit` and never more than 25. Each element has `id`, `role` and `title`, and may have `subrole`, `url` and `attributes`. It has no `content`, `children`, `selected`, `focused` or `visible`. An empty list is a valid answer.
2. *Section 4, new operation `read`.* Input: an `id` from a `search` answer or from `current`, issued by the same instance. Output: that element with its `content`, under the same size limits as `current`. An id whose thing no longer exists is answered as gone, as `locate` does; an id never issued is an error.
3. *Identity.* An id returned by `search` is valid for `read` for the rest of that run of the provider. A provider that cannot promise this for a kind of thing does not return that kind from `search`.
4. *Section 7, the binding.* Each operation is declared separately in the extension's capabilities, as locations are. How the two are carried in MCP is open question 1.
5. *Section 9, rules for providers.* A provider returns from `search` only things the user could find by searching inside the app itself, under the account and permissions the app is running with. It does not search the contents of things it would not show in its own search.
6. *Section 9, rules for hosts.* A host calls `search` only while the user is choosing something to mention, and `read` only for a thing the user chose or that the user's request plainly names. A host shows each chosen thing to the user before sending it, and sends only that thing. A host does not call `search` to gather context the user did not ask for.

## 5. Compatibility

Additive. A provider that offers neither operation is unchanged, and a host that never calls them is unchanged. A host must not assume a provider offers either: it reads the capabilities first.

## 6. Privacy and security

This is the largest widening of what a provider exposes since the first version, and the RFC should not be accepted without weighing it.

1. *From what is open to everything in the app.* `current` exposes the documents on screen. `search` and `read` expose anything the app can find: every task, every note, every thread. The callers are the same as today, any program that can read the descriptor's token, which means any program running as the user. For an app whose data already sits in readable files, this adds convenience for an attacker and little else. For an app whose data is in a protected store or on a server, it is a new way in. Such an app should think before offering these operations, and the specification should say so plainly.
2. *What the user typed goes to every provider.* When the host asks all running providers, each one learns the characters typed after `@`, including providers the user was not thinking of. Rule 6 keeps this to the moment of choosing. A host can reduce it further by asking only the named app once the user has typed one.
3. *Apps not in front are asked.* For latent context that was ruled out. It is acceptable here because the user started the search and chooses the result; nothing is sent to the agent that the user did not pick and see.
4. *An agent as the caller.* If the host gives these operations to an agent as tools, the agent can search and read without the user picking each thing. That is a different grant from a menu, and a host must present it to the user as one. This RFC allows it only where "the user's request plainly names" the thing; whether that wording is tight enough is open question 3.
5. *Enumeration.* A caller can walk the alphabet and list everything. The cap of 25 slows this and does not stop it. Stopping it needs a stronger check on who is calling, which no version has yet.

## 7. Conformance

Draft requirements, to be added to the product model on acceptance:

| Draft | Requirement | Check from outside |
|---|---|---|
| S1 | A provider that declares search answers a query with at most `limit` elements, never more than 25, each with `id`, `role` and `title` | Call with several limits; count and validate |
| S2 | A search result carries no `content`, `children` or state | Validate the answer |
| S3 | An id from a search answer can be read for the rest of the run | Search, wait, read |
| S4 | Reading an id never issued is an error; reading one whose thing is gone answers gone | Call with a made-up id; delete a thing, then read |
| S5 | Search and read refuse a request without the token or with an `Origin` header | The existing access checks, run against the new operations |
| S6 | A host calls search only while the user is choosing a mention | Not checkable from outside; an inspection of the host |
| S7 | A provider returns only what its own search would show the user | Not checkable from outside |

## 8. Rationale, alternatives and prior art

- *Why two operations and not one.* Returning content with every search result would send the user's data to the host for things never picked, and make each keystroke expensive.
- *Why the provider ranks.* A host ranking across apps would need to understand each app's objects. Grouping by app avoids the question.
- *A file index instead (the operating system's search).* Finds files, not tasks or comments, and knows nothing an app has not written to disk in a readable form.
- *Each app registers a list of everything in advance.* Stale at once, and exposes everything without a query.
- *Do nothing.* The user brings the app to the front and selects the thing. It works today and costs a context switch each time.
- *Prior art.* MCP has completion for the arguments of a resource template, which returns strings, not typed objects with titles (my knowledge of MCP; to be checked against the current revision). Editors' language servers split the same way: a cheap list of symbols, then a separate request to resolve one. Mention menus in chat and document tools follow the pattern type, list, pick, and send only the pick.

*Drawbacks.* Every provider that offers search takes on a query path it must keep fast. The privacy cost in section 6 is real. Two more operations move the protocol from "what is on screen" toward "an interface to the app's data", which is a larger thing to standardize and overlaps with what an app's own MCP server may already offer.

## 9. Open questions

1. The MCP binding: two resource templates (a search address carrying the query, and an element address carrying the id), or two tools. Resources match how `current` and `locate` are carried; tools are what an agent can call directly.
2. Should `read` also serve as the way to fetch one element's full content from `current`, so that `current` can stay small?
3. May an agent call these as tools, and under what rule, or are they for the host's menu only in the first version?
4. Does a provider with an MCP server of its own, which already lets an agent search the app, need this at all, or should the host use that server?
5. A time limit for search that the specification names, or the host's choice as for `current`.
6. Whether a provider should be able to say that some results need the user's confirmation before `read`.

## 10. Decision and outcome

Pending.
