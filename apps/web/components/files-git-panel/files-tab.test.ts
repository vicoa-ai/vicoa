import { describe, test, expect } from 'vitest';
import { gitStatusColor, gitStatusLetter } from './files-tab';

describe('gitStatusColor', () => {
  test('added / untracked are green', () => {
    const green = 'text-emerald-600 dark:text-emerald-400';
    expect(gitStatusColor('A')).toBe(green);
    expect(gitStatusColor('??')).toBe(green);
  });

  test('modified / typechange are amber', () => {
    const amber = 'text-amber-600 dark:text-amber-400';
    expect(gitStatusColor('M')).toBe(amber);
    expect(gitStatusColor('T')).toBe(amber);
  });

  test('deleted is red, rename/copy is sky', () => {
    expect(gitStatusColor('D')).toBe('text-red-600 dark:text-red-400');
    expect(gitStatusColor('R')).toBe('text-sky-600 dark:text-sky-400');
    expect(gitStatusColor('C')).toBe('text-sky-600 dark:text-sky-400');
  });

  test('unknown / undefined is uncolored', () => {
    expect(gitStatusColor(undefined)).toBe('');
    expect(gitStatusColor('X')).toBe('');
  });
});

describe('gitStatusLetter', () => {
  test('untracked renders as U; others keep their first letter', () => {
    expect(gitStatusLetter('??')).toBe('U');
    expect(gitStatusLetter('M')).toBe('M');
    expect(gitStatusLetter('A')).toBe('A');
    expect(gitStatusLetter('D')).toBe('D');
  });
});
