import { describe, test, expect } from 'vitest';
import {
  loadPanelState,
  savePanelState,
  clampPanelWidth,
  MIN_PANEL_WIDTH,
  loadExpansion,
  saveExpansion,
  loadPanelSessionView,
  savePanelSessionView,
  loadFileTabs,
  saveFileTabs,
  clearWorkspaceLayout,
} from './panel-storage';

function fakeStorage(initial: Record<string, string> = {}): Storage {
  const data = new Map(Object.entries(initial));
  return {
    getItem: (k) => (data.has(k) ? (data.get(k) as string) : null),
    setItem: (k, v) => void data.set(k, String(v)),
    removeItem: (k) => void data.delete(k),
    clear: () => data.clear(),
    key: (i) => Array.from(data.keys())[i] ?? null,
    get length() {
      return data.size;
    },
  };
}

describe('loadPanelState', () => {
  test('returns defaults when storage is empty', () => {
    const state = loadPanelState(fakeStorage());
    expect(state).toEqual({
      open: false,
      width: 400,
      lastTab: 'files',
      maximized: false,
      splitHeight: 280,
    });
  });

  test('reads values saved by savePanelState (round trip)', () => {
    const storage = fakeStorage();
    savePanelState(storage, {
      open: true,
      width: 520,
      lastTab: 'git',
      maximized: true,
      splitHeight: 340,
    });
    expect(loadPanelState(storage)).toEqual({
      open: true,
      width: 520,
      lastTab: 'git',
      maximized: true,
      splitHeight: 340,
    });
  });

  test('split height clamps up to the minimum and survives corrupt input', () => {
    expect(loadPanelState(fakeStorage({ 'files-panel-split-height': '50' })).splitHeight).toBe(120);
    expect(loadPanelState(fakeStorage({ 'files-panel-split-height': 'banana' })).splitHeight).toBe(
      280,
    );
  });

  test('maximized defaults to false and is not set by an unrelated legacy value', () => {
    // A store written before focus mode existed has no maximized key.
    const state = loadPanelState(fakeStorage({ 'files-panel-open': 'true' }));
    expect(state.maximized).toBe(false);
  });

  test('legacy persisted "terminal" tab falls back to files', () => {
    // Terminal tabs are now dynamic/ephemeral and never persisted; an older
    // build may still have written 'terminal' — it must not strand the panel.
    const state = loadPanelState(fakeStorage({ 'files-panel-tab': 'terminal' }));
    expect(state.lastTab).toBe('files');
  });

});

describe('clampPanelWidth', () => {
  test('returns the value unchanged when within bounds', () => {
    expect(clampPanelWidth(500, 1600)).toBe(500);
  });

  test('clamps below the minimum (300px) up to MIN_PANEL_WIDTH', () => {
    expect(clampPanelWidth(120, 1600)).toBe(MIN_PANEL_WIDTH);
    expect(MIN_PANEL_WIDTH).toBe(300);
  });

  test('clamps above 60% of viewport down to 60% of viewport', () => {
    expect(clampPanelWidth(2000, 1000)).toBe(600);
  });

  test('falls back to the default when the value is not finite', () => {
    expect(clampPanelWidth(Number.NaN, 1600)).toBe(400);
  });
});

describe('loadPanelState (corrupt input)', () => {
  test('non-numeric width falls back to default', () => {
    const state = loadPanelState(fakeStorage({ 'files-panel-width': 'banana' }));
    expect(state.width).toBe(400);
  });

  test('unknown tab value falls back to files', () => {
    const state = loadPanelState(fakeStorage({ 'files-panel-tab': 'somethingelse' }));
    expect(state.lastTab).toBe('files');
  });
});

describe('loadExpansion (corrupt input)', () => {
  test('malformed JSON returns empty Set', () => {
    const exp = loadExpansion(fakeStorage({ 'files-panel-expansion:i1': '{not json' }), 'i1');
    expect(exp.size).toBe(0);
  });

  test('non-array JSON returns empty Set', () => {
    const exp = loadExpansion(fakeStorage({ 'files-panel-expansion:i1': '{"a":1}' }), 'i1');
    expect(exp.size).toBe(0);
  });

  test('non-string entries are filtered out', () => {
    const exp = loadExpansion(
      fakeStorage({ 'files-panel-expansion:i1': '["src", 42, null, "lib"]' }),
      'i1',
    );
    expect(exp).toEqual(new Set(['src', 'lib']));
  });
});

