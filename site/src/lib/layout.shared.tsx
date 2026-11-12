import type { BaseLayoutProps } from 'fumadocs-ui/layouts/shared';
import { name } from './name';

export function baseOptions(): BaseLayoutProps {
  return {
    themeSwitch: { enabled: false },
    nav: {
      title: <span className="wordmark">{name}</span>,
    },
  };
}
