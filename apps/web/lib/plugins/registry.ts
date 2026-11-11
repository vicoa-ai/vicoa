/**
 * Plugin registry — the renderer's single source of truth for installed
 * plugins, aggregated across every connected machine.
 *
 * Data flows in from the daemon's `plugin-catalog` RPC (per machine) via
 * `setMachinePlugins`, plus any built-in example plugins registered at startup.
 * Components read it through `usePluginRegistry()` (a `useSyncExternalStore`
 * hook with a stable snapshot) and derive their slice with `useMemo`.
 * `theme-provider.tsx` also reads it synchronously through the non-hook
 * `getPluginThemesSnapshot()` accessor.
 *
 * Only **Tier 1** (declarative manifest) data lives here. The store is a plain
 * module singleton — no React, no context — so it is safe to touch from the WS
 * layer and from the theme provider's effect alike.
 */

import { getLocalMachineId } from '@/lib/local-machine';
import { isSupportedSidebarAction } from './sidebar';
import {
  type PluginManifest,
  type PluginThemeContribution,
  type PluginSidebarItem,
  type PluginComposerAction,
  PLUGIN_API_VERSION,
} from './types';

/** Synthetic machine id for built-in/example plugins that ship with the app. */
export const BUILTIN_MACHINE_ID = 'builtin';

export interface RegisteredPlugin {
  machineId: string;
  pluginId: string;
  manifest: PluginManifest;
  /** User toggle from the daemon config; disabled plugins contribute nothing. */
  enabled: boolean;
  /** Trust-gate state. Untrusted plugins contribute nothing until confirmed. */
  trusted: boolean;
  /** Whether the plugin's optional backend subprocess is reachable (Tier 2). */
  serverAvailable: boolean;
  /** Built-in example plugins are always trusted and need no daemon round-trip. */
  builtin: boolean;
  /** Where the daemon installed it from: a local folder or a git URL. */
  source?: string | null;
  /** The machine's name as the user knows it, for the trust prompt. */
  machineLabel?: string;
  /** Set when the daemon says this machine's Vicoa is too old for the plugin. */
  requirementError?: string | null;
  /** Bumped by `vicoa plugin reload`; a change reloads open pages. */
  reloadNonce?: number;
  /** The daemon's CLI version; null when it predates plugin pages. */
  daemonVersion?: string | null;
  /** Hash of the manifest shown, sent back with a trust grant. */
  manifestHash?: string | null;
}

/** A theme resolved to its owning plugin, ready for the picker / injector. */
export interface ResolvedTheme extends PluginThemeContribution {
  pluginId: string;
  machineId: string;
  pluginName: string;
}

function pluginKey(machineId: string, pluginId: string): string {
  return `${machineId}::${pluginId}`;
}

