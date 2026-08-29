// Terminal pane patterns adapted from Orca (https://github.com/stablyai/orca),
// MIT License, Copyright (c) 2026 Lovecast Inc.
//
// Default xterm options + a fixed dark theme matching the Vicoa dashboard
// (.dark tokens in app/globals.css: background #161C24, card #212B36).
// ANSI colors are the Tailwind 400-series the dashboard already leans on.

import type { ITerminalOptions, ITheme } from '@xterm/xterm';

export const VICOA_TERMINAL_BACKGROUND = '#161C24';

export const VICOA_TERMINAL_THEME: ITheme = {
  background: VICOA_TERMINAL_BACKGROUND,
  foreground: '#E2E8F0',
  cursor: '#E2E8F0',
  cursorAccent: VICOA_TERMINAL_BACKGROUND,
  selectionBackground: 'rgba(148, 163, 184, 0.30)',
  black: '#1C2430',
  red: '#F87171',
  green: '#4ADE80',
  yellow: '#FACC15',
  blue: '#60A5FA',
  magenta: '#C084FC',
  cyan: '#22D3EE',
  white: '#E2E8F0',
  brightBlack: '#64748B',
  brightRed: '#FCA5A5',
  brightGreen: '#86EFAC',
  brightYellow: '#FDE047',
  brightBlue: '#93C5FD',
  brightMagenta: '#D8B4FE',
  brightCyan: '#67E8F9',
  brightWhite: '#F8FAFC',
  // Match the dashboard scrollbar (dark: bg-muted-foreground/20).
  scrollbarSliderBackground: 'rgba(148, 163, 184, 0.20)',
  scrollbarSliderHoverBackground: 'rgba(148, 163, 184, 0.30)',
  scrollbarSliderActiveBackground: 'rgba(148, 163, 184, 0.40)',
};

// Orca-derived defaults, trimmed to what stable @xterm/xterm 6.0.0 supports
// (their `scrollbar.width` / `vtExtensions.kittyKeyboard` options are 6.1-beta
// only). WebGL, ligatures, and IME layers are intentionally out of scope (v1).
export function buildTerminalOptions(): ITerminalOptions {
  return {
    // Unicode11Addon requires the proposed API surface.
    allowProposedApi: true,
    cursorBlink: true,
    cursorStyle: 'block',
    // Why (Orca): only block cursors benefit from the inactive outline.
    cursorInactiveStyle: 'outline',
    fontSize: 14,
    // Symbols-only Nerd Font first (bundled, see terminal-fonts.css) supplies
    // powerline + Nerd Font icon glyphs; it has no Latin glyphs, so the browser
    // falls through to the cross-platform monospace text chain (Orca's) for all
    // normal characters and cell-width measurement.
    fontFamily:
      '"Symbols Nerd Font Mono", "SF Mono", Menlo, Monaco, "Cascadia Mono", ' +
      'Consolas, "DejaVu Sans Mono", "Liberation Mono", "JetBrains Mono", monospace',
    fontWeight: '400',
    fontWeightBold: '600',
    scrollback: 5000,
    allowTransparency: false,
    // Why (Orca): agent CLIs render body text ANSI white/bright-white; keep
    // those cells readable regardless of theme.
    minimumContrastRatio: 4.5,
    // Why (Orca): on macOS, non-US layouts rely on Option to compose @ and €.
    macOptionIsMeta: false,
    macOptionClickForcesSelection: true,
    drawBoldTextInBrightColors: true,
    theme: VICOA_TERMINAL_THEME,
  };
}
