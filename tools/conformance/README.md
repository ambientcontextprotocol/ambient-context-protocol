# The outside check

> A script that tests any running Ambient Context Protocol provider from outside, and a fake provider for testing a host. Both are for version `0.2.2` and need only Python 3 and its standard library.

## What it is

`check.py` sends requests to a running provider, as a host would, and judges the answers against the requirements in [`docs/pm.md`](../../docs/pm.md). It needs nothing from the provider but what a host gets: the descriptor file, or the endpoint and token. It works the same on a provider built with one of the packages here and on one written from the specification alone, in any language.

`fake_provider.py` is a small provider that serves one valid tree, offers `watch`, and changes the tree only when told to. It can also be started with a fault, which makes it break exactly one requirement. That is how the check is tested, and it gives a host something to be tested against: a host should refuse or survive every one of the faults.

`test_check.py` starts the fake provider, confirms the check passes it clean, and confirms that each fault is caught under the right requirement and that nothing else is reported. It also drives the fake provider while a watch is open, for the rules the check cannot reach from outside.

## Checking your own app

Start your app with its provider turned on, find its descriptor, and pass the path:

```sh
python3 tools/conformance/check.py ~/Library/Application\ Support/AmbientContext/providers/<bundle-id>.<pid>.json
```

The check reads the descriptor and never writes to that folder. If your provider has no descriptor yet, give the endpoint and token instead. The descriptor checks are then left out, and the instance is compared only if you give it:

```sh
python3 tools/conformance/check.py --endpoint http://127.0.0.1:53124/mcp --token <token> --instance <instance> --pid <pid>
```

A token given on the command line can be seen by other programs of yours while the check runs, in the process list. Prefer the descriptor path.

Each check prints one line: the outcome, the requirement it tests, a short name and a detail.

```
PASS  PR-032  token-missing     no Authorization header: HTTP 401, no body
FAIL  PR-053  hovered-single    2 elements are hovered: element 'link-1', element 'img-1'
WARN  PR-026  ping              not answered (HTTP 404, error -32601); a provider should answer ping
SKIP  PR-011  locate-issued     the provider does not offer locate
```

`FAIL` is a requirement the provider breaks, and the script exits with status 1 if there is any. `WARN` is something the specification says a provider should do and this one does not, or an answer slower than `--slow` seconds; it does not change the exit status. `SKIP` is a check that did not apply, such as the `locate` checks for a provider that does not report positions. `--json` prints the same results for a program to read. `--timeout` sets how long each request may take, `--locate-limit` how many ids `locate` is asked about, and `--watch-hold` how long the watch is held open.

Put your app in an interesting state before running it: something selected, the cursor somewhere, the pointer over a reported element, more than one window open. The check judges the one answer it gets.

If your provider offers `watch`, the check opens one and holds it for two seconds. Select something else in your app during those two seconds and the check judges the notices it gets; change nothing and it says that no change happened while watching, and passes. Two seconds is too short to judge the keep-alive rule, which allows 15 seconds of silence, so that check is skipped by default and says so. Before you call your provider done, run the check once with `--watch-hold 20` and leave the app alone: it takes 20 seconds longer and judges the keep-alive. The default is short because the check is run many times while a provider is being written, and a run that takes 20 seconds each time would be run less often.

```sh
python3 tools/conformance/check.py <descriptor.json> --watch-hold 20
```

## What is printed, and what is not

The check is meant to be pointed at real apps holding private documents, so its output can be pasted into an issue. It never prints the token, the instance, or any element's title, content, url or attributes. A result holds element ids, role names, counts, times, HTTP status codes and JSON-RPC error codes, and nothing else from the provider. Nothing a watch's stream carries is printed either: a notice that holds more than it should is reported as a count of extra fields. An element whose id is malformed is named by its position in the tree, such as `root/0/2`, and a role or version that is not a plain word is not printed at all.

The token is sent only to this machine. If a descriptor's endpoint names any other host, the check reports that and sends no request.

## What it checks

