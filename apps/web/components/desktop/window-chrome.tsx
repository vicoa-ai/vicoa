'use client';

import { useEffect, useState } from 'react';
import { MoreHorizontal, PanelLeft } from 'lucide-react';
import { DRAG_REGION, NO_DRAG, TRAFFIC_LIGHTS_INSET } from '@/lib/app-region';
import { getDesktopPlatform, getDesktopWindowBridge } from '@/lib/runtime-config';
import { useDesktopChrome } from '@/components/dashboard/desktop-chrome-context';

/**
 * Windows custom title bar (Orca pattern). On Windows the shell runs with
 * `titleBarStyle: 'hidden'` (electron/src/window.ts), so the renderer must draw
 * its own chrome: a logo + a ··· button that pops the application menu on the
 * left of each titlebar strip (`DesktopTitlebarLead`), and a fixed min/max/close
 * cluster at the top-right of the window (`DesktopWindowControls`).
 *
 * macOS is untouched: it keeps `hiddenInset` + native traffic lights, so every
 * component here degrades to the exact pre-existing macOS behaviour (the lead
 * renders the traffic-light gutter; the controls + spacer render nothing).
 *
 * Platform is a RUNTIME signal (`window.__VICOA_PLATFORM__`, injected by the
 * preload) — not available during SSR — so `useDesktopWindows` returns false on
 * the server and the first client render (matching the macOS layout, no
 * hydration mismatch) and flips to true after mount on Windows.
 */
export function useDesktopWindows(): boolean {
  const [isWindows, setIsWindows] = useState(false);
  useEffect(() => {
    setIsWindows(getDesktopPlatform() === 'win32');
  }, []);
  return isWindows;
}

/**
 * The leading slot of a titlebar strip. macOS: the traffic-light gutter (exactly
 * as before). Windows: the app logo + a ··· button that pops the Edit/View/Window
 * application menu.
 */
export function DesktopTitlebarLead() {
  const isWindows = useDesktopWindows();
  if (!isWindows) {
    return <div style={{ width: TRAFFIC_LIGHTS_INSET }} className="h-full shrink-0" aria-hidden />;
  }
  return (
    <div style={NO_DRAG} className="flex h-full items-center gap-0.5">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src="/images/vicoa-logo-small.webp"
        alt=""
        aria-hidden
        draggable={false}
        className="h-5 w-5 shrink-0 rounded-[5px]"
      />
      <button
        type="button"
        onClick={() => getDesktopWindowBridge()?.popupMenu()}
        title="Menu"
        aria-label="Application menu"
        className="flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
      >
        <MoreHorizontal className="h-4 w-4" />
      </button>
    </div>
  );
}

const CONTROL_BTN =
  'flex h-full w-[46px] items-center justify-center text-muted-foreground transition-colors';

/**
 * Fixed min/max/close cluster at the top-right of the window (Windows only).
 * Mounted once at the app root so it covers every screen (the frameless window
 * has no native controls anywhere). Rendered LAST in DOM order at its mount site
 * and marked no-drag, so Electron's DOM-order-based drag hit-test leaves the
 * buttons clickable over the surrounding drag strips.
 */
export function DesktopWindowControls() {
  const isWindows = useDesktopWindows();
  const [maximized, setMaximized] = useState(false);

  useEffect(() => {
    if (!isWindows) return;
    const bridge = getDesktopWindowBridge();
    if (!bridge) return;
    void bridge.isMaximized().then(setMaximized);
    return bridge.onMaximizeChanged(setMaximized);
  }, [isWindows]);

  if (!isWindows) return null;
  const bridge = getDesktopWindowBridge();

  return (
    <div
      style={NO_DRAG}
      className="fixed right-0 top-0 z-[100] flex h-11 items-stretch"
      role="group"
      aria-label="Window controls"
    >
      <button
        type="button"
        onClick={() => bridge?.minimize()}
        aria-label="Minimize"
        title="Minimize"
        className={`${CONTROL_BTN} hover:bg-foreground/10 hover:text-foreground`}
      >
        <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1">
          <path d="M0 5 H10" />
        </svg>
      </button>
      <button
        type="button"
        onClick={() => bridge?.toggleMaximize()}
        aria-label={maximized ? 'Restore' : 'Maximize'}
        title={maximized ? 'Restore' : 'Maximize'}
        className={`${CONTROL_BTN} hover:bg-foreground/10 hover:text-foreground`}
      >
        {maximized ? (
          <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1">
            <path d="M2.5 2.5 V0.5 H9.5 V7.5 H7.5" />
            <rect x="0.5" y="2.5" width="7" height="7" />
          </svg>
        ) : (
          <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1">
            <rect x="0.5" y="0.5" width="9" height="9" />
          </svg>
        )}
      </button>
      <button
        type="button"
        onClick={() => bridge?.close()}
        aria-label="Close"
        title="Close"
        className={`${CONTROL_BTN} hover:bg-[#c42b1c] hover:text-white`}
      >
        <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.1">
          <path d="M0 0 L10 10 M10 0 L0 10" />
        </svg>
      </button>
    </div>
  );
}

/**
 * A no-op on macOS/web; on Windows, a spacer as wide as the fixed
 * `DesktopWindowControls`. Drop it at the end of a titlebar strip that has
 * right-aligned actions (e.g. the chat header) so they don't slide underneath
 * the window controls.
 */
export function DesktopWindowControlsSpacer() {
  const isWindows = useDesktopWindows();
  if (!isWindows) return null;
  return <div className="h-full w-[138px] shrink-0" aria-hidden />;
}

/**
 * The leading group a page header must render when the desktop sidebar is
 * collapsed: the titlebar lead (macOS traffic-light gutter / Windows logo+menu)
 * + the Vicoa wordmark + an expand-sidebar button. Placing it at the start of a
 * page's own top header keeps the header content out from under the macOS
 * traffic lights and keeps the brand + expand control reachable while the
 * sidebar is hidden. Renders nothing on web or when the sidebar is expanded.
 */
export function DesktopCollapsedLead() {
  const { isDesktop, sidebarCollapsed, expandSidebar } = useDesktopChrome();
  if (!isDesktop || !sidebarCollapsed) return null;
  return (
    <div style={DRAG_REGION} className="flex h-full shrink-0 items-center gap-1.5">
      <DesktopTitlebarLead />
      <span className="text-sm font-normal text-foreground">Vicoa</span>
      <button
        type="button"
        onClick={expandSidebar}
        style={NO_DRAG}
        title="Expand sidebar"
        aria-label="Expand sidebar"
        className="flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
      >
        <PanelLeft className="h-4 w-4" />
      </button>
    </div>
  );
}
