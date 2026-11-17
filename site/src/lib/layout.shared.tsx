import { ProtocolLogo } from '@/components/protocol-logo';
import type { BaseLayoutProps } from 'fumadocs-ui/layouts/shared';
import { name } from './name';
import { repoUrl } from './repo.mjs';

export function baseOptions(): BaseLayoutProps {
  return {
    themeSwitch: { enabled: false },
    githubUrl: repoUrl,
    nav: {
      title: (
        <span className="inline-flex items-center gap-2">
          <ProtocolLogo className="size-5 shrink-0" />
          <span className="wordmark">{name}</span>
        </span>
      ),
    },
  };
}
