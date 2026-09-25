'use client';

/**
 * Visibility preferences for the sidebar's fixed nav rows (New Session, Tasks,
 * Automations, Agents, Skills, Search). Not everyone uses all of them, so each
 * can be hidden from Settings → Appearance; the session list below them is
 * always shown.
 *
 * Stored as the list of *hidden* ids so the default (everything shown) is an
 * absent key, and a row added later shows up for existing users. Persisted via
 * the desktop settings bridge (falls back to localStorage on web), with a
 * same-document event to keep the sidebar and the settings toggles in sync —
 * the native `storage` event only fires cross-tab. Same shape as
 * `mobile-sidebar-pref`, which still owns the separate "Vicoa Mobile" row.
 */

import { useEffect, useState } from 'react';
import { getPref, setPref } from './desktop-prefs';

const HIDDEN_ITEMS_KEY = 'sidebar-hidden-nav-items';
const CHANGE_EVENT = 'vicoa:sidebar-nav-pref';

export type SidebarNavItemId =
  | 'new-session'
  | 'tasks'
  | 'automations'
  | 'agents'
  | 'skills'
  | 'search';

/** Rendered in sidebar order; the settings list reuses it. */
export const SIDEBAR_NAV_ITEMS: ReadonlyArray<{
  id: SidebarNavItemId;
  label: string;
  description: string;
}> = [
  { id: 'new-session', label: 'New Session', description: 'Start a session from the sidebar' },
  { id: 'tasks', label: 'Tasks', description: 'Your task backlog' },
  { id: 'automations', label: 'Automations', description: 'Scheduled agent runs' },
  { id: 'agents', label: 'Agents', description: 'Saved agent presets' },
  { id: 'skills', label: 'Skills', description: 'Agent skills installed on your machines' },
  { id: 'search', label: 'Search', description: 'Search sessions, tasks and automations' },
];

const KNOWN_IDS = new Set<string>(SIDEBAR_NAV_ITEMS.map((item) => item.id));

/**
 * Ids the user has hidden. Unknown entries (a row removed in a later build) are
 * dropped on read rather than written back, so downgrading keeps its setting.
 */
export function hiddenSidebarNavItems(): Set<SidebarNavItemId> {
  const stored = getPref<unknown>(HIDDEN_ITEMS_KEY);
  if (!Array.isArray(stored)) return new Set();
  return new Set(
    stored.filter((id): id is SidebarNavItemId => typeof id === 'string' && KNOWN_IDS.has(id)),
  );
}

export function isSidebarNavItemHidden(id: SidebarNavItemId): boolean {
  return hiddenSidebarNavItems().has(id);
}

export function setSidebarNavItemHidden(id: SidebarNavItemId, hidden: boolean): void {
  const next = hiddenSidebarNavItems();
  if (hidden) next.add(id);
  else next.delete(id);
  // Clear the key when nothing is hidden (the default), and keep the stored
  // order stable so the file diff stays readable.
  const ids = SIDEBAR_NAV_ITEMS.filter((item) => next.has(item.id)).map((item) => item.id);
  setPref(HIDDEN_ITEMS_KEY, ids.length > 0 ? ids : null);
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event(CHANGE_EVENT));
  }
}

/** Reactive read: re-renders when the preference changes in this document. */
export function useHiddenSidebarNavItems(): Set<SidebarNavItemId> {
  // Empty on the first render (nothing hidden) so SSR and the first client
  // paint agree; the real value lands post-mount.
  const [hidden, setHidden] = useState<Set<SidebarNavItemId>>(() => new Set());
  useEffect(() => {
    const read = () => setHidden(hiddenSidebarNavItems());
    read();
    window.addEventListener(CHANGE_EVENT, read);
    return () => window.removeEventListener(CHANGE_EVENT, read);
  }, []);
  return hidden;
}
