# RFC-0006 — Watching current

> Let a host that is showing the user a provider's context ask to be told when that context changes, so the line it shows stays true without asking again and again.

| Field | Value |
|---|---|
| Author | The protocol session, for Andrew Jones, with the Sirius session on the host's side |
| Status | Draft |
| Created | `2026.11.17` |
| Decided | |
| Discussion | Not yet opened as a pull request |
| Specification sections | 3 (principle 3), new 4.4, 7.1, 7.2, new 7.7, 7.4, 9.1, 9.2, 10, 12, 14 |
| Version effect | Additive: `0.2.1` to `0.2.2` |
| Supersedes or amends | None. Takes "Watching" out of section 12 for `current` only |
| Released in | |

## 1. Summary

A host reads `current` once, when the user invokes it, and shows the user what it read. If the user then selects something else in the app while the host's composer is still open, the host is showing a stale line. This RFC adds one optional operation, `watch`: while the host is showing that provider's context, it holds one request open to the provider, and the provider says "changed" on it, with no content, each time its answer to `current` would differ. The host then reads `current` again in the ordinary way. MCP revision `2026-07-28` already has the mechanism, `subscriptions/listen`; this RFC decides to allow it for `ambient://current` and says when a host may use it.

## 2. Motivation

Sirius shows, at the bottom of its composer, what it read from the app behind it: `[favicon] release-runbook.md · lines 12–18`. The user opens the composer, sees the line, notices it names the wrong paragraph, selects the right one in the editor, and looks back. The line still names the wrong paragraph. It corrects itself only when the composer becomes the key window again, and the message is safe only because the host reads once more at send. For the seconds in between, the host is telling the user something false about what will be sent, which is the one thing that line exists to prevent.

Two ways to fix it. The host can ask again on a timer while the composer is open. Or the provider can tell the host when there is something new to ask about. The maintainer ruled out the first on 2026.11.17: polling spends work when nothing changes, is late by up to its interval when something does, and breaks the principle that a host does not poll. This RFC is the second.

## 3. Proposal

The user opens the host's composer over an editor. The host reads `current` as today and shows the line. Then, to that same provider, it sends one more request and leaves it open:

```json
{
  "jsonrpc": "2.0",
  "id": 7,
  "method": "subscriptions/listen",
  "params": {
    "_meta": {
      "io.modelcontextprotocol/protocolVersion": "2026-07-28",
      "io.modelcontextprotocol/clientCapabilities": {}
    },
    "notifications": { "resourceSubscriptions": ["ambient://current"] }
  }
}
```

The provider answers with an event stream. First it acknowledges what it will send. Then it says nothing until the user selects another paragraph, when it sends one small message:

```json
{
  "jsonrpc": "2.0",
  "method": "notifications/resources/updated",
  "params": {
    "_meta": { "io.modelcontextprotocol/subscriptionId": 7 },
    "uri": "ambient://current"
  }
}
```

The host reads `ambient://current` again, with the same token and the same checks as any read, and redraws its line. When the user sends the message, removes the context or closes the composer, the host closes the stream and the watch is over.

Scope and exclusions:

- Only `current` can be watched. Locations cannot: where an element is changes with every scroll and window move, and a host asks for a location at the moment it needs one.
- The notice carries nothing about what changed. A host learns the new state only by reading `current`, so nothing can reach it by a route the read's checks do not cover.
- A watch exists only while the host is showing the user that provider's context. It is not a way to follow an app in the background.
- A provider is complete without it. A host that finds no watch falls back to what it does today.

## 4. Specification changes

