import { describe, test, expect } from 'vitest';
import { Text } from '@codemirror/state';
import { Chunk, diff } from '@codemirror/merge';
import { lineRefinedDiff, lineRefinedDiffConfig } from './cm-line-diff';

/** Apply `changes` to `a` (replacing each A range with its B range) — must
 *  reproduce `b` exactly for the diff to be valid. */
function apply(a: string, b: string, changes: readonly { fromA: number; toA: number; fromB: number; toB: number }[]): string {
  let out = '';
  let pos = 0;
  for (const ch of changes) {
    out += a.slice(pos, ch.fromA) + b.slice(ch.fromB, ch.toB);
    pos = ch.toA;
  }
  return out + a.slice(pos);
}

/** Line numbers (1-based) of each chunk on each side. */
function chunkLines(a: string, b: string): string[] {
  const ta = Text.of(a.split('\n'));
  const tb = Text.of(b.split('\n'));
  return Chunk.build(ta, tb, lineRefinedDiffConfig).map(
    (c) =>
      `${ta.lineAt(c.fromA).number}-${ta.lineAt(c.endA).number}:${tb.lineAt(c.fromB).number}-${tb.lineAt(c.endB).number}`,
  );
}

describe('lineRefinedDiff', () => {
  const cases: [string, string, string][] = [
    ['single line edit', 'a\nb\nc', 'a\nx\nc'],
    ['insert in middle', 'a\nc', 'a\nb\nc'],
    ['delete in middle', 'a\nb\nc', 'a\nc'],
    ['append at end', 'a\nb', 'a\nb\nc'],
    ['append at end, trailing newline', 'a\nb\n', 'a\nb\nc\n'],
    ['remove from end', 'a\nb\nc', 'a\nb'],
    ['prepend at start', 'b\nc', 'a\nb\nc'],
    ['remove from start', 'a\nb\nc', 'b\nc'],
    ['replace everything', 'a\nb', 'x\ny\nz'],
    ['empty to text', '', 'x\ny'],
    ['text to empty', 'x\ny', ''],
    ['identical', 'a\nb', 'a\nb'],
    ['blank lines', 'a\n\nb', 'a\n\n\nb\n'],
    ['partial lines (incremental re-diff)', 'llo wor\nfoo\nba', 'llo world\nbar\nba'],
  ];
  for (const [name, a, b] of cases) {
    test(`is a valid edit script: ${name}`, () => {
      expect(apply(a, b, lineRefinedDiff(a, b))).toBe(b);
    });
  }

  test('refines a changed line down to the characters that differ', () => {
    const [ch] = lineRefinedDiff('const a = 1;\nx', 'const a = 2;\nx');
    expect('const a = 1;\nx'.slice(ch.fromA, ch.toA)).toBe('1');
    expect('const a = 2;\nx'.slice(ch.fromB, ch.toB)).toBe('2');
  });

  test('keeps scattered edits in a large file as separate chunks', () => {
    // A file big enough that the package's stock diff gives up (its scan
    // budget is per document) and reports one chunk spanning every edit.
    const lines = Array.from({ length: 600 }, (_, i) => `line ${i} of some prose that goes on for a while to make it big`);
    const edited = lines.map((l, i) => (i % 50 === 25 ? `${l} (edited)` : l));
    const a = lines.join('\n');
    const b = edited.join('\n');
    expect(Chunk.build(Text.of(lines), Text.of(edited), { scanLimit: 500 })).toHaveLength(1);
    expect(chunkLines(a, b)).toEqual(
      Array.from({ length: 12 }, (_, k) => `${k * 50 + 26}-${k * 50 + 26}:${k * 50 + 26}-${k * 50 + 26}`),
    );
    expect(apply(a, b, lineRefinedDiff(a, b))).toBe(b);
  });

  test('matches the stock diff on a small input', () => {
    const a = 'the quick\nbrown fox\njumps';
    const b = 'the quick\nred fox\njumps over';
    expect(lineRefinedDiff(a, b).map((c) => [c.fromA, c.toA, c.fromB, c.toB])).toEqual(
      diff(a, b).map((c) => [c.fromA, c.toA, c.fromB, c.toB]),
    );
  });
});
