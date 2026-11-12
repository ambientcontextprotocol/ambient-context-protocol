import { docs } from 'fumadocs-mdx:collections/server';
import { type InferPageType, loader } from 'fumadocs-core/source';
import { lucideIconsPlugin } from 'fumadocs-core/source/lucide-icons';

export const source = loader({
  baseUrl: '/',
  source: docs.toFumadocsSource(),
  plugins: [lucideIconsPlugin()],
});

type Page = InferPageType<typeof source>;

/** Where a page's Markdown is served: `/docs/concepts` is at `/md/docs/concepts.md`. */
export function markdownUrl(page: Page) {
  return `/md${page.url}.md`;
}

export async function getLLMText(page: Page) {
  const processed = await page.data.getText('processed');
  const description = page.data.description ? `${page.data.description}\n\n` : '';
  return `# ${page.data.title}\n\n${description}${processed.trim()}\n`;
}
