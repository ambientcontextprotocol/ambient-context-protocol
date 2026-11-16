# RFC-0004 — A provider started by the app it answers for

> Let a helper program that an app started answer Ambient Context requests for that app, so that an app whose own process cannot listen, such as a browser reached through an extension, can still have a provider.

| Field | Value |
|---|---|
| Author | The Chrome provider session, for Andrew Jones |
| Status | Draft |
| Created | `2026.11.15` |
| Decided | |
| Discussion | Not yet opened as a pull request |
| Specification sections | 7.1 (the server), 8 (discovery: the descriptor, host steps 2 and 3), 9.2 (rules for hosts), 12 (not in this version) |
| Version effect | Additive |
| Supersedes or amends | None |
| Released in | — |

## 1. Summary

Version 0.2.0 requires the process that answers to be the app's own: a host accepts a descriptor only when the process listening on its port is the process in front. This RFC adds one optional field to the descriptor, `for`, naming an app the provider answers for, and one rule for when a host may accept it: the app in front has no descriptor of its own, and the provider's process was started by that app.

## 2. Motivation

A browser holds what a person is most often looking at, and nobody but its maker can add a listener to its process. Chrome does give extensions a supported way out: it starts a helper program for an extension and talks to it over standard input and output. The helper can listen on the loopback interface and write a descriptor. It is a different process from the browser, so a 0.2.0 host refuses it, correctly: without the process check, any program could write a descriptor saying it is the browser and hand an agent whatever it liked as the page in front.

"One program answering for another, such as a browser extension's helper" is listed under what 0.2.0 does not cover. This is that case. The first implementation is the Chrome provider in `providers/chrome/`.

## 3. Proposal

A browser with process id 1054 starts a helper, process id 20311. The helper opens its listener and writes this descriptor:

```json
{
  "protocol": "0.2.0",
  "app": { "id": "io.github.ambientcontextprotocol.chrome", "name": "Ambient Context for Chrome", "version": "0.1.0" },
  "pid": 20311,
  "for": { "id": "com.google.Chrome", "pid": 1054 },
  "instance": "k3f9x2",
  "endpoint": "http://127.0.0.1:53124/mcp",
  "token": "q7Jm…",
  "started": "2026-11-15T21:14:03Z"
}
```

under the name `com.google.Chrome.1054.for.20311.json`.

`app` and `pid` describe the helper, as they describe any provider, so the existing check still proves who is listening. `for` names the app whose context the helper reports.

When the user invokes the host with the browser in front, the host looks for the browser's own descriptor, `com.google.Chrome.1054.json`, and finds none. It then looks for files named `com.google.Chrome.1054.for.<pid>.json`. For each it applies every check it applies to an app's own descriptor, with the helper in the app's place, and two more: `for` names the process in front, and the helper's parent process is the process in front. A helper that passes is read as any provider is.

Scope and exclusions:

