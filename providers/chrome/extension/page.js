// The one function that runs inside a page. The background worker hands
// it to the browser, which runs it in every frame of the active tab, so
// it must stand alone: it can use nothing defined outside itself.
//
// In every frame it reads the selection. In the top frame, when `view` is
// set, it also reads what is inside the window: the text in view, and
// the headings, images and links among it. It reads nothing typed into a
// form field, and nothing scrolled out of view.

export function readPage(options) {
  const limits = Object.assign(
    { view: false, text: 6000, headings: 10, images: 10, links: 20, title: 200, nodes: 6000, ms: 60 },
    options || {},
  );

  // The selection in the document or, when the cursor is in a text box,
  // the selected part of what was typed there. A password box has none
  // to give.
  function selectedText() {
    const picked = window.getSelection();
    const text = picked ? picked.toString() : "";
    if (text) return text;
    const box = document.activeElement;
    if (!box) return "";
    const typed =
      box.tagName === "TEXTAREA" || (box.tagName === "INPUT" && /^(text|search|url|tel|email)$/.test(box.type));
    if (!typed || box.selectionStart == null || box.selectionStart === box.selectionEnd) return "";
    return box.value.slice(box.selectionStart, box.selectionEnd);
  }

  const result = { selection: selectedText() };
  if (!limits.view || window !== window.top || !document.body) return result;

  const started = performance.now();
  const late = () => performance.now() - started > limits.ms;
  const width = window.innerWidth;
  const height = window.innerHeight;

  // Whether an element is drawn inside the window. Asked of the same
  // element many times, so the answer is kept.
  const seen = new Map();
  function look(element) {
    let found = seen.get(element);
    if (found) return found;
    const box = element.getBoundingClientRect();
    let shown =
      box.width >= 1 && box.height >= 1 && box.bottom > 0 && box.top < height && box.right > 0 && box.left < width;
    // Not opacity: a picture drawn as a background often has a clear
    // image laid over it to carry its address and alt text.
    if (shown && element.checkVisibility) shown = element.checkVisibility({ checkVisibilityCSS: true });
    found = { shown, box };
    seen.set(element, found);
    return found;
  }
  const inView = (element) => look(element).shown;
  // Text that is there but cannot be seen is not what the user sees.
  const clear = (element) => element.checkVisibility && !element.checkVisibility({ checkOpacity: true });

  const oneLine = (text) => (text || "").replace(/\s+/g, " ").trim().slice(0, limits.title);
  const address = (value) => {
    try {
      const url = new URL(value, document.baseURI);
      return url.protocol === "http:" || url.protocol === "https:" ? url.href : undefined;
    } catch {
      return undefined;
    }
  };

  // A number for each element reported, the same each time this page is
  // read, with a word for this page that no other page shares. Kept in
  // this extension's own world of the page, which the page cannot reach.
  const memory = (globalThis.__ambientContext ??= {
    page: Math.random().toString(36).slice(2, 8),
    numbers: new WeakMap(),
    next: 0,
  });
  function number(element) {
    let n = memory.numbers.get(element);
    if (n === undefined) {
      n = memory.next += 1;
      memory.numbers.set(element, n);
    }
    return n;
  }

  // The parts of a page that are the site's and not the page's: its
  // menus, sidebars and footer. Left out of the text when the page marks
  // its main content, so that an article is not crowded out by them.
  const FURNITURE =
    "nav,aside,footer,[role='navigation'],[role='banner'],[role='contentinfo'],[role='complementary'],[role='search']";
  const main = [...document.querySelectorAll("main,[role='main']")].find(inView);

  // The text in view, in reading order: every piece of text whose
  // element is drawn inside the window, a new line where the block it
  // sits in changes, and a space where two pieces sit apart on the
  // screen with nothing between them in the page.
  const SKIP = "script,style,noscript,template,textarea,select,option,svg,[aria-hidden='true']";
  const BLOCK =
    "p,div,li,h1,h2,h3,h4,h5,h6,blockquote,pre,figcaption,td,th,dt,dd,section,article,header,footer,nav,aside,main,figure,ul,ol,table,tr,form";
  function visibleText(root, skipFurniture) {
    const pieces = [];
    let length = 0;
    let lastBlock = null;
    let lastParent = null;
    let lastWords = "";
    let cut = false;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let scanned = 0;
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      scanned += 1;
      if (scanned > limits.nodes || (scanned % 200 === 0 && late())) {
        cut = true;
        break;
      }
      const parent = node.parentElement;
      if (!parent || !/\S/.test(node.data) || parent.closest(SKIP) || !inView(parent) || clear(parent)) continue;
      if (skipFurniture && parent.closest(FURNITURE)) continue;
      const block = parent.closest(BLOCK);
      const words = parent.closest("pre") ? node.data : node.data.replace(/\s+/g, " ");
      let joint = "";
      if (pieces.length) {
        if (block !== lastBlock) {
          joint = "\n";
        } else if (parent !== lastParent && !/\s$/.test(lastWords) && !/^\s/.test(words)) {
          // Two pieces the page runs together but draws apart: on
          // different lines, or with a gap between them.
          const before = look(lastParent).box;
          const after = look(parent).box;
          const nested = lastParent.contains(parent) || parent.contains(lastParent);
          if (!nested && (after.top >= before.bottom - 1 || after.left - before.right >= 3)) joint = " ";
        }
      }
      const piece = joint + words;
      if (length + piece.length > limits.text) {
        pieces.push(piece.slice(0, limits.text - length));
        cut = true;
        break;
      }
      pieces.push(piece);
      length += piece.length;
      lastBlock = block;
      lastParent = parent;
      lastWords = words;
    }
    return { text: pieces.join("").replace(/ *\n */g, "\n").trim(), cut };
  }
  let read = main ? visibleText(main, true) : visibleText(document.body, false);
  // A page whose marked content holds next to nothing is read whole.
  if (main && read.text.length < 80) read = visibleText(document.body, false);
  if (read.text) result.text = read.text;
  if (read.cut) result.textCut = true;

  // Headings, images and links in view, each kind up to its limit.
  const found = [];
  function collect(selector, limit, describe) {
    let taken = 0;
    for (const element of document.querySelectorAll(selector)) {
      if (taken >= limit || late()) break;
      if (!inView(element)) continue;
      // As for the text: the site's own parts are left out where the
      // page marks its content.
      if (main && element.closest(FURNITURE)) continue;
      const described = describe(element);
      if (!described) continue;
      found.push({ element, described });
      taken += 1;
    }
  }

  collect("h1,h2,h3,h4,h5,h6,[role='heading']", limits.headings, (element) => {
    const title = oneLine(element.innerText);
    if (!title) return null;
    const level = /^H[1-6]$/.test(element.tagName)
      ? Number(element.tagName[1])
      : Number(element.getAttribute("aria-level")) || undefined;
    return { kind: "heading", title, level };
  });

  collect("img", limits.images, (element) => {
    const box = element.getBoundingClientRect();
    // Icons, spacers and trackers are images too, and say nothing. A
    // small portrait beside a post is the smallest picture worth naming.
    if (box.width < 32 || box.height < 32) return null;
    const caption = element.closest("figure")?.querySelector("figcaption");
    // Failing a caption and alt text, what the link or button around the
    // image is called.
    const around = element.closest("a,button,[role='img'],[role='link'],[role='button']");
    const title =
      oneLine(caption?.innerText) ||
      oneLine(element.alt) ||
      oneLine(element.title) ||
      oneLine(around?.getAttribute("aria-label")) ||
      undefined;
    const url = address(element.currentSrc || element.src);
    if (!title && !url) return null;
    return { kind: "image", title, url, width: element.naturalWidth || undefined, height: element.naturalHeight || undefined };
  });

  // Links in the page's own content first, so that a site's header and
  // footer take only the room that is left.
  const links = [...document.querySelectorAll("a[href]")];
  const furniture = (element) => Boolean(element.closest("header,footer,nav,aside,[role='navigation'],[role='banner']"));
  const ordered = links.filter((link) => !furniture(link)).concat(links.filter(furniture));
  const addresses = new Set();
  let linked = 0;
  for (const element of ordered) {
    if (linked >= limits.links || late()) break;
    if (!inView(element)) continue;
    const url = address(element.getAttribute("href"));
    const title =
      oneLine(element.innerText) || oneLine(element.getAttribute("aria-label")) || oneLine(element.querySelector("img")?.alt);
    if (!url || !title || addresses.has(url)) continue;
    addresses.add(url);
    found.push({ element, described: { kind: "link", title, url } });
    linked += 1;
  }

  // In the page's own order, whatever order they were found in.
  found.sort((a, b) => (a.element.compareDocumentPosition(b.element) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1));
  if (found.length) {
    result.page = memory.page;
    result.elements = found.map(({ element, described }) => Object.assign({ n: number(element) }, described));
  }
  return result;
}
