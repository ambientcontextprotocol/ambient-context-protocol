#!/usr/bin/env node
// Generates the site's Specification and RFC sections from the repository's Markdown, so the site cannot drift from it.
//
//   docs/spec/*.md                          -> content/docs/specification/*.md + meta.json
//   docs/rfcs/index.md, README.md, NNNN-*.md -> content/docs/rfcs/*.md + meta.json   (0000-template.md is not a page)
//
// For each file it takes the title from the H1, writes fumadocs frontmatter, drops the H1 and the "Part of the specification" line, and rewrites relative links: a link to another generated page becomes a site URL, a link to any other file in the repository becomes a GitHub URL. It exits non-zero on a relative link or an anchor it cannot resolve.
//
// The output is plain `.md`, which fumadocs-mdx compiles as Markdown and not MDX, so `<bundle-id>` and `{id}` in the specification need no escaping. Heading anchors need no rewriting: fumadocs slugs headings with github-slugger, the same algorithm GitHub uses, and this script checks every anchor with that same library.

import { existsSync, mkdirSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { dirname, join, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import GithubSlugger from 'github-slugger';
import { repoBranch, repoFileUrl, repoUrl } from '../src/lib/repo.mjs';

const siteDir = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const repoDir = resolve(siteDir, '..');
const specSrc = join(repoDir, 'docs/spec');
const rfcSrc = join(repoDir, 'docs/rfcs');
const specOut = join(siteDir, 'content/docs/specification');
const rfcOut = join(siteDir, 'content/docs/rfcs');

const TITLE_PREFIX = 'Ambient Context Protocol · ';
const PART_OF = /^> Part of the \[specification\]\(index\.md\), version `([^`]+)`\.\s*$/;
const RFC_FILE = /^(\d{4})-.+\.md$/;

const errors = [];
const fail = (file, message) => errors.push(`${relative(repoDir, file)}: ${message}`);

// ---------------------------------------------------------------------------------------------------------------------
// Reading a source file

/** Calls `onLine(line, inFence)` for each line, tracking fenced code blocks. */
function eachLine(text, onLine) {
  let fence = null;
  return text.split('\n').map((line) => {
    const open = line.match(/^\s{0,3}(`{3,}|~{3,})/);
    if (fence) {
      if (open && open[1][0] === fence[0] && open[1].length >= fence.length && line.trim() === open[1]) fence = null;
      return onLine(line, true);
    }
    if (open) {
      fence = open[1];
      return onLine(line, true);
    }
    return onLine(line, false);
  });
}

