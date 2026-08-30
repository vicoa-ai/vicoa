/**
 * Desktop keyboard shortcuts: definitions, user overrides, and matching.
 *
 * The handlers (desktop sidebar, files/git panel) match key events through
 * `matchesShortcut`, and the settings page records overrides through
 * `setShortcutOverride` — so a rebind takes effect immediately, no reload.
 * Overrides persist in localStorage; the module keeps an in-memory cache
 * invalidated via a window event so keydown paths never re-parse JSON.
 *
 * `meta` on a combo means "the primary modifier", which differs by OS: ⌘ on
 * macOS, Ctrl on Windows/Linux. One binding, the platform-appropriate key —
 * so ⌘W closes a terminal tab on a Mac while Ctrl+W is left alone (it's the
 * terminal's own delete-word), and Ctrl+W closes it on Windows/Linux.
 */

import { getPref, setPref } from '@/lib/desktop-prefs';
import { getDesktopPlatform } from '@/lib/runtime-config';

export interface ShortcutCombo {
  /** KeyboardEvent.code of the non-modifier key, e.g. 'KeyT', 'BracketRight'. */
  code: string;
  meta: boolean;
  shift: boolean;
  alt: boolean;
}

export type ShortcutId =
  | 'open-search'
  | 'open-file-search'
  | 'open-settings'
  | 'session-next'
  | 'session-prev'
  | 'session-new'
  | 'session-archive'
  | 'focus-chat'
  | 'find-in-page'
  | 'open-diff'
  | 'open-files'
  | 'peek-chat'
  | 'peek-chat-toggle'
  | 'terminal-new-focused'
  | 'terminal-new'
  | 'terminal-close'
  | 'terminal-focus';

export interface ShortcutDef {
  id: ShortcutId;
  section: string;
  label: string;
  defaultCombo: ShortcutCombo;
}

export const SHORTCUT_DEFS: ShortcutDef[] = [
  {
    id: 'open-search',
    section: 'General',
    label: 'Search workspace',
    defaultCombo: { code: 'KeyK', meta: true, shift: false, alt: false },
  },
  {
    id: 'open-settings',
    section: 'General',
    label: 'Open settings',
    defaultCombo: { code: 'Comma', meta: true, shift: false, alt: false },
  },
  {
    id: 'session-next',
    section: 'Sessions',
    label: 'Next session (below)',
    defaultCombo: { code: 'BracketRight', meta: true, shift: false, alt: false },
  },
  {
    id: 'session-prev',
    section: 'Sessions',
    label: 'Previous session (above)',
    defaultCombo: { code: 'BracketLeft', meta: true, shift: false, alt: false },
  },
  {
    id: 'session-new',
    section: 'Sessions',
    label: 'New session',
    defaultCombo: { code: 'KeyN', meta: true, shift: false, alt: false },
  },
  {
    id: 'session-archive',
    section: 'Sessions',
    label: 'Archive current session',
    defaultCombo: { code: 'KeyA', meta: true, shift: true, alt: false },
  },
  {
    id: 'focus-chat',
    section: 'Chat',
    label: 'Focus chat input',
    defaultCombo: { code: 'KeyL', meta: true, shift: false, alt: false },
  },
  {
    id: 'find-in-page',
    section: 'Chat',
    // Replaces the browser's native ⌘F. Context-aware: searches the whole
    // loaded transcript (which virtualization hides from native find) when the
    // chat is focused, or the open file / git diff when the files panel is.
    label: 'Find in view (chat or file)',
    defaultCombo: { code: 'KeyF', meta: true, shift: false, alt: false },
  },
  {
    id: 'open-diff',
    section: 'Code review',
    label: 'Open diff view',
    defaultCombo: { code: 'KeyD', meta: true, shift: true, alt: false },
  },
  {
    id: 'open-files',
    section: 'Files',
    label: 'Open files tab',
    defaultCombo: { code: 'KeyF', meta: true, shift: true, alt: false },
  },
  {
    id: 'open-file-search',
    section: 'Files',
    // Quick-open a file by name (VS Code's ⌘P). Overrides the browser's native
    // ⌘P print in-session; only active while viewing a session whose machine is
    // online, since the finder reads the live project index off the daemon.
    label: 'Search files by name',
    defaultCombo: { code: 'KeyP', meta: true, shift: false, alt: false },
  },
  // Panel tab cycling is Ctrl+Tab / Ctrl+Shift+Tab — a fixed, cross-platform
  // binding handled directly in FilesGitPanel. It isn't rebindable here because
  // this combo model has no Control modifier (only the per-platform "primary"
  // ⌘/Ctrl), so it can't represent literal Ctrl+Tab on macOS.
  {
    id: 'peek-chat',
    section: 'Panel',
    // Hold to reveal the chat beneath the maximized file view; release to snap
    // back. Defaults to a bare `. NOTE: re-recording forces a modifier (the
    // capture UI rejects modifier-less chords), so the bare default can be
    // replaced by a ⌘/⌥ combo but not by another bare key — a fine trade for
    // making the actual gesture the listed, rebindable shortcut.
    label: 'Peek chat (hold, focus mode)',
    defaultCombo: { code: 'Backquote', meta: false, shift: false, alt: false },
  },
  {
    id: 'peek-chat-toggle',
    section: 'Panel',
    // Sibling of the hold-peek above, for anyone who'd rather latch it than hold
    // the key: press once to reveal the chat beneath the maximized file view,
    // again to snap back. Defaults to ⌥` — same physical key as the hold
    // gesture, plus Option. NOT ⌘` (or ⇧⌘`): macOS reserves those for "move
    // focus to next/previous window" and swallows the keydown before the app
    // ever sees it, so the handler would never fire.
    label: 'Peek chat (toggle, focus mode)',
    defaultCombo: { code: 'Backquote', meta: false, shift: false, alt: true },
  },
  {
    id: 'terminal-new-focused',
    section: 'Terminal',
    label: 'Open terminal (new tab when terminal focused)',
    defaultCombo: { code: 'KeyT', meta: true, shift: false, alt: false },
  },
  {
    id: 'terminal-new',
    section: 'Terminal',
    label: 'New terminal tab',
    defaultCombo: { code: 'KeyT', meta: true, shift: true, alt: false },
  },
  {
    id: 'terminal-close',
    section: 'Terminal',
    label: 'Close terminal tab (when terminal focused)',
    defaultCombo: { code: 'KeyW', meta: true, shift: false, alt: false },
  },
  {
    id: 'terminal-focus',
    section: 'Terminal',
    label: 'Focus terminal (opens one if needed)',
    defaultCombo: { code: 'KeyJ', meta: true, shift: false, alt: false },
  },
];

