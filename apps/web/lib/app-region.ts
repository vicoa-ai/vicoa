import type { CSSProperties } from 'react';

/**
 * Electron custom-titlebar draggable-region styles.
 *
 * With `titleBarStyle: 'hiddenInset'` the renderer paints its own titlebar, so
 * we mark which regions drag the window (`-webkit-app-region: drag`) and which
 * stay interactive (`-webkit-app-region: no-drag`). That CSS property isn't in
 * the DOM typings, so we augment `CSSProperties` once here and export pre-typed
 * constants instead of casting at every call site.
 */
declare module 'react' {
  interface CSSProperties {
    WebkitAppRegion?: 'drag' | 'no-drag';
  }
}

/** Apply to a titlebar strip so dragging it moves the window. */
export const DRAG_REGION: CSSProperties = { WebkitAppRegion: 'drag' };

/** Apply to interactive elements inside a drag region (buttons, inputs). */
export const NO_DRAG: CSSProperties = { WebkitAppRegion: 'no-drag' };

/**
 * Left inset (px) reserved for the macOS traffic-light controls, which the OS
 * paints over the top-left of the window at roughly {x:16, y:16}. The desktop
 * build is macOS-first today; on other platforms this is harmless padding.
 */
export const TRAFFIC_LIGHTS_INSET = 70;
