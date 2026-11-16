// The parts of the extension that need no browser, so they can be tested
// without one.

// The most selected text sent, in characters: what a host passes on.
export const MAX_SELECTION = 20000;

// Sites whose pages are never read, until the user says otherwise on the
// options page. A site is its host name; a listed name covers the names
// under it.
export const DEFAULT_NEVER = [
  "mail.google.com",
  "accounts.google.com",
  "outlook.live.com",
  "outlook.office.com",
  "mail.proton.me",
  "icloud.com",
  "1password.com",
  "bitwarden.com",
  "lastpass.com",
];

export const DEFAULT_SETTINGS = { view: true, never: DEFAULT_NEVER };

// One host name per line, as typed on the options page: lowered, with
// any scheme, path or leading "*." taken off, and no repeats.
export function parseNever(typed) {
  const names = [];
  for (const line of String(typed || "").split(/[\s,]+/)) {
    let name = line.trim().toLowerCase();
    if (!name) continue;
    name = name.replace(/^[a-z]+:\/\//, "").replace(/^\*\./, "").replace(/[/:?#].*$/, "").replace(/^\.+|\.+$/g, "");
    if (name && !names.includes(name)) names.push(name);
  }
  return names;
}

// Whether the page at `url` is on the list: its host is a listed name,
// or a name under one. "bank.example" covers "www.bank.example" and not
// "notbank.example".
export function neverRead(url, never) {
  let host;
  try {
    host = new URL(url).hostname.toLowerCase();
  } catch {
    return false;
  }
  return (never || []).some((name) => host === name || host.endsWith("." + name));
}

// What the frames of a page said, as one answer: the first frame with a
// selection gives the selection, and the top frame gives what is in
// view. `frames` is undefined when the browser refused the page and null
// when the page did not answer in time.
export function combine(frames) {
  if (frames === undefined) return { readable: false };
  if (frames === null) return { readable: true };
  const state = { readable: true };
  const results = frames.map((frame) => frame && frame.result).filter((result) => result && typeof result === "object");
  const picked = results.map((result) => result.selection).find((text) => typeof text === "string" && text.length > 0);
  if (picked) {
    state.selection = picked.slice(0, MAX_SELECTION);
    if (picked.length > MAX_SELECTION) state.cut = true;
  }
  const top = results.find((result) => typeof result.text === "string" || Array.isArray(result.elements));
  if (top) {
    if (top.text) state.text = top.text;
    if (top.textCut) state.textCut = true;
    if (top.page && Array.isArray(top.elements)) {
      state.page = top.page;
      state.elements = top.elements;
    }
  }
  return state;
}