class PluginRegistry {
  private byKey = new Map<string, RegisteredPlugin>();
  /** Machines whose catalog has arrived at least once this session. */
  private synced = new Set<string>();
  private listeners = new Set<() => void>();
  /** Cached array handed to React; rebuilt only when data changes. */
  private snapshot: RegisteredPlugin[] = [];

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };

  getSnapshot = (): RegisteredPlugin[] => this.snapshot;

  private syncListeners = new Set<() => void>();

  /** Ask the catalog sync to fetch every machine's plugins now. */
  requestSync() {
    for (const l of this.syncListeners) l();
  }

  onSyncRequest(listener: () => void): () => void {
    this.syncListeners.add(listener);
    return () => {
      this.syncListeners.delete(listener);
    };
  }

  /** SSR: no plugins. Stable empty array keeps hydration deterministic. */
  getServerSnapshot = (): RegisteredPlugin[] => EMPTY;

  private commit() {
    this.snapshot = Array.from(this.byKey.values());
    for (const l of this.listeners) l();
  }

  /**
   * Replace the full set of plugins reported by one machine. Called after a
   * `plugin-catalog` fetch. Built-in plugins live under BUILTIN_MACHINE_ID and
   * are untouched by real-machine updates.
   */
  setMachinePlugins(machineId: string, plugins: RegisteredPlugin[]) {
    let changed = false;
    if (!this.synced.has(machineId)) {
      this.synced.add(machineId);
      changed = true;
    }
    // Drop any existing plugins from this machine that are no longer present.
    const incoming = new Set(plugins.map((p) => pluginKey(machineId, p.pluginId)));
    for (const key of Array.from(this.byKey.keys())) {
      const p = this.byKey.get(key)!;
      if (p.machineId === machineId && !incoming.has(key)) {
        this.byKey.delete(key);
        changed = true;
      }
    }
    for (const p of plugins) {
      if (p.manifest.apiVersion > PLUGIN_API_VERSION) continue; // host too old
      this.byKey.set(pluginKey(machineId, p.pluginId), p);
      changed = true;
    }
    if (changed) this.commit();
  }

  /** Whether this machine's catalog has arrived, so "not installed" is a real answer. */
  isMachineSynced(machineId: string): boolean {
    return this.synced.has(machineId);
  }

  /** Register built-in example plugins (idempotent). */
  registerBuiltins(manifests: PluginManifest[]) {
    let changed = false;
    for (const manifest of manifests) {
      const key = pluginKey(BUILTIN_MACHINE_ID, manifest.id);
      if (this.byKey.has(key)) continue;
      this.byKey.set(key, {
        machineId: BUILTIN_MACHINE_ID,
        pluginId: manifest.id,
        manifest,
        enabled: true,
        trusted: true,
        serverAvailable: false,
        builtin: true,
      });
      changed = true;
    }
    if (changed) this.commit();
  }

  /** Flip a plugin's trust flag locally (after the user clears the trust gate). */
  setTrusted(machineId: string, pluginId: string, trusted: boolean) {
    const p = this.byKey.get(pluginKey(machineId, pluginId));
    if (p && p.trusted !== trusted) {
      this.byKey.set(pluginKey(machineId, pluginId), { ...p, trusted });
      this.commit();
    }
  }

  /** Optimistic local toggle; the daemon config is the durable source. */
  setEnabled(machineId: string, pluginId: string, enabled: boolean) {
    const p = this.byKey.get(pluginKey(machineId, pluginId));
    if (p && p.enabled !== enabled) {
      this.byKey.set(pluginKey(machineId, pluginId), { ...p, enabled });
      this.commit();
    }
  }

  /** Remove a single plugin (e.g. after an uninstall from settings). */
  removePlugin(machineId: string, pluginId: string) {
    if (this.byKey.delete(pluginKey(machineId, pluginId))) this.commit();
  }

  /** Remove every plugin belonging to a machine (e.g. on disconnect). */
  clearMachine(machineId: string) {
    let changed = false;
    for (const key of Array.from(this.byKey.keys())) {
      if (this.byKey.get(key)!.machineId === machineId) {
        this.byKey.delete(key);
        changed = true;
      }
    }
    if (this.synced.delete(machineId)) changed = true;
    if (changed) this.commit();
  }
}

const EMPTY: RegisteredPlugin[] = [];

/** Process-wide singleton. */
export const pluginRegistry = new PluginRegistry();

// ---------------------------------------------------------------------------
// Non-hook selectors (safe to call outside React, e.g. the theme provider).
// ---------------------------------------------------------------------------

/**
 * Plugins that are switched on, on any machine: enabled, trusted, and not
 * waiting for a newer Vicoa on that machine.
 */
export function activePlugins(all: RegisteredPlugin[] = pluginRegistry.getSnapshot()): RegisteredPlugin[] {
  return all.filter((p) => p.enabled && p.trusted && !p.requirementError);
}

/**
 * The active plugins that contribute to the app: one copy per plugin id. A
 * plugin installed on several machines would otherwise add its sidebar row,
 * themes and composer buttons once per machine. The copy on `preferMachineId`
 * (this desktop's own machine) wins; then a real machine over a built-in, so an
 * installed plugin overrides a built-in of the same id; then the lowest machine
 * id, so the choice doesn't depend on which machine answered first.
 */
