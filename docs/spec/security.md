# Ambient Context Protocol · Rules

> Part of the [specification](index.md), version `0.2.2`.

## 9. Rules

### 9.1 — For providers

- **Answer only when asked.** Send nothing unprompted.
- **Answer from what you already hold.** `current` is answered from state the app has in memory, without waiting on disk or network.
- **Keep ids meaningful.** An id refers to the element it was minted for, for as long as that thing exists and the app is running. An id for a text selection keeps referring to that passage after the user selects something else, and follows the passage through edits where it can. A provider does not reuse an id while it is running. When the thing is gone, answer `gone`.
- **Say each state once.** `selected`, `focused`, `visible` and `hovered` are stated on the element they describe and nowhere else ([5.3](elements.md#53--states)).
- **Expose what the user would expect.** The provider chooses what to report. It leaves out anything the user would be surprised to see handed to an agent, such as the contents of a password field or a private window. A tree does not change this: it is not a reason to report more of what is open than a list was ([5.7](elements.md#57--what-to-report)).
- **Name an author only where the app does.** The `author` attribute attaches a person's name to content. A provider sends it only where the app already shows it.
- **Say no more in `display` than in the tree.** `display` ([4.3](operations.md#43--display)) labels the answer it is in. It holds no content the provider does not report as an element, and names nothing from an element the provider left out.
- **Keep the token and answers out of logs.** A provider does not write its token, or anything from an answer, to a log.

### 9.2 — For hosts

- **Ask on the user's action.** Read `current` when the user invokes the agent, not on a timer.
- **Ask the front app only.** Which app is in front is the host's knowledge, from the operating system; the `focused` path in a provider's answer says what has focus inside that app. A host passes the front app's context in full. A user asking about a paragraph in an editor does not expect their mail to go along.
- **Show what was collected.** Before a message is sent, the user must be able to see which context will go with it, and remove it.
- **A label is not the context.** `display` ([4.3](operations.md#43--display)) is the app's wording for what was collected. A host that shows it still lets the user remove the context it labels, draws it as plain text from another program, and never refuses an answer because `display` is missing or malformed.
- **Find the favicon yourself.** A host reads an app's favicon only from the profile's place in the installed app whose process it identified ([8.2](discovery.md#82--the-apps-favicon)), never from a place a provider names.
- **Pass ids through unchanged.** When an agent names an element, use exactly the id the provider issued.
- **Keep the provider with the id.** Record which provider and which `instance` issued every id passed to an agent. When the agent names an id later, ask that provider only, and only if its instance is unchanged. If the provider has quit or restarted, treat the element as gone. Never look an id up again by app name or process id.
- **Removed means removed.** If the user removes context, or sends the message, while a provider's answer is still on its way, the late answer is discarded.
- **Read absent states as defined.** An absent `selected`, `focused` or `hovered` is false; an absent `visible` is the parent's value. An absent `hovered` everywhere means nothing: the provider may not track the pointer.
- **Hover is weaker than selection.** The pointer is wherever it was last left, and may rest on something the user never meant to indicate. A host presents `hovered` to an agent as where the pointer is, distinct from and weaker than `selected`. A host does not send more of an element's content because it is hovered than it would otherwise send.
- **Never wait on a provider.** Set a time limit. If a provider does not answer, or answers `offscreen` or `gone`, carry on without the context or the placement.
