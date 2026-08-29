import { describe, test, expect } from 'vitest';
import { ancestorPaths, flattenTree, joinPath, parentPath } from './tree';
import type { FileEntry } from './rpc';

const dir = (name: string): FileEntry => ({ name, type: 'dir' });
const file = (name: string, size = 0): FileEntry => ({ name, type: 'file', size });

describe('ancestorPaths', () => {
  test('returns root-first directory prefixes', () => {
    expect(ancestorPaths('a/b/c')).toEqual(['a', 'a/b', 'a/b/c']);
  });
  test('single segment yields one prefix', () => {
    expect(ancestorPaths('a')).toEqual(['a']);
  });
  test('empty string yields no prefixes', () => {
    expect(ancestorPaths('')).toEqual([]);
  });
  test('ignores empty segments from stray slashes', () => {
    expect(ancestorPaths('a//b/')).toEqual(['a', 'a/b']);
  });
});

describe('joinPath / parentPath', () => {
  test('joins root + child without leading slash', () => {
    expect(joinPath('', 'src')).toBe('src');
    expect(joinPath('src', 'lib')).toBe('src/lib');
  });

  test('parentPath returns the parent or empty string for root children', () => {
    expect(parentPath('src')).toBe('');
    expect(parentPath('src/lib')).toBe('src');
    expect(parentPath('src/lib/foo.ts')).toBe('src/lib');
  });
});

describe('flattenTree', () => {
  test('only the root is flattened when nothing is expanded', () => {
    const listings = new Map<string, FileEntry[]>([
      ['', [dir('src'), file('README.md')]],
    ]);
    const rows = flattenTree(listings, new Set());
    expect(rows).toEqual([
      { path: 'src', name: 'src', type: 'dir', depth: 0, expanded: false, loading: false },
      { path: 'README.md', name: 'README.md', type: 'file', depth: 0, size: 0 },
    ]);
  });

  test('expanded directory expands children inline at correct depth', () => {
    const listings = new Map<string, FileEntry[]>([
      ['', [dir('src')]],
      ['src', [dir('components'), file('index.ts', 100)]],
      ['src/components', [file('button.tsx', 50)]],
    ]);
    const rows = flattenTree(listings, new Set(['src', 'src/components']));
    expect(rows.map((r) => `${r.depth}:${'path' in r ? r.path : ''}`)).toEqual([
      '0:src',
      '1:src/components',
      '2:src/components/button.tsx',
      '1:src/index.ts',
    ]);
  });

  test('expanded directory that has not loaded yet shows as loading', () => {
    const listings = new Map<string, FileEntry[]>([
      ['', [dir('src')]],
    ]);
    const rows = flattenTree(listings, new Set(['src']));
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({ path: 'src', expanded: true, loading: true });
  });

  test('null listing means in-flight: parent shows expanded + loading', () => {
    const listings = new Map<string, FileEntry[] | null>([
      ['', [dir('src')]],
      ['src', null],
    ]);
    const rows = flattenTree(listings, new Set(['src']));
    expect(rows[0]).toMatchObject({ expanded: true, loading: true });
  });

  test('empty root listing returns no rows', () => {
    const rows = flattenTree(new Map([['', []]]), new Set());
    expect(rows).toEqual([]);
  });
});