/** The text of a heading as the slugger sees it: inline Markdown removed. */
function headingText(raw) {
  return raw
    .replace(/\s+#+\s*$/, '')
    .replace(/!?\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/`([^`]*)`/g, '$1')
    .replace(/(\*\*|__|\*|_)(.+?)\1/g, '$2')
    .trim();
}

/** Plain text for a frontmatter description. */
function plain(text) {
  return text
    .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/`([^`]*)`/g, '$1')
    .replace(/\s+/g, ' ')
    .trim();
}

function load(src,{ section, slug, title: fixedTitle }) {
  const lines = readFileSync(src, 'utf8').replace(/\r\n/g, '\n').split('\n');

  const h1 = lines.findIndex((line) => line.trim() !== '');
  const h1Match = h1 >= 0 ? lines[h1].match(/^# (.+)$/) : null;
  if (!h1Match) fail(src, 'the first line is not an H1, so there is no title');
  let title = h1Match ? headingText(h1Match[1]) : slug;
  if (title.startsWith(TITLE_PREFIX)) title = title.slice(TITLE_PREFIX.length);
  if (fixedTitle) title = fixedTitle;

  const body = lines.slice(h1 + 1);
  const page = { src, section, slug, title, description: undefined, version: undefined };
  page.url = slug === 'index' ? `/${section}` : `/${section}/${slug}`;

  // The "Part of the specification, version x" line becomes the description.
  const partOf = body.findIndex((line) => PART_OF.test(line));
  if (partOf >= 0) {
    page.version = body[partOf].match(PART_OF)[1];
    page.description = `Version ${page.version} of the specification.`;
    body.splice(partOf, 1);
  }

  const firstBlock = () => {
    const start = body.findIndex((line) => line.trim() !== '');
    if (start < 0) return null;
    let end = start;
    while (end < body.length && body[end].trim() !== '') end++;
    return { start, end, lines: body.slice(start, end) };
  };

  // The specification index opens with its version line: "Version `0.2.4` · Draft of ...".
  if (section === 'specification' && slug === 'index') {
    const block = firstBlock();
    const version = block?.lines.join(' ').match(/^Version `([^`]+)`/);
    if (version) {
      page.version = version[1];
      page.description = plain(block.lines.join(' '));
      body.splice(block.start, block.end - block.start);
    } else {
      fail(src, 'no "Version `x.y.z`" line after the H1, so the specification version is unknown');
    }
  }

  // An RFC opens with a one-paragraph summary in a block quote. It becomes the description when it holds no link.
  if (section === 'rfcs' && !page.description) {
    const block = firstBlock();
    if (block && block.lines.every((line) => line.startsWith('>'))) {
      const text = block.lines.map((line) => line.replace(/^>\s?/, '')).join(' ');
      if (!/\]\(/.test(text)) {
        page.description = plain(text);
        body.splice(block.start, block.end - block.start);
      }
    }
  }

  while (body.length && body[0].trim() === '') body.shift();
  page.body = body.join('\n').replace(/\s+$/, '') + '\n';

  // Heading anchors, as fumadocs (and GitHub) will generate them. The H1 is dropped, so it has none.
  const slugger = new GithubSlugger();
  page.anchors = new Set();
  eachLine(page.body, (line, inFence) => {
    const heading = !inFence && line.match(/^\s{0,3}#{1,6}\s+(.+)$/);
    if (heading) page.anchors.add(slugger.slug(headingText(heading[1])));
  });

  return page;
}

// ---------------------------------------------------------------------------------------------------------------------
// Collecting the pages

const pages = new Map(); // absolute source path -> page

function add(src, options) {
  if (!existsSync(src)) {
    fail(src, 'expected source file is missing');
    return null;
  }
  const page = load(src, options);
  pages.set(src, page);
  return page;
}

// Specification: the order is the order of the Contents table in docs/spec/index.md.
const specIndex = add(join(specSrc, 'index.md'), { section: 'specification', slug: 'index', title: 'Specification' });
const specOrder = ['index'];
if (specIndex) {
  for (const row of specIndex.body.split('\n')) {
    const first = row.match(/^\|\s*\[[^\]]+\]\(([^)#\s]+\.md)\)\s*\|/);
    if (first && !specOrder.includes(first[1].replace(/\.md$/, ''))) specOrder.push(first[1].replace(/\.md$/, ''));
  }
}
const specFiles = readdirSync(specSrc).filter((name) => name.endsWith('.md')).map((name) => name.replace(/\.md$/, ''));
for (const name of specFiles) {
  if (!specOrder.includes(name)) fail(join(specSrc, `${name}.md`), 'not listed in the Contents table of docs/spec/index.md, so it has no place in the order');
}
for (const name of specOrder.slice(1)) add(join(specSrc, `${name}.md`), { section: 'specification', slug: name });

const version = specIndex?.version;
for (const page of pages.values()) {
  if (page.section === 'specification' && page.slug !== 'index') {
    if (!page.version) fail(page.src, 'no "> Part of the [specification](index.md), version `x.y.z`." line');
    else if (version && page.version !== version) fail(page.src, `says version ${page.version}, but docs/spec/index.md says ${version}`);
  }
}

// RFCs: index.md is the section's landing page (the list with statuses), README.md is the process, then each numbered RFC. 0000-template.md is not a page; links to it go to the repository.
add(join(rfcSrc, 'index.md'), { section: 'rfcs', slug: 'index', title: 'RFCs' });
add(join(rfcSrc, 'README.md'), { section: 'rfcs', slug: 'process' });
const rfcOrder = readdirSync(rfcSrc)
  .filter((name) => RFC_FILE.test(name) && !name.startsWith('0000-'))
  .sort()
  .map((name) => name.replace(/\.md$/, ''));
for (const name of rfcOrder) add(join(rfcSrc, `${name}.md`), { section: 'rfcs', slug: name });

// ---------------------------------------------------------------------------------------------------------------------
// Rewriting links

function rewriteHref(page, href, isImage) {
  if (/^[a-z][a-z0-9+.-]*:/i.test(href) || href.startsWith('//')) return href; // absolute
  if (href.startsWith('/')) {
    fail(page.src, `link "${href}" is root-relative; it means nothing in the repository`);
    return href;
  }

  const hash = href.indexOf('#');
  const path = hash >= 0 ? href.slice(0, hash) : href;
  const anchor = hash >= 0 ? decodeURIComponent(href.slice(hash + 1)) : '';

  if (path === '') {
    if (anchor && !page.anchors.has(anchor)) fail(page.src, `anchor "#${anchor}" matches no heading in this file`);
    return href;
  }

  const target = resolve(dirname(page.src), decodeURIComponent(path));
  const targetPage = pages.get(target);
  if (targetPage && !isImage) {
    if (anchor && !targetPage.anchors.has(anchor)) {
      fail(page.src, `link "${href}": no heading in ${relative(repoDir, target)} has the anchor "#${anchor}"`);
    }
    return targetPage.url + (anchor ? `#${anchor}` : '');
  }

  const inRepo = target === repoDir || target.startsWith(repoDir + sep);
  if (!inRepo || !existsSync(target)) {
    fail(page.src, `link "${href}" resolves to ${inRepo ? relative(repoDir, target) : target}, which ${inRepo ? 'does not exist' : 'is outside the repository'}`);
    return href;
  }
  if (isImage) {
    fail(page.src, `image "${href}": this script does not copy images into the site yet`);
    return href;
  }
  const repoPath = relative(repoDir, target).split(sep).join('/');
  const url = statSync(target).isDirectory() ? `${repoUrl}/tree/${repoBranch}/${repoPath}` : repoFileUrl(repoPath);
  return url + (anchor ? `#${anchor}` : '');
}

function rewriteLinks(page) {
  return eachLine(page.body, (line, inFence) => {
    if (inFence) return line;

    // Reference-style definition: [label]: target
    const definition = line.match(/^(\s{0,3}\[[^\]]+\]:\s*)(<?)([^\s>]+)(>?)(.*)$/);
    if (definition) {
      return definition[1] + definition[2] + rewriteHref(page, definition[3], false) + definition[4] + definition[5];
    }

    // Inline links and images, outside code spans. A code span never contains "](", so splitting on spans is safe.
    const parts = line.split(/(`+[^`]*`+)/);
    for (let i = 0; i < parts.length; i += 2) {
      parts[i] = parts[i].replace(/\]\((<?)([^)\s>]+)(>?)((?:\s+"[^"]*")?)\)/g, (match, open, href, close, linkTitle, offset) => {
        const before = parts.slice(0, i).join('') + parts[i].slice(0, offset);
        const isImage = /!\[[^\]]*$/.test(before);
        return `](${open}${rewriteHref(page, href, isImage)}${close}${linkTitle})`;
      });
    }
    return parts.join('');
  }).join('\n');
}

// ---------------------------------------------------------------------------------------------------------------------
// Writing

const outputs = new Map(); // absolute output path -> content

for (const page of pages.values()) {
  const frontmatter = [
    '---',
    `# Generated from ${relative(repoDir, page.src)} by site/scripts/sync-spec.mjs. Do not edit; edit the source.`,
    `title: ${JSON.stringify(page.title)}`,
  ];
  if (page.description) frontmatter.push(`description: ${JSON.stringify(page.description)}`);
  frontmatter.push('---', '');
  const dir = page.section === 'specification' ? specOut : rfcOut;
  outputs.set(join(dir, `${page.slug}.md`), frontmatter.join('\n') + '\n' + rewriteLinks(page));
}

const json = (value) => JSON.stringify(value, null, 2) + '\n';
outputs.set(join(specOut, 'meta.json'), json({ title: 'Specification', root: true, pages: [`---Draft ${version}---`, ...specOrder] }));
outputs.set(join(rfcOut, 'meta.json'), json({ title: 'RFCs', root: true, pages: ['index', 'process', '---Proposals---', ...rfcOrder] }));

if (errors.length) {
  console.error(`sync-spec: ${errors.length} problem${errors.length === 1 ? '' : 's'}; nothing written.\n`);
  for (const error of errors) console.error(`  - ${error}`);
  process.exit(1);
}

// Write only what changed and remove what is stale, so a running dev server reloads no more than it must.
let written = 0;
let removed = 0;
for (const dir of [specOut, rfcOut]) {
  mkdirSync(dir, { recursive: true });
  for (const name of readdirSync(dir)) {
    if (!outputs.has(join(dir, name))) {
      rmSync(join(dir, name), { recursive: true });
      removed++;
    }
  }
}
for (const [file, content] of outputs) {
  if (existsSync(file) && readFileSync(file, 'utf8') === content) continue;
  writeFileSync(file, content);
  written++;
}

console.log(`sync-spec: specification ${version}, ${specOrder.length} pages; ${rfcOrder.length} RFCs, ${rfcOrder.length + 2} pages; ${written} files written, ${removed} removed.`);
