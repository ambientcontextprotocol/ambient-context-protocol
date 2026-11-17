import { getLLMText, markdownUrl } from '@/lib/llm';
import { source } from '@/lib/source';
import { notFound } from 'next/navigation';

// Each page's Markdown as a static file: `/docs/concepts` is at `/md/docs/concepts.md`. The `.md` ending is part of the last path segment, so the export writes a real `.md` file that a static host serves as text.
export const revalidate = false;
export const dynamic = 'force-static';
export const dynamicParams = false;

export async function GET(_req: Request, { params }: RouteContext<'/md/[...slug]'>) {
  const { slug } = await params;
  const last = slug[slug.length - 1];
  if (!last.endsWith('.md')) notFound();
  const page = source.getPage([...slug.slice(0, -1), last.slice(0, -'.md'.length)]);
  if (!page) notFound();

  return new Response(await getLLMText(page), {
    headers: { 'Content-Type': 'text/markdown; charset=utf-8' },
  });
}

export function generateStaticParams() {
  return source.getPages().map((page) => ({
    slug: markdownUrl(page).split('/').slice(2),
  }));
}
