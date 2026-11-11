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

// --- The short version the prompt leads with --------------------------------

/** One line of the trust prompt's summary. */
export interface SummaryLine {
  kind: 'adds' | 'reads' | 'acts' | 'files' | 'network' | 'code';
  text: string;
  /** A file pattern, shown after `text` in a monospace face. */
  code?: string;
  /** Draw attention: the plugin can act as the user, or runs code. */
  tone?: 'warn' | 'danger';
}

/** "a, b and c". */
export function joinWords(words: string[]): string {
  if (words.length <= 1) return words.join('');
  return `${words.slice(0, -1).join(', ')} and ${words[words.length - 1]}`;
}

const counted = (n: number, one: string, many: string) => (n === 1 ? `a ${one}` : `${n} ${many}`);

const READS: Partial<Record<string, string>> = {
  'projects:read': 'projects',
  'tasks:read': 'tasks',
  'sessions:read': 'sessions',
  'automations:read': 'automations',
};

const ACTS: Partial<Record<string, string>> = {
  'tasks:write': 'change tasks',
  'sessions:write': 'message your sessions',
  'sessions:start': 'start sessions',
  'automations:run': 'run automations',
};

const host = (origin: string) => origin.replace(/^https?:\/\//, '');

/**
 * At most a handful of short lines: what the plugin adds, what its pages can
 * read and do, which local files, and whether it reaches the internet. The
 * item-by-item list (`describeContributions`) is the prompt's "Details".
 */
export function summarizeTrust(manifest: PluginManifest): SummaryLine[] {
  const lines: SummaryLine[] = [];

  const pages = (manifest.surfaces ?? []).filter((s) => s.kind === 'page').length;
  const rows = (manifest.sidebarItems ?? []).filter((i) => isSupportedSidebarAction(i.action)).length;
  const themes = (manifest.themes ?? []).length;
  const composer = (manifest.composerActions ?? []).length;
  const adds = [
    pages ? counted(pages, 'page', 'pages') : null,
    rows ? counted(rows, 'sidebar row', 'sidebar rows') : null,
    themes ? counted(themes, 'theme', 'themes') : null,
    composer ? counted(composer, 'composer action', 'composer actions') : null,
  ].filter((x): x is string => x !== null);
  lines.push({ kind: 'adds', text: adds.length ? `Adds ${joinWords(adds)}` : 'Adds nothing this version of Vicoa shows' });

  const permissions = manifest.permissions ?? [];
  const reads = permissions.map((p) => READS[p]).filter((x): x is string => Boolean(x));
  if (reads.length) lines.push({ kind: 'reads', text: `Reads your ${joinWords(reads)}` });
  const acts = permissions.map((p) => ACTS[p]).filter((x): x is string => Boolean(x));
  if (acts.length) lines.push({ kind: 'acts', text: `Can ${joinWords(acts)} as you`, tone: 'warn' });

  const files = manifest.files ?? [];
  if (files.length === 1) lines.push({ kind: 'files', text: 'Reads', code: files[0] });
  else if (files.length > 1) lines.push({ kind: 'files', text: `Reads files in ${files.length} places on this machine` });

  if (pages) {
    const network = manifest.network ?? [];
    const shown = network.slice(0, 2).map(host);
    if (network.length > 2) shown.push(`${network.length - 2} more`);
    lines.push({ kind: 'network', text: network.length ? `Loads from ${joinWords(shown)}` : 'No internet access' });
  }

  if (manifest.server || permissions.includes('backend')) {
    lines.push({ kind: 'code', text: 'Runs its own code on this machine', tone: 'danger' });
  }
  return lines;
}
