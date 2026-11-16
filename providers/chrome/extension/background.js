// Ambient Context for Chrome: the extension half.
//
// It keeps one connection open to a helper program on this Mac, which is
// the Ambient Context provider. It sends nothing by itself. When the
// helper asks what is current, it answers with the window in front, that
// window's active tab (title and address) and the text selected in the
// page. Nothing leaves the Mac from here, and nothing is stored.

const HOST = "io.github.ambientcontextprotocol.chrome";
// The most selected text sent, in characters: what a host passes on.
const MAX_SELECTION = 20000;
// How long the page has to give its selection. The helper waits 150 ms
// for the whole answer, so a slow page costs the selection, not the page.
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
  const read = await selection(tab.id);
  state.readable = read.readable;
  if (read.text) {
    state.selection = read.text.slice(0, MAX_SELECTION);
    if (read.text.length > MAX_SELECTION) state.cut = true;
  }
  return state;
}

// The selected text, from whichever frame of the page has one. Runs in
// the page only when asked, and reads only the selection.
async function selection(tabId) {
  const timeout = new Promise((resolve) => setTimeout(() => resolve(null), PAGE_LIMIT_MS));
  const reading = chrome.scripting
    .executeScript({ target: { tabId, allFrames: true }, func: selectedText })
    .catch(() => undefined);
  const frames = await Promise.race([reading, timeout]);
  // Too slow: the page may be readable, and no selection is reported.
  if (frames === null) return { readable: true, text: "" };
  // The browser refused: one of its own pages, the store, some viewers.
  if (frames === undefined) return { readable: false, text: "" };
  const found = frames.map((frame) => frame.result).find((text) => typeof text === "string" && text.length > 0);
  return { readable: true, text: found || "" };
}

// Runs inside the page. The selection in the document or, when the
// cursor is in a text box, the selected part of what was typed there. A
// password box has no selection to give.
function selectedText() {
  const picked = window.getSelection();
  const text = picked ? picked.toString() : "";
  if (text) return text;
  const box = document.activeElement;
  if (!box) return "";
  const typed = box.tagName === "TEXTAREA" || (box.tagName === "INPUT" && /^(text|search|url|tel|email)$/.test(box.type));
  if (!typed || box.selectionStart == null || box.selectionStart === box.selectionEnd) return "";
  return box.value.slice(box.selectionStart, box.selectionEnd);
}

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
