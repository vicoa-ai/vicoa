import { getDesktopAuthBridge } from '@/lib/desktop-auth';

/**
 * Open a URL outside the app: in the desktop shell via the `openExternal`
 * bridge (a plain `window.open`/navigation there gets cancelled by the
 * `will-navigate` handler — see lib/desktop-paywall.ts), on the web in a new
 * tab.
 */
export function openExternalUrl(url: string): void {
  const bridge = getDesktopAuthBridge();
  if (bridge) {
    void bridge.openExternal(url);
    return;
  }
  window.open(url, '_blank', 'noopener,noreferrer');
}
