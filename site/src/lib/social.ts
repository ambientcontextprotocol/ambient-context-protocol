import type { Metadata } from 'next';
import { name } from './name';

// The address the site is published at. Link previews need absolute addresses, and a static export has no request to take one from.
export const siteUrl = 'https://ambientcontextprotocol.com';

const image = { url: '/social-preview.png', width: 1280, height: 640, alt: name };

/**
 * The link preview for a page: the same image everywhere, with the page's own title and description.
 * A page that sets `openGraph` replaces the layout's whole, so every page builds its own from here.
 */
export function social(page?: { title?: string; description?: string; path?: string }): Pick<Metadata, 'openGraph' | 'twitter'> {
  const title = page?.title ? `${page.title} | ${name}` : name;
  return {
    openGraph: { type: 'website', siteName: name, title, description: page?.description, url: page?.path, images: [image] },
    twitter: { card: 'summary_large_image', title, description: page?.description, images: [image] },
  };
}
