import { describe, test, expect, beforeEach, afterEach, vi } from 'vitest';
import { confirmAgentStart, setConfirmAgentStart } from './assign-agent-pref';

const KEY = 'confirm-agent-start';

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
const dispatched: string[] = [];

beforeEach(() => {
  storage = memoryStorage();
  dispatched.length = 0;
  // No __VICOA_SETTINGS__: the web/localStorage path of desktop-prefs.
  vi.stubGlobal('window', {
    localStorage: storage,
    dispatchEvent: (e: Event) => { dispatched.push(e.type); return true; },
  });
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe('confirm-before-starting-an-agent preference', () => {
  test('asks by default', () => {
    expect(confirmAgentStart()).toBe(true);
  });

  test("don't ask again is remembered and announced", () => {
    setConfirmAgentStart(false);
    expect(confirmAgentStart()).toBe(false);
    expect(dispatched).toEqual(['vicoa:confirm-agent-start']);
  });

  test('asking again is the absent key, not a stored value', () => {
    setConfirmAgentStart(false);
    setConfirmAgentStart(true);
    expect(storage.getItem(KEY)).toBeNull();
    expect(confirmAgentStart()).toBe(true);
  });

  test('anything but an explicit false keeps asking', () => {
    storage.setItem(KEY, JSON.stringify('no'));
    expect(confirmAgentStart()).toBe(true);
    storage.setItem(KEY, JSON.stringify(0));
    expect(confirmAgentStart()).toBe(true);
  });
});
