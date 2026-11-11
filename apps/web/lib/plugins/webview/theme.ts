/**
 * The host's current theme as `--vicoa-*` CSS variables for plugin pages.
 *
 * Read from the live document, so a plugin page matches whatever the app shows
 * (built-in light/dark or a plugin theme). Pages are free to ignore them.
 */

import { THEME_TOKEN_WHITELIST } from '../types';

export const PLUGIN_FONT_SANS =
  "ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif";
export const PLUGIN_FONT_MONO = "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace";

export type ThemeMode = 'dark' | 'light';

/** `hsl(...)` for an HSL triplet token; `radius` and anything else as-is. */
export function tokenValue(name: string, raw: string): string | null {
  const value = raw.trim();
  if (!value) return null;
  if (name === 'radius') return value;
  return /^[\d.]+\s+[\d.]+%\s+[\d.]+%$/.test(value) ? `hsl(${value})` : value;
}

/** `:root{--vicoa-…}` from a token reader (the host's computed style). */
export function themeCss(read: (token: string) => string, mode: ThemeMode): string {
  const decls = [`--vicoa-color-scheme:${mode}`, `--vicoa-font-sans:${PLUGIN_FONT_SANS}`, `--vicoa-font-mono:${PLUGIN_FONT_MONO}`];
  for (const token of THEME_TOKEN_WHITELIST) {
    const value = tokenValue(token, read(token));
    // Values come from the app's own stylesheet; still refuse anything that
    // could end the declaration.
    if (value && !/[;{}<>]/.test(value)) decls.push(`--vicoa-${token}:${value}`);
  }
  return `:root{${decls.join(';')}}`;
}

/** The theme as the browser currently shows it. */
export function readHostTheme(): { mode: ThemeMode; css: string } {
  if (typeof document === 'undefined') return { mode: 'dark', css: '' };
  const root = document.documentElement;
  const mode: ThemeMode = root.classList.contains('dark') ? 'dark' : 'light';
  const style = getComputedStyle(root);
  return { mode, css: themeCss((token) => style.getPropertyValue(`--${token}`), mode) };
}
