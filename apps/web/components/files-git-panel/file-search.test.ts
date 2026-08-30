import { describe, expect, it } from 'vitest';
import { rankFileMatches, searchFileNames } from './file-search';

const FILES = [
  'src/app.ts',
  'src/components/app-header.tsx',
  'lib/happy/index.ts',
  'docs/roadmap.md',
  'app.config.js',
];

describe('searchFileNames', () => {
  it('ranks basename prefix over basename substring over scattered path match', () => {
    expect(searchFileNames(FILES, 'app')).toEqual([
      'src/app.ts', // basename prefix, shortest
      'app.config.js', // basename prefix
      'src/components/app-header.tsx', // basename prefix, longer path
      'lib/happy/index.ts', // scattered subsequence ("h·app·y"), far lower
    ]);
  });

  it('matches non-adjacent subsequences (gaps allowed)', () => {
    // "apphead" spans the hyphen in app-header — a substring search would miss it.
    expect(searchFileNames(FILES, 'apphead')).toEqual(['src/components/app-header.tsx']);
  });

  it('is case-insensitive and trims the query', () => {
    expect(searchFileNames(FILES, '  ROADMAP ')).toEqual(['docs/roadmap.md']);
  });

  it('returns nothing when the characters are not a subsequence', () => {
    expect(searchFileNames(FILES, 'zzq')).toEqual([]);
  });

  it('returns empty for empty query and respects the cap', () => {
    expect(searchFileNames(FILES, '')).toEqual([]);
    expect(searchFileNames(FILES, 'a', 2)).toHaveLength(2);
  });
});

describe('rankFileMatches', () => {
  it('reports the matched character positions for highlighting', () => {
    const [top] = rankFileMatches(['app.config.js'], 'app');
    expect(top.positions).toEqual([0, 1, 2]);
  });

  it('anchors positions inside the basename, not an earlier path hit', () => {
    const [top] = rankFileMatches(['app/src/app.ts'], 'app');
    // Prefers the basename "app.ts" (indices 8-10) over the leading dir "app".
    expect(top.positions).toEqual([8, 9, 10]);
  });
});
