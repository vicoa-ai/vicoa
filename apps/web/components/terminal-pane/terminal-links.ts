// Terminal link activation: ⌘/Ctrl+click opens a URL in the browser.
//
// Both link flavours route here — the `https?://…` text the WebLinksAddon
// finds, and OSC 8 hyperlinks emitted by agent CLIs (wired via the
// `linkHandler` option in terminal-options.ts).
//
// Why a custom handler instead of xterm's default:
//
//  1. The default opens with a bare `window.open()` and then assigns
//     `location.href`. The Electron shell denies that popup in its
//     `setWindowOpenHandler` (apps/desktop/src/window.ts), so `window.open()`
//     returns null and the click silently does nothing — on desktop, which is
//     where the terminal is used most. `openExternalUrl` hands the URL to the
//     preload bridge (system browser) there, and opens a new tab on the web.
//
//  2. xterm activates a link on ANY left click, so a stray click on a URL
//     printed by a running TUI would hijack the browser. Real terminals
//     (VS Code, iTerm2, Windows Terminal, Ghostty) all gate activation behind
//     the platform modifier; we match that.

import { isMacPlatform } from '@/lib/desktop-shortcuts';
import { openExternalUrl } from '@/lib/open-external';

/** The modifier flags of a mouse/key event — all the decision needs. */
export interface LinkModifierState {
  metaKey: boolean;
  ctrlKey: boolean;
}

/**
 * Is the OS's link modifier held? ⌘ on macOS, Ctrl on Windows/Linux.
 * Deliberately not "either one": Ctrl+click on macOS is a right-click
 * (context menu), which must never open a link.
 */
export function isLinkModifierHeld(
  event: LinkModifierState,
  mac: boolean = isMacPlatform(),
): boolean {
  return mac ? event.metaKey : event.ctrlKey;
}

/** Belt-and-braces: only ever hand http(s) to the opener. The web-links regex
 *  and xterm's OSC 8 handling are http-only already, so this just keeps a
 *  future regex/provider change from reaching `openExternalUrl` with, say, a
 *  `javascript:` URL. */
function isOpenableUrl(uri: string): boolean {
  return /^https?:\/\//i.test(uri);
}

/** The pure decision behind `openTerminalLink`, split out so it can be tested
 *  without a DOM. */
export function shouldOpenTerminalLink(
  event: LinkModifierState & Pick<MouseEvent, 'button'>,
  uri: string,
  mac: boolean = isMacPlatform(),
): boolean {
  // `button === 0`: xterm activates on mouseup, and only a left click should
  // open (middle-click is paste on Linux, right-click opens the menu).
  return event.button === 0 && isLinkModifierHeld(event, mac) && isOpenableUrl(uri);
}

/** Link `activate` handler for both the WebLinksAddon and OSC 8 hyperlinks. */
export function openTerminalLink(event: MouseEvent, uri: string): void {
  if (!shouldOpenTerminalLink(event, uri)) return;
  openExternalUrl(uri);
}

/** Set on the pane element while the link modifier is held; terminal-links.css
 *  keys the pointer cursor off it. */
export const LINK_MODIFIER_ATTR = 'data-link-modifier';

/**
 * Mirror "is the link modifier held?" onto `el` as a data attribute, so a
 * hovered link only shows the pointer cursor when a click would actually open
 * it. Returns an unsubscribe.
 */
export function trackLinkModifier(el: HTMLElement): () => void {
  const set = (held: boolean): void => {
    el.setAttribute(LINK_MODIFIER_ATTR, held ? 'true' : 'false');
  };
  // keydown and keyup both carry the post-event modifier flags (pressing ⌘
  // sets metaKey, releasing it clears it), so one reader serves both.
  const handleKey = (event: KeyboardEvent): void => set(isLinkModifierHeld(event));
  // ⌘Tab / ⌘-clicking into another window swallows the keyup, which would
  // otherwise leave links armed forever.
  const handleBlur = (): void => set(false);

  set(false);
  window.addEventListener('keydown', handleKey);
  window.addEventListener('keyup', handleKey);
  window.addEventListener('blur', handleBlur);
  return () => {
    window.removeEventListener('keydown', handleKey);
    window.removeEventListener('keyup', handleKey);
    window.removeEventListener('blur', handleBlur);
  };
}
