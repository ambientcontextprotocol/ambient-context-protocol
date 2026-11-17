# RFC-0005 — The app's words and favicon for what was read

> Let a provider say, in two short strings, how a host should name what it read, and let an app ship a favicon a host can draw beside those words.

| Field | Value |
|---|---|
| Author | The protocol session, for Andrew Jones |
| Status | Accepted |
| Created | `2026.11.17` |
| Decided | `2026.11.17` |
| Discussion | Not yet opened as a pull request |
| Specification sections | 4.1 (the answer to `current`), new 4.3 and 8.2, 8.1 (the macOS profile), 9.1 and 9.2 (rules), 10 (the version) |
| Version effect | Additive: `0.2.0` to `0.2.1` |
| Supersedes or amends | None |
| Released in | |

## 1. Summary

A host must show the user which context will go with a message (9.2). Today it has to compose that line itself from the tree. This RFC adds an optional `display` object to the answer to `current`, holding a `title` and a `detail` in the app's own words, and a file convention by which an app ships a favicon in its own bundle. Both are optional for a provider and ignorable by a host. A host that gets neither falls back to its own wording and the app's system icon.

## 2. Motivation

Sirius reads the front app when its composer opens and sends what it read with the message. Nothing on screen said so. The fix is one quiet line in the composer: a small picture, what is open, what is selected. A host can derive those words from the tree (the innermost titled element in focus, then a count of the selection), but the result is generic: `draft.md · 14 words` where the app would say `draft.md · lines 12–18`, or `3 selected` where a task tracker would say `3 tasks in Cycle 12`. The app knows its own nouns. A web page has the same relationship with the sites that link to it: its meta tags word the link card, and the site that shows the card draws it.

The picture has the same problem. The app's system icon is drawn for the Dock at large sizes, in full color. At 16 points beside dim text on a dark surface it is noise. A favicon made for that size is what the web settled on.

## 3. Proposal

An editor with lines 12 to 18 of `release-runbook.md` selected answers `current` with:

```json
{
  "protocol": "0.2.1",
  "instance": "k3f9x2",
  "display": { "title": "release-runbook.md", "detail": "lines 12–18" },
  "root": { "id": "app", "role": "Application", "title": "Editor" }
}
```

and ships `Editor.app/Contents/Resources/favicon.svg`. The host shows the user `[favicon] release-runbook.md · lines 12–18` and lets them remove it.

Scope and exclusions:

- `display` is for the user. It labels what the host is about to send; it is not part of what is sent to the agent, and this RFC does not ask a host to pass it on.
- `display` rides on the answer to `current`, because it changes with the selection. It is not in the descriptor, which is written once per run.
- The favicon is a file, never a message. No field anywhere names it or carries it.
- A helper process that answers for an app it does not own cannot add a file to that app's bundle, so it gets the host's fallback. One program answering for another is not in this version of the protocol (section 12); an inline favicon can be proposed when it is.

## 4. Specification changes

1. *The answer to `current` (4.1).* The result has three required fields and one optional: `display`, an object. "Exactly these three fields" becomes "these fields and no others".
2. *`display` (new 4.3).* Two optional fields, both strings: `title`, what is open, and `detail`, what is selected or in focus within it. Each is plain text on one line, with no markup and no line breaks, written for a person. A provider keeps each to 80 characters or fewer. A provider that has nothing in particular to say leaves `display` out. `display` describes the same moment and the same tree as the answer it is in: it must not name something the tree does not hold.
3. *What a host does with it (4.3, 9.2).* A host may show `display` to the user as the name of what it read. It uses `display` only when `title` is a non-empty string; a `detail` with no `title` is ignored. A `display` that is not an object, or a `title` or `detail` that is not a string, is read as absent, and the answer is used as if it were not there: a malformed `display` never causes a host to refuse an answer. A host cuts each string to one line and to a length of its choosing, and draws it as plain text. A host that gets no usable `display` words the line itself from the tree.
4. *The favicon (new 8.2).* An app may ship one image for hosts to draw beside its context, at the place its platform's profile names. A host that draws a picture for a provider looks for that file itself, in the installed app whose process it identified in section 8, step 1. A host never reads a favicon from a path, a URL or bytes that a provider or a descriptor names. A file that is missing, too large for the host's limit or not a readable image is treated as absent. Without one, the host draws what it would for any app, such as the app's system icon.
5. *The macOS profile (8.1).* One row added: the favicon is `Contents/Resources/favicon.svg` in the app's bundle, or `favicon.png` beside it when there is no SVG. A PNG is at least 32 by 32 pixels.
6. *Rules for providers (9.1).* `display` says no more than the tree: it holds no content the provider would not report as an element, and nothing from an element the provider left out.
7. *Rules for hosts (9.2).* "Show what was collected" still holds on its own terms: `display` is a label, and the user must still be able to remove the context it labels. A host treats `display` as text from another program: it does not interpret markup, links or control characters in it.
8. *The version (10).* `0.2.1`. A provider that sends `display` gives `0.2.1` in the descriptor, the extension declaration and the answer. A `0.2.0` host works with it unchanged: it agrees on the major and minor parts and ignores the field.

## 5. Compatibility

Additive. A provider that sends neither is correct. A host that knows neither ignores the field, as section 10 already requires for any field it does not know, and never looks for the file.

One thing changes for a checker. The schema for `0.2.0` refuses any field beside `protocol`, `instance` and `root`, and the outside check does the same (PR-047). A `0.2.1` answer with `display` fails both, by design: they state what a `0.2.0` provider sends. A new schema, `schema/current-0.2.1.json`, and the check allow the one new field and still refuse any other. PR-047 is retired at `0.2.0` and replaced.

