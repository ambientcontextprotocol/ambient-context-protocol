import { absolute, getLLMText, markdownUrl, sections } from '@/lib/llm';
import { name } from '@/lib/name';

// Every page of the site as one Markdown file, in the order the navigation shows them, for a model that would rather read it all at once.
export const revalidate = false;
export const dynamic = 'force-static';

export async function GET() {
  const parts = [`# ${name}: the whole site\n\nEvery page of ${absolute('/')} in reading order. The index of the same pages is at ${absolute('/llms.txt')}.`];

  for (const section of sections()) {
    for (const page of section.pages) {
      const text = await getLLMText(page);
      parts.push(`<!-- ${section.title} · ${absolute(markdownUrl(page))} -->\n\n${text.trim()}`);
    }
  }

  return new Response(`${parts.join('\n\n---\n\n')}\n`, { headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
}
