import { RootProvider } from 'fumadocs-ui/provider/next';
import type { Metadata } from 'next';
import { name } from '@/lib/name';
import './global.css';

export const metadata: Metadata = {
  title: { template: `%s | ${name}`, default: name },
  icons: { icon: [{ url: '/favicon.svg', type: 'image/svg+xml' }] },
};

export default function Layout({ children }: LayoutProps<'/'>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="flex flex-col min-h-screen">
        <RootProvider
          // Static search: the dialog downloads the index the build wrote and searches in the browser.
          search={{ options: { type: 'static', api: '/search-index.json' } }}
          theme={{ forcedTheme: 'dark', defaultTheme: 'dark', enableSystem: false }}>
          {children}
        </RootProvider>
      </body>
    </html>
  );
}
