import { afterEach, describe, expect, test } from 'vitest';
import { isTextSelectionClick } from './text-selection';

// The vitest environment is `node`, so `window` is stubbed per case with just
// the `getSelection()` surface the helper reads.
function stubSelection(selection: { isCollapsed: boolean; text: string } | null) {
  (globalThis as { window?: unknown }).window = {
    getSelection: () =>
      selection === null
        ? null
        : { isCollapsed: selection.isCollapsed, toString: () => selection.text },
  };
}

afterEach(() => {
  delete (globalThis as { window?: unknown }).window;
});

describe('isTextSelectionClick', () => {
  test('a pointer click that left a range selection behind is a selection', () => {
    stubSelection({ isCollapsed: false, text: 'Read file.ts' });
    expect(isTextSelectionClick({ detail: 1 })).toBe(true);
  });

  test('a plain click (caret only) is an activation', () => {
    stubSelection({ isCollapsed: true, text: '' });
    expect(isTextSelectionClick({ detail: 1 })).toBe(false);
  });

  test('a non-collapsed selection with no text (e.g. only an icon) is an activation', () => {
    stubSelection({ isCollapsed: false, text: '' });
    expect(isTextSelectionClick({ detail: 1 })).toBe(false);
  });

  test('keyboard activation (detail 0) is never a selection, whatever is selected', () => {
    stubSelection({ isCollapsed: false, text: 'anything' });
    expect(isTextSelectionClick({ detail: 0 })).toBe(false);
  });

  test('no selection object or no window is an activation', () => {
    stubSelection(null);
    expect(isTextSelectionClick({ detail: 1 })).toBe(false);
    delete (globalThis as { window?: unknown }).window;
    expect(isTextSelectionClick({ detail: 1 })).toBe(false);
  });
});
