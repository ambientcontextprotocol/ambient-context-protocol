# RFC-0004 — A provider started by the app it answers for

> Let a helper program that an app started answer Ambient Context requests for that app, so that an app whose own process cannot listen, such as a browser reached through an extension, can still have a provider.

| Field | Value |
|---|---|
| Author | The Chrome provider session, for Andrew Jones; revised against `0.2.2` by the RFC-0004 session |
| Status | Accepted |
| Created | `2026.11.15` |
| Decided | `2026.11.18` |
| Discussion | Not yet opened as a pull request |
| Specification sections | 7.1 (the server), 8 (discovery: the descriptor, host steps 2 to 4, what this defends against), 8.2 (the favicon), 9.1 (rules for providers), 10 (changelog), 12 (not in this version), 13 (open questions) |
| Version effect | Additive: `0.2.2` to `0.2.3` |
| Supersedes or amends | None. Narrows "One program answering for another" in section 12 |
| Released in | — |

## 1. Summary

Version 0.2.2 requires the process that answers to be the app's own: a host accepts a descriptor only when the process listening on its port is the process in front. This RFC adds one optional field to the descriptor, `for`, naming an app the provider answers for, and one rule for when a host may accept it: the app in front has no descriptor of its own, and the provider's process was started by that app. Such a provider marks its answer as second-hand with the `via` attribute, and a provider that can read any site keeps a list of sites it never reads.

## 2. Motivation

A browser holds what a person is most often looking at, and nobody but its maker can add a listener to its process. Chrome does give extensions a supported way out: it starts a helper program for an extension and talks to it over standard input and output. The helper can listen on the loopback interface and write a descriptor. It is a different process from the browser, so a 0.2.2 host refuses it, correctly: without the process check, any program could write a descriptor saying it is the browser and hand an agent whatever it liked as the page in front.

"One program answering for another, such as a browser extension's helper" is listed under what 0.2.2 does not cover. This is that case. The first implementation is the Chrome provider in `providers/chrome/`; the first host is Sirius.

## 3. Proposal

A browser with process id 1054 starts a helper, process id 20311. The helper opens its listener and writes this descriptor:

```json
{
  "protocol": "0.2.3",
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

When the user invokes the host with the browser in front, the host looks for the browser's own descriptor, `com.google.Chrome.1054.json`, and finds none. It then looks for files named `com.google.Chrome.1054.for.<pid>.json`. For each it applies every check it applies to an app's own descriptor, with the helper in the app's place, and two more: `for` names the process in front, and the helper's parent process is the process in front. A helper that passes is read as any provider is. Its answer's root carries `"via": "browser-extension"` among its attributes, so a host can tell an agent that the page was reported by an extension and not by the browser.

Scope and exclusions:

- **The app must have started the helper.** A helper started by the user, at login, or by any other program is not accepted under this RFC, whatever its descriptor says. That case (a bridge to an app's local server, for example) needs a different ground for trust, such as the user's approval of a signed helper. It can use the same `for` field under a later RFC; nothing here decides it.
- **The app's own provider wins.** A host does not look for helpers when the app in front has a descriptor of its own, even one it refuses.
- **Direct parent only.** A process further down, started by something the app started, is not accepted.
- **No change to the operations or to the tree,** beyond the `via` attribute. A helper answers `current`, and may answer `locate` and offer `watch` as any provider may. A helper offers `watch` only if the app tells it of changes as they happen (section 9.1, "Know your own changes"); the Chrome helper does not, and offers no watch.
- **No change to who may ask.** A helper is behind the same token as any provider. A rule on the caller is left to a later RFC (section 9, question 2).

## 4. Specification changes

**Section 7.1.** The closing sentence, "A provider answered by a different process than the app, and a provider without a token, are not defined by this version", becomes: "A provider answered by a different process than the app is defined only for a process the app started ([section 8](../spec/discovery.md#8-discovery)). A provider without a token is not defined by this version."

**Section 8, the descriptor.** One row is added to the field table:

| Field | Meaning |
|---|---|
| `for` | Optional. Present only when the provider answers for an app that is not its own process. An object with `id`, that app's identifier on its platform, and `pid`, its process id. `app` and `pid` then describe the provider's own program and process. |

After the table:

> A provider that answers for another app writes `for` only when the process `for.pid` names started it: the operating system records that process as its parent. Its file is named `<for.id>.<for.pid>.for.<pid>.json`, with the same permissions as any descriptor. It removes the file when that app closes its connection to it or quits, and at launch it removes any such file left by an earlier run of itself for the same app.

**Section 8, what the host does.** Step 2 gains:

> If no file is named for the front app's process, look for files named `<app-id>.<pid>.for.<n>.json` for that process, where `<n>` is a process id. Ignore one whose `for` does not name the front app's identifier and process id, whose `pid` is not `<n>`, whose `pid` is the front app's own, whose process is no longer running, whose process was not started by the front app (the front app is not its direct parent), or whose `protocol` the host does not support. The file and folder permissions are checked as for any descriptor. A host does not look for these files when the front app has a descriptor of its own, even one it ignores.

Step 3 is applied to the provider's own `pid`: the process listening on the endpoint's port must be the process the descriptor names.

Step 4 gains:

> More than one such provider may pass, as when a browser runs one helper for each of its profiles. A host may bound how many it reads. It reads each within its one time limit and uses the answer whose tree has a focus path. If none has, it uses the first to answer.

**Section 8, what this defends against.** One paragraph is added, the substance of section 6 below: the parent check shows that the operating system recorded the front app as the process that started the provider, and that cannot be arranged after the fact by writing a file. It does not show that the app's maker wrote or approved the provider: any extension the user has installed can have a helper, and a program already running as the user can register one. The rule trusts what the user has installed in the app.

**Section 8.2.** The last paragraph, "A process that answers for an app it does not own has no bundle of that app to put a file in, and gets what step 3 gives. Answering for another program is not in this version", becomes: "A provider that answers for another app ([section 8](../spec/discovery.md#8-discovery)) has no bundle of that app to put a file in. A host takes the favicon from the front app, as step 1 says, never from the provider's program, and so for a browser gets what step 3 gives unless the browser ships one."

**Section 8.1, the macOS profile.** The row "How a host learns which app is in front and which process is listening on a port" becomes "How a host learns which app is in front, which process is listening on a port, and which process started another", with the same answer.

**Section 9.1.** Two rules for providers:

> - **Say when the answer is second-hand.** A provider that answers for another app sets `via` among the root's attributes: a short lowercase word for how it learned what it reports. `browser-extension` is the value for a browser extension's helper. A host reads a value it does not know as "second-hand, by an unknown route".
> - **Keep a list of sites never read.** A provider that can report any site, such as a browser's, keeps a list of sites whose pages it does not read, which the user can see and change. For a listed site it may name the page and reports nothing in it, not even the selection. The list starts with the sites where people sign in and keep passwords.

**Section 12.** "One program answering for another" is narrowed to "One program answering for another that the app did not start. A helper the app started is defined in section 8; one started by the user or another program needs a different ground for trust."

**Section 13.** Two open questions are added: whether a provider that can report any site should answer only callers the user approved, and the second ground for trust, for helpers the app did not start.

**Section 10, the changelog.** An entry for `0.2.3`, naming this RFC.

## 5. Compatibility

Additive: `0.2.2` to `0.2.3`. A host that does not know `for` never opens these files, because none is named for the front app's process alone; it finds no provider and carries on with no context, as it does today. A provider that does not use `for` is unaffected. `via` is an attribute, which a receiver that does not know it ignores. Under section 10 a new optional field is a patch.

A provider that answers for another app works only with hosts that implement this RFC.

## 6. Privacy and security

**What the parent check shows.** That the operating system recorded the app in front as the process that started the helper. A program cannot choose its parent after the fact, so a stray program cannot pass by writing a file. It does not show that the app's maker wrote or approved the helper. For a browser, any extension the user has installed can have a helper registered for it, and a program already running as the user can register one. So this rule trusts what the user has installed in the app. That is weaker than the rule for an app's own provider, and a host should let an agent know it: the `via` attribute is how.

**What it does not change.** A hostile program already running as the user is outside what the descriptor defends against, as in 0.2.2. It could read the token, and it could register a helper with the browser.

**What a helper can reach.** A browser helper can report the page in front on any site the extension may read. A provider answers any program that can read its token, which for an editor exposes the document being edited and for a browser exposes far more. This RFC does not add a check on the caller (section 9, question 2). It narrows what is reachable instead: the never-read list in 9.1, private windows left out under the existing rule, and the existing host rule that the user sees and can remove what is collected before it is sent.

**What the provider chooses to report.** Section 9.1 already says to leave out what the user would be surprised to see handed over. For a browser that includes private windows, password fields, text typed into forms, and any site on the never-read list. The Chrome provider's list starts with sign-in, password-manager and mail sites (section 9, question 5); the user can change it on the options page.

**Sensitive pages not on any list.** ACP issue #1 records an order confirmation page whose name, address and order number went with a message from Sirius without the user noticing. No list of sites would have caught it: the store is not a sign-in or mail site. The provider's list is a floor. The remedy for #1 is on the host's side, where 9.2 already requires that the user can see and remove what is collected, and where a warning before sending can be added; that is a host's business and not part of this RFC.

**A web page.** The `Origin` refusal is unchanged. The helper's endpoint is as closed to pages as any provider's.

## 7. Conformance

The outside check (`tools/conformance/check.py`), run on a descriptor with `for`, checks:

- `for` is an object with a string `id` and a positive integer `pid`, and `pid` is not the provider's own.
- The file is named `<for.id>.<for.pid>.for.<pid>.json`.
- The provider's parent process is `for.pid`.
- The root of the answer to `current` carries a `via` attribute that is a non-empty string.

Run with only an endpoint and token, it cannot tell a helper from an app's own provider and does not make these checks.

Requirements for [the product model](../pm.md), from `0.2.3`:

| Requirement | Statement | On | Check |
|---|---|---|---|
| PR-093 — Answering for the app that started it | A provider writes `for` only when the app it names is its parent process, names the file `<for.id>.<for.pid>.for.<pid>.json`, and removes it when that app closes its connection or quits. | Provider | Outside check |
| PR-094 — A helper is accepted only from its app | A host looks for a provider that answers for the front app only when that app has no descriptor of its own, and accepts one only when `for` names the front app and its process, the provider passes every check an app's own provider passes, and the front app is the provider's direct parent. It refuses one whose parent is any other process. | Host | The host's own tests, with a fake provider started by a stand-in for the app and one started by something else |
| PR-095 — Several helpers | When more than one provider answers for the front app, a host uses the answer whose tree has a focus path, or the first to answer if none has. | Host | The host's own tests |
| PR-096 — Second-hand is said | A provider that answers for another app sets `via` among the root's attributes. | Provider | Outside check, when run on the descriptor |
| PR-097 — Sites never read | A provider that can report any site keeps a list of sites whose pages it does not read, which the user can see and change, starting with sign-in and password sites. | Provider | Not checkable from outside; an inspection of the provider |
| PR-098 — Declared version, three places | A provider gives the same version, `0.2.3`, in the MCP extension, the descriptor and the `current` answer. Replaces PR-092. | Provider | Outside check |

PR-017 (descriptor) and PR-018 (descriptor fields) are unchanged: `for` is optional, and the file name of PR-017 holds for a provider that answers for itself.

## 8. Rationale, alternatives and prior art

- **Why the parent process.** It is a fact the operating system holds, it needs no knowledge of any one app, and it asks nothing of the user. It fits exactly the helpers that browsers start.
- **The user approves each helper, by code signature.** Sketched for a bridge to Figma's desktop server and for Zed. It covers helpers the app did not start, which this rule does not. It costs an approval step and a list of approved helpers in every host, and a signed helper. It is the natural second ground for trust and can share the `for` field.
- **The helper claims the app's process id.** Rejected: it fails the listener check by design, and is the impersonation that check exists to stop.
- **The host reads the browser itself**, through Accessibility or Apple Events. It needs nothing installed in the browser. It puts app-specific reading in the host, sees less (no tab ids, and the selection only after switching on a mode the browser keeps off for speed), and is the host's own business, outside the protocol.
- **The provider connects to the host instead.** The other open route for apps that cannot listen. A browser extension could open a socket to a host directly, with no helper. It needs a listener in every host and a way to tell which app connected, and is a larger change.
- **The provider says which helper is in front,** instead of the focus-path rule. Each helper of a browser with several profiles sees only its own profile's windows, so none can say that another's is in front; what each can say is whether one of its own windows has the keyboard, which is what a focus path already says.
- **Doing nothing.** Browsers stay without providers.

Drawback: the file name carries meaning (`.for.`), and a host now lists a folder where before it opened one file by name. The listing is confined to names that begin with the front app's identifier and process id.

## 9. Open questions

Before acceptance, each with the answer this revision proposes:

1. *Whether a browser's helper is always its direct child.* **Answered for Chrome.** On Chrome 157 on macOS, on 2026.11.15, the helper's parent was Chrome's main process directly, across a reload of the extension (helpers 33932 and 36761, parent 1054 both times). Chrome's documentation says it "starts each native messaging host in a separate process". Other Chromium browsers (Edge, Brave, Arc) are untested; a helper they start that is not their direct child is refused under this RFC, which fails closed.
2. *Whether the check on the caller can stay as it is for a provider that can report any site.* **Proposed:** yes for this RFC. The token stays the only check on the caller, as for every provider. What is reachable is narrowed instead by a never-read list a provider for any site must keep (9.1), on top of the existing rules on private windows and on the host showing what it collected. A rule on the caller, such as answering only hosts the user approved, is left to a later RFC and listed in section 13. Issue #1 is a host's matter (section 6) and does not wait on it.
3. *Whether `via` should be required, and whether its values should be listed.* **Proposed:** required for a provider that answers for another app, and checked from outside when the check is run on the descriptor. Values are open: a short lowercase word, with `browser-extension` named in the specification. A host reads an unknown value as second-hand by an unknown route.
4. *Whether the focus-path rule is the right way to choose among several helpers, or the provider should say which is in front.* **Proposed:** the focus-path rule, with a bound of the host's choosing on how many it reads. A helper cannot see another profile's windows, so it cannot say which is in front (section 8). Sirius implements the rule and reads at most 16.
5. *Whether mail sites are on the Chrome provider's never-read list by default.* A question for the provider, not the protocol, recorded here because it bears on issue #1. On 2026.11.15 Andrew said "honestly just think it should read gmail. i like the idea of a configurable never read list tho", and the list was cut to sign-in and password sites. This revision proposed keeping that. **Decided otherwise** (section 10): mail sites are on the list by default.

Can stay open during implementation:

6. Whether a helper may answer `locate`, since it would need the app's window position as well as the page's. The Chrome helper does not.
7. The second ground for trust, for helpers the app did not start.

## 10. Decision and outcome

Accepted on 2026.11.18 by Andrew Jones, maintainer, on the revision of commit `48e509d`, for protocol version `0.2.3`.

Why: a browser is where people most often are, it cannot carry a provider in its own process, and the parent check admits only a helper the browser itself started. Each of his answers to the open questions was given in the RFC-0004 session on 2026.11.18, as a choice among stated options:

- (2) Accepted with no new check on the caller. A provider that can report any site must keep a never-read list the user can change; a rule on the caller is left to a later RFC (section 13).
- (3) `via` is required for a provider that answers for another app, with open values; `browser-extension` is named.
- (4) The focus-path rule chooses among several helpers, with a bound of the host's choosing.
- (5) Mail sites are not read by default: his answer was "Don't read mail by default", reversing his call of 2026.11.15. The Chrome provider's default list gains the mail hosts again, before this lands.

Question 1 is answered for Chrome on macOS only; other Chromium browsers are untested and fail closed. Questions 6 and 7 stay open.