- *The descriptor,* when a path is given: the seven fields, the file's name, mode `0600` on the file and `0700` on its folder, a running process, protocol `0.2.2`, an endpoint at `127.0.0.1` with a path and no query or fragment (PR-017, PR-018, PR-019, PR-020, PR-028, PR-031, PR-062).
- *Refusals:* no token and a wrong token get `401`; any `Origin` header gets `403` with no body, before the token is judged and on `OPTIONS` too; a method other than `POST` gets `405`; an oversized request gets `413`; no response carries an `Access-Control-Allow-*` header (PR-032, PR-033, PR-063, PR-065).
- *MCP's request rules:* a body that is not a request, a missing `protocolVersion` or `clientCapabilities`, headers that are missing or disagree with the body, an unknown method and an unknown MCP version each get the status and error code in section 7.4 (PR-026, PR-064, PR-065).
- *Declaring and listing:* `server/discover` names MCP `2026-07-28` and declares the extension with version `0.2.2`; `resources/list` lists `ambient://current`; `resources/templates/list` answers; reading `ambient://current` returns one `application/json` entry (PR-024, PR-026, PR-092).
- *The answer:* `protocol`, `instance` and `root`, optionally `display`, and nothing else; the protocol is `0.2.2` and the instance is the descriptor's; a `display` that is sent is an object whose `title` and `detail` are each a string on one line of at most 80 characters; every element has the fields, types, id form, role and content blocks that [`schema/current-0.2.2.json`](../../schema/current-0.2.2.json) requires; and the three rules the schema cannot state: ids are unique, the focused elements form one unbroken path, and at most one element is hovered (PR-005, PR-040, PR-072, PR-048, PR-049, PR-050, PR-051, PR-053, PR-059, PR-092).
- *Locations,* when the provider offers them: each id in the answer gets a well-formed location or the "cannot place" error, and an id never issued gets the error (PR-011, PR-060).
- *Watching,* when the provider declares `resources.subscribe`: `subscriptions/listen` for `ambient://current` is answered with an event stream whose first message is the acknowledgment, carrying the request's id and naming that address alone; a filter that also asks for a location and for list changes is acknowledged for `ambient://current` alone (PR-080). A filter that does not name `ambient://current` is refused with `400` and `-32602`; this is reported under PR-082, since a provider that opened a watch for it would be sending what the host did not ask for. The watch request with no token or a wrong one gets `401`, and with an `Origin` header `403`, with no stream (PR-087). While the watch is held, every message on it is the acknowledgment, a notice (`notifications/resources/updated` for `ambient://current` with the subscription id and no other field), or the completion result (PR-082); no two notices arrive less than 250 ms apart, less 50 ms for scheduling (PR-083); and, when the watch is held longer than 15 seconds, a comment line or a notice arrives at least every 15 seconds, plus a quarter second for scheduling (PR-085).
- *Not watching,* when the provider declares no `subscribe`: `subscriptions/listen` is answered `404` with `-32601` (PR-081), and the watch checks above are skipped. A provider that declares `subscribe` and does not open the stream fails PR-080; one that opens the stream without declaring it fails PR-081.
- *Older clients:* `ping` is answered, the `initialize` handshake is answered and declares the extension under `capabilities.experimental`, and a client that sends nothing in `_meta` can list and read (PR-025, PR-026, PR-092). A provider that offers neither `ping` nor the handshake is warned, not failed.

The tree is validated by hand in `check.py`, so that the check needs no package. `tools/check-schema.py` validates the specification's examples against the schema itself and needs `jsonschema`.

## What it cannot check

A check that only sends requests sees what a provider answers. It does not see what the provider is. These requirements stay with the implementer, and passing this check says nothing about them.

