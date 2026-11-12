import { source } from '@/lib/source';
import { createFromSource } from 'fumadocs-core/search/server';

// Static search: the build writes the whole index to `/search-index.json`, and the search dialog downloads it and searches in the browser. See `searchOptions` in `src/app/layout.tsx`.
export const revalidate = false;
export const dynamic = 'force-static';

export const { staticGET: GET } = createFromSource(source, {
  language: 'english',
});
