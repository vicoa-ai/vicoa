import { describe, test, expect } from 'vitest';
import { hunkToRows } from './diff-lines';
import type { DiffHunk } from './rpc';

const ctx = (content: string) => ({ type: 'context' as const, content });
const add = (content: string) => ({ type: 'add' as const, content });
const del = (content: string) => ({ type: 'remove' as const, content });

describe('hunkToRows', () => {
  test('numbers context lines on both sides', () => {
    const hunk: DiffHunk = {
      header: '@@ -10,3 +10,3 @@',
      old_start: 10,
      old_count: 3,
      new_start: 10,
      new_count: 3,
      lines: [ctx('a'), ctx('b'), ctx('c')],
    };
    expect(hunkToRows(hunk)).toEqual([
      { kind: 'context', content: 'a', oldNo: 10, newNo: 10 },
      { kind: 'context', content: 'b', oldNo: 11, newNo: 11 },
      { kind: 'context', content: 'c', oldNo: 12, newNo: 12 },
    ]);
  });

  test('add advances only the new side number', () => {
    const hunk: DiffHunk = {
      header: '@@ -1,1 +1,2 @@',
      old_start: 1,
      old_count: 1,
      new_start: 1,
      new_count: 2,
      lines: [ctx('a'), add('b')],
    };
    expect(hunkToRows(hunk)).toEqual([
      { kind: 'context', content: 'a', oldNo: 1, newNo: 1 },
      { kind: 'add', content: 'b', oldNo: null, newNo: 2 },
    ]);
  });

  test('remove advances only the old side number', () => {
    const hunk: DiffHunk = {
      header: '@@ -1,2 +1,1 @@',
      old_start: 1,
      old_count: 2,
      new_start: 1,
      new_count: 1,
      lines: [ctx('a'), del('b')],
    };
    expect(hunkToRows(hunk)).toEqual([
      { kind: 'context', content: 'a', oldNo: 1, newNo: 1 },
      { kind: 'remove', content: 'b', oldNo: 2, newNo: null },
    ]);
  });

  test('add followed by remove keeps both sides numbered independently', () => {
    const hunk: DiffHunk = {
      header: '@@ -1,2 +1,2 @@',
      old_start: 1,
      old_count: 2,
      new_start: 1,
      new_count: 2,
      lines: [del('old'), add('new')],
    };
    expect(hunkToRows(hunk)).toEqual([
      { kind: 'remove', content: 'old', oldNo: 1, newNo: null },
      { kind: 'add', content: 'new', oldNo: null, newNo: 1 },
    ]);
  });
});
