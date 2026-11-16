import { DEFAULT_SETTINGS, parseNever } from "./lib.js";

const view = document.getElementById("view");
const never = document.getElementById("never");
const saved = document.getElementById("saved");

const settings = Object.assign({}, DEFAULT_SETTINGS, await chrome.storage.local.get(["view", "never"]));
view.checked = settings.view !== false;
never.value = settings.never.join("\n");

document.getElementById("save").addEventListener("click", async () => {
  const names = parseNever(never.value);
  await chrome.storage.local.set({ view: view.checked, never: names });
  never.value = names.join("\n");
  saved.textContent = "Saved";
  setTimeout(() => (saved.textContent = ""), 1500);
});
