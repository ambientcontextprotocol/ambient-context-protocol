import { name } from './name';
import { repoFileUrl, repoUrl } from './repo.mjs';
import { siteUrl } from './social';
import { source } from './source';

// What the site gives to a program that reads it instead of a person: each page as plain Markdown, an index of them at /llms.txt, and all of them in one file at /llms-full.txt.

type Page = ReturnType<typeof source.getPages>[number];

/** Where a page's Markdown is served: `/docs/concepts` is at `/md/docs/concepts.md`. */
export function markdownUrl(page: Page) {
  return `/md${page.url}.md`;
}

/** An address on the published site. A static file has no request to take the host from. */
export function absolute(path: string) {
  return `${siteUrl}${path}`;
}

const diagram = [
  'Three parties, left to right:',
  '',
  '* **Providers** are the apps the user works in: editors, design tools, task and mail apps. They answer what is open and selected, and where it is on screen.',
  `* **The ${name}**, an extension to MCP, sits between them as two resources: \`ambient://current\` and \`ambient://location/{id}\`.`,
  '* **Hosts** are MCP clients, such as an ambient assistant. They read when the user asks, and pass on to the agent only what they choose.',
].join('\n');

function attribute(tag: string, key: string) {
  return new RegExp(`\\b${key}="([^"]*)"`).exec(tag)?.[1];
}

/** A link to another page of the site becomes the absolute address of that page's Markdown, so a reader that follows it gets text. */
function link(target: string) {
  const [path, fragment] = target.split('#');
  const slug = path.split('/').filter(Boolean);
  const page = source.getPage(slug);
  const address = page ? absolute(markdownUrl(page)) : absolute(path);
  return fragment ? `${address}#${fragment}` : address;
}

/**
 * A page's processed Markdown with the site's components turned into plain Markdown.
 * The processed text still carries MDX: import lines, `<Cards>`, `<Steps>`, `<Tabs>`, `<Callout>` and the diagram. A model reading it should not have to guess what those draw.
 */
export function plain(markdown: string) {
  const out: string[] = [];
  let depth = 0; // how many components we are inside; their content is indented two spaces a level
  let fence: string | null = null;

  for (const raw of markdown.split('\n')) {
    const indent = Math.min(raw.length - raw.trimStart().length, depth * 2);
    const line = raw.slice(indent);
    const text = line.trim();

    const mark = /^(`{3,}|~{3,})/.exec(text)?.[1];
    if (fence) {
      if (mark && mark.startsWith(fence)) fence = null;
      out.push(line);
      continue;
    }
    if (mark) {
      fence = mark;
      out.push(line);
      continue;
    }

    if (/^import .* from '[^']+';$/.test(text)) continue;
    if (text === '<OverviewDiagram />') {
      out.push(diagram);
      continue;
    }

    const open = /^<(Cards|Card|Steps|Step|Tabs|Tab|Callout)\b[^]*?(\/?)>$/.exec(text);
    if (open) {
      const [tag, kind, selfClosing] = open;
      const title = attribute(tag, 'title');
      if (kind === 'Card' && selfClosing) {
        const href = attribute(tag, 'href');
        const description = attribute(tag, 'description');
        out.push(`* ${href ? `[${title}](${link(href)})` : `**${title}**`}${description ? `: ${description}` : ''}`);
        continue;
      }
      if (kind === 'Card' && title) out.push(`**${title}**`, '');
      if (kind === 'Tab') out.push(`**${attribute(tag, 'value')}**`, '');
      if (kind === 'Callout') out.push(`**${title ?? (attribute(tag, 'type') === 'warn' ? 'Warning' : 'Note')}**`, '');
      depth += 1;
      continue;
    }
    if (/^<\/(Cards|Card|Steps|Step|Tabs|Tab|Callout)>$/.test(text)) {
      depth = Math.max(0, depth - 1);
      continue;
    }

    out.push(
      line
        .replaceAll('<ProtocolName />', name)
        .replace(/\]\((\/[^)\s]*)\)/g, (_, target: string) => `](${link(target)})`),
    );
  }

  return out.join('\n').replace(/\n{3,}/g, '\n\n').trim();
}

export async function getLLMText(page: Page) {
  const processed = await page.data.getText('processed');
  const description = page.data.description ? `${page.data.description}\n\n` : '';
  return `# ${page.data.title}\n\n${description}${plain(processed)}\n`;
}

/** The site's sections in the order the navigation shows them, each with its pages in order. */
export function sections() {
  const result: { title: string; pages: Page[] }[] = [];
  type Node = (typeof source.pageTree.children)[number];
  const walk = (node: Node, pages: Page[]) => {
    if (node.type === 'page') {
      const page = source.getPages().find((candidate) => candidate.url === node.url);
      if (page && !pages.includes(page)) pages.push(page);
    } else if (node.type === 'folder') {
      if (node.index) walk(node.index, pages);
      for (const child of node.children) walk(child, pages);
    }
  };
  for (const node of source.pageTree.children) {
    if (node.type !== 'folder') continue;
    const pages: Page[] = [];
    walk(node, pages);
    result.push({ title: typeof node.name === 'string' ? node.name : 'Pages', pages });
  }
  return result;
}

// What each page is for, where the page's own description does not say. The specification's pages all carry the same generated description, which tells a reader nothing about which one to open.
const summaries: Record<string, string> = {
  '/specification': 'Where to start: the contents of the specification, version 0.2.0, with its numbered sections.',
  '/specification/overview': 'Sections 1 to 3. The problem, one worked example of a request and its answer, and the roles and principles.',
  '/specification/operations': 'Section 4. The two operations, `current` and `locate`, and the exact shape of each answer.',
  '/specification/elements': 'Section 5. The element: its fields, the thirteen roles, the states, ids and instances, content, attributes and what to report.',
  '/specification/locations': 'Section 6. The answer to `locate`: states, rectangles, coordinates and hints.',
  '/specification/binding': 'Sections 7, 11 and 14. How it is carried over MCP: the server, declaring the extension, the two resources, errors and refusals, older clients, and what a provider must implement.',
  '/specification/discovery': 'Section 8. The descriptor file, what a host does to find and check a provider, what that defends against, and the macOS platform profile.',
  '/specification/security': 'Section 9. The rules for providers and for hosts.',
  '/specification/versioning': 'Sections 10, 12 and 13. Versioning, what is not in 0.2.0, the open questions and the changelog.',
  '/rfcs': 'Every RFC with its status and the version it was released in.',
  '/rfcs/process': 'What needs an RFC, and how one is written, reviewed, decided and released.',
};

/** One line on what a page is for. */
export function summary(page: Page) {
  return summaries[page.url] ?? page.data.description ?? '';
}

export { repoFileUrl, repoUrl };
