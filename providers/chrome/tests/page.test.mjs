// Runs the page reader in a real page: a fixture loaded in a headless
// Chrome with a profile of its own, apart from the one a person uses.
// Skipped where Chrome is not installed.

import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { existsSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { pathToFileURL } from "node:url";
import { readPage } from "../extension/page.js";

const CHROME = process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";

const FIXTURE = `<!doctype html>
<html><head><meta charset="utf-8"><base href="https://site.example/"><title>Fixture</title>
<style>body{margin:0;font:16px/1.4 sans-serif} header{height:40px} .far{margin-top:4000px} .gone{display:none}</style></head>
<body>
<header><nav><a href="/issues">Issues</a> <a href="/about">About</a> <span>Menu words</span></nav></header>
<main><article>
<h1>The seven vices</h1>
<p>First paragraph in view, with a <a href="https://example.org/source">source link</a>.</p>
<p class="gone">Hidden paragraph.</p>
<figure>
  <img src="https://example.invalid/gin-palace.jpg" alt="alt words" width="300" height="200">
  <figcaption>A gin palace in London</figcaption>
</figure>
<img src="https://example.invalid/icon.png" alt="tiny icon" width="16" height="16">
<a href="/photo" aria-label="Opens profile photo"><div style="width:120px;height:120px;background:#ccc"><img src="https://example.invalid/avatar.jpg" alt="" width="120" height="120" style="opacity:0"></div></a>
<div><span style="margin-right:12px">San Francisco, CA</span><span style="margin-right:12px">murraycole.com</span><span>Born January 1</span></div>
<div><span><b>bold</b>ly joined</span> <span style="opacity:0">unseen words</span></div>
<aside><h2>You might like</h2><p>You might like these.</p><img src="https://example.invalid/suggested.jpg" alt="Suggested account" width="64" height="64"></aside>
<h2>Second heading</h2>
<p>Second paragraph in view.</p>
<form><input type="text" value="typed secret"><textarea>typed draft</textarea><button>Send it</button></form>
<pre>kept   as
typed</pre>
<p class="far">Far below the window. <a href="/below">Below link</a></p>
<h2 class="far">Heading far below</h2>
</article></main>
<pre id="out"></pre>
<script>
const readPage = ${readPage.toString()};
const first = readPage({ view: true });
const second = readPage({ view: true });
const plain = readPage({});
const capped = readPage({ view: true, text: 30, links: 1 });
document.getElementById("out").textContent = JSON.stringify({ first, second, plain, capped });
</script>
</body></html>`;

test("the page reader, in a real page", { skip: !existsSync(CHROME) && "Chrome is not installed" }, () => {
  const folder = mkdtempSync(join(tmpdir(), "acp-page-"));
  try {
    const page = join(folder, "fixture.html");
    writeFileSync(page, FIXTURE);
    const dom = execFileSync(
      CHROME,
      [
        "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
        `--user-data-dir=${join(folder, "profile")}`, "--window-size=1000,1400", "--virtual-time-budget=3000",
        "--dump-dom", pathToFileURL(page).href,
      ],
      { encoding: "utf8", timeout: 60000, stdio: ["ignore", "pipe", "ignore"] },
    );
    const out = /<pre id="out">([\s\S]*?)<\/pre>/.exec(dom);
    assert.ok(out, "the fixture wrote no result");
    const decode = (text) => text.replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&amp;/g, "&");
    const { first, second, plain, capped } = JSON.parse(decode(out[1]));

    // What is in view is read; what is hidden, typed or far below is not.
    assert.match(first.text, /The seven vices/);
    assert.match(first.text, /First paragraph in view, with a source link\./);
    assert.match(first.text, /A gin palace in London/);
    assert.match(first.text, /Second paragraph in view\./);
    assert.match(first.text, /kept {3}as\ntyped/);
    assert.doesNotMatch(first.text, /Hidden paragraph/);
    assert.doesNotMatch(first.text, /Far below/);
    assert.doesNotMatch(first.text, /typed secret|typed draft/);
    // A button's label is on the screen like any other words.
    assert.match(first.text, /Send it/);
    // The site's own parts are left out when the page marks its content.
    assert.doesNotMatch(first.text, /Menu words|You might like/);
    // Pieces the page runs together but draws apart get a space; pieces
    // it draws together stay together; clear text is not read.
    assert.match(first.text, /San Francisco, CA murraycole\.com Born January 1/);
    assert.match(first.text, /boldly joined/);
    assert.doesNotMatch(first.text, /unseen words/);
    // Blocks are on lines of their own.
    assert.match(first.text, /The seven vices\nFirst paragraph/);
    assert.equal(first.textCut, undefined);

    const kinds = (kind) => first.elements.filter((element) => element.kind === kind);
    // Headings and images in the site's own parts are left out with its text.
    assert.ok(first.elements.every((element) => !/You might like|Suggested account/.test(element.title || "")));
    assert.deepEqual(kinds("heading").map((h) => [h.title, h.level]), [["The seven vices", 1], ["Second heading", 2]]);
    // The caption names the image; the icon is left out.
    // A clear image over a drawn background is still the picture, named
    // by the link around it.
    assert.deepEqual(kinds("image").map((i) => [i.title, i.url]), [
      ["A gin palace in London", "https://example.invalid/gin-palace.jpg"],
      ["Opens profile photo", "https://example.invalid/avatar.jpg"],
    ]);
    // The page's own link, then the header's; none from below the window.
    const links = kinds("link");
    assert.equal(links.length, 4);
    assert.ok(links.some((l) => l.title === "source link" && l.url === "https://example.org/source"));
    assert.ok(links.every((l) => !/below/.test(l.url)));
    // In the page's order: the header's links come first there.
    assert.deepEqual(first.elements.map((e) => e.title).slice(0, 3), ["Issues", "About", "The seven vices"]);

    // The same things keep the same numbers, under the same word.
    assert.match(first.page, /^[a-z0-9]{1,8}$/);
    assert.equal(second.page, first.page);
    assert.deepEqual(second.elements.map((e) => e.n), first.elements.map((e) => e.n));
    assert.equal(new Set(first.elements.map((e) => e.n)).size, first.elements.length);

    // Without `view`, the selection alone.
    assert.deepEqual(plain, { selection: "" });

    // The limits hold, and the page's own link is the one kept.
    assert.ok(capped.text.length <= 30);
    assert.equal(capped.textCut, true);
    assert.deepEqual(capped.elements.filter((e) => e.kind === "link").map((l) => l.title), ["source link"]);
  } finally {
    rmSync(folder, { recursive: true, force: true });
  }
});
