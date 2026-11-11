# Ambient Context Protocol · Discovery

> Part of the [specification](index.md), version `0.2.0`.

## 8. Discovery

A host has to find the provider for the app in front. Version 0.2.0 defines one way, for apps that can write a file in the user's Library folder.

A running provider writes one descriptor file and removes it at quit.

- **Folder.** `~/Library/Application Support/AmbientContext/providers/`, created with permissions `0700`.
- **File.** `<bundle-id>.<pid>.json`, permissions `0600`.

```json
{
  "protocol": "0.2.0",
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
| `app` | The app's bundle identifier, name and version. |
| `pid` | The provider's process id. |
| `instance` | The value the provider minted at this launch. The same value `current` returns. |
| `endpoint` | The MCP endpoint: `http://127.0.0.1:<port><path>`. The path is the provider's choice ([7.1](binding.md#71--the-server)). |
| `token` | The bearer token for this run. |
| `started` | When the provider started, in UTC. |

A provider writes the file after its listener is up, and writes it atomically: to a temporary name in the same folder, then renamed into place, so a host never reads half a file. At launch it removes any descriptor left by an earlier run of itself that did not exit cleanly. When the user has turned the provider off, it writes no file and opens no listener.

**What the host does:**

1. When the user invokes it, take the front app's process id from the operating system.
2. Look for a descriptor with that process id. Ignore a file whose process is no longer running, whose bundle identifier does not match the process, or whose `protocol` the host does not support.
3. Check the endpoint before using it. Its address must be `127.0.0.1`, and the process listening on its port must be the process the descriptor names. Ignore the descriptor otherwise. The path is used as given; a host does not assume `/mcp`.
4. Read `ambient://current` with the token and a time limit of the host's choosing, without following redirects. Ignore the answer if its `instance` or its `protocol` differs from the descriptor's. On any failure, carry on with no context.
5. To place something beside an element, read `ambient://location/<id>` from the same provider and instance that issued the id.

**What this defends against, and what it does not.** The folder and file permissions keep other users of the machine out. The token keeps out a program that can reach the port but cannot read the file. The check in step 3 keeps a descriptor from pointing a host at a server run by some other process. None of this defends against a hostile program already running as the user: it can read the token, and it can read the user's documents without this protocol. Version 0.2.0 states that limit and does not try to remove it. The token is also not consent: it shows that a caller can read the user's files, not that the user approved that caller. A host can additionally check the provider's code signature from its process id without any change to the format.

On a listener the app shares with other routes ([7.1](binding.md#71--the-server)), the port may be fixed and so easier to find than a random one. The token and the check in step 3 still hold: a program that takes the port first is not the process the descriptor names. A host checks the address in the descriptor; whether it can also confirm that the socket is bound to loopback only is an open question ([section 13](versioning.md#13-open-questions)).

**Apps that cannot do this.** A sandboxed Mac app can listen for connections when it has the network server entitlement, but it cannot write to a folder shared with other developers' apps, so it cannot publish a descriptor this way. A web page cannot listen at all. For these the open problem is discovery. One answer is a second mode in which the provider connects out to the host and the same resources are read over that connection; others may be simpler for sandboxed apps. None is designed yet.
