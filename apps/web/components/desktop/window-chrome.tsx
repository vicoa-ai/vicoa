'use client';

import { useEffect, useState } from 'react';
import { MoreHorizontal, PanelLeft } from 'lucide-react';
import { DRAG_REGION, NO_DRAG, TRAFFIC_LIGHTS_INSET } from '@/lib/app-region';
import {
  getDesktopPlatform,
  getDesktopWindowBridge,
  getDesktopWindowChrome,
} from '@/lib/runtime-config';
import { useDesktopChrome } from '@/components/dashboard/desktop-chrome-context';

/**
 * Custom title bar (Orca pattern), drawn by the renderer on every platform that
 * doesn't hand us one. The shell tells us which of three shapes this window has
 * (`window.__VICOA_WINDOW_CHROME__`, from electron/src/window.ts):
 *
 *  - 'mac'    — `titleBarStyle: 'hiddenInset'`: the OS paints traffic lights over
 *               our header, so the lead is just a gutter reserving their space.
 *  - 'custom' — frameless (Windows always, Linux by default): we draw everything —
 *               a logo + ··· button that pops the application menu on the left of
 *               each titlebar strip (`DesktopTitlebarLead`), and a min/max/close
 *               cluster fixed at the window's top-right (`DesktopWindowControls`).
 *  - 'system' — the Linux opt-out: the desktop environment draws the frame and its
 *               own buttons, so we draw the lead (the app menu bar is hidden there
 *               too, and ··· is how it's reached) but NO window controls.
 *
 * Chrome is a RUNTIME signal — not available during SSR — so the hooks return the
 * macOS shape on the server and the first client render (no hydration mismatch)
 * and settle after mount.
 */
export function useWindowChrome(): 'mac' | 'custom' | 'system' {
  const [chrome, setChrome] = useState<'mac' | 'custom' | 'system'>('mac');
  useEffect(() => {
    setChrome(getDesktopWindowChrome());
  }, []);
  return chrome;
}

/**
 * True when this window has no OS-drawn buttons and we must draw (and reserve
 * room for) min/max/close ourselves — Windows, and Linux unless the user picked
 * their DE's title bar.
 */
export function useDesktopWindowControls(): boolean {
  return useWindowChrome() === 'custom';
}

/**
 * True on the Windows desktop app. A PLATFORM check, not a chrome one — for
 * capability gates (e.g. the daemon's missing ConPTY backend), never for
 * titlebar layout; use `useDesktopWindowControls()` for that.
 */
export function useDesktopWindows(): boolean {
  const [isWindows, setIsWindows] = useState(false);
  useEffect(() => {
    setIsWindows(getDesktopPlatform() === 'win32');
  }, []);
  return isWindows;
}

/**
 * The leading slot of a titlebar strip. macOS: the traffic-light gutter. Windows
 * and Linux: the app logo + a ··· button that pops the Edit/View/Window
 * application menu (the native menu bar is auto-hidden on both).
 */
export function DesktopTitlebarLead() {
  const chrome = useWindowChrome();
  if (chrome === 'mac') {
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
        className="flex h-7 w-7 cursor-pointer items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
      >
        <MoreHorizontal className="h-4 w-4" />
      </button>
    </div>
  );
}

const CONTROL_BTN =
  'flex h-full w-[46px] cursor-pointer items-center justify-center text-muted-foreground transition-colors';

/**
 * Fixed min/max/close cluster at the top-right of the window, for frameless
 * windows only (Windows, and Linux unless the user kept their DE's title bar).
 * Mounted once at the app root so it covers every screen — a frameless window
 * has no native controls anywhere. Rendered LAST in DOM order at its mount site
 * and marked no-drag, so Electron's DOM-order-based drag hit-test leaves the
 * buttons clickable over the surrounding drag strips.
 *
 * Always the RIGHT edge, as on Windows (and as Orca does on both). Every
 * mainstream Linux desktop puts them there too — GNOME, KDE Plasma, Xfce,
 * Cinnamon, MATE. The left-hand layouts are elementary OS's Pantheon, the
 * retired Ubuntu Unity, and anyone who moved their buttons by hand; mirroring
 * the whole title bar for them would mean mirroring the lead (logo + menu) and
 * every strip's reserved space as well, so they are served by the 'system'
 * title bar instead — that one is drawn by their desktop, in their layout.
 */
export function DesktopWindowControls() {
  const hasControls = useDesktopWindowControls();
  const [maximized, setMaximized] = useState(false);

  useEffect(() => {
    if (!hasControls) return;
    const bridge = getDesktopWindowBridge();
    if (!bridge) return;
    void bridge.isMaximized().then(setMaximized);
    return bridge.onMaximizeChanged(setMaximized);
  }, [hasControls]);

  if (!hasControls) return null;
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
        className={`${CONTROL_BTN} hover:bg-foreground/[0.06] dark:hover:bg-foreground/10 hover:text-foreground`}
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
        className={`${CONTROL_BTN} hover:bg-foreground/[0.06] dark:hover:bg-foreground/10 hover:text-foreground`}
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
 * A no-op unless we draw the window controls ourselves; then, a spacer as wide
 * as the fixed `DesktopWindowControls`. Drop it at the end of a titlebar strip
 * that has right-aligned actions (e.g. the chat header) so they don't slide
 * underneath the window controls.
 */
export function DesktopWindowControlsSpacer() {
  const hasControls = useDesktopWindowControls();
  if (!hasControls) return null;
  return <div className="h-full w-[138px] shrink-0" aria-hidden />;
}

/**
 * The leading group a page header must render when the desktop sidebar is
 * collapsed: the titlebar lead (macOS traffic-light gutter / Windows+Linux
 * logo + menu button)
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
