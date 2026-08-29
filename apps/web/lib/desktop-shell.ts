/**
 * Renderer-side accessor for the desktop shell bridge (preload-injected).
 * Null on the web build and during SSR — callers hide their affordance then;
 * browsers can't expose real filesystem paths, so there is no web fallback.
 */

export interface DesktopShellBridge {
  pickFolder: () => Promise<string | null>;
}

export function getDesktopShellBridge(): DesktopShellBridge | null {
  if (typeof window === 'undefined') return null;
  const bridge = (window as unknown as { vicoaDesktopShell?: DesktopShellBridge }).vicoaDesktopShell;
  return bridge && typeof bridge.pickFolder === 'function' ? bridge : null;
}
