import assert from "node:assert/strict";
import test from "node:test";
import { DEFAULT_NEVER, MAX_SELECTION, combine, neverRead, parseNever } from "../extension/lib.js";

test("a listed name covers itself and the names under it, and nothing else", () => {
  const never = ["bank.example", "mail.google.com"];
  assert.equal(neverRead("https://bank.example/accounts", never), true);
  assert.equal(neverRead("https://www.bank.example/", never), true);
  assert.equal(neverRead("https://BANK.example/", never), true);
  assert.equal(neverRead("https://notbank.example/", never), false);
  assert.equal(neverRead("https://bank.example.evil.test/", never), false);
  assert.equal(neverRead("https://mail.google.com/mail/u/0/", never), true);
  assert.equal(neverRead("https://www.google.com/", never), false);
  assert.equal(neverRead("not an address", never), false);
  assert.equal(neverRead("https://bank.example/", undefined), false);
});

test("the list is read as typed, tidied", () => {
  assert.deepEqual(parseNever(" Bank.Example \nhttps://www.shop.test/cart?x=1\n*.health.test\n\nbank.example\n"), [
    "bank.example",
    "www.shop.test",
    "health.test",
  ]);
  assert.deepEqual(parseNever(""), []);
  assert.deepEqual(parseNever(DEFAULT_NEVER.join("\n")), DEFAULT_NEVER);
});

test("by default, sign-in, password and mail sites are never read", () => {
  for (const url of ["https://accounts.google.com/", "https://my.1password.com/", "https://mail.google.com/mail/u/0/", "https://outlook.office.com/mail/", "https://mail.proton.me/u/0/inbox", "https://www.icloud.com/mail/"]) {
    assert.equal(neverRead(url, DEFAULT_NEVER), true, url);
  }
  assert.equal(neverRead("https://www.google.com/search?q=x", DEFAULT_NEVER), false);
});

test("a page the browser refused, and one that was too slow", () => {
  assert.deepEqual(combine(undefined), { readable: false });
  assert.deepEqual(combine(null), { readable: true });
});

test("the selection comes from whichever frame has one, and what is in view from the top", () => {
  const frames = [
    { result: { selection: "", text: "Visible words", page: "k3f9x2", elements: [{ n: 1, kind: "heading", title: "T" }] } },
    { result: { selection: "picked in a frame" } },
    { result: null },
    undefined,
  ];
  assert.deepEqual(combine(frames), {
    readable: true,
    selection: "picked in a frame",
    text: "Visible words",
    page: "k3f9x2",
    elements: [{ n: 1, kind: "heading", title: "T" }],
  });
});

test("nothing selected and nothing in view is the page alone", () => {
  assert.deepEqual(combine([{ result: { selection: "" } }]), { readable: true });
});

test("elements without the page's word are not passed on", () => {
  const state = combine([{ result: { selection: "", text: "t", elements: [{ n: 1, kind: "link" }] } }]);
  assert.equal(state.elements, undefined);
  assert.equal(state.text, "t");
});

test("a long selection is cut and says so", () => {
  const state = combine([{ result: { selection: "x".repeat(MAX_SELECTION + 1) } }]);
  assert.equal(state.selection.length, MAX_SELECTION);
  assert.equal(state.cut, true);
  assert.equal(combine([{ result: { selection: "short", text: "t", textCut: true } }]).textCut, true);
});