- **The app must have started the helper.** A helper started by the user, at login, or by any other program is not accepted under this RFC, whatever its descriptor says. That case (a bridge to an app's local server, for example) needs a different ground for trust, such as the user's approval of a signed helper. It can use the same `for` field under a later RFC; nothing here decides it.
- **The app's own provider wins.** A host does not look for helpers when the app in front has a descriptor of its own, even one it refuses.
- **Direct parent only.** A process further down, started by something the app started, is not accepted.
- **No change to the operations or to the tree.** A helper answers `current` and, if it can, `locate`, as any provider does.

## 4. Specification changes

**Section 7.1.** The closing sentence, "A provider answered by a different process than the app, and a provider without a token, are not defined by this version", becomes: "A provider answered by a different process than the app is defined only for a process the app started (section 8). A provider without a token is not defined by this version."

**Section 8, the descriptor.** One row is added to the field table:

| Field | Meaning |
|---|---|
| `for` | Optional. Present only when the provider answers for an app that is not its own process. An object with `id`, the bundle identifier of that app, and `pid`, its process id. `app` and `pid` then describe the provider's own program and process. |

A descriptor with `for` is named `<for.id>.<for.pid>.for.<pid>.json`. A provider writes `for` only when the process `for.pid` names is its parent. It removes the descriptor when that app closes its connection to it or quits.

**Section 8, what the host does.** Step 2 gains:

> If no file is named for the front app's process, look for files named `<bundle-id>.<pid>.for.<n>.json` for that process, where `<n>` is a process id. Ignore one whose `for` does not name the front app's bundle identifier and process id, whose `pid` is not `<n>`, whose `pid` is the front app's own, whose process is no longer running, whose process was not started by the front app (the front app is not its parent), or whose `protocol` the host does not support. The file and folder permissions are checked as for any descriptor.

Step 3 is applied to the provider's own `pid`: the process listening on the endpoint's port must be the process the descriptor names.

Step 4 gains:

> More than one such provider may pass, as when a browser runs one helper for each of its profiles. A host reads each within its one time limit and uses the answer whose tree has a focus path. If none has, it uses the first to answer.

**Section 8, what this defends against.** One paragraph is added, the text of section 6 below on what the parent check does and does not show.

**Section 9.1.** One rule for providers: "**Say when the answer is second-hand.** A provider that answers for another app sets `via` among the root's attributes to a short word for how it learned what it reports, such as `browser-extension`."

**Section 9.2.** "Keep the provider with the id" is unchanged and applies to the helper: an id is asked of the provider and instance that issued it.

**Section 12.** "One program answering for another" is narrowed to "One program answering for another that the app did not start."

## 5. Compatibility

Additive. A host that does not know `for` never opens these files, because none is named for the front app's process alone; it finds no provider and carries on with no context, as it does today. A provider that does not use `for` is unaffected. Under section 10 a new optional field is a patch, so this would be `0.2.1`.

A provider that answers for another app works only with hosts that implement this RFC.

## 6. Privacy and security

**What the parent check shows.** That the operating system recorded the app in front as the process that started the helper. A program cannot choose its parent after the fact, so a stray program cannot pass by writing a file. It does not show that the app's maker wrote or approved the helper. For a browser, any extension the user has installed can have a helper registered for it, and a program already running as the user can register one. So this rule trusts what the user has installed in the app. That is weaker than the rule for an app's own provider, and a host should let an agent know it: the `via` attribute is how.

**What it does not change.** A hostile program already running as the user is outside what the descriptor defends against, as in 0.2.0. It could read the token, and it could register a helper with the browser.

**What a helper can reach.** A browser helper can report what the user selects on any site. A provider answers any program that can read its token, which for an editor exposes the document being edited and for a browser exposes far more. This RFC does not add a check on the caller. It is the sharpest open question (section 9), and a provider for a browser should not be given to other people's machines before it is answered.

**What the provider chooses to report.** Section 9.1 already says to leave out what the user would be surprised to see handed over. For a browser that includes private windows, password fields, and any site the user has said not to read.

**A web page.** The `Origin` refusal is unchanged. The helper's endpoint is as closed to pages as any provider's.

## 7. Conformance

The outside check (`tools/conformance/check.py`) accepts a descriptor with `for`, and checks:

- `for` is an object with a string `id` and a positive `pid`.
- The file is named `<for.id>.<for.pid>.for.<pid>.json`.
- The provider's parent process is `for.pid`.

Proposed requirements for `docs/pm.md`, not yet added: a provider writes `for` only when the app it names started it; a host accepts such a descriptor only when the app in front has none of its own and is the provider's parent; a host refuses it when the parent is any other process. The host requirements are checked in the host's own tests, with a fake provider started by a stand-in for the app.

Not checkable from outside: that the root carries `via`, since the check cannot tell a helper's tree from an app's own except by the descriptor.

## 8. Rationale, alternatives and prior art

- **Why the parent process.** It is a fact the operating system holds, it needs no knowledge of any one app, and it asks nothing of the user. It fits exactly the helpers that browsers start.
- **The user approves each helper, by code signature.** Sketched for a bridge to Figma's desktop server and for Zed. It covers helpers the app did not start, which this rule does not. It costs an approval step and a list of approved helpers in every host, and a signed helper. It is the natural second ground for trust and can share the `for` field.
- **The helper claims the app's process id.** Rejected: it fails the listener check by design, and is the impersonation that check exists to stop.
- **The host reads the browser itself**, through Accessibility or Apple Events. It needs nothing installed in the browser. It puts app-specific reading in the host, sees less (no tab ids, and the selection only after switching on a mode the browser keeps off for speed), and is the host's own business, outside the protocol.
- **The provider connects to the host instead.** The other open route for apps that cannot listen. A browser extension could open a socket to a host directly, with no helper. It needs a listener in every host and a way to tell which app connected, and is a larger change.
- **Doing nothing.** Browsers stay without providers.

Drawback: the file name carries meaning (`.for.`), and a host now lists a folder where before it opened one file by name. The listing is confined to names that begin with the front app's identifier and process id.

## 9. Open questions

Before acceptance:

1. Whether a browser's helper is always its direct child. Chrome's documentation says Chrome "starts each native messaging host in a separate process"; that the parent is the browser's main process is to be confirmed on a running browser, and for other Chromium browsers.
2. Whether the check on the caller can stay as it is for a provider that can report any site, or whether this RFC must wait for one.
3. Whether `via` should be required, and whether its values should be listed.
4. Whether the focus-path rule is the right way to choose among several helpers, or the provider should say which is in front.

Can stay open during implementation:

5. Whether a helper may answer `locate`, since it would need the app's window position as well as the page's.
6. The second ground for trust, for helpers the app did not start.

## 10. Decision and outcome

Pending.
