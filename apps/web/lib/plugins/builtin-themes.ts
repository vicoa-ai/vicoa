/**
 * Built-in example theme plugins.
 *
 * These ship with the app so the theme picker demonstrates plugin themes with
 * no daemon/backend involved (P0). They register under the synthetic
 * `builtin` machine and are always trusted. Real user plugins arrive later via
 * the `plugin-catalog` RPC and flow through the exact same code path.
 *
 * Tokens are bare HSL triplets consumed as `hsl(var(--token))`, matching
 * `app/globals.css`. Only whitelisted tokens are honoured (see
 * `THEME_TOKEN_WHITELIST`).
 */

import { type PluginManifest, PLUGIN_API_VERSION } from './types';

const catppuccin: PluginManifest = {
  id: 'catppuccin',
  apiVersion: PLUGIN_API_VERSION,
  name: 'Catppuccin',
  description: 'Soothing pastel themes — the community Catppuccin palette.',
  author: 'Vicoa (example)',
  themes: [
    {
      id: 'mocha',
      label: 'Catppuccin Mocha',
      base: 'dark',
      tokens: {
        background: '240 21% 15%',
        foreground: '226 64% 88%',
        card: '240 21% 12%',
        'card-foreground': '226 64% 88%',
        popover: '240 21% 12%',
        'popover-foreground': '226 64% 88%',
        primary: '267 84% 81%',
        'primary-foreground': '240 21% 15%',
        secondary: '237 16% 23%',
        'secondary-foreground': '226 64% 88%',
        muted: '237 16% 23%',
        'muted-foreground': '228 24% 72%',
        accent: '237 16% 23%',
        'accent-foreground': '226 64% 88%',
        destructive: '343 81% 75%',
        'destructive-foreground': '240 21% 15%',
        border: '234 13% 31%',
        input: '234 13% 31%',
        ring: '267 84% 81%',
        'sidebar-background': '240 23% 9%',
        'sidebar-foreground': '226 64% 88%',
        'sidebar-primary': '267 84% 81%',
        'sidebar-primary-foreground': '240 21% 15%',
        'sidebar-accent': '237 16% 23%',
        'sidebar-accent-foreground': '226 64% 88%',
        'sidebar-border': '234 13% 31%',
        'sidebar-ring': '267 84% 81%',
        'message-text': '226 64% 88%',
      },
    },
    {
      id: 'latte',
      label: 'Catppuccin Latte',
      base: 'light',
      tokens: {
        background: '220 23% 95%',
        foreground: '234 16% 35%',
        card: '220 22% 92%',
        'card-foreground': '234 16% 35%',
        popover: '220 22% 92%',
        'popover-foreground': '234 16% 35%',
        primary: '266 85% 58%',
        'primary-foreground': '220 23% 95%',
        secondary: '223 16% 83%',
        'secondary-foreground': '234 16% 35%',
        muted: '223 16% 83%',
        'muted-foreground': '233 10% 47%',
        accent: '223 16% 83%',
        'accent-foreground': '234 16% 35%',
        destructive: '347 87% 44%',
        'destructive-foreground': '220 23% 95%',
        border: '223 16% 83%',
        input: '223 16% 83%',
        ring: '266 85% 58%',
        'sidebar-background': '223 16% 88%',
        'sidebar-foreground': '234 16% 35%',
        'sidebar-primary': '266 85% 58%',
        'sidebar-primary-foreground': '220 23% 95%',
        'sidebar-accent': '223 16% 83%',
        'sidebar-accent-foreground': '234 16% 35%',
        'sidebar-border': '223 16% 83%',
        'sidebar-ring': '266 85% 58%',
        'message-text': '234 16% 35%',
      },
    },
  ],
};

export const BUILTIN_PLUGIN_MANIFESTS: PluginManifest[] = [catppuccin];
