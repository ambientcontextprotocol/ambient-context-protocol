# RFC-0002 — A provider on a listener the app already has

> Let an app that already runs a local HTTP server answer Ambient Context requests on that server, at a path of its own, with the same three checks as today.

| Field | Value |
|---|---|
| Author | The protocol session, for Andrew Jones, at the request of a provider's author |
| Status | Released |
| Created | `2026.11.10` |
| Decided | `2026.11.10` |
| Discussion | Not yet opened as a pull request |
| Specification sections | 7.1 (the server), 8 (discovery, host step 3), 11 (implementing a provider) |
| Version effect | Additive |
| Supersedes or amends | None. Replaces an earlier idea of a provider with no token, which is withdrawn |
| Released in | `0.2.0` |

## 1. Summary

Version 0.1 says a provider listens "on a port the system assigns at launch", which reads as a listener opened for this protocol alone. Some apps already run a local MCP or HTTP server. This RFC lets such an app serve the Ambient Context endpoint from that server, at a path it chooses, provided the listener is bound to `127.0.0.1` only and the Ambient Context path checks the token and refuses `Origin` itself.

## 2. Motivation

An app with its own local server (an editor with an MCP server for agents, for example) would otherwise open a second port only to answer two resources. The earlier idea for these apps was a provider with no token, since their server is already open to any local program. That would have weakened the trust rule for every host. Mounting the endpoint on the existing listener gets the same result and changes no rule.

No current provider needs this: Paper, Sync and Threads have no server of their own. It is requested so that the packages and the specification do not push the next app toward a second port or toward asking for the no-token exception.

## 3. Proposal

The app keeps its server. It adds one route, for example `/ambient`, and hands every request on that route to the package's answering layer, which checks the token and the `Origin` header and answers the four MCP methods. The app writes the usual descriptor, with `endpoint` set to that route:

```json
{ "endpoint": "http://127.0.0.1:7801/ambient", "token": "q7Jm…" }
```

The host does what it does today. It already treats `endpoint` as an opaque address, checks that it is `127.0.0.1`, and checks that the process holding the port is the process the descriptor names. The one host that exists today needs no change: it uses the address as given.

Out of scope: a provider answered by a different process than the app (a browser extension's helper program, for example), and any provider without a token.

## 4. Specification changes

1. *7.1, Address.* Replace "on a port the system assigns at launch" with: the provider listens on `127.0.0.1` only. It may open a listener for this protocol on a port the system assigns, or use a listener the app already has. A listener bound to any other address, including all interfaces, must not carry the endpoint.
2. *7.1, new item, Path.* The endpoint is a single path. On a shared listener, the token and `Origin` rules of this section apply to that path and are enforced before any other handling the server applies to requests. The provider must not answer a cross-origin preflight (`OPTIONS`) on that path with permission.
3. *7.1, Authentication.* Add: the token is used for this endpoint only. It must not be a credential the app's server accepts elsewhere.
4. *8, host step 3.* No change in what is checked. Add a note that the path of `endpoint` is the provider's choice and the host uses it as given.
5. *11.* Add the second way to implement a provider: mount the answering layer on an existing server.

In the packages: the answering layer (`ContextResponder` in both) becomes public, takes the path as a setting instead of the fixed `/mcp`, and is documented as "one request in, one response out, token checked". The descriptor writer is already separate in the TypeScript package; the Swift one needs the same.

## 5. Compatibility

Additive. Every existing provider remains correct. A host written to 0.1 as specified already works, since it never assumed the path. A host that hard-codes `/mcp` instead of reading `endpoint` would be wrong under 0.1 as well.

## 6. Privacy and security

No new information leaves an app, and the set of callers is unchanged: whoever can read the descriptor's token. What changes is the listener's neighbors, and each brings a risk the dedicated listener did not have:

1. *A wider bind.* An existing server may listen on all interfaces. If the endpoint were mounted there, the token would be the only thing between the user's selection and the local network. Hence the rule in 4.1. A host checks that the address in the descriptor is `127.0.0.1`; whether it can also confirm that the socket is not bound more widely is unverified (open question 1).
2. *Shared middleware.* A server that adds permissive cross-origin headers to every response, or answers preflights globally, could undo the `Origin` refusal. Hence "before any other handling" in 4.2. This is the risk I rate highest, because it is easy to get wrong in common web frameworks and invisible in testing with a non-browser client.
3. *Logging.* Servers often log request headers or response bodies. On a shared listener that could write the token, or the user's selected text, to a log file. The specification should say a provider must not log either.
4. *A known port.* A fixed port is easier to find than a random one. The token and the host's process check still hold, and a program that takes the port first fails the host's step 3.
5. *Token reuse.* If the app's server has its own credential, using it as the Ambient Context token would publish it in the descriptor. Hence 4.3.

## 7. Conformance

An outside check can test, against a provider that declares a shared listener: the endpoint path refuses a request without the token (`401`); refuses any request carrying `Origin` (`403`), including `OPTIONS`; and returns no `Access-Control-Allow-*` header on any response from that path. It cannot test the bind address from the request side alone, or what the server logs; those stay as requirements on the implementer, marked unchecked.

## 8. Rationale, alternatives and prior art

- *A provider with no token.* Rejected: it makes the trust rule conditional on what else the app exposes, which a host cannot know.
- *Require a second port.* Works today and stays allowed. It costs each such app a listener and a second place to get the checks right.
- *Do nothing.* Reasonable for now, since no provider needs it. The cost of waiting is that the public answering layer in the packages would have no sentence in the specification behind it.
- *Prior art.* MCP's Streamable HTTP transport defines one endpoint path on a server that may serve other things, and asks local servers to validate `Origin` and bind to loopback.

## 9. Open questions

1. Can a host confirm from the process id and port that the socket is bound to loopback only, and should step 3 require it?
2. Should the descriptor say that the listener is shared, so a conformance check knows to run the extra tests? I lean no: run them against every provider.
3. Timing: with 0.2.0 (RFC-0001) rewriting the same sections, this is cheapest folded into that edit.

## 10. Decision and outcome

Accepted on 2026.11.10 by Andrew Jones, maintainer, for protocol version `0.2.0`, together with RFC-0001.

Why: it is additive, changes no trust rule, and replaces the proposal for a provider with no token. The open questions in section 9 stay open during implementation. Released in protocol version `0.2.0`.
