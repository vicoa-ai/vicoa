import { describe, test, expect } from 'vitest';
import { alignHunk, wordDiff, tokenize } from './diff-align';
import type { DiffRow } from './diff-lines';

const ctx = (content: string, oldNo: number, newNo: number): DiffRow => ({
  kind: 'context',
  content,
  oldNo,
  newNo,
});
const del = (content: string, oldNo: number): DiffRow => ({
  kind: 'remove',
  content,
  oldNo,
  newNo: null,
});
const add = (content: string, newNo: number): DiffRow => ({
  kind: 'add',
  content,
  oldNo: null,
  newNo,
});

/** Flatten segments back to text so we can assert the split is lossless. */
const segText = (row: DiffRow) => (row.segments ?? []).map((s) => s.text).join('');
const changedText = (row: DiffRow) =>
  (row.segments ?? [])
    .filter((s) => s.changed)
    .map((s) => s.text)
    .join('');

describe('tokenize', () => {
  test('keeps words, whitespace, and punctuation as separate tokens', () => {
    expect(tokenize('a = b;')).toEqual(['a', ' ', '=', ' ', 'b', ';']);
  });

  test('round-trips exactly (lossless)', () => {
    const s = '  const x = foo(bar, 42);  ';
    expect(tokenize(s).join('')).toBe(s);
  });

  test('empty string yields no tokens', () => {
    expect(tokenize('')).toEqual([]);
  });
});

describe('wordDiff', () => {
  test('marks only the changed word on each side', () => {
    const wd = wordDiff('the quick brown fox', 'the slow brown fox');
    expect(wd).not.toBeNull();
    const [rem, added] = wd!;
    expect(rem.map((s) => s.text).join('')).toBe('the quick brown fox');
    expect(added.map((s) => s.text).join('')).toBe('the slow brown fox');
    expect(rem.filter((s) => s.changed).map((s) => s.text).join('')).toBe('quick');
    expect(added.filter((s) => s.changed).map((s) => s.text).join('')).toBe('slow');
  });

  test('returns null when the lines share no tokens', () => {
    expect(wordDiff('aaa', 'zzz')).toBeNull();
  });

  test('returns null past the per-line token cap (cheap fallback)', () => {
    const long = Array.from({ length: 500 }, (_, i) => `t${i}`).join(' ');
    expect(wordDiff(long, long + ' extra')).toBeNull();
  });
});

describe('alignHunk', () => {
  test('pairs a single-line edit and highlights the changed word (unified)', () => {
    const rows = [del('const a = 1', 1), add('const a = 2', 1)];
    const { unified } = alignHunk(rows);
    expect(unified.map((r) => r.kind)).toEqual(['remove', 'add']);
    expect(changedText(unified[0])).toBe('1');
    expect(changedText(unified[1])).toBe('2');
    // Order preserved: removes before adds.
    expect(unified[0].kind).toBe('remove');
  });

  test('single-line edit sits side by side in split view', () => {
    const rows = [del('const a = 1', 1), add('const a = 2', 1)];
    const { split } = alignHunk(rows);
    expect(split).toHaveLength(1);
    expect(split[0].left?.content).toBe('const a = 1');
    expect(split[0].right?.content).toBe('const a = 2');
  });

  test('aligns a block with a mid-block insertion instead of stacking', () => {
    // Four edited rows + one inserted row (the table case from the report):
    // naive index pairing would mis-pair every row after the insertion.
    const rows = [
      del('| Price | free |', 1),
      del('| Free option | yes |', 2),
      del('| Paid tier | 12 |', 3),
      add('| Price | paid |', 1),
      add('| Plan required | none |', 2), // inserted
      add('| Free option | no |', 3),
      add('| Paid tier | 100 |', 4),
    ];
    const { split } = alignHunk(rows);
    // Each removed row is paired with the added row it became; the inserted
    // "Plan required" row stands alone against a blank left cell.
    const paired = split.filter((p) => p.left && p.right);
    expect(paired.map((p) => [p.left!.content, p.right!.content])).toEqual([
      ['| Price | free |', '| Price | paid |'],
      ['| Free option | yes |', '| Free option | no |'],
      ['| Paid tier | 12 |', '| Paid tier | 100 |'],
    ]);
    const insertOnly = split.filter((p) => !p.left && p.right);
    expect(insertOnly.map((p) => p.right!.content)).toEqual(['| Plan required | none |']);
  });

  test('does not pair unrelated lines (below similarity threshold)', () => {
    const rows = [
      del('completely different removed line one', 1),
      del('another totally unrelated removed line', 2),
      add('fresh added content that shares nothing', 1),
      add('yet more brand new added text here', 2),
    ];
    const { split } = alignHunk(rows);
    // No cross pairing: all lefts blank-right, all rights blank-left.
    expect(split.every((p) => !(p.left && p.right))).toBe(true);
  });

  test('context lines fill both sides and split is order-preserving', () => {
    const rows = [
      ctx('unchanged', 1, 1),
      del('old value', 2),
      add('new value', 2),
      ctx('tail', 3, 3),
    ];
    const { split } = alignHunk(rows);
    // Head ctx, one paired remove/add row, tail ctx.
    expect(split).toHaveLength(3);
    expect(split[0]).toEqual({ left: rows[0], right: rows[0] });
    expect(split[1].left?.content).toBe('old value');
    expect(split[1].right?.content).toBe('new value');
    expect(split[2]).toEqual({ left: rows[3], right: rows[3] });
  });

  test('pure insertion region has no removes to pair', () => {
    const rows = [ctx('a', 1, 1), add('b', 2), add('c', 3)];
    const { unified, split } = alignHunk(rows);
    expect(unified.map((r) => r.kind)).toEqual(['context', 'add', 'add']);
    expect(split.map((p) => p.left?.content ?? null)).toEqual(['a', null, null]);
    expect(split.map((p) => p.right?.content ?? null)).toEqual(['a', 'b', 'c']);
  });

  test('segments are lossless — concatenation equals the original line', () => {
    const rows = [
      del('the quick brown fox jumps', 1),
      add('the quick red fox leaps', 1),
    ];
    const { unified } = alignHunk(rows);
    expect(segText(unified[0]) || unified[0].content).toBe('the quick brown fox jumps');
    expect(segText(unified[1]) || unified[1].content).toBe('the quick red fox leaps');
  });
});