const STORAGE_KEY = 'desktop-shortcut-overrides';
const CHANGE_EVENT = 'vicoa:shortcuts-changed';

type Overrides = Partial<Record<ShortcutId, ShortcutCombo>>;

let overridesCache: Overrides | null = null;

function isValidCombo(value: unknown): value is ShortcutCombo {
  if (typeof value !== 'object' || value === null) return false;
  const combo = value as Record<string, unknown>;
  return (
    typeof combo.code === 'string' &&
    typeof combo.meta === 'boolean' &&
    typeof combo.shift === 'boolean' &&
    typeof combo.alt === 'boolean'
  );
}

function loadOverrides(): Overrides {
  if (overridesCache !== null) return overridesCache;
  if (typeof window === 'undefined') return {};
  const parsed: Overrides = {};
  const data = getPref<Record<string, unknown>>(STORAGE_KEY);
  if (typeof data === 'object' && data !== null) {
    for (const def of SHORTCUT_DEFS) {
      const combo = data[def.id];
      if (isValidCombo(combo)) parsed[def.id] = combo;
    }
  }
  overridesCache = parsed;
  return parsed;
}

function saveOverrides(overrides: Overrides): void {
  overridesCache = overrides;
  setPref(STORAGE_KEY, Object.keys(overrides).length === 0 ? null : overrides);
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

export function getShortcutCombo(id: ShortcutId): ShortcutCombo {
  const def = SHORTCUT_DEFS.find((d) => d.id === id)!;
  return loadOverrides()[id] ?? def.defaultCombo;
}

export function isShortcutOverridden(id: ShortcutId): boolean {
  return loadOverrides()[id] !== undefined;
}

export function setShortcutOverride(id: ShortcutId, combo: ShortcutCombo): void {
  const def = SHORTCUT_DEFS.find((d) => d.id === id)!;
  const next = { ...loadOverrides() };
  if (combosEqual(combo, def.defaultCombo)) {
    delete next[id];
  } else {
    next[id] = combo;
  }
  saveOverrides(next);
}

export function clearShortcutOverride(id: ShortcutId): void {
  const next = { ...loadOverrides() };
  delete next[id];
  saveOverrides(next);
}

/** Re-render hook point for the settings UI. Returns an unsubscribe fn. */
export function subscribeShortcuts(callback: () => void): () => void {
  window.addEventListener(CHANGE_EVENT, callback);
  return () => window.removeEventListener(CHANGE_EVENT, callback);
}

export function combosEqual(a: ShortcutCombo, b: ShortcutCombo): boolean {
  return a.code === b.code && a.meta === b.meta && a.shift === b.shift && a.alt === b.alt;
}

/**
 * Is the OS's "primary" modifier ⌘ (macOS) rather than Ctrl (Windows/Linux)?
 * Prefers Electron's real `process.platform`; falls back to the UA on plain
 * web. Unknown (SSR/tests) resolves to non-mac, so Ctrl is the primary.
 */
export function isMacPlatform(): boolean {
  const electronPlatform = getDesktopPlatform();
  if (electronPlatform !== null) return electronPlatform === 'darwin';
  if (typeof navigator !== 'undefined') return /Mac/i.test(navigator.userAgent);
  return false;
}

/** Does this key event exactly match the shortcut's current binding? */
export function matchesShortcut(event: KeyboardEvent, id: ShortcutId): boolean {
  const combo = getShortcutCombo(id);
  const mac = isMacPlatform();
  // The primary modifier is ⌘ on mac, Ctrl elsewhere. The *other* one is never
  // part of a binding — so a Mac's Ctrl+W (delete-word) never fires a ⌘ combo,
  // and Windows' Win+W never fires a Ctrl combo.
  const primaryPressed = mac ? event.metaKey : event.ctrlKey;
  const secondaryPressed = mac ? event.ctrlKey : event.metaKey;
  return (
    event.code === combo.code &&
    primaryPressed === combo.meta &&
    !secondaryPressed &&
    event.shiftKey === combo.shift &&
    event.altKey === combo.alt
  );
}

/**
 * The customizable shortcut (≠ excludeId) whose current binding equals
 * `combo`, or the fixed ⌘1–9 jump range — used to refuse conflicting rebinds.
 */
export function findShortcutConflict(
  excludeId: ShortcutId,
  combo: ShortcutCombo,
): { label: string } | null {
  if (combo.meta && !combo.shift && !combo.alt && /^Digit[1-9]$/.test(combo.code)) {
    return { label: 'Go to the 1st–9th session' };
  }
  for (const def of SHORTCUT_DEFS) {
    if (def.id === excludeId) continue;
    if (combosEqual(getShortcutCombo(def.id), combo)) return { label: def.label };
  }
  return null;
}

const MODIFIER_CODES = new Set([
  'MetaLeft', 'MetaRight',
  'ControlLeft', 'ControlRight',
  'ShiftLeft', 'ShiftRight',
  'AltLeft', 'AltRight',
  'CapsLock', 'Fn', 'FnLock',
]);

export function isModifierCode(code: string): boolean {
  return MODIFIER_CODES.has(code);
}

/** Human keycap for a KeyboardEvent.code ('KeyD' → 'D', 'BracketRight' → ']'). */
export function keycapForCode(code: string): string {
  if (/^Key[A-Z]$/.test(code)) return code.slice(3);
  if (/^Digit[0-9]$/.test(code)) return code.slice(5);
  const named: Record<string, string> = {
    BracketLeft: '[',
    BracketRight: ']',
    Backslash: '\\',
    Semicolon: ';',
    Quote: "'",
    Comma: ',',
    Period: '.',
    Slash: '/',
    Backquote: '`',
    Minus: '-',
    Equal: '=',
    Space: 'Space',
    Enter: '⏎',
    Backspace: '⌫',
    Delete: '⌦',
    Tab: '⇥',
    Escape: 'Esc',
    ArrowUp: '↑',
    ArrowDown: '↓',
    ArrowLeft: '←',
    ArrowRight: '→',
    Home: '↖',
    End: '↘',
    PageUp: '⇞',
    PageDown: '⇟',
  };
  return named[code] ?? code;
}

/**
 * Combo → ordered keycap labels for this OS: ['⌘', '⇧', 'D'] on macOS,
 * ['Ctrl', 'Shift', 'D'] on Windows/Linux (matching what actually fires).
 */
export function comboKeycaps(combo: ShortcutCombo): string[] {
  const mac = isMacPlatform();
  const keys: string[] = [];
  if (combo.meta) keys.push(mac ? '⌘' : 'Ctrl');
  if (combo.alt) keys.push(mac ? '⌥' : 'Alt');
  if (combo.shift) keys.push(mac ? '⇧' : 'Shift');
  keys.push(keycapForCode(combo.code));
  return keys;
}

/**
 * Combo as a single inline hint string: '⌘L' on macOS (glyphs run together),
 * 'Ctrl+L' on Windows/Linux (word modifiers joined with '+').
 */
export function comboInline(combo: ShortcutCombo): string {
  const keys = comboKeycaps(combo);
  return isMacPlatform() ? keys.join('') : keys.join('+');
}

/** The primary-modifier label for this OS: '⌘' on macOS, 'Ctrl' elsewhere. */
export function primaryModifierLabel(): string {
  return isMacPlatform() ? '⌘' : 'Ctrl';
}
