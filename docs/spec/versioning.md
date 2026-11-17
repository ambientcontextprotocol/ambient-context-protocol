# Ambient Context Protocol · Versioning

> Part of the [specification](index.md), version `0.2.1`.

## 10. Versioning

The protocol has a version of three parts, `major.minor.patch`, sent as a string. This draft is `0.2.1`.

- **Where it appears.** In the descriptor's `protocol` field, in the extension's settings object in the provider's capabilities, and in the `protocol` field of the `current` result. A provider gives the same value in all three.
- **While the major version is 0,** a new minor version may change or remove anything, and a new patch version only adds: new optional fields, new roles, new values a receiver may ignore. A host and a provider work together only if they agree on the major and minor parts. A host may support more than one version at a time, choosing by the descriptor's `protocol` field. A host that does not support a provider's version treats the app as if it were not a provider.
- **From 1.0,** a minor version only adds: new optional fields, new resources, new values a receiver may ignore. Anything that would break an existing implementation takes a new major version.
- **Unknown fields are ignored.** A receiver must not fail on a field, a `subrole` or an `attributes` name it does not recognize. A `role` it does not recognize is read as `Group`.
- **MCP's version is separate.** Each request names the MCP revision it uses, and MCP's own rules settle that. This protocol's version says nothing about it, except that content blocks follow the MCP schema this version names (`2026-07-28` for `0.2.1`). A host skips block types it cannot handle.

Every change to this specification that alters behavior goes through the [RFC process](../rfcs/README.md), bumps the version and is listed in the changelog at the end.

## 12. Not in version 0.2.1

- **What changed.** A request for what changed since a point the host names ("a task was moved to tomorrow"), so an agent can resolve "what I just did."
- **Watching.** A provider telling the host when context, a location or the pointer's position changes. MCP resources already support subscriptions, so this needs no new mechanism, only a decision to allow it.
- **Other visible apps.** One line of context for each visible app that is not in front.
- **Actions.** A provider declaring operations an agent can run on an element.
- **Things that are not open.** Search over what the app holds but is not showing.
- **One program answering for another.** A provider answered by a different process than the app, such as a browser extension's helper. Such a process also has no place to ship a favicon ([8.2](discovery.md#82--the-apps-favicon)).
- **`display` for the agent.** Passing the app's wording ([4.3](operations.md#43--display)) on to the agent, so that it is told the words the user saw.
- **A provider with no token.**
- **Discovery for sandboxed and web apps.** See the end of section 8.
- **Profiles for other platforms.** Version 0.2.1 defines the macOS profile only ([8.1](discovery.md#81--platform-profiles)).

## 13. Open questions

1. Whether an agent can ask to locate something the provider did not list, such as lines 40 to 42 of an open file. This would need a way to mint an id for an address.
2. How long ids must stay valid after the app quits and reopens, if at all.
3. Limits. "Keep content small" is not something two implementations can agree on. The protocol needs stated bounds on the size of an element's content, the size and depth of a tree, and how many ids a provider must keep alive. To be set from what the first providers send.
4. Web apps: the page knows where an element is in the page, and only the browser knows where the page is on screen. Either the browser is the provider or something bridges the two.
5. The token in a file is not MCP's own authorization scheme, which is built on OAuth. MCP makes authorization optional and allows other strategies, so this is permitted, but it is not conformance with that scheme. Whether a local provider should offer it as well.
6. The final names: the extension identifier, the `ambient` address scheme, the descriptor folder and the protocol itself.
7. Which discovery mechanism a sandboxed app can use, and whether dial-in is needed for it or only for web pages.
8. The profiles for Windows and Linux: the descriptor folder, how it is kept to the user, the app's identifier, how a host makes the process checks in section 8, and the coordinate space. To be written with the first provider and host on each. Whether the role names, eleven of which are Apple's, read well to implementers on platforms that use other words for some of them.
9. Whether a host can confirm, from the process id and port, that a provider's socket is bound to loopback only, and whether discovery should require it.
10. Whether a provider should report `hovered` only once the pointer has rested for a moment. The current answer is no: the provider reports the fact and the host decides its weight.
11. Whether a touch-and-hold on a device with no pointer deserves the same state.

## Changelog

- `0.2.1` · `2026.11.17` · Additive. The answer to `current` may carry `display`, the app's own `title` and `detail` for the line a host shows the user ([4.3](operations.md#43--display)), and an app may ship a favicon at a place its platform's profile names, which a host finds itself and no message carries ([8.2](discovery.md#82--the-apps-favicon)) (RFC-0005). A `0.2.0` host and a `0.2.1` provider work together unchanged. The schema is `schema/current-0.2.1.json`.
- `0.2.0` · `2026.11.10` · Breaking. The flat list of items and the `focus` list are replaced by one tree of elements rooted at the app: thirteen roles, an optional `subrole`, and the states `selected`, `focused`, `visible` and `hovered` stated on the element (RFC-0001, RFC-0003). `type`, `parent`, `locatable`, `payload` and the answer's `app`, `items` and `focus` are removed; `attributes` replaces `payload`, and the answer carries `protocol`. A provider may serve the endpoint at a path of its own on a listener the app already has (RFC-0002). The version has three parts. Corrections to match what the packages do: `ping`, the order of the `Origin` and token checks, the `405`, `413` and `-32020` refusals, a request that names no MCP version, and how the extension is declared to older clients. The extension id is `io.github.ambientcontextprotocol/context`; `0.1` used `org.humanitas/ambient-context`. Before the tag, on `2026.11.16`, section 8 was restated for any platform and the macOS values moved into a profile in 8.1, with no change to what a provider or host on macOS does.
- `0.1` · `2026.11.09` · First version. Two operations, `current` and `locate`; items with MCP content blocks; locations. Carried as an MCP extension: two resources on a loopback MCP server, found through a descriptor file. Revised the same day after an adversarial review: provider instances, endpoint checks, the limits of the descriptor's protection, and corrected request metadata.
