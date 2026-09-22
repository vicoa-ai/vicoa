import { describe, test, expect } from 'vitest';
import { Text } from '@codemirror/state';
import { Chunk } from '@codemirror/merge';
import { chunkMarkRanges } from './cm-diff-marks';

/** Diff two documents and return the boxed text on each side, per chunk. */
function boxes(a: string[], b: string[]): { a: string[]; b: string[] }[] {
  const docA = Text.of(a);
  const docB = Text.of(b);
  return Chunk.build(docA, docB).map((chunk) => ({
    a: chunkMarkRanges(chunk, docA, docB, 'a').map(([f, t]) => docA.sliceString(f, t)),
    b: chunkMarkRanges(chunk, docA, docB, 'b').map(([f, t]) => docB.sliceString(f, t)),
  }));
}

describe('chunkMarkRanges', () => {
  test('boxes only the changed word of a single-line edit', () => {
    expect(boxes(['x', 'const a = 1;', 'y'], ['x', 'const a = 2;', 'y'])).toEqual([
      { a: ['1'], b: ['2'] },
    ]);
  });

  test('re-wrapped prose boxes the inserted words, not the moved line breaks', () => {
    const before = [
      '  The quick brown fox jumps over the lazy dog and then runs off into the',
      '  woods again.',
    ];
    const after = [
      '  The quick brown fox jumps over the very lazy dog and then runs off into',
      '  the woods again.',
    ];
    const [chunk] = boxes(before, after);
    expect(chunk.a).toEqual([]);
    expect(chunk.b.map((s) => s.trim())).toEqual(['very']);
  });

  test('pure insertion and pure deletion chunks get no boxes', () => {
    expect(boxes(['a', 'c'], ['a', 'b', 'c'])).toEqual([{ a: [], b: [] }]);
    expect(boxes(['a', 'b', 'c'], ['a', 'c'])).toEqual([{ a: [], b: [] }]);
  });

  test('a rewrite (little surviving text) gets no boxes', () => {
    expect(
      boxes(['completely different removed line one'], ['fresh added content that shares nothing']),
    ).toEqual([{ a: [], b: [] }]);
  });

  test('a box never covers a whole line, but does cover a partial one', () => {
    // Line 1 edited in place; line 2 wholly new inside the same chunk.
    const [chunk] = boxes(['foo(a, b)', 'tail'], ['foo(a, b, c)', 'brand new', 'tail']);
    expect(chunk.b.some((s) => s === 'brand new')).toBe(false);
    expect(chunk.b.join('')).toContain('c');
  });

  test('an added space on the same line is still boxed', () => {
    const [chunk] = boxes(['x', 'foo bar baz'], ['x', 'foo  bar baz']);
    expect(chunk.b.join('|')).toMatch(/ /);
    expect(chunk.a).toEqual([]);
  });
});