1. *Principle 3 (section 3).* From "Pulled on the user's action. … A provider does not push, and a host does not poll" to: "Pulled on the user's action, and kept current while the user is looking. A host asks for context when the user does something that calls for it. While it is showing the user what it read, it may ask the provider to say when that changes. A provider sends nothing a host did not ask for, and a host does not poll." The word "Provisional" is dropped: this is the change it was waiting for.
2. *A third operation, `watch` (new 4.4).* Asks the provider to say when its answer to `current` changes. Takes no input. It has no result while it lasts: the provider sends a notice, with no content, each time its answer to `current` would differ from the one it last gave or last announced. The operation ends when the host ends it, when the provider ends it, or when the connection between them is lost. Optional for a provider.
3. *What counts as a change.* Anything that would alter the answer to `current`, `display` included, except a change in `hovered` alone. The pointer moves constantly, and a notice for each movement would report the user's attention and little else (see section 6 and open question 1).
4. *The binding (new 7.7).* `watch` is MCP's `subscriptions/listen` with `notifications.resourceSubscriptions` holding exactly `ambient://current`. The provider answers with `Content-Type: text/event-stream`, sends `notifications/subscriptions/acknowledged` first, then `notifications/resources/updated` with `uri: "ambient://current"` for each change. It ends a watch by answering the request with a completion result and closing the stream, or by closing the stream. A provider that offers `watch` declares `"resources": { "subscribe": true }` in its capabilities; one that does not declares `"resources": {}` as today and answers the method as any method it does not implement ([7.4](../spec/binding.md#74--errors-and-refusals): `404` with `-32601`).
5. *Transport (7.1).* "It does not need to stream" becomes: it streams only for `watch`. Every other request is still answered with one JSON object. The token and `Origin` rules apply to the watch request exactly as to a read, and are checked before the stream opens. A host sends `Accept: application/json, text/event-stream` on the watch request.
6. *A filter the provider does not serve.* A `subscriptions/listen` request that names any resource other than `ambient://current`, or asks for list-changed notifications, is acknowledged for `ambient://current` alone if it names it, and otherwise refused with `-32602`. A provider never sends a notification type or address the host did not ask for.
7. *Rules for providers (9.1).* "Answer only when asked. Send nothing unprompted" becomes "Send nothing a host did not ask for": a notice on an open watch is asked for.
   - *Coalesce.* At most one notice in any 250 milliseconds on one watch, and the last change always produces a notice: a provider may delay a notice, never drop the final one.
   - *Say nothing else.* A notice carries the address and the subscription id and nothing from the app.
   - *Keep quiet streams alive.* On a watch with nothing to say, send an SSE comment line at least every 15 seconds, so a host can tell a quiet provider from a dead one.
   - *Bound the watches.* A provider may limit how many watches it holds at once, to no fewer than four, and may end any watch at any time. It ends them all when it quits and when the user turns the provider off.
   - *Know your own changes.* A provider notices changes from the app's own events (a selection changed, a document opened). It does not find them by rebuilding its answer on a timer: that is polling moved into the app.
8. *Rules for hosts (9.2).* "Ask on the user's action" gains a second sentence: after such a read, and only while the host is showing the user that provider's context, a host may hold one watch on that provider and read `current` again when a notice arrives.
   - *One watch, one provider, in view.* A host opens a watch only on the provider it has just read on the user's action, holds one at a time, and ends it when the message is sent, the context is removed or its interface closes. It does not watch an app the user is not being shown context from.
   - *A notice is not context.* A host learns the new state only by reading `current`, with every check a read has, the instance check included.
   - *One read per notice, at most.* A host that gets a notice while a read is outstanding finishes that read and reads once more. It does not read except on the user's action or a notice.
   - *A lost watch is silence.* If the stream ends or fails, the host carries on with what it last read, shows the user no error, and may try to open the watch again once. It still reads at send.
9. *Versioning (10, 12).* The version becomes `0.2.2`. "Watching" in section 12 is narrowed to what remains: locations and the pointer's position.
10. *MCP details (14).* Three rows: `subscriptions/listen` and its filter; the acknowledgment and `notifications/resources/updated`; a request answered by an event stream that stays open, with no session, no `GET` stream and no resumption.

