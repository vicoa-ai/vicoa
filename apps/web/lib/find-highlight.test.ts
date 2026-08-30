import { describe, expect, it } from 'vitest';
import { splitOnQuery } from './find-highlight';

describe('splitOnQuery', () => {
  it('returns a single non-hit segment when the query is empty', () => {
    expect(splitOnQuery('hello world', '')).toEqual([{ text: 'hello world', hit: false }]);
  });

  it('returns a single non-hit segment when there is no match', () => {
    expect(splitOnQuery('hello world', 'xyz')).toEqual([{ text: 'hello world', hit: false }]);
  });

  it('splits around a single match', () => {
    expect(splitOnQuery('a foo b', 'foo')).toEqual([
      { text: 'a ', hit: false },
      { text: 'foo', hit: true },
      { text: ' b', hit: false },
    ]);
  });

  it('matches case-insensitively but preserves original casing', () => {
    expect(splitOnQuery('The FOO and foo', 'foo')).toEqual([
      { text: 'The ', hit: false },
      { text: 'FOO', hit: true },
      { text: ' and ', hit: false },
      { text: 'foo', hit: true },
    ]);
  });

  it('handles a match at the very start and end', () => {
    expect(splitOnQuery('foofoo', 'foo')).toEqual([
      { text: 'foo', hit: true },
      { text: 'foo', hit: true },
    ]);
  });

  it('reassembles to the original text', () => {
    const text = 'Find the needle in this needle-heavy haystack';
    const joined = splitOnQuery(text, 'needle')
      .map((s) => s.text)
      .join('');
    expect(joined).toBe(text);
  });
});
