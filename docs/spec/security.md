# Ambient Context Protocol · Rules

> Part of the [specification](index.md), version `0.2.4`.

## 9. Rules

### 9.1 — For providers

- **Send nothing a host did not ask for.** A provider answers requests. A notice on a watch a host opened ([4.4](operations.md#44--watch)) is asked for; nothing else is sent.
- **Know your own changes.** A provider that offers `watch` learns that its answer changed from the app's own events: a selection changed, a document opened. It does not find changes by rebuilding its answer on a timer, which is polling moved into the app.
- **Gather notices.** At most one notice in any 250 milliseconds on one watch, and the last change always produces a notice. A provider may delay a notice; it never drops the final one. A change in `hovered` alone produces none.
- **Say nothing in a notice.** A notice carries the address and the subscription id, and nothing from the app.
- **Keep quiet watches alive.** On a watch with nothing to say, send a comment line at least every 15 seconds, so a host can tell a quiet provider from a dead one.
- **Bound the watches.** A provider may limit how many watches it holds at once, to no fewer than four, and may end any watch at any time, in particular one that has been open longer than ten minutes. It ends them all when it quits and when the user turns the provider off.
- **Answer from what you already hold.** `current` is answered from state the app has in memory, without waiting on disk or network.
- **Keep ids meaningful.** An id refers to the element it was minted for, for as long as that thing exists and the app is running. An id for a text selection keeps referring to that passage after the user selects something else, and follows the passage through edits where it can. A provider does not reuse an id while it is running. When the thing is gone, answer `gone`.
- **Say each state once.** `selected`, `focused`, `visible` and `hovered` are stated on the element they describe and nowhere else ([5.3](elements.md#53--states)).
- **Expose what the user would expect.** The provider chooses what to report. It leaves out anything the user would be surprised to see handed to an agent, such as the contents of a password field or a private window. A tree does not change this: it is not a reason to report more of what is open than a list was ([5.7](elements.md#57--what-to-report)).
- **Say when the answer is second-hand.** A provider that answers for another app ([section 8](discovery.md#8-discovery)) sets `via` among the root's attributes: a short lowercase word for how it learned what it reports. `browser-extension` is the value for a browser extension's helper. A host reads a value it does not know as "second-hand, by an unknown route".
- **Keep a list of sites never read.** A provider that can report any site, such as a browser's, keeps a list of sites whose pages it does not read, which the user can see and change. For a listed site it may name the page and reports nothing in it, not even the selection. The list starts with the sites where people sign in and keep passwords.
- **Name an author only where the app does.** The `author` attribute attaches a person's name to content. A provider sends it only where the app already shows it.
- **Say no more in `display` than in the tree.** `display` ([4.3](operations.md#43--display)) labels the answer it is in. It holds no content the provider does not report as an element, and names nothing from an element the provider left out.
- **Redact what you report.** Removing or masking private details inside what it reports is the provider's job. The app knows which of its content is private, and it reports only what should leave it. A provider does not rely on a host to inspect, classify or clean an answer: none is required to ([9.2](#92--for-hosts)).
- **Marking is not leaving out.** `sensitive` ([4.5](operations.md#45--sensitive)) marks content the provider is right to report and the user may not want sent. It does not replace leaving things out: what a provider must never report, it still never reports, because a host written before `0.2.4` ignores the mark. A provider sends it only as `true` and never sends `false` to claim an answer is safe.
- **Keep the token and answers out of logs.** A provider does not write its token, or anything from an answer, to a log.

### 9.2 — For hosts

- **Ask on the user's action.** Read `current` when the user invokes the agent, not on a timer. After such a read, and only while the host is showing the user that provider's context, it may hold one watch on that provider ([4.4](operations.md#44--watch)) and read `current` again when a notice arrives. It reads at no other time.
- **One watch, one provider, in view.** A host opens a watch only on the provider it has just read on the user's action. It holds one at a time, however many of its interfaces show that context, and ends it when the message is sent, the context is removed or its interface closes. It does not watch an app the user is not being shown context from.
- **A notice is not context.** A host learns the new state only by reading `current`, with every check a read has, the instance check included.
- **One read per notice, at most.** A host that gets a notice while a read is outstanding finishes that read and reads once more. It never has two reads outstanding.
- **A lost watch is silence.** If a watch's stream ends or fails, the host carries on with what it last read, shows the user no error, and may try to open the watch again once. It still reads at send.
- **Ask the front app only.** Which app is in front is the host's knowledge, from the operating system; the `focused` path in a provider's answer says what has focus inside that app. A host passes the front app's context in full. A user asking about a paragraph in an editor does not expect their mail to go along.
- **Show what was collected.** Before a message is sent, the user must be able to see which context will go with it, and remove it.
- **A label is not the context.** `display` ([4.3](operations.md#43--display)) is the app's wording for what was collected. A host that shows it still lets the user remove the context it labels, draws it as plain text from another program, and never refuses an answer because `display` is missing or malformed.
- **Find the favicon yourself.** A host reads an app's favicon only from the profile's place in the installed app whose process it identified ([8.2](discovery.md#82--the-apps-favicon)), never from a place a provider names.
- **Ask before sending what an app marked sensitive.** A host that holds an answer with `"sensitive": true` ([4.5](operations.md#45--sensitive)) does not send that context to an agent, or anywhere off the device, until the user has confirmed that send knowing which app it came from, or has earlier told the host not to ask for that app. A host with no way to ask leaves the context out and tells the user it did. The user's choice not to be asked is kept per app, for the app answered for when a helper answers, and can be undone.
- **Redaction is the provider's.** A host is not required to inspect, classify or redact the content of an answer. `sensitive` asks a host for the user's confirmation, not to clean the answer. A host may still do more as a feature of its own.
- **No mark is not a clearance.** Only the JSON value `true` marks an answer; `false`, a missing field and any other type are read as absent, and never cause a host to refuse the answer. A host never reads the absence of `sensitive`, or `"sensitive": false`, as a reason to skip a warning it would otherwise give.
- **Pass ids through unchanged.** When an agent names an element, use exactly the id the provider issued.
- **Keep the provider with the id.** Record which provider and which `instance` issued every id passed to an agent. When the agent names an id later, ask that provider only, and only if its instance is unchanged. If the provider has quit or restarted, treat the element as gone. Never look an id up again by app name or process id.
- **Removed means removed.** If the user removes context, or sends the message, while a provider's answer is still on its way, the late answer is discarded.
- **Read absent states as defined.** An absent `selected`, `focused` or `hovered` is false; an absent `visible` is the parent's value. An absent `hovered` everywhere means nothing: the provider may not track the pointer.
- **Hover is weaker than selection.** The pointer is wherever it was last left, and may rest on something the user never meant to indicate. A host presents `hovered` to an agent as where the pointer is, distinct from and weaker than `selected`. A host does not send more of an element's content because it is hovered than it would otherwise send.
- **Never wait on a provider.** Set a time limit. If a provider does not answer, or answers `offscreen` or `gone`, carry on without the context or the placement.
