import { describe, test, expect, beforeEach, afterEach, vi } from 'vitest';
import { loadPromptDraft, savePromptDraft, clearPromptDraft } from './new-session-draft';

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

beforeEach(() => {
  vi.stubGlobal('window', { localStorage: memoryStorage() });
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe('new-session prompt draft', () => {
  test('saves and loads a draft', () => {
    savePromptDraft('build a login page');
    expect(loadPromptDraft()).toBe('build a login page');
  });

  test('empty text clears the draft', () => {
    savePromptDraft('something');
    savePromptDraft('');
    expect(loadPromptDraft()).toBe('');
  });

  test('clearPromptDraft removes the draft', () => {
    savePromptDraft('something');
    clearPromptDraft();
    expect(loadPromptDraft()).toBe('');
  });

  test('load returns empty string when nothing is saved', () => {
    expect(loadPromptDraft()).toBe('');
  });
});
