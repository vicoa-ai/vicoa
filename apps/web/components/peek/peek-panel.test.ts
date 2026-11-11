import { describe, expect, it } from 'vitest';
import { clampPeekWidth, PEEK_MIN_WIDTH } from './peek-panel';

describe('clampPeekWidth', () => {
  it('keeps the panel between 360px and 60% of the space', () => {
    expect(clampPeekWidth(100, 1400)).toBe(PEEK_MIN_WIDTH);
    expect(clampPeekWidth(500, 1400)).toBe(500);
    expect(clampPeekWidth(1200, 1400)).toBe(840);
  });

  it('never goes below the minimum, even in a narrow window', () => {
    expect(clampPeekWidth(500, 400)).toBe(PEEK_MIN_WIDTH);
  });
});
