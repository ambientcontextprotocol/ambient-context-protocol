import { createMDX } from 'fumadocs-mdx/next';

const withMDX = createMDX();

/** @type {import('next').NextConfig} */
const config = {
  reactStrictMode: true,
  // `next build` writes plain static files to `out/`, which any static host can serve. No redirects, rewrites or server routes: the root redirect is `src/app/page.tsx`, search is a static index at `/search-index.json`, and each page's Markdown is a static file under `/md/`.
  output: 'export',
  // Every page is a directory with an `index.html` (`out/docs/index.html`), the one layout every static host and plain file server resolves without a rewrite rule.
  trailingSlash: true,
  // Set NEXT_DIST_DIR to build beside a running dev server without sharing `.next`.
  distDir: process.env.NEXT_DIST_DIR || '.next',
};

export default withMDX(config);
