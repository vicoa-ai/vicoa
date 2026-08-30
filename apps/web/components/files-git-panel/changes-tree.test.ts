import { describe, test, expect } from 'vitest';
import { buildChangesTree } from './changes-tree';
import type { GitStatusEntry } from './rpc';

const entry = (path: string): GitStatusEntry => ({
  path,
  status: 'M',
  additions: 1,
  deletions: 0,
  content_hash: null,
});

describe('buildChangesTree', () => {
  test('groups files under their directories', () => {
    const tree = buildChangesTree([entry('a/one.ts'), entry('a/two.ts'), entry('top.ts')]);
    expect(tree.files.map((f) => f.path)).toEqual(['top.ts']);
    expect(tree.dirs).toHaveLength(1);
    expect(tree.dirs[0].name).toBe('a');
    expect(tree.dirs[0].files.map((f) => f.path)).toEqual(['a/one.ts', 'a/two.ts']);
  });

  test('compresses single-child directory chains', () => {
    const tree = buildChangesTree([entry('src/app/api/route.ts')]);
    expect(tree.dirs).toHaveLength(1);
    expect(tree.dirs[0].name).toBe('src/app/api');
    expect(tree.dirs[0].path).toBe('src/app/api');
    expect(tree.dirs[0].files.map((f) => f.path)).toEqual(['src/app/api/route.ts']);
  });

  test('stops compressing where a folder has its own files', () => {
    const tree = buildChangesTree([entry('src/index.ts'), entry('src/deep/nested/leaf.ts')]);
    expect(tree.dirs[0].name).toBe('src');
    expect(tree.dirs[0].files.map((f) => f.path)).toEqual(['src/index.ts']);
    expect(tree.dirs[0].dirs.map((d) => d.name)).toEqual(['deep/nested']);
  });

  test('root level never compresses into its only child', () => {
    const tree = buildChangesTree([entry('only/file.ts')]);
    expect(tree.name).toBe('');
    expect(tree.path).toBe('');
    expect(tree.dirs[0].name).toBe('only');
  });

  test('sorts sibling folders alphabetically, keeps file order', () => {
    const tree = buildChangesTree([
      entry('zeta/z.ts'),
      entry('alpha/b.ts'),
      entry('alpha/a.ts'),
    ]);
    expect(tree.dirs.map((d) => d.name)).toEqual(['alpha', 'zeta']);
    expect(tree.dirs[0].files.map((f) => f.path)).toEqual(['alpha/b.ts', 'alpha/a.ts']);
  });

  test('trailing-slash entries stay leaf rows under their parent', () => {
    const tree = buildChangesTree([entry('vendor/embedded/')]);
    expect(tree.dirs[0].name).toBe('vendor');
    expect(tree.dirs[0].files.map((f) => f.path)).toEqual(['vendor/embedded/']);
  });
});
