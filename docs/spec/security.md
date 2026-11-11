# Ambient Context Protocol · Rules

> Part of the [specification](index.md), version `0.1`.

## 9. Rules

### 9.1 — For providers

- **Answer only when asked.** Send nothing unprompted.
- **Answer from what you already hold.** `current` is answered from state the app has in memory, without waiting on disk or network.
- **Keep ids meaningful.** An id refers to the thing it was minted for, for as long as that thing exists and the app is running. An id for a text selection keeps referring to that passage after the user selects something else, and follows the passage through edits where it can. A provider does not reuse an id while it is running. When the thing is gone, answer `gone`.
- **Expose what the user would expect.** The provider chooses what to list. It leaves out anything the user would be surprised to see handed to an agent, such as the contents of a password field or a private window.

### 9.2 — For hosts

- **Ask on the user's action.** Read `current` when the user invokes the agent, not on a timer.
- **Ask the front app only.** Which app is in front is the host's knowledge, from the operating system; `focus` in a provider's answer says what has focus inside that app. A host passes the front app's context in full. A user asking about a paragraph in an editor does not expect their mail to go along.
- **Show what was collected.** Before a message is sent, the user must be able to see which context will go with it, and remove it.
- **Pass ids through unchanged.** When an agent names an item, use exactly the id the provider issued.
- **Keep the provider with the id.** Record which provider and which `instance` issued every id passed to an agent. When the agent names an id later, ask that provider only, and only if its instance is unchanged. If the provider has quit or restarted, treat the item as gone. Never look an id up again by app name or process id.
- **Removed means removed.** If the user removes context, or sends the message, while a provider's answer is still on its way, the late answer is discarded.
- **Never wait on a provider.** Set a time limit. If a provider does not answer, or answers `offscreen` or `gone`, carry on without the context or the placement.
