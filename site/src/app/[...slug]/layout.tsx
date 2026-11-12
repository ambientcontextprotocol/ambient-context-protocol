import { source } from '@/lib/source';
import { DocsLayout } from 'fumadocs-ui/layouts/notebook';
import { baseOptions } from '@/lib/layout.shared';

export default function Layout({ children }: LayoutProps<'/[...slug]'>) {
  const base = baseOptions();
  return (
    <DocsLayout
      tree={source.getPageTree()}
      {...base}
      tabMode="navbar"
      // No collapse button: the sidebar always shows on desktop. Phones keep the menu button.
      sidebar={{ collapsible: false }}
      nav={{ ...base.nav, mode: 'top' }}
    >
      {children}
    </DocsLayout>
  );
}