The first-party host reads any `0.2.x` descriptor, so a provider that moves to `0.2.1` keeps working with the released host.

## 6. Privacy and security

1. *What new information leaves an app.* Two strings the app composes. Under rule 6 they say nothing the tree does not already say, so a caller that can read `current` learns nothing new. The favicon is a file in an installed app, readable by any program already.
2. *A label that does not match what is sent.* This is the new risk. A provider with a bug, or a hostile one, could send `display` saying "one line" with a tree that holds the whole document, and the user would approve by the label. A hostile provider gains nothing by this: the content is its own, and it chose to report it. A buggy one misleads its user. The mitigations are rule 2 (same moment, same tree), the provider SDKs building both in one call, and the host's existing duty to let the user see and remove what goes. A host that offers a way to inspect the full context shows the tree, not `display`.
3. *Text from another program in the host's interface.* A host draws `display` as plain text, on one line, cut to a length it chooses, with control characters removed. It does not render markup or follow links in it. Otherwise a provider could draw something that reads as the host's own interface.
4. *Why the favicon is not in the descriptor.* The descriptor folder is writable by any program running as the user (section 8). A favicon named or carried there could be replaced by any such program, which could then dress its own provider as another app. A file in the app's bundle is covered by the app's code signature on macOS, and the host finds the bundle from the process it already checked, so a provider cannot point the host anywhere. A host never follows a path or URL from a provider, so the favicon cannot be used to make the host read an arbitrary file or reach the network.
5. *Decoding an image.* A host decodes a file an app's developer made. It bounds the size it will read (the first-party host reads at most 256 KB) and treats anything that does not decode as absent. An SVG is drawn as a static image: a host does not run scripts in it or load anything it refers to.
6. *Callers are unchanged.* The same programs that can read `current` can read `display`.

## 7. Conformance

| Draft | Requirement | Check from outside |
|---|---|---|
| D1 | The answer holds `protocol`, `instance` and `root`, may hold `display`, and holds nothing else | The field names of the answer |
| D2 | `display`, when sent, is an object whose `title` and `detail`, when sent, are strings on one line of at most 80 characters | The types, a search for line breaks, and the lengths |
| D3 | `display` names nothing the tree does not hold | Not checkable from outside in general; a provider's own test |
| D4 | A host uses `display` only when `title` is a non-empty string, and reads a malformed `display` as absent without refusing the answer | A test of the host's reader on fixed answers; the fake provider serves them |
| D5 | A host draws `display` as plain text on one line | An inspection of the host |
| D6 | A host reads a favicon only from the profile's place in the app whose process it identified, never from a place a provider names | An inspection of the host; not checkable from outside |
| D7 | A favicon file, when shipped, is at the profile's place and is a readable SVG or PNG | A look in the app's bundle; the outside check does not do this, since it is given an endpoint and not an app |

PR-047 (exactly three fields) and PR-066 (the version `0.2.0` in three places) are retired at `0.2.0`. The requirements above are added from `0.2.1`, with replacements for those two.

## 8. Rationale, alternatives and prior art

- *Why the app words it.* The host can always produce a line from the tree, and does when `display` is absent. The app's line is better because the app knows its nouns and units: lines, tasks, frames, cells.
- *Why two fields and not one string.* A host draws the subject and the selection with different weight, and cuts them separately when space is short. One string would force every host to guess where the subject ends.
- *Why on `current` and not on elements.* An element already has a `title`. `display` is a summary of the whole answer for one line of interface; putting it on an element would raise the question of which element's to use.
- *The favicon inline in the descriptor.* Simple to implement and works for a helper process. Rejected for now because of item 4 of section 6, and because it would bring a size limit, validation and versioning into the protocol's messages for a static asset.
- *The favicon as a resource read over MCP.* The provider would be the source of bytes the host decodes and draws on every read. The file in the bundle is static, signed with the app and needs no request.
- *A URL to an icon.* A host would fetch something a provider named. Rejected outright.
- *Do nothing.* The host words the line and greys the app's icon. It works for every provider today and remains the fallback.
- *Prior art.* A web page's `<title>`, its Open Graph `og:title` and `og:description`, and `favicon.ico` or `<link rel="icon">`: the page says how it wants to be named, the site that links to it draws the card and may cut or ignore what it was given. The fixed file name follows `favicon.ico`, which browsers look for at a known place without being told.

*Drawbacks.* Two descriptions of one answer can disagree. An app ships one more asset. The favicon convention is defined per platform, so each new profile has to name a place.

## 9. Open questions

1. Whether a host should draw an SVG favicon in the colors the app chose or force one tint. The first-party host draws it as made, and the guidance to app authors is one light color that reads at 16 points on a dark surface. Not a matter for the protocol unless hosts diverge badly.
2. Whether `display` should also be passed to the agent, so the agent is told the same words the user saw. It would change what hosts send and is left to a later proposal.
3. The names `display`, `title`, `detail` and `favicon`. Placeholders like every other name before 1.0.
4. Whether 80 characters is the right bound, and whether it should be a rule for providers at all or only a host's cut. To be set from what the first providers send.

## 10. Decision and outcome

Accepted on 2026.11.17 by Andrew Jones, maintainer, on the revision of commit `1d7d19a`, for protocol version `0.2.1`.

Why: a host must show what it collected, and the app can word that line better than the host can. It is optional and additive, and the released first-party host already reads any `0.2.x` provider. The open questions in section 9 stay open during implementation.
