import Image from 'next/image';
import type { LucideIcon } from 'lucide-react';
import { Code, FolderOpen, Terminal } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { OpenApp, OpenAppKind } from './rpc';

/**
 * App marks for the "Open in…" menu, in the apps' own colours.
 *
 * Assets live in `public/images/open-in/` (Cursor reuses the one already in
 * `integrations/`). Sources: the real app icons, plus Iconify's `logos`,
 * `thesvg-color` and `selfh.st` sets.
 *
 * `invertForDark` is the same treatment `agent-type-icon.tsx` calls `isOpenAI`:
 * a mark that is a single near-black glyph reads fine on the light menu but
 * vanishes on the dark one, so invert it there. Only the two monochrome marks
 * need it — every other logo carries its own colour and works on both themes
 * (verified by rendering the whole set over both menu backgrounds).
 *
 * Apps with no usable mark — the Linux `xdg-open` file manager, macOS
 * Terminal.app, kitty, Konsole — fall back to the icon for their kind, which
 * reads fine next to the label.
 */

const KIND_FALLBACK: Record<OpenAppKind, LucideIcon> = {
  'file-manager': FolderOpen,
  editor: Code,
  terminal: Terminal,
};

interface AppMark {
  src: string;
  /** Near-black single-colour glyph: invert it on the dark menu. */
  invertForDark?: boolean;
}

/** App id (from the daemon catalogue) → its brand mark. */
const APP_MARKS: Record<string, AppMark> = {
  // ── File managers ──────────────────────────────────────────────────────────
  finder: { src: '/images/open-in/finder.png' },
  explorer: { src: '/images/open-in/explorer.png' },
  // ── Editors ────────────────────────────────────────────────────────────────
  vscode: { src: '/images/open-in/vscode.png' },
  'vscode-insiders': { src: '/images/open-in/vscode.png' },
  cursor: { src: '/images/integrations/cursor.svg', invertForDark: true },
  windsurf: { src: '/images/open-in/windsurf.svg', invertForDark: true },
  zed: { src: '/images/open-in/zed.png' },
  sublime: { src: '/images/open-in/sublime.svg' },
  intellij: { src: '/images/open-in/intellij.svg' },
  webstorm: { src: '/images/open-in/webstorm.png' },
  pycharm: { src: '/images/open-in/pycharm.svg' },
  goland: { src: '/images/open-in/goland.svg' },
  // ── Terminals ──────────────────────────────────────────────────────────────
  iterm: { src: '/images/open-in/iterm.svg' },
  ghostty: { src: '/images/open-in/ghostty.svg' },
  warp: { src: '/images/open-in/warp.svg' },
  'windows-terminal': { src: '/images/open-in/windows-terminal.svg' },
  'gnome-terminal': { src: '/images/open-in/gnome-terminal.svg' },
  alacritty: { src: '/images/open-in/alacritty.svg' },
  wezterm: { src: '/images/open-in/wezterm.svg' },
};

export function OpenAppIcon({ app, size = 16 }: { app: OpenApp; size?: number }) {
  const mark = APP_MARKS[app.id];
  if (!mark) {
    const Fallback = KIND_FALLBACK[app.kind];
    return <Fallback className="shrink-0 text-muted-foreground" style={{ width: size, height: size }} />;
  }
  return (
    <Image
      src={mark.src}
      alt=""
      aria-hidden
      width={size}
      height={size}
      unoptimized
      className={cn('shrink-0 object-contain', mark.invertForDark && 'dark:invert')}
      style={{ width: size, height: size }}
    />
  );
}