- *The bind address.* The check confirms that the descriptor names `127.0.0.1`. It cannot tell from a request whether the socket is bound to loopback only or to every interface (PR-031). Inspect the listener yourself, for example with `lsof -nP -iTCP -sTCP:LISTEN`.
- *Logging.* Whether the token or anything from an answer is written to a log (PR-070) cannot be seen from outside.
- *Display and the favicon.* The check confirms the shape of `display` (PR-074). It cannot tell whether `display` names only what the tree holds (PR-075), and it does not look for a favicon file (PR-078): it is given an endpoint, not an app. What a host does with either (PR-076, PR-077, PR-079) is host conduct. To test a host's reader, start the fake provider with `--no-display` or with one of the `display-` faults: the host should fall back to its own wording and still use the tree.
- *Whether the answer is true.* The check confirms that at most one element is hovered, not that the pointer is over it (PR-054). The same holds for `selected`, `focused` and `visible`, for whether rectangles match the screen (PR-012, PR-013), and for whether the provider reports what the user would expect and no controls or window furniture (PR-049, PR-056, PR-057, PR-058). A provider's own test must place the pointer or the selection and read the answer.
- *Ids over time.* Whether an id keeps its meaning through edits and is never reused (PR-009, PR-010) would need the app to be driven between two reads. The `gone` state is checked only if the provider happens to answer with it.
- *The life of the descriptor and the token.* That the descriptor is written after the listener is up and by rename, removed at quit and absent when the provider is turned off (PR-020, PR-021, PR-042); that the token and the instance are new at each launch, stored nowhere else and accepted nowhere else (PR-034, PR-040, PR-069). The check sees one run. It also does not check that the descriptor is in the real folder, since a provider under test may be told to write elsewhere.
- *Watching, where the app must be driven.* The check judges only the notices that happen to arrive while it holds a watch. It cannot make your app change, so it cannot tell that a change is always followed by a notice, that a change made just after a notice is delayed and not dropped (PR-083), that moving the pointer alone sends nothing (PR-084), or that watches end when the provider quits or is turned off (PR-086). `check.py` has a client and three helpers for a test of your own that can drive the app: open a watch with `check.Watch.from_descriptor(path)`, then call `drive_changes(watch, change, results, burst=None)`, `drive_hover(watch, hover, results)` and `drive_stop(watch, stop, results)`, giving each a function that makes one real change, several at once, a change of the hovered element only, or stops the provider. They add results in the same form as the check: `watch-change-noticed` and `watch-hover-silent` (PR-084), `watch-trailing-notice` and `watch-burst-coalesced` (PR-083), `watch-ends-at-stop` (PR-086). `test_check.py` uses them on the fake provider. Three things stay with the implementer: that the provider notices changes from the app's own events and not by rebuilding its answer on a timer, that every place where the answer can change sends a notice, and that it holds at least four watches at once.
- *Speed, properly.* The check times one answer and warns past a limit you choose. It cannot tell whether the provider waited on disk or network (PR-004).
- *A shared listener's other routes.* The check tests the endpoint's path only. It cannot confirm that the checks run before the app's other middleware, beyond seeing no permission headers on the responses it gets (PR-063).
- *Host conduct.* Everything a host must do is out of reach of a check that plays the host: asking only on the user's action, showing what was collected, keeping an id with its provider and instance, refusing a redirect or a mismatched instance, reading absent states correctly, treating hover as weaker than selection, and everything about how a host uses a watch (PR-036 to PR-039, PR-041, PR-043, PR-045, PR-052, PR-055, PR-061, PR-068, PR-071, PR-088 to PR-091). The fake provider exists to test those from the other side; for the watch rules, see [Testing a host's watch](#testing-a-hosts-watch).

Two checks are judgments the specification leaves room for. The oversized-request check declares a body of one gibibyte and sends none of it; a provider that refuses only once the bytes arrive is warned, not failed. The `started` field is required to look like `2026-11-09T21:14:03Z`, which is the form of the specification's example and not a stated rule.

## The fake provider

```sh
python3 tools/conformance/fake_provider.py --directory /tmp/acp/providers
```

It listens on a loopback port the system assigns, writes its descriptor into the folder and prints the descriptor's path. Stop it with Ctrl-C and the descriptor is removed. `--directory` is required, and a path inside the real descriptor folder is refused: a fake provider among real ones would be offered to a real host.

The tree it serves is a notes app with two windows, text selected, a focus path three elements deep and a link under the pointer. Three of its elements can be located as visible and one as off screen; the rest cannot be placed. The id `gone-1` is not in the tree and locates as `gone`.

It offers `watch`: it declares `"resources": {"subscribe": true}`, answers `subscriptions/listen` for `ambient://current` with an event stream, sends a comment line after 10 seconds with nothing to say, and ends every watch with a completion result when it stops. The tree stays as it is until something changes it. `--change-every SECONDS` changes it on a timer: the selection moves between the selected text and a comment, `display.detail` follows it, the document's word count goes up by one, and every open watch gets a notice, at most one in any 250 ms with the last change always noticed. In a test, a `FakeProvider` object has `change()` for one such change, `burst(n)` for `n` at once, and `hover()`, which moves the pointer to another element and sends no notice.

To test a host, start it with a fault and confirm the host ignores the provider or carries on without context:

```sh
python3 tools/conformance/fake_provider.py --directory /tmp/acp/providers --fault instance-mismatch
python3 tools/conformance/fake_provider.py --list-faults
```

`--list-faults` prints every fault with the requirement it breaks, how the check reports it, what it does and the checks that catch it. `--fault` may be given more than once. Other options change the provider without breaking a rule: `--delay SECONDS` makes `current` slow, for a host's time limit; `--no-locate` offers no location template; `--no-display` sends no `display`; `--no-watch` offers no watch, declaring no `subscribe` and answering `subscriptions/listen` with `404`; `--change-every SECONDS` changes the tree on a timer; `--keep-alive SECONDS` sets how long a watch is quiet before a comment line is sent; `--drop-watch-after SECONDS` closes each watch abruptly that long after it opens; `--redirect` answers the endpoint with a `307`, which a host must not follow; `--keep-descriptor` leaves the descriptor behind at exit, as a crash would; `--path` and `--port` move the endpoint; and `--tree FILE` serves a root element of your own.

The faults for `watch` all begin with `watch-`:

| Fault | Breaks | What the provider does |
|---|---|---|
| `watch-declared-not-served` | PR-080 | Declares `subscribe` and answers `subscriptions/listen` with `404` |
| `watch-no-ack` | PR-080 | Sends a notice first and never the acknowledgment |
| `watch-ack-extra` | PR-080 | Acknowledges a second address beside `ambient://current` |
| `watch-ack-echo` | PR-080 | Acknowledges the filter as asked, other addresses and list changes included |
| `watch-undeclared` | PR-081 | Opens the stream without declaring `subscribe` |
| `watch-any-filter` | PR-082 | Opens a watch for a filter that does not name `ambient://current` |
| `watch-notice-content` | PR-082 | Puts the new `display` in each notice |
| `watch-wrong-uri` | PR-082 | Sends notices that name a location |
| `watch-flood` | PR-083 | Sends a notice for every change at once; with `--change-every`, each tick is ten changes |
| `watch-drops-last` | PR-083 | Drops a change made inside the 250 ms after a notice |
| `watch-no-notice` | PR-084 | Sends no notice for a change |
| `watch-hover-notice` | PR-084 | Sends a notice when only the hovered element changes |
| `watch-no-keepalive` | PR-085 | Sends no comment line on a quiet watch |
| `watch-left-open` | PR-086 | Leaves its watches open when it stops |
| `watch-no-token-check` | PR-087 | Opens a watch with or without the token |
| `watch-allows-origin` | PR-087 | Opens a watch for a request with an `Origin` header |

The check sees `watch-notice-content`, `watch-wrong-uri` and `watch-flood` only if the tree changes while it watches, so start the provider with `--change-every 0.5` as well; it sees `watch-no-keepalive` only with `--watch-hold 20`. Four faults are marked `DRIVE` in `--list-faults`: `watch-drops-last`, `watch-no-notice`, `watch-hover-notice` and `watch-left-open`. The check passes a provider that has one of them, because the app must be made to change at a chosen moment to show it; the `drive_` helpers in `check.py` catch them, and `test_check.py` confirms that. The older faults `no-token-check` and `allow-origin` leave the watch request alone, so that each fault still breaks one requirement.

### Testing a host's watch

The four rules for a host that watches (PR-088 to PR-091) are host conduct, and the check cannot see them. The fake provider can, from its side. It counts what the host does and prints the counts when it stops; the same numbers are attributes of a `FakeProvider` object (`watches_open`, `watches_opened`, `most_watches_open`, `longest_watch`, `reads_served`, `most_reads_outstanding`, `notices_sent`, and all of them from `counters()`):

```
watches: 3 opened, 1 at most at once, 0 still open, the longest 41.2 s
reads of current: 9 served, 1 at most outstanding at once
notices: 7 sent for 12 changes
```

- *A host reads only on the user's action or a notice (PR-088).* Start the provider with `--change-every 5`, invoke the host once and leave it showing the context for a minute. The reads served should be one for the invocation, one for each notice sent, and one for each further action of yours such as sending. More reads than that is a host that polls. With no `--change-every`, no notice is sent, and every read should be one you caused.
- *One watch, in view (PR-089).* "At most at once" should be 1 however many of the host's interfaces show the context. Send the message, remove the context or close the host's interface, then stop the provider: "still open" should be 0, and "the longest" should be about as long as the context was on screen. A watch the host has closed leaves the count at once.
- *A notice is not context, and never two reads outstanding (PR-090).* Start with `--change-every 0.3 --delay 1`, so that notices arrive while a read is still being answered: "at most outstanding at once" must stay 1. With `--fault watch-flood --change-every 1` the host gets ten notices at a time and must still make one read after another, not ten. With `--fault watch-notice-content` each notice carries a `display`, which the host must ignore: its line must show what the next read returns.
- *A lost watch is silence (PR-091).* `--drop-watch-after 3` closes each watch three seconds after it opens, with no completion result and with a connection reset where the system gives one. The host should keep showing what it last read, show no error, and open the watch again once and no more: "opened" should be 2 for one invocation. It should still read at send, which shows as one more read. Stopping the provider with Ctrl-C while the host watches ends the watch properly, with a completion result, and removes the descriptor; the host should again show no error. `--fault watch-no-ack` gives a stream that never acknowledges, `--fault watch-no-keepalive` one that goes silent, and `--no-watch` a provider with nothing to watch, where the host must fall back to reading on the user's action alone.

## Running the tests

From the repository root:

```sh
python3 -m unittest discover -s tools/conformance
```

The tests take about 20 seconds. They use short intervals in place of the real ones: a comment line every 0.1 seconds from the fake provider, and a check that asks for one every 0.4 seconds.
