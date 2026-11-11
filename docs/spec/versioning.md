# Ambient Context Protocol · Versioning

> Part of the [specification](index.md), version `0.1`.

## 10. Versioning

The protocol has a version of the form `major.minor`, sent as a string. This draft is `0.1`.

- **Where it appears.** In the descriptor's `protocol` field, and in the extension's settings object in the provider's capabilities.
- **While the major version is 0,** any minor version may change or remove anything. A host and a provider work together only if they agree on the exact version. A host that does not support a provider's version treats the app as if it were not a provider.
- **From 1.0,** a minor version only adds: new optional fields, new resources, new values a receiver may ignore. Anything that would break an existing implementation takes a new major version.
- **Unknown fields are ignored.** A receiver must not fail on a field, an item `type` or a `payload` key it does not recognize.
- **MCP's version is separate.** Each request names the MCP revision it uses, and MCP's own rules settle that. This protocol's version says nothing about it, except that content blocks follow the MCP schema this version names (`2026-07-28` for `0.1`). A host skips block types it cannot handle.

Every change to this document that alters behavior bumps the version and is listed in the changelog at the end.

## 12. Not in version 0.1

- **What changed.** A request for what changed since a point the host names ("a task was moved to tomorrow"), so an agent can resolve "what I just did."
- **Watching.** A provider telling the host when context or a location changes. MCP resources already support subscriptions, so this needs no new mechanism, only a decision to allow it.
- **Other visible apps.** One line of context for each visible app that is not in front.
- **Actions.** A provider declaring operations an agent can run on an item.
- **Discovery for sandboxed and web apps.** See the end of section 8.
- **Other platforms.** Coordinates and the descriptor folder are defined for macOS only.

## 13. Open questions

1. Whether an agent can ask to locate something the provider did not list, such as lines 40 to 42 of an open file. This would need a way to mint an id for an address.
2. How long ids must stay valid after the app quits and reopens, if at all.
3. Limits. "Keep content small" is not something two implementations can agree on. The protocol needs stated bounds on the size of an item's content, the number of items in one answer, and how many ids a provider must keep alive.
4. Web apps: the page knows where an element is in the page, and only the browser knows where the page is on screen. Either the browser is the provider or something bridges the two.
5. The token in a file is not MCP's own authorization scheme, which is built on OAuth. MCP makes authorization optional and allows other strategies, so this is permitted, but it is not conformance with that scheme. Whether a local provider should offer it as well.
6. The final names: the extension identifier, the `ambient` address scheme, the descriptor folder and the protocol itself.
7. Which discovery mechanism a sandboxed Mac app can use, and whether dial-in is needed for it or only for web pages.
8. Windows and Linux: the descriptor folder, the process checks in section 8 and the coordinate space are all defined for macOS only. Version 0.1 is a macOS profile, not yet a cross-platform protocol.

## Changelog

- `0.1` · `2026.11.09` · First version. Two operations, `current` and `locate`; items with MCP content blocks; locations. Carried as an MCP extension: two resources on a loopback MCP server, found through a descriptor file. Revised the same day after an adversarial review: provider instances, endpoint checks, the limits of the descriptor's protection, and corrected request metadata.
