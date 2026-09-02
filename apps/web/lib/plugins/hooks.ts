'use client';

/**
 * React bindings for the plugin registry. Components use these; the registry
 * itself (`registry.ts`) stays framework-free so non-React callers (the WS
 * layer, the theme provider) can read it too.
 */

import { useMemo, useSyncExternalStore } from 'react';
import {
  pluginRegistry,
  getPluginThemesSnapshot,
  getPluginSidebarItems,
  getPluginComposerActions,
  type RegisteredPlugin,
  type ResolvedTheme,
  type OwnedSidebarItem,
  type OwnedComposerAction,
} from './registry';

/** All registered plugins (across every machine), re-rendering on change. */
export function usePluginRegistry(): RegisteredPlugin[] {
  return useSyncExternalStore(
    pluginRegistry.subscribe,
    pluginRegistry.getSnapshot,
    pluginRegistry.getServerSnapshot,
  );
}

/** Themes from all active (enabled + trusted) plugins. */
export function usePluginThemes(): ResolvedTheme[] {
  const all = usePluginRegistry();
  return useMemo(() => getPluginThemesSnapshot(all), [all]);
}

/** Sidebar items contributed to a given slot. */
export function usePluginSidebarItems(slot: 'nav' | 'footer'): OwnedSidebarItem[] {
  const all = usePluginRegistry();
  return useMemo(() => getPluginSidebarItems(slot, all), [all, slot]);
}

/** Composer actions contributed to a given placement. */
export function usePluginComposerActions(
  placement: 'menu' | 'toolbar',
): OwnedComposerAction[] {
  const all = usePluginRegistry();
  return useMemo(() => getPluginComposerActions(placement, all), [all, placement]);
}
