# RFC-0007 — An app says its context is sensitive

> Let a provider mark an answer to `current` as sensitive, so a host asks the user before sending it on.

| Field | Value |
|---|---|
| Author | The Sirius session, for Andrew Jones |
| Status | Accepted |
| Created | `2026.11.18` |
| Decided | `2026.11.18` |
| Discussion | Issue #1, "Sensitive page content goes out silently with ambient context". Not yet opened as a pull request |
| Specification sections | 4.1 (the answer to `current`), new 4.4, 9.1 and 9.2 (rules), 10 (the version) |
| Version effect | Additive: `0.2.3` to `0.2.4` |
| Supersedes or amends | None |
| Released in | |

## 1. Summary

Some apps mostly show things that are private to the user or to someone else: mail, messages, a browser signed in to a bank. Today only the host can decide which apps deserve a warning before their context goes to an agent, from a list it keeps itself. This RFC adds one optional field, `sensitive`, to the answer to `current`. A provider sets it to `true` when what the answer holds is likely private. A host that sees it asks the user before that context leaves, unless the user has told it not to ask for that app. A provider that does not send it is unchanged, and a host that does not know it ignores it.

## 2. Motivation

On 2026.11.17 a message sent from Sirius with an order-confirmation page in front carried the user's name, shipping address and order number, and nothing in the send said so (issue #1). Sirius now warns before sending context from Mail or Chrome: the first Return shows what would go, the second sends, and the user can stop the warning per app.

That list is two bundle identifiers written into the host. It does not scale: a password manager, a banking app, a health record, a second browser or a chat client each need the host's author to hear of them. The app's author already knows. An app that knows its content is private should be able to say so once and get the warning in every host.

## 3. Proposal

A mail client with a message selected answers `current` with:

```json
{
  "protocol": "0.2.4",
  "instance": "k3f9x2",
  "sensitive": true,
  "display": { "title": "Re: Lease renewal terms", "detail": "“We can offer twelve…”" },
  "root": { "id": "app", "role": "Application", "title": "Mail" }
}
```

The host shows the user what it read, as before. When the user sends, the host first asks, in its own way, whether this context should go. The first-party host turns its send button white, says "Sends your selection in Mail to Claude." and waits for a second Return, with a checkbox to stop asking for that app.

Scope and exclusions:

- `sensitive` is one bit about the whole answer. It does not mark elements, spans or kinds of data, and it is not a classifier's verdict.
- It asks for more care, never less. Its absence says nothing: a host may still treat any app as sensitive by its own list or its own judgment.
- It is not protection. A host written before this version ignores it, so a provider must still leave out what it should never report (9.1). `sensitive` is for content the provider is right to report and the user may not want sent.
- It is for the host and the user. This RFC does not ask a host to pass it to the agent.
- A provider may send it on every answer (a mail client) or only on some (a browser, for a page behind a sign-in). The rule for choosing is the provider's.

## 4. Specification changes

1. *The answer to `current` (4.1).* One more optional field: `sensitive`, a boolean.
2. *`sensitive` (new 4.4).* A provider sends `"sensitive": true` when what the answer holds is likely private to the user or to another person. It describes the same moment and the same tree as the answer it is in. A provider that has no reason to say so leaves the field out; it does not send `false` to claim the content is safe.
3. *What a host does with it (4.4, 9.2).* Only the JSON value `true` counts. `false`, a missing field and a value of any other type are all read as absent, and never cause a host to refuse the answer. A host that holds an answer marked sensitive does not send that context to an agent, or anywhere off the device, until the user has confirmed that send knowing which app it came from, or has earlier told the host not to ask for that app. How the host asks is its own business. When the host has no way to ask, it leaves the context out and tells the user it did.
4. *Rules for providers (9.1).* `sensitive` does not replace leaving things out. What a provider must never report, it still never reports.
5. *Rules for hosts (9.2).* A host never reads the absence of `sensitive`, or `"sensitive": false`, as a reason to skip a warning it would otherwise give. The user's choice not to be asked again is kept per app and can be undone.
6. *A provider that answers for another app (8).* The field means the same from a helper. The app the host names to the user, and keeps the user's choice for, is the app answered for.
7. *The version (10).* `0.2.4`. A provider that sends `sensitive` gives `0.2.4` in the descriptor, the extension declaration and the answer. A `0.2.3` host works with it unchanged and ignores the field.

## 5. Compatibility

Additive. A provider that never sends the field is correct. A host that does not know it ignores it, as section 10 requires for any field it does not know; such a host gives no warning, which is why item 4 above holds.

The schema for `0.2.3` refuses fields it does not list. A new schema, `schema/current-0.2.4.json`, and the outside check allow the one new field. The first-party host reads any `0.2.x` provider, so a provider that moves to `0.2.4` keeps working with the released host, without the warning until the host is updated.