describe('expansion state per instance', () => {
  test('empty storage returns an empty Set', () => {
    const exp = loadExpansion(fakeStorage(), 'inst-1');
    expect(exp).toBeInstanceOf(Set);
    expect(exp.size).toBe(0);
  });

  test('saved paths for one instance round-trip into a Set', () => {
    const storage = fakeStorage();
    saveExpansion(storage, 'inst-1', new Set(['src', 'src/components']));
    expect(loadExpansion(storage, 'inst-1')).toEqual(new Set(['src', 'src/components']));
  });

  test('expansion state is isolated per instance', () => {
    const storage = fakeStorage();
    saveExpansion(storage, 'inst-1', new Set(['src']));
    saveExpansion(storage, 'inst-2', new Set(['lib']));
    expect(loadExpansion(storage, 'inst-1')).toEqual(new Set(['src']));
    expect(loadExpansion(storage, 'inst-2')).toEqual(new Set(['lib']));
  });
});

const CLOSED_VIEW = { open: false, maximized: false, split: false, splitTop: false };

describe('per-session panel view (open + focus + split)', () => {
  test('a never-touched session defaults to closed, not focused, unsplit', () => {
    expect(loadPanelSessionView(fakeStorage(), 'inst-1')).toEqual(CLOSED_VIEW);
  });

  test('round-trips open + maximized + split per instance', () => {
    const storage = fakeStorage();
    savePanelSessionView(storage, 'inst-1', {
      open: true,
      maximized: true,
      split: true,
      splitTop: true,
    });
    expect(loadPanelSessionView(storage, 'inst-1')).toEqual({
      open: true,
      maximized: true,
      split: true,
      splitTop: true,
    });
  });

  test('view is isolated per session', () => {
    const storage = fakeStorage();
    savePanelSessionView(storage, 'inst-1', { ...CLOSED_VIEW, open: true, maximized: true });
    savePanelSessionView(storage, 'inst-2', { ...CLOSED_VIEW, open: true, split: true });
    expect(loadPanelSessionView(storage, 'inst-1')).toEqual({
      ...CLOSED_VIEW,
      open: true,
      maximized: true,
    });
    expect(loadPanelSessionView(storage, 'inst-2')).toEqual({
      ...CLOSED_VIEW,
      open: true,
      split: true,
    });
    // A session never written stays at the chat-only default.
    expect(loadPanelSessionView(storage, 'inst-3')).toEqual(CLOSED_VIEW);
  });

  test('a legacy view written before the split existed loads as unsplit', () => {
    const storage = fakeStorage({
      'files-panel-view:inst-1': JSON.stringify({ open: true, maximized: false }),
    });
    expect(loadPanelSessionView(storage, 'inst-1')).toEqual({ ...CLOSED_VIEW, open: true });
  });

  test('saving the default clears the key (chat-only leaves no trace)', () => {
    const storage = fakeStorage();
    savePanelSessionView(storage, 'inst-1', { ...CLOSED_VIEW, open: true, maximized: true });
    savePanelSessionView(storage, 'inst-1', CLOSED_VIEW);
    expect(storage.getItem('files-panel-view:inst-1')).toBeNull();
    expect(loadPanelSessionView(storage, 'inst-1')).toEqual(CLOSED_VIEW);
  });

  test('a closed-but-split session still persists (split alone holds the key)', () => {
    const storage = fakeStorage();
    savePanelSessionView(storage, 'inst-1', { ...CLOSED_VIEW, split: true });
    expect(loadPanelSessionView(storage, 'inst-1')).toEqual({ ...CLOSED_VIEW, split: true });
  });

  test('malformed JSON falls back to the default', () => {
    expect(
      loadPanelSessionView(fakeStorage({ 'files-panel-view:inst-1': '{oops' }), 'inst-1'),
    ).toEqual(CLOSED_VIEW);
  });

  test('clearWorkspaceLayout drops the session view', () => {
    const storage = fakeStorage();
    savePanelSessionView(storage, 'inst-1', { ...CLOSED_VIEW, open: true, maximized: true });
    clearWorkspaceLayout(storage, 'inst-1');
    expect(loadPanelSessionView(storage, 'inst-1')).toEqual(CLOSED_VIEW);
  });
});

describe('savePanelState (partial)', () => {
  test('save only persists the supplied keys', () => {
    const storage = fakeStorage();
    savePanelState(storage, { open: true, width: 520, lastTab: 'git' });
    savePanelState(storage, { open: false });
    expect(loadPanelState(storage)).toEqual({
      open: false,
      width: 520,
      lastTab: 'git',
      maximized: false,
      splitHeight: 280,
    });
  });
});