export function contributingPlugins(
  all: RegisteredPlugin[] = pluginRegistry.getSnapshot(),
  preferMachineId: string | null = getLocalMachineId(),
): RegisteredPlugin[] {
  const rank = (p: RegisteredPlugin) =>
    p.machineId === preferMachineId ? 0 : p.builtin ? 2 : 1;
  const chosen = new Map<string, RegisteredPlugin>();
  for (const p of activePlugins(all)) {
    const held = chosen.get(p.pluginId);
    if (
      !held ||
      rank(p) < rank(held) ||
      (rank(p) === rank(held) && p.machineId < held.machineId)
    ) {
      chosen.set(p.pluginId, p);
    }
  }
  // Keep registry order so rows don't reshuffle when a copy is swapped.
  return activePlugins(all).filter((p) => chosen.get(p.pluginId) === p);
}

/** Every theme from every active plugin, flattened and resolved to its owner. */
export function getPluginThemesSnapshot(
  all: RegisteredPlugin[] = pluginRegistry.getSnapshot(),
): ResolvedTheme[] {
  const out: ResolvedTheme[] = [];
  for (const p of contributingPlugins(all)) {
    for (const theme of p.manifest.themes ?? []) {
      out.push({
        ...theme,
        pluginId: p.pluginId,
        machineId: p.machineId,
        pluginName: p.manifest.name ?? p.pluginId,
      });
    }
  }
  return out;
}

/** Look up a single theme by `pluginId` + `themeId` across active plugins. */
export function findPluginTheme(
  pluginId: string,
  themeId: string,
  all: RegisteredPlugin[] = pluginRegistry.getSnapshot(),
): ResolvedTheme | null {
  for (const t of getPluginThemesSnapshot(all)) {
    if (t.pluginId === pluginId && t.id === themeId) return t;
  }
  return null;
}

/** Sidebar items from active plugins for a given slot, tagged with owner. */
export interface OwnedSidebarItem {
  item: PluginSidebarItem;
  pluginId: string;
  machineId: string;
}

export function getPluginSidebarItems(
  slot: 'nav' | 'footer',
  all: RegisteredPlugin[] = pluginRegistry.getSnapshot(),
): OwnedSidebarItem[] {
  const out: OwnedSidebarItem[] = [];
  for (const p of contributingPlugins(all)) {
    for (const item of p.manifest.sidebarItems ?? []) {
      if ((item.slot ?? 'nav') === slot && isSupportedSidebarAction(item.action)) {
        out.push({ item, pluginId: p.pluginId, machineId: p.machineId });
      }
    }
  }
  return out;
}

/** Composer actions from active plugins for a given placement, tagged with owner. */
export interface OwnedComposerAction {
  action: PluginComposerAction;
  pluginId: string;
  machineId: string;
}

export function getPluginComposerActions(
  placement: 'menu' | 'toolbar',
  all: RegisteredPlugin[] = pluginRegistry.getSnapshot(),
): OwnedComposerAction[] {
  const out: OwnedComposerAction[] = [];
  for (const p of contributingPlugins(all)) {
    for (const action of p.manifest.composerActions ?? []) {
      if ((action.placement ?? 'menu') === placement) {
        out.push({ action, pluginId: p.pluginId, machineId: p.machineId });
      }
    }
  }
  return out;
}

/** One plugin on one machine, whatever its state. */
export function findPlugin(
  machineId: string,
  pluginId: string,
  all: RegisteredPlugin[] = pluginRegistry.getSnapshot(),
): RegisteredPlugin | null {
  return all.find((p) => p.machineId === machineId && p.pluginId === pluginId) ?? null;
}

/** Every machine's copy of a plugin, for the page's machine picker. */
export function pluginCopies(
  pluginId: string,
  all: RegisteredPlugin[] = pluginRegistry.getSnapshot(),
): RegisteredPlugin[] {
  return all.filter((p) => p.pluginId === pluginId && !p.builtin);
}