## 6. Privacy and security

1. *What new information leaves an app.* One bit, to a caller that can already read the content the bit is about.
2. *A hostile or careless provider that leaves it out.* The content is the provider's own and it chose to report it. The user is no worse off than today, and the host's own list still applies (rule 5).
3. *A provider that sends it always, to nag.* The cost falls on that app's own users, who can stop the warning for that app.
4. *Tampering.* The field travels in the answer, from the provider's endpoint, behind its token. It is not in the descriptor, whose folder any program running as the user can write: there, another program could strip it. Because the field can only add care, stripping it anywhere would at worst return the host to its own judgment.
5. *False comfort.* The risk is a user or an app author reading "not marked sensitive" as "safe". The specification says the opposite in 4.4 and 9.2, and a host's interface should not show unmarked context as vetted.
6. *Callers are unchanged.* The same programs that can read `current` can read `sensitive`.

## 7. Conformance

| Draft | Requirement | Check from outside |
|---|---|---|
| S1 | `sensitive`, when sent, is the boolean `true` | The type and value in the answer; the schema |
| S2 | A provider that marks an answer sensitive still leaves out what 9.1 forbids | Not checkable from outside; a provider's own test |
| S3 | A host reads only `true` as sensitive, and reads any other value as absent without refusing the answer | A test of the host's reader on fixed answers; the fake provider serves them |
| S4 | A host does not send context from an answer marked sensitive without the user's confirmation for that send or an earlier choice for that app | A test of the host's send path |
| S5 | A host with no way to ask leaves the context out and says so | A test of the host; an inspection |
| S6 | A host never treats absence or `false` as a reason to skip its own warning | An inspection of the host |

The requirement that the answer holds exactly its listed fields is replaced from `0.2.4` by one that also allows `sensitive`.

## 8. Rationale, alternatives and prior art

- *Why the app says it.* The app's author knows what the app shows. The host's author knows two or three apps by name.
- *In the descriptor, once per run.* Simpler to read before any context is taken, and enough for a mail client. Not chosen: the descriptor folder is writable by other programs (section 6, item 4), and a browser's answer is sensitive for some pages and not others, which a once-per-run file cannot say. A host that wants to label an app as sensitive in its settings can remember that the app has said so.
- *Per element.* A provider could mark the one field that holds an address. It would let a host strip only that. It asks every provider to classify its own content at a finer grain than most can, and a host still needs the answer-level question "should I ask?". Left to a later proposal, which this field does not block.
- *Kinds of sensitivity* (`"sensitive": "financial"`). More to agree on and no host behavior that differs by kind yet.
- *A classifier in the host* (issue #1's first option). It catches what no app marked, and it is a host's own feature, needing nothing from the protocol. The two work together: the mark is cheap and certain where it exists, the classifier covers the rest.
- *Do nothing.* Each host keeps a list. That is today, and it stays as the floor under this field.
- *Prior art.* macOS lets a window opt out of screen capture (`NSWindow.sharingType`), and Android's `FLAG_SECURE` does the same: the app, not the capturing program, says "this is private". Password fields have long told the system not to record what is typed. All are declarations by the content's owner that the reader is expected to honor.

*Drawbacks.* One more thing a user may be asked. A mark that every app sets by default would turn the warning into noise; the guidance to providers is to set it only where most of what the app shows is private, or for the particular views that are.

## 9. Open questions

1. *Where it is declared.* On the answer (this draft) or in the descriptor. Your words were "the app should just declare that it is sensitive", which either satisfies; the answer is harder to tamper with and lets a browser mark some pages only.
2. *The name.* `sensitive`, a placeholder like every other name before 1.0.
3. *"Does not send" or "should not send".* This draft makes the host's confirmation a requirement. A softer rule would let a host choose to ignore the mark.
4. *What Chrome's provider sends.* Every answer, or only pages it has a reason to mark (a sign-in, a checkout, mail). This draft leaves it to the provider; the first version of the Chrome provider would mark every answer, matching what Sirius does for Chrome today.
5. *Whether the first-party host keeps its own list* once providers mark themselves. This draft says a host may; Sirius would keep Mail, which it reads through Accessibility and which has no provider to speak for it.

## 10. Decision and outcome

Accepted on 2026.11.18 by Andrew Jones, maintainer, on the revision of commit `38a51f3`, for protocol version `0.2.4`. His words, as relayed by the sirius-claude session, were "looks good on the sensitive thing".

The open questions in section 9 stay open during implementation. It is built as the draft states: `sensitive` is declared on the answer, and a host may keep its own list.

One correction for the implementation: the specification already has a section 4.4 (watch, from RFC-0006), so the section this RFC calls "new 4.4" is written as 4.5.
