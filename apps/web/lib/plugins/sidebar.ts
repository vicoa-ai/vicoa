/**
 * Pure rules for plugin sidebar rows: which actions this renderer runs, where a
 * row leads, and whether it is the selected row for the current route. Kept
 * free of the RPC client so it can be unit-tested.
 */

import type { SidebarItemAction } from './types';

/** Route prefix of plugin pages: `/dashboard/plugin/<machine>/<plugin>/<surface>`. */
export const PLUGIN_ROUTE_PREFIX = '/dashboard/plugin/';

/**
 * An in-app route like `/dashboard/tasks`. `//host` and `/\host` are
 * protocol-relative: the browser resolves them to another site, which would
 * then load inside the app window. So is `/<tab>/host`: URL parsing drops
 * tabs and newlines. Control characters are refused outright, and the path
 * must still resolve to the app's own origin. Mirrors `_is_app_path` in
 * `backend/src/protocol/plugin_manifest.py`.
 */
export function isAppPath(url: string): boolean {
  if (!url.startsWith('/') || url.startsWith('//') || url.includes('\\')) return false;
  if (/[\u0000-\u001f\u007f]/.test(url)) return false;
  try {
    return new URL(url, 'https://app.invalid').origin === 'https://app.invalid';
  } catch {
    return false;
  }
}

/**
 * Whether this renderer can run `action`. The daemon validates manifests, but
 * an older daemon still reports actions this build no longer supports (the
 * removed `rpc` action) or a URL the current rules reject; those rows are
 * dropped rather than drawn as buttons that do nothing.
 */
export function isSupportedSidebarAction(action: unknown): action is SidebarItemAction {
  if (!action || typeof action !== 'object') return false;
  const a = action as Record<string, unknown>;
  if (a.type === 'open-url') {
    return typeof a.url === 'string' && (/^https?:\/\//.test(a.url) || isAppPath(a.url));
  }
  if (a.type === 'surface') {
    return typeof a.surfaceId === 'string' && /^[a-z0-9][a-z0-9_-]{0,63}$/.test(a.surfaceId);
  }
  return false;
}

/** The route of one plugin page. */
export function pluginSurfacePath(machineId: string, pluginId: string, surfaceId: string): string {
  return (
    PLUGIN_ROUTE_PREFIX +
    [machineId, pluginId, surfaceId].map((part) => encodeURIComponent(part)).join('/')
  );
}

/**
 * Whether an `open-url` action leaves the app (opens in the system browser).
 * Any absolute URL does; an app path never can, so the manifest's `external`
 * flag changes nothing either way.
 */
export function opensExternally(action: Extract<SidebarItemAction, { type: 'open-url' }>): boolean {
  return /^https?:\/\//.test(action.url);
}

/**
 * The in-app route a row navigates to, or null when it opens outside the app.
 */
export function sidebarItemHref(
  action: SidebarItemAction,
  pluginId: string,
  machineId: string,
): string | null {
  if (action.type === 'surface') return pluginSurfacePath(machineId, pluginId, action.surfaceId);
  return opensExternally(action) ? null : action.url;
}

/**
 * Whether a row is the selected one for `pathname`. A plugin page matches on
 * plugin and page only, so the row stays selected whichever machine's copy of
 * the plugin the page is showing.
 */
export function isSidebarItemActive(
  action: SidebarItemAction,
  pluginId: string,
  pathname: string | null,
): boolean {
  if (!pathname) return false;
  if (action.type === 'surface') {
    if (!pathname.startsWith(PLUGIN_ROUTE_PREFIX)) return false;
    const [, plugin, surface] = pathname.slice(PLUGIN_ROUTE_PREFIX.length).split('/');
    return safeDecode(plugin) === pluginId && safeDecode(surface) === action.surfaceId;
  }
  if (opensExternally(action)) return false;
  const path = action.url.split(/[?#]/, 1)[0];
  return path === pathname;
}

function safeDecode(part: string | undefined): string | null {
  if (part === undefined) return null;
  try {
    return decodeURIComponent(part);
  } catch {
    return null;
  }
}
