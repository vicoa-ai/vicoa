import { describe, test, expect } from 'vitest';
import {
  indexOfTab,
  withLoadingTab,
  replacePreviewSlot,
  patchTab,
  removeTab,
  nextActiveAfterClose,
  blankEditState,
  type OpenFile,
} from './file-tabs';

const f = (path: string): OpenFile => ({
  path,
  loading: false,
  result: null,
  error: null,
  ...blankEditState(),
});

describe('blankEditState', () => {
  test('a fresh tab defaults to edit mode with no baseline', () => {
    expect(blankEditState().viewMode).toBe('edit');
    expect(blankEditState().base).toBeNull();
  });
});

describe('withLoadingTab', () => {
  test('appends a loading placeholder for a new path', () => {
    const next = withLoadingTab([f('a')], 'b');
    expect(next.map((t) => t.path)).toEqual(['a', 'b']);
    expect(next[1]).toEqual({ path: 'b', loading: true, result: null, error: null, ...blankEditState() });
  });

  test('resets an existing tab to loading in place', () => {
    const start = patchTab([f('a'), f('b')], 'a', { error: 'boom' });
    const next = withLoadingTab(start, 'a');
    expect(next.map((t) => t.path)).toEqual(['a', 'b']);
    expect(next[0]).toEqual({ path: 'a', loading: true, result: null, error: null, ...blankEditState() });
  });

  test('carries a diff view mode + baseline across a refetch', () => {
    const start = patchTab([f('a')], 'a', {
      viewMode: 'diff',
      base: { loading: false, content: 'HEAD', error: null },
    });
    const next = withLoadingTab(start, 'a');
    expect(next[0].viewMode).toBe('diff');
    expect(next[0].base).toEqual({ loading: false, content: 'HEAD', error: null });
    expect(next[0].loading).toBe(true);
  });
});

describe('replacePreviewSlot', () => {
  test('replaces the preview tab in place with a fresh loading preview', () => {
    const start = patchTab([f('a'), f('b'), f('c')], 'b', { preview: true, result: {} as never });
    const next = replacePreviewSlot(start, 'b', 'z');
    expect(next.map((t) => t.path)).toEqual(['a', 'z', 'c']); // same index
    expect(next[1]).toMatchObject({ path: 'z', loading: true, result: null, preview: true });
  });

  test('is a no-op when the old path is gone', () => {
    const tabs = [f('a')];
    expect(replacePreviewSlot(tabs, 'gone', 'z')).toBe(tabs);
  });
});

describe('patchTab', () => {
  test('merges a patch into the matching tab', () => {
    const next = patchTab([f('a'), f('b')], 'b', { loading: false, error: 'x' });
    expect(next[1]).toEqual({ path: 'b', loading: false, result: null, error: 'x', ...blankEditState() });
  });

  test('is a no-op when the tab is gone', () => {
    const tabs = [f('a')];
    expect(patchTab(tabs, 'zzz', { error: 'x' })).toBe(tabs);
  });
});

describe('removeTab', () => {
  test('drops the matching tab', () => {
    expect(removeTab([f('a'), f('b')], 'a').map((t) => t.path)).toEqual(['b']);
  });
});

describe('indexOfTab', () => {
  test('finds an open tab or returns -1', () => {
    expect(indexOfTab([f('a'), f('b')], 'b')).toBe(1);
    expect(indexOfTab([f('a')], 'z')).toBe(-1);
  });
});

describe('nextActiveAfterClose', () => {
  const tabs = [f('a'), f('b'), f('c')];

  test('closing an inactive tab keeps the active tab', () => {
    expect(nextActiveAfterClose(tabs, 'b', 'a')).toBe('b');
  });

  test('closing the active middle tab selects the left neighbor', () => {
    expect(nextActiveAfterClose(tabs, 'b', 'b')).toBe('a');
  });

  test('closing the active first tab selects the right neighbor', () => {
    expect(nextActiveAfterClose(tabs, 'a', 'a')).toBe('b');
  });

  test('closing the only tab clears the active path', () => {
    expect(nextActiveAfterClose([f('a')], 'a', 'a')).toBe(null);
  });
});
