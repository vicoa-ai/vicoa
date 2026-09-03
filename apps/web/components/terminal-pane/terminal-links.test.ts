import { afterEach, describe, expect, it, vi } from 'vitest';
import { isLinkModifierHeld, shouldOpenTerminalLink, trackLinkModifier } from './terminal-links';

/** A left-click mouseup with no modifier, overridable per case. */
const click = (over: Partial<MouseEvent> = {}): MouseEvent =>
  ({ button: 0, metaKey: false, ctrlKey: false, ...over }) as MouseEvent;

const URL = 'https://vicoa.ai/docs';

afterEach(() => vi.unstubAllGlobals());

describe('isLinkModifierHeld', () => {
  it('is ⌘ on macOS and Ctrl elsewhere', () => {
    expect(isLinkModifierHeld(click({ metaKey: true }), true)).toBe(true);
    expect(isLinkModifierHeld(click({ ctrlKey: true }), false)).toBe(true);
  });

  it('never accepts the other platform’s modifier', () => {
    // Ctrl+click on macOS is a right-click — it must not open a link.
    expect(isLinkModifierHeld(click({ ctrlKey: true }), true)).toBe(false);
    expect(isLinkModifierHeld(click({ metaKey: true }), false)).toBe(false);
  });
});

describe('shouldOpenTerminalLink', () => {
  it('opens on ⌘/Ctrl + left click', () => {
    expect(shouldOpenTerminalLink(click({ metaKey: true }), URL, true)).toBe(true);
    expect(shouldOpenTerminalLink(click({ ctrlKey: true }), URL, false)).toBe(true);
  });

  it('ignores a plain click, so a stray click in a TUI cannot hijack the browser', () => {
    expect(shouldOpenTerminalLink(click(), URL, true)).toBe(false);
    expect(shouldOpenTerminalLink(click(), URL, false)).toBe(false);
  });

  it('ignores non-left buttons (middle-click pastes, right-click opens the menu)', () => {
    expect(shouldOpenTerminalLink(click({ button: 1, metaKey: true }), URL, true)).toBe(false);
    expect(shouldOpenTerminalLink(click({ button: 2, ctrlKey: true }), URL, false)).toBe(false);
  });

  it('only opens http(s) URLs', () => {
    const modified = click({ metaKey: true });
    expect(shouldOpenTerminalLink(modified, 'http://localhost:3000/', true)).toBe(true);
    expect(shouldOpenTerminalLink(modified, 'javascript:alert(1)', true)).toBe(false);
    expect(shouldOpenTerminalLink(modified, 'file:///etc/passwd', true)).toBe(false);
    expect(shouldOpenTerminalLink(modified, 'vicoa://auth/callback', true)).toBe(false);
  });

  it('falls back to the detected platform when none is passed', () => {
    vi.stubGlobal('navigator', { userAgent: 'Mozilla/5.0 (Macintosh)' });
    expect(shouldOpenTerminalLink(click({ metaKey: true }), URL)).toBe(true);
    expect(shouldOpenTerminalLink(click({ ctrlKey: true }), URL)).toBe(false);
  });
});

describe('trackLinkModifier', () => {
  /** Minimal window/element stand-ins — the node test env has neither. */
  const setup = () => {
    const listeners = new Map<string, (event: unknown) => void>();
    const attrs: Record<string, string> = {};
    vi.stubGlobal('navigator', { userAgent: 'Mozilla/5.0 (Macintosh)' });
    vi.stubGlobal('window', {
      addEventListener: (type: string, fn: (event: unknown) => void) => listeners.set(type, fn),
      removeEventListener: (type: string) => listeners.delete(type),
    });
    const el = {
      setAttribute: (name: string, value: string) => {
        attrs[name] = value;
      },
    } as HTMLElement;
    return { listeners, attrs, el };
  };

  it('mirrors the held modifier onto the element and cleans up', () => {
    const { listeners, attrs, el } = setup();
    const stop = trackLinkModifier(el);
    expect(attrs['data-link-modifier']).toBe('false');

    listeners.get('keydown')?.({ metaKey: true, ctrlKey: false });
    expect(attrs['data-link-modifier']).toBe('true');

    // keyup of ⌘ reports metaKey: false, which disarms without special-casing.
    listeners.get('keyup')?.({ metaKey: false, ctrlKey: false });
    expect(attrs['data-link-modifier']).toBe('false');

    // A swallowed keyup (⌘Tab away) must not leave links armed.
    listeners.get('keydown')?.({ metaKey: true, ctrlKey: false });
    listeners.get('blur')?.(undefined);
    expect(attrs['data-link-modifier']).toBe('false');

    stop();
    expect(listeners.size).toBe(0);
  });
});
