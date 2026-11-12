import type { BaseLayoutProps } from 'fumadocs-ui/layouts/shared';
import { name } from './name';
import { repoUrl } from './repo.mjs';

export function baseOptions(): BaseLayoutProps {
  return {
    themeSwitch: { enabled: false },
    githubUrl: repoUrl,
    nav: {
      title: <span className="wordmark">{name}</span>,
    },
  };
}
