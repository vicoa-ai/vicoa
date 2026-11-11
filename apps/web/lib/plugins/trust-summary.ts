/**
 * What a plugin will add, in words, for the trust prompt. One line per
 * contribution, saying what it does when used, so approving a plugin is a
 * decision about concrete behaviour rather than a count of items.
 */

import { PERMISSION_TEXT } from './bridge/permissions';
import { isSupportedSidebarAction, opensExternally } from './sidebar';
import type { ComposerActionBehavior, PluginManifest } from './types';

export interface ContributionLine {
  /** What kind of thing it is, e.g. "Sidebar row". */
  kind: string;
  /** The name the plugin gives it. */
  label: string;
  /** What it does. */
  detail: string;
}

const SNIPPET_MAX = 60;

/** A one-line preview of inserted text. */
export function snippet(text: string): string {
  const flat = text.replace(/\s+/g, ' ').trim();
  return flat.length > SNIPPET_MAX ? `${flat.slice(0, SNIPPET_MAX - 1)}…` : flat;
}

function composerDetail(behavior: ComposerActionBehavior): string {
  switch (behavior.type) {
    case 'insert-text':
      return `Inserts text: ${snippet(behavior.text)}`;
    case 'insert-path-ref':
      return `Inserts a reference to ${behavior.path}`;
    case 'panel':
      return `Opens the ${behavior.panelId} picker`;
  }
}

export function describeContributions(manifest: PluginManifest): ContributionLine[] {
  const lines: ContributionLine[] = [];
  for (const surface of manifest.surfaces ?? []) {
    if (surface.kind !== 'page') continue;
    lines.push({
      kind: 'Page',
      label: surface.title ?? surface.id,
      detail: 'Its own page in Vicoa, drawn by the plugin in a sandbox',
    });
  }
  for (const theme of manifest.themes ?? []) {
    lines.push({
      kind: 'Theme',
      label: theme.label,
      detail: `A ${theme.base} theme in the theme picker`,
    });
  }
  for (const item of manifest.sidebarItems ?? []) {
    // A row this build won't draw (e.g. an old `rpc` action) adds nothing.
    if (!isSupportedSidebarAction(item.action)) continue;
    const { action } = item;
    let detail: string;
    if (action.type === 'surface') detail = `Opens the plugin's "${action.surfaceId}" page`;
    else if (opensExternally(action)) detail = `Opens ${action.url} in your browser`;
    else detail = `Opens ${action.url} in Vicoa`;
    lines.push({ kind: 'Sidebar row', label: item.label, detail });
  }
  for (const action of manifest.composerActions ?? []) {
    lines.push({
      kind: (action.placement ?? 'menu') === 'toolbar' ? 'Composer button' : 'Composer menu item',
      label: action.label,
      detail: composerDetail(action.behavior),
    });
  }
  // `slashCommands` pass validation but the composer doesn't offer them yet,
  // so they add nothing and aren't listed.
  return lines;
}

/** What a plugin's pages may reach, for the trust prompt. Empty for v1 plugins. */
export interface AccessSummary {
  /** Plain-words permissions, in manifest order. */
  permissions: string[];
  /** Local file patterns the pages may read. */
  files: string[];
  /** Sites the pages may load from; empty means none. */
  network: string[];
  /** Whether any of this applies (the plugin has pages or declares access). */
  any: boolean;
  /** It runs code on the machine (a plugin backend). */
  runsCode: boolean;
}

export function describeAccess(manifest: PluginManifest): AccessSummary {
  const permissions = (manifest.permissions ?? []).map((p) => PERMISSION_TEXT[p] ?? p);
  const files = [...(manifest.files ?? [])];
  const network = [...(manifest.network ?? [])];
  const hasPages = (manifest.surfaces ?? []).length > 0;
  const runsCode = Boolean(manifest.server) || (manifest.permissions ?? []).includes('backend');
  return {
    permissions,
    files,
    network,
    any: hasPages || permissions.length > 0 || files.length > 0 || network.length > 0,
    runsCode,
  };
}
