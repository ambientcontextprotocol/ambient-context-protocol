# Ambient Context Protocol · Discovery

> Part of the [specification](index.md), version `0.2.2`.

## 8. Discovery

A host has to find the provider for the app in front. Version 0.2.2 defines one way, for apps that can write a file in a folder the user's other apps can read.

A running provider writes one descriptor file and removes it at quit.

- **Folder.** The platform's descriptor folder ([8.1](#81--platform-profiles)), created so that only the user can read or write it.
- **File.** `<app-id>.<pid>.json`, which only the user can read or write. `<app-id>` is the app's identifier on its platform and `<pid>` is the provider's process id.

```json
{
  "protocol": "0.2.2",
  "app": { "id": "org.example.editor", "name": "Editor", "version": "2.3.0" },
  "pid": 48211,
  "instance": "k3f9x2",
  "endpoint": "http://127.0.0.1:53124/mcp",
  "token": "q7Jm…",
  "started": "2026-11-09T21:14:03Z"
}
```

| Field | Meaning |
|---|---|
| `protocol` | The version of this protocol the provider speaks. The same value it declares in 7.2 and returns from `current`. |
| `app` | The app's identifier on its platform ([8.1](#81--platform-profiles)), its name and its version. |
| `pid` | The provider's process id. |
| `instance` | The value the provider minted at this launch. The same value `current` returns. |
| `endpoint` | The MCP endpoint: `http://127.0.0.1:<port><path>`. The path is the provider's choice ([7.1](binding.md#71--the-server)). |
| `token` | The bearer token for this run. |
| `started` | When the provider started, in UTC. |

A provider writes the file after its listener is up, and writes it atomically: to a temporary name in the same folder, then renamed into place, so a host never reads half a file. At launch it removes any descriptor left by an earlier run of itself that did not exit cleanly. When the user has turned the provider off, it writes no file and opens no listener.

**What the host does:**

1. When the user invokes it, take the front app's process id from the operating system.
2. Look for a descriptor with that process id. Ignore a file whose process is no longer running, whose app identifier does not match the process, or whose `protocol` the host does not support.
3. Check the endpoint before using it. Its address must be `127.0.0.1`, and the process listening on its port must be the process the descriptor names. Ignore the descriptor otherwise. The path is used as given; a host does not assume `/mcp`.
4. Read `ambient://current` with the token and a time limit of the host's choosing, without following redirects. Ignore the answer if its `instance` or its `protocol` differs from the descriptor's. On any failure, carry on with no context.
5. To place something beside an element, read `ambient://location/<id>` from the same provider and instance that issued the id.

**What this defends against, and what it does not.** Keeping the folder and the file to the user keeps other users of the machine out. The token keeps out a program that can reach the port but cannot read the file. The check in step 3 keeps a descriptor from pointing a host at a server run by some other process. None of this defends against a hostile program already running as the user: it can read the token, and it can read the user's documents without this protocol. Version 0.2.2 states that limit and does not try to remove it. The token is also not consent: it shows that a caller can read the user's files, not that the user approved that caller.

On a listener the app shares with other routes ([7.1](binding.md#71--the-server)), the port may be fixed and so easier to find than a random one. The token and the check in step 3 still hold: a program that takes the port first is not the process the descriptor names. A host checks the address in the descriptor; whether it can also confirm that the socket is bound to loopback only is an open question ([section 13](versioning.md#13-open-questions)).

**Apps that cannot do this.** An app that its platform keeps from writing to a folder shared with other developers' apps cannot publish a descriptor this way, and a web page cannot listen at all. For these the open problem is discovery. One answer is a second mode in which the provider connects out to the host and the same resources are read over that connection; others may be simpler for sandboxed apps. None is designed yet.

### 8.1 · Platform profiles

Sections 8 and 8.2 leave six things to the platform. A profile fixes them. Version 0.2.2 defines one profile, for macOS. A provider or host on a platform that has no profile cannot yet conform to section 8: it must not choose a folder of its own, because two hosts that guess differently would not find each other's providers. A profile for another platform is added by an RFC.

| A profile fixes | macOS |
|---|---|
| The descriptor folder | `~/Library/Application Support/AmbientContext/providers/` |
| How the folder and the file are kept to the user | The folder has permissions `0700` and the file `0600`. |
| The app's identifier | The bundle identifier. |
| How a host learns which app is in front and which process is listening on a port | From the operating system. The means are the host's choice. |
| Where an app ships its favicon ([8.2](#82--the-apps-favicon)) | In the app's bundle: `Contents/Resources/favicon.svg`, or `Contents/Resources/favicon.png` when there is no SVG. A host looks for them in that order. |
| The coordinate space of a location ([section 6](locations.md#6-locations)) | Global display coordinates, in points, with the origin at the top-left corner of the primary display and y increasing downward. This is the space the Accessibility API and Core Graphics use. AppKit's own coordinates have a bottom-left origin and must be converted. |

Two notes on the macOS profile:

- A sandboxed app can listen for connections when it has the network server entitlement, but it cannot write to the descriptor folder, so it is one of the apps that cannot publish a descriptor this way.
- A host can additionally check the provider's code signature from its process id without any change to the format.
- An app's bundle is covered by its code signature, so a favicon in it cannot be replaced by another program without breaking the signature. The descriptor folder has no such protection, which is why the favicon is not kept there.

### 8.2 · The app's favicon

A host that shows the user what it read ([4.3](operations.md#43--display)) may draw a small picture of the app beside the words. An app may ship one image made for that purpose, its favicon, at the place its platform's profile names ([8.1](#81--platform-profiles)). It is optional, and nothing in the descriptor or in any answer names it or carries it.

**What the app ships.** One image, SVG or PNG. It is drawn small, typically at 16 points, often on a dark surface: a simple shape in one light color reads best. A PNG is at least 32 by 32 pixels. An SVG is a static drawing: a host runs no script in it and loads nothing it refers to.

**What the host does:**

1. Take the installed app from the process it identified in section 8, step 1, and look for the file at the profile's place in it. A host never reads a favicon from a path, a URL or bytes that a provider or a descriptor names.
2. Read no more than a size limit of the host's choosing, and treat a file that is missing, larger than the limit or not a readable image as absent.
3. With no favicon, draw what it would for any app, such as the app's system icon, or nothing.

A process that answers for an app it does not own has no bundle of that app to put a file in, and gets what step 3 gives. Answering for another program is not in this version ([section 12](versioning.md#12-not-in-version-021)).
