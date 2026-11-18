import { absolute, markdownUrl, repoFileUrl, repoUrl, sections, summary } from '@/lib/llm';
import { name } from '@/lib/name';

// The index a model reads first (llmstxt.org): what the protocol is, the facts needed to use it, and a link to every page as Markdown.
export const revalidate = false;
export const dynamic = 'force-static';

const facts = `> An extension to the Model Context Protocol (MCP) that lets a desktop app tell an AI assistant what the user is looking at: which windows and documents are open, what is selected, and where each of those things is on screen.

Version \`0.2.4\`. Any name may change before 1.0.

The facts most often needed:

- It is ordinary MCP. A **provider** is an MCP server inside a desktop app. A **host** is an MCP client, such as an assistant the user calls from anywhere. The **agent** sees only what the host passes on.
- A provider answers two MCP resources. \`ambient://current\` returns what is open and selected, as one tree of elements rooted at the app. \`ambient://location/{id}\` returns where one element is on screen.
- The extension is declared as \`io.github.ambientcontextprotocol/context\` under \`capabilities.extensions\`, with \`{ "version": "0.2.4" }\`. The MCP revision relied on is \`2026-07-28\`.
- The answer to \`current\` has three required fields, \`protocol\`, \`instance\` and \`root\`, and two optional. \`display\`: the app's own \`title\` and \`detail\`, each one line of plain text of at most 80 characters, for the line a host shows the user. A host uses \`display\` only when \`title\` is a non-empty string and reads a malformed one as absent. \`sensitive\`, sent only as \`true\`, says that what the answer holds is likely private: a host asks the user before sending that context to an agent, reads any other value as absent, and never reads its absence as safe. Redacting private details inside an answer is the provider's job; no host is required to. An app may also ship a favicon for hosts at \`Contents/Resources/favicon.svg\` (or \`favicon.png\`) in its macOS bundle; no message names or carries it. An element has an \`id\` and a \`role\`, and may have \`subrole\`, \`title\`, \`url\`, \`content\` (MCP content blocks), \`attributes\`, \`children\` and the states \`selected\`, \`focused\`, \`visible\` and \`hovered\`.
- There are thirteen roles: \`Application\`, \`Window\`, \`Document\`, \`Group\`, \`List\`, \`Table\`, \`Row\`, \`Cell\`, \`Text\`, \`Heading\`, \`Link\`, \`Image\` and \`Page\`. The role says how a thing is shown; the app's own word for what it is goes in \`subrole\`.
- The server listens on \`127.0.0.1\` only, over MCP's Streamable HTTP transport. Every request carries \`Authorization: Bearer <token>\`, and a request with an \`Origin\` header is refused.
- A host finds a provider through a descriptor file the running provider writes: \`<app-id>.<pid>.json\` in the platform's descriptor folder. Version 0.2.4 defines one platform profile, macOS, where the folder is \`~/Library/Application Support/AmbientContext/providers/\`. The file gives the protocol version, the app, the process id, the instance, the endpoint and the token.
- A host reads only when the user calls on it. It takes the front app's process id, finds that app's descriptor, checks that the process listening on the endpoint's port is the process the descriptor names, and then reads \`ambient://current\`.
- The specification is the contract. Where a guide and the specification differ, the specification is right.

Every link below is to plain Markdown. The whole site in one file is at ${absolute('/llms-full.txt')}.`;

export function GET() {
  const lines = [`# ${name}`, '', facts];

  for (const section of sections()) {
    lines.push('', `## ${section.title}`, '');
    for (const page of section.pages) {
      const description = summary(page);
      lines.push(`- [${page.data.title}](${absolute(markdownUrl(page))})${description ? `: ${description}` : ''}`);
    }
  }

  lines.push(
    '',
    '## Code',
    '',
    `- [Repository](${repoUrl}): the specification's source, the RFCs, the packages and the checks.`,
    `- [JSON Schema for the answer to current](${repoFileUrl('schema/current-0.2.4.json')}): validate a provider's tree against it.`,
    `- [Swift package](${repoFileUrl('sdk/swift/README.md')}): makes a macOS app a provider. The app says what is open and selected; the package runs the server and keeps the descriptor.`,
    `- [TypeScript package](${repoFileUrl('sdk/typescript/README.md')}): the same for an Electron or Node app, with no dependencies.`,
    `- [Conformance check](${repoFileUrl('tools/conformance/README.md')}): a script that checks a running provider from outside.`,
    '',
  );

  return new Response(lines.join('\n'), { headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
}
