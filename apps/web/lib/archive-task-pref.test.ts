import { describe, test, expect, beforeEach, afterEach, vi } from 'vitest';
import { archiveTaskAction, setArchiveTaskAction } from './archive-task-pref';
import { archiveStatusBody } from './archive-task';

const KEY = 'archive-task-action';

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

describe('archive task preference', () => {
  test('asks by default', () => {
    expect(archiveTaskAction()).toBe('ask');
  });

  test('remembers a choice and tells the document', () => {
    setArchiveTaskAction('leave');
    expect(archiveTaskAction()).toBe('leave');
    expect(dispatched).toEqual(['vicoa:archive-task-action']);
    setArchiveTaskAction('mark_done');
    expect(archiveTaskAction()).toBe('mark_done');
  });

  test('asking again is the absent key, not a stored value', () => {
    setArchiveTaskAction('leave');
    setArchiveTaskAction('ask');
    expect(storage.getItem(KEY)).toBeNull();
    expect(archiveTaskAction()).toBe('ask');
  });

  test('a value this build does not know falls back to asking', () => {
    storage.setItem(KEY, JSON.stringify('archive-quietly'));
    expect(archiveTaskAction()).toBe('ask');
    storage.setItem(KEY, JSON.stringify(7));
    expect(archiveTaskAction()).toBe('ask');
  });
});

describe('archive request body follows this device', () => {
  test('ask and mark_done name no choice, so the server maps as usual', () => {
    expect(archiveStatusBody()).toEqual({ status: 'COMPLETED' });
    setArchiveTaskAction('mark_done');
    expect(archiveStatusBody()).toEqual({ status: 'COMPLETED' });
  });

  test('leave sends no_change for an archive that names nothing', () => {
    setArchiveTaskAction('leave');
    expect(archiveStatusBody()).toEqual({ status: 'COMPLETED', task_status: 'no_change' });
  });

  test('a choice made in the dialog beats the standing answer', () => {
    setArchiveTaskAction('leave');
    expect(archiveStatusBody('done')).toEqual({ status: 'COMPLETED', task_status: 'done' });
    expect(archiveStatusBody('in_review')).toEqual({ status: 'COMPLETED', task_status: 'in_review' });
  });

  test('the answer can be passed in, for a caller that already holds it', () => {
    expect(archiveStatusBody(undefined, 'leave')).toEqual({
      status: 'COMPLETED',
      task_status: 'no_change',
    });
    expect(archiveStatusBody(undefined, 'ask')).toEqual({ status: 'COMPLETED' });
  });
});
