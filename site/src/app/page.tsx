import type { Metadata } from 'next';

// The site has no landing page yet, so the root sends the reader to the documentation. A static export has no server to answer with a redirect, so the page carries a meta refresh, which works from any static host.
const target = '/docs/';

export const metadata: Metadata = {
  alternates: { canonical: target },
  robots: { index: false, follow: true },
};

export default function Home() {
  return (
    <main className="p-8">
      <meta httpEquiv="refresh" content={`0; url=${target}`} />
      <p>
        Continue to the <a href={target}>documentation</a>.
      </p>
    </main>
  );
}