describe('file tabs persistence', () => {
  test('round-trips open tabs with their view mode', () => {
    const storage = fakeStorage();
    saveFileTabs(storage, 'inst', {
      openFiles: [
        { path: 'a.ts', viewMode: 'diff' },
        { path: 'b.ts', viewMode: 'edit' },
      ],
      activeFile: 'a.ts',
    });
    expect(loadFileTabs(storage, 'inst')).toEqual({
      openFiles: [
        { path: 'a.ts', viewMode: 'diff' },
        { path: 'b.ts', viewMode: 'edit' },
      ],
      activeFile: 'a.ts',
    });
  });

  test('reads the legacy string[] layout as edit-mode tabs', () => {
    const storage = fakeStorage({
      'files-panel-filetabs:inst': JSON.stringify({ openFiles: ['a.ts', 'b.ts'], activeFile: 'b.ts' }),
    });
    expect(loadFileTabs(storage, 'inst')).toEqual({
      openFiles: [
        { path: 'a.ts', viewMode: 'edit' },
        { path: 'b.ts', viewMode: 'edit' },
      ],
      activeFile: 'b.ts',
    });
  });

  test('drops an active file that is not among the open tabs', () => {
    const storage = fakeStorage({
      'files-panel-filetabs:inst': JSON.stringify({
        openFiles: [{ path: 'a.ts', viewMode: 'diff' }],
        activeFile: 'gone.ts',
      }),
    });
    expect(loadFileTabs(storage, 'inst').activeFile).toBeNull();
  });

  test('empty tabs clear the storage key', () => {
    const storage = fakeStorage();
    saveFileTabs(storage, 'inst', { openFiles: [{ path: 'a.ts', viewMode: 'edit' }], activeFile: 'a.ts' });
    saveFileTabs(storage, 'inst', { openFiles: [], activeFile: null });
    expect(loadFileTabs(storage, 'inst')).toEqual({ openFiles: [], activeFile: null });
  });

  test('round-trips a saved scroll anchor (line + offset), omitting when absent', () => {
    const storage = fakeStorage();
    saveFileTabs(storage, 'inst', {
      openFiles: [
        { path: 'a.ts', viewMode: 'edit', scrollLine: 42, scrollOffset: 6 },
        { path: 'b.ts', viewMode: 'edit', scrollLine: 12 },
        { path: 'c.ts', viewMode: 'edit' },
      ],
      activeFile: 'a.ts',
    });
    expect(loadFileTabs(storage, 'inst')).toEqual({
      openFiles: [
        { path: 'a.ts', viewMode: 'edit', scrollLine: 42, scrollOffset: 6 },
        { path: 'b.ts', viewMode: 'edit', scrollLine: 12 },
        { path: 'c.ts', viewMode: 'edit' },
      ],
      activeFile: 'a.ts',
    });
  });

  test('ignores a non-numeric or top-of-file scroll line on load', () => {
    const storage = fakeStorage({
      'files-panel-filetabs:inst': JSON.stringify({
        openFiles: [
          { path: 'a.ts', viewMode: 'edit', scrollLine: 'nope' },
          { path: 'b.ts', viewMode: 'edit', scrollLine: 1 },
          { path: 'c.ts', viewMode: 'edit', scrollLine: 7.9 },
        ],
        activeFile: 'a.ts',
      }),
    });
    expect(loadFileTabs(storage, 'inst').openFiles).toEqual([
      { path: 'a.ts', viewMode: 'edit' },
      { path: 'b.ts', viewMode: 'edit' },
      { path: 'c.ts', viewMode: 'edit', scrollLine: 7 },
    ]);
  });

  test('drops a scroll offset that is invalid or has no line to anchor to', () => {
    const storage = fakeStorage({
      'files-panel-filetabs:inst': JSON.stringify({
        openFiles: [
          { path: 'a.ts', viewMode: 'edit', scrollOffset: 8 }, // no line → drop offset
          { path: 'b.ts', viewMode: 'edit', scrollLine: 5, scrollOffset: 0 }, // 0 → drop
          { path: 'c.ts', viewMode: 'edit', scrollLine: 9, scrollOffset: 'x' }, // non-numeric → drop
        ],
        activeFile: 'a.ts',
      }),
    });
    expect(loadFileTabs(storage, 'inst').openFiles).toEqual([
      { path: 'a.ts', viewMode: 'edit' },
      { path: 'b.ts', viewMode: 'edit', scrollLine: 5 },
      { path: 'c.ts', viewMode: 'edit', scrollLine: 9 },
    ]);
  });
});
