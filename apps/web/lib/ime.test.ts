import type { KeyboardEvent } from 'react';
import { describe, expect, it } from 'vitest';

import { isImeComposing } from './ime';

const keydown = (isComposing: boolean, keyCode: number) =>
  ({ nativeEvent: { isComposing }, keyCode }) as unknown as KeyboardEvent;

describe('isImeComposing', () => {
  it('is true while a candidate window is open', () => {
    expect(isImeComposing(keydown(true, 13))).toBe(true);
  });

  it("is true for Safari's committing Enter, which reports isComposing false", () => {
    expect(isImeComposing(keydown(false, 229))).toBe(true);
  });

  it('is false for a plain Enter', () => {
    expect(isImeComposing(keydown(false, 13))).toBe(false);
  });
});
