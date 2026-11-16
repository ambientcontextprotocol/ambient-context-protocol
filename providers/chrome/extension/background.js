// Ambient Context for Chrome: the extension half.
//
// It keeps one connection open to a helper program on this Mac, which is
// the Ambient Context provider. Unasked, it sends the helper only the fact
// that the keyboard moved between windows. When the
// helper asks what is current, it answers with the window in front, that
// window's active tab (title and address), the text selected in the
// page and, unless switched off, what of the page is in view. Sites on
// the never-read list are named and not read. Nothing leaves the Mac from
// here, and nothing of a page is stored.

import { DEFAULT_SETTINGS, combine, neverRead } from "./lib.js";
import { readPage } from "./page.js";

const HOST = "io.github.ambientcontextprotocol.chrome";
// How long the page has to answer. The helper waits 150 ms for the whole
// answer, so a slow page costs what is in it, not the page itself.
const PAGE_LIMIT_MS = 100;

let port = null;

function connect() {
  if (port) return;
  try {
    port = chrome.runtime.connectNative(HOST);
  } catch {
    port = null;
    return;
  }
  port.onMessage.addListener(onMessage);
  port.onDisconnect.addListener(() => {
    // Reading lastError marks it as seen. The helper is not installed, or
    // it stopped; the alarm below tries again.
    void chrome.runtime.lastError;
    port = null;
  });
}

async function onMessage(message) {
  if (!message || message.type !== "current") return;
  const sender = port;
  let state = {};
  try {
    state = await current();
  } catch {
    // An answer with nothing in it: the helper reports the browser alone.
  }
  try {
    sender?.postMessage({ type: "state", id: message.id, state });
  } catch {
    // The helper went away while the page was being read.
  }
}

// The window in front and its active tab. A private window is not seen
// by this extension unless the user has allowed it there, so with one in
// front the last ordinary window is what the browser reports, and its
// `focused` is false.
async function current() {
  const frontmost = await chrome.windows.getLastFocused({ populate: true, windowTypes: ["normal"] });
  if (!frontmost || frontmost.incognito) return {};
  const tab = (frontmost.tabs || []).find((candidate) => candidate.active);
  if (!tab) return {};
  const state = {
    window: { id: frontmost.id, focused: frontmost.focused === true },
    tab: { id: tab.id, title: tab.title || undefined, url: tab.url || undefined },
  };
  const settings = Object.assign({}, DEFAULT_SETTINGS, await chrome.storage.local.get(["view", "never"]));
  // A site the user has said never to read: the page is named and
  // nothing in it is looked at, not even the selection.
  if (neverRead(tab.url, settings.never)) {
    state.never = true;
    return state;
  }
  return Object.assign(state, await read(tab.id, settings.view !== false));
}

// Runs `readPage` in the page, only when asked: the selection from
// whichever frame has one and, from the top frame, what is in view.
async function read(tabId, view) {
  const timeout = new Promise((resolve) => setTimeout(() => resolve(null), PAGE_LIMIT_MS));
  const reading = chrome.scripting
    .executeScript({ target: { tabId, allFrames: true }, func: readPage, args: [{ view }] })
    // The browser refused: one of its own pages, the store, some viewers.
    .catch(() => undefined);
  return combine(await Promise.race([reading, timeout]));
}

// Tell the helper when the keyboard moves to or from one of this
// extension's windows, with nothing about the window. The helper uses the
// moment to work out whether a window this extension cannot see, such as
// a private one, has come to the front.
chrome.windows.onFocusChanged.addListener(() => {
  try {
    port?.postMessage({ type: "focus" });
  } catch {
    // No helper to tell.
  }
});

// An open connection to the helper keeps this worker running. The alarm
// starts it again, and reconnects, if the browser stopped it or the
// helper was installed after the extension.
chrome.runtime.onInstalled.addListener(() => {
  chrome.alarms.create("connect", { periodInMinutes: 0.5 });
  connect();
});
chrome.runtime.onStartup.addListener(connect);
chrome.alarms.onAlarm.addListener(connect);
connect();
