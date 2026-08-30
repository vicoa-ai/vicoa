import type { DocsLayoutProps } from 'fumadocs-ui/layouts/docs';
import { pageTree } from '@/lib/source';

export const docsOptions: DocsLayoutProps = {
  tree: pageTree,
  nav: {
    title: 'Vicoa Docs',
    url: '/',
    transparentMode: 'top',
  },
  themeSwitch: {
    enabled: false,
  },
  sidebar: {
    defaultOpenLevel: 1,
    tabs: false,
  },
};