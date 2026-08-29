import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  comboInline,
  comboKeycaps,
  combosEqual,
  findShortcutConflict,
  getShortcutCombo,
  isModifierCode,
  keycapForCode,
  matchesShortcut,
} from './desktop-shortcuts';

// No window in the vitest node env, so all combos resolve to the defaults —
// which is exactly what these pure-logic tests want.

const keyEvent = (over: Partial<KeyboardEvent>): KeyboardEvent =>
  ({ code: '', metaKey: false, ctrlKey: false, shiftKey: false, altKey: false, ...over }) as KeyboardEvent;

/** Pin the platform for matchesShortcut's ⌘-vs-Ctrl branch. */
const usePlatform = (ua: 'Macintosh' | 'Windows NT 10.0') =>
  vi.stubGlobal('navigator', { userAgent: `Mozilla/5.0 (${ua})` });

afterEach(() => vi.unstubAllGlobals());

describe('matchesShortcut', () => {
  it('matches the default binding exactly (⌘ on mac)', () => {
    usePlatform('Macintosh');
    expect(matchesShortcut(keyEvent({ code: 'KeyD', metaKey: true, shiftKey: true }), 'open-diff')).toBe(true);
    expect(matchesShortcut(keyEvent({ code: 'KeyD', metaKey: true }), 'open-diff')).toBe(false);
    expect(matchesShortcut(keyEvent({ code: 'KeyD', shiftKey: true }), 'open-diff')).toBe(false);
  });

  it('treats Ctrl as the primary modifier on Windows/Linux', () => {
    usePlatform('Windows NT 10.0');
    expect(matchesShortcut(keyEvent({ code: 'BracketRight', ctrlKey: true }), 'session-next')).toBe(true);
  });

  it('leaves Ctrl+W alone on a Mac (it is the terminal delete-word, not close-tab)', () => {
    usePlatform('Macintosh');
    expect(matchesShortcut(keyEvent({ code: 'KeyW', ctrlKey: true }), 'terminal-close')).toBe(false);
    expect(matchesShortcut(keyEvent({ code: 'KeyW', metaKey: true }), 'terminal-close')).toBe(true);
  });

  it('closes the terminal on Ctrl+W on Windows, but not Win+W', () => {
    usePlatform('Windows NT 10.0');
    expect(matchesShortcut(keyEvent({ code: 'KeyW', ctrlKey: true }), 'terminal-close')).toBe(true);
    expect(matchesShortcut(keyEvent({ code: 'KeyW', metaKey: true }), 'terminal-close')).toBe(false);
  });

  it('rejects extra modifiers', () => {
    usePlatform('Macintosh');
    expect(matchesShortcut(keyEvent({ code: 'KeyW', metaKey: true, altKey: true }), 'terminal-close')).toBe(false);
  });
});

describe('findShortcutConflict', () => {
  it('flags a combo already used by another shortcut', () => {
    const conflict = findShortcutConflict('terminal-new', getShortcutCombo('open-diff'));
    expect(conflict?.label).toBe('Open diff view');
  });

  it('flags the fixed ⌘1–9 jump range', () => {
    const conflict = findShortcutConflict('session-next', {
      code: 'Digit3', meta: true, shift: false, alt: false,
    });
    expect(conflict?.label).toContain('1st–9th');
  });

  it('allows a free combo and ignores the shortcut itself', () => {
    expect(findShortcutConflict('open-diff', getShortcutCombo('open-diff'))).toBeNull();
    expect(
      findShortcutConflict('open-diff', { code: 'KeyG', meta: true, shift: true, alt: false }),
    ).toBeNull();
  });
});

describe('keycap formatting', () => {
  it('maps codes to keycaps', () => {
    expect(keycapForCode('KeyD')).toBe('D');
    expect(keycapForCode('Digit7')).toBe('7');
    expect(keycapForCode('BracketRight')).toBe(']');
    expect(keycapForCode('Escape')).toBe('Esc');
  });

  it('orders modifiers ⌘ ⌥ ⇧ before the key on macOS', () => {
    usePlatform('Macintosh');
    expect(comboKeycaps({ code: 'KeyT', meta: true, shift: true, alt: true })).toEqual(['⌘', '⌥', '⇧', 'T']);
    expect(comboKeycaps(getShortcutCombo('session-prev'))).toEqual(['⌘', '[']);
  });

  it('spells modifiers as words on Windows/Linux', () => {
    usePlatform('Windows NT 10.0');
    expect(comboKeycaps({ code: 'KeyT', meta: true, shift: true, alt: true })).toEqual(['Ctrl', 'Alt', 'Shift', 'T']);
    expect(comboKeycaps(getShortcutCombo('session-prev'))).toEqual(['Ctrl', '[']);
  });

  it('renders inline hints per OS: ⌘L vs Ctrl+L', () => {
    usePlatform('Macintosh');
    expect(comboInline(getShortcutCombo('focus-chat'))).toBe('⌘L');
    usePlatform('Windows NT 10.0');
    expect(comboInline(getShortcutCombo('focus-chat'))).toBe('Ctrl+L');
  });
});

describe('helpers', () => {
  it('combosEqual compares all fields', () => {
    const a = { code: 'KeyT', meta: true, shift: false, alt: false };
    expect(combosEqual(a, { ...a })).toBe(true);
    expect(combosEqual(a, { ...a, shift: true })).toBe(false);
  });

  it('isModifierCode recognizes bare modifiers', () => {
    expect(isModifierCode('MetaLeft')).toBe(true);
    expect(isModifierCode('ShiftRight')).toBe(true);
    expect(isModifierCode('KeyA')).toBe(false);
  });
});