## 5. Compatibility

Additive. A `0.2.1` provider does not declare `subscribe` and answers the method with `-32601`; a `0.2.2` host sees that and behaves as it does today. A `0.2.1` host never sends the request. Nothing a provider or host does today becomes wrong.

What changes for implementers:

- *A provider that wants to be watched* must answer one request with a response that stays open, which the packages' "one request in, one response out" responder does not do today, and must tell the package when its state changes. The second is the real work: each app has to call one function from the places where its selection, focus and open documents change.
- *A provider on a shared listener (RFC-0002)* needs its app's server to stream a response on the endpoint's path. A server that cannot simply does not offer `watch`.
- *A host* needs a client that can hold one event stream per watch. The first-party host's client today makes one short request per read and accepts JSON only.

MCP clients older than `2026-07-28` used `resources/subscribe` and a separate `GET` stream. This RFC does not ask a provider to serve `watch` to them; [7.6](../spec/binding.md#76--older-mcp-clients) is unchanged.

## 6. Privacy and security

1. *What new information leaves an app.* The times at which the user changes what is open or selected. No content: the notice says only that `current` changed. A caller that can open a watch can already read `current` at will, so it learns nothing it could not learn by polling, but it learns it more cheaply and exactly.
2. *Following the user.* A watch held open for hours would trace when the user works in an app. Rule 8 forbids a host from holding one except while it is showing the user that app's context, and a provider may end any watch. Neither can be enforced on a hostile program that holds the token; section 8 of the specification already states that such a program is outside what the protocol defends against, and it could read the user's documents directly.
3. *Hover.* Notices for pointer movement would turn a watch into a record of what the user points at, moment by moment. Change 3 excludes hover-only changes. The reread a notice causes still carries the hovered element as any read does.
4. *Nothing arrives unchecked.* Because a notice has no content, a provider cannot use it to put text in front of the user or the agent without the read's checks. This is the reason not to send the new answer, or even the new `display`, in the notice.
5. *A stream as a way to hold resources.* A program with the token could open many watches. A provider bounds how many it holds and may end the oldest. Each costs one idle connection.
6. *A noisy provider.* A provider that sends notices constantly makes the host read constantly. The coalescing rule bounds a correct provider to four a second; a host protects itself from an incorrect one by never having more than one read outstanding and may end a watch that floods it.
7. *The token and `Origin`.* The watch request is a `POST` to the same path and gets the same two checks, first. A web page cannot open a watch for the same reason it cannot read.
8. *Shared listeners.* A long-lived response on an app's own server must still keep the token and everything from an answer out of that server's logs.

## 7. Conformance

| Draft | Requirement | Check from outside |
|---|---|---|
| W1 | A provider that declares `resources.subscribe` answers `subscriptions/listen` for `ambient://current` with an event stream whose first message is the acknowledgment, naming that address and no other | Open a watch and read the first event |
| W2 | A provider that does not offer `watch` declares no `subscribe` and answers the method with `404` and `-32601` | Send the request |
| W3 | The watch request is refused without the token (`401`) and with an `Origin` header (`403`), before any stream opens | As for a read |
| W4 | A notice is `notifications/resources/updated` with `uri` `ambient://current`, the subscription id, and nothing else | Inspect each event |
| W5 | No more than one notice in any 250 ms on one watch, and a notice follows the last change | Needs the app driven: the fake provider changes its tree on command; for a real app, the author's own test |
| W6 | A change in `hovered` alone produces no notice | The fake provider, on command; a real app's own test |
| W7 | A quiet watch carries an SSE comment at least every 15 seconds | Hold a watch open for 20 seconds |
| W8 | A provider ends its watches when it stops | Stop the fake provider and see the stream end |
| W9 | A host opens a watch only on the provider it read on the user's action, holds one at a time and ends it at send, removal or close | An inspection of the host; the fake provider can report how many watches it holds and for how long |
| W10 | A host reads `current` on a notice, never has two reads outstanding, and shows no error when the stream is lost | A test of the host against the fake provider with faults: a dropped stream, a flood, a stream that never acknowledges |
| W11 | A host does not read `current` except on the user's action or a notice | The fake provider counts reads; an inspection of the host |

In the product model, PR-035 (a host requests context only in response to an action by the user) is retired and replaced by one that allows the read a notice causes. The rest are new, from `0.2.2`.

## 8. Rationale, alternatives and prior art

- *Polling.* The host rereads every few hundred milliseconds while its composer is open. No protocol change and no provider work. Rejected by the maintainer: it costs a full tree per tick when nothing has changed, is late by up to its interval, and makes "a host does not poll" false.
- *Why MCP's own mechanism.* The provider is already an MCP server and `current` is already a resource. `subscriptions/listen` with `notifications/resources/updated` is exactly "tell me when this resource changes". Section 12 of the specification anticipated this: "MCP resources already support subscriptions, so this needs no new mechanism, only a decision to allow it." A stock MCP client can use it unchanged.
- *The new answer in the notice.* Saves the reread. Rejected because content would then arrive outside the read and its checks, the notice would be as large as a tree, and a host would need two code paths that must agree.
- *Only `display` in the notice.* Smaller, and enough to redraw the line. Rejected for the same reason at smaller scale: the line must describe what the next read returns, and the simplest way to guarantee that is to draw it from a read.
- *A read that waits.* `current` with a parameter meaning "answer when this differs from instance and revision N". One request, one JSON response, no event stream. Simpler for both clients. Rejected because it invents a mechanism beside the one MCP defines, needs a revision counter the protocol does not have, and a stock MCP client could not use it.
- *The host watches through Accessibility.* macOS can tell an observer when the selection changes in another app. It needs no provider work, but it needs the Accessibility permission, reports only what the system's own controls expose, and knows nothing of app state such as an open card or a pinned task. A host may still use it for apps that are not providers.
- *The provider finds changes by rebuilding its answer on a timer and comparing.* It would let the packages offer `watch` with no work from the app. Rejected as a rule (4.7): it is polling moved into the app, and costs the same when nothing changes.
- *Do nothing.* The host rereads when its window becomes key and at send. The message is always right; the line is wrong for the seconds in which the user is checking it.
- *Prior art.* Language servers push `textDocument/publishDiagnostics` and clients pull the details they need. File watchers report that a path changed and leave the reading to the caller. Both separate "something changed" from "here is the new state" for the reason given above.

*Drawbacks.* A provider becomes a server that holds connections, and every app must find the places where its context changes; a missed place is a line that goes stale with no error anywhere. A host gains a streaming client and one more thing that can fail. The times of a user's selections become observable to any caller with the token at almost no cost.

## 9. Open questions

1. *Hover.* Excluded from notices here. The cost: a host that shows the hovered thing in its line would show a stale one. No host does today. Is exclusion right, or should a provider that tracks the pointer notify when the hovered element changes, coalesced like anything else?
2. *The numbers.* 250 ms for coalescing, 15 seconds for the keep-alive, four for the least number of watches. Chosen from what the first-party host asked for; to be set from what the first providers do.
3. *Whether a provider should end a watch that has been open very long,* say ten minutes, to bound item 2 of section 6 against a careless host. It costs a host one reconnect.
4. *A host with more than one interface showing context at once,* such as a composer and a dictation pill. Rule 8 says one watch; is that one per host or one per interface?
5. *The packages' interface.* A provider must tell its package that something changed, and a shared-listener responder must hand back a response that stays open. The names and shapes are for the implementation, but the second changes the responder's "one request in, one response out" contract in both packages.
6. *Whether to tell a host how fresh a notice is.* A notice has no sequence number. A host that rereads on every notice does not need one.

## 10. Decision and outcome

Pending.
