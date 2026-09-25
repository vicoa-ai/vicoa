import { describe, test, expect, beforeEach, afterEach, vi } from 'vitest';
import {
  SIDEBAR_NAV_ITEMS,
  hiddenSidebarNavItems,
  isSidebarNavItemHidden,
  setSidebarNavItemHidden,
} from './sidebar-nav-pref';

const KEY = 'sidebar-hidden-nav-items';

function memoryStorage(): Storage {
  const m = new Map<string, string>();
  return {
    getItem: (k: string) => (m.has(k) ? (m.get(k) as string) : null),
    setItem: (k: string, v: string) => { m.set(k, String(v)); },
    removeItem: (k: string) => { m.delete(k); },
    clear: () => { m.clear(); },
    key: (i: number) => Array.from(m.keys())[i] ?? null,
    get length() { return m.size; },
  } as Storage;
}

let storage: Storage;

beforeEach(() => {
  storage = memoryStorage();
  // No __VICOA_SETTINGS__ — the web/localStorage path of desktop-prefs.
  vi.stubGlobal('window', { localStorage: storage, dispatchEvent: () => true });
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe('sidebar nav visibility', () => {
  test('everything is shown by default', () => {
    expect(hiddenSidebarNavItems().size).toBe(0);
    for (const item of SIDEBAR_NAV_ITEMS) {
      expect(isSidebarNavItemHidden(item.id)).toBe(false);
    }
  });

  test('hiding and re-showing a row round-trips', () => {
    setSidebarNavItemHidden('automations', true);
    expect(isSidebarNavItemHidden('automations')).toBe(true);
    expect(isSidebarNavItemHidden('tasks')).toBe(false);

    setSidebarNavItemHidden('automations', false);
    expect(isSidebarNavItemHidden('automations')).toBe(false);
  });

  test('hidden ids are stored in sidebar order', () => {
    setSidebarNavItemHidden('search', true);
    setSidebarNavItemHidden('tasks', true);
    expect(JSON.parse(storage.getItem(KEY) as string)).toEqual(['tasks', 'search']);
  });

  test('the key is cleared once nothing is hidden', () => {
    setSidebarNavItemHidden('skills', true);
    expect(storage.getItem(KEY)).not.toBeNull();
    setSidebarNavItemHidden('skills', false);
    expect(storage.getItem(KEY)).toBeNull();
  });

  test('unknown stored ids are ignored, not written back', () => {
    storage.setItem(KEY, JSON.stringify(['kanban', 'skills']));
    expect(Array.from(hiddenSidebarNavItems())).toEqual(['skills']);
    // A row this build does not know about stays untouched until something
    // else is toggled, so downgrading keeps the setting.
    expect(JSON.parse(storage.getItem(KEY) as string)).toEqual(['kanban', 'skills']);
  });

  test('a malformed value falls back to everything shown', () => {
    storage.setItem(KEY, JSON.stringify('skills'));
    expect(hiddenSidebarNavItems().size).toBe(0);
  });
});
