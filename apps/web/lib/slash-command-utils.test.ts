import { describe, expect, it } from 'vitest';
import {
  applySlashCommandSelection,
  detectSlashCommand,
  slashCommandMatches,
} from './slash-command-utils';
import type { SlashCommand } from '@/lib/constants/slash-commands';

const cmd = (command: string, insert?: string): SlashCommand => ({
  command,
  description: '',
  ...(insert ? { insert } : {}),
});

describe('detectSlashCommand', () => {
  it('does not open on an empty input', () => {
    expect(detectSlashCommand('', 0)).toEqual({ active: false, query: '' });
  });

  it('opens with an empty query for a lone "/"', () => {
    expect(detectSlashCommand('/', 1)).toEqual({ active: true, query: '' });
  });

  it('filters by the command word being typed', () => {
    expect(detectSlashCommand('/rev', 4)).toEqual({ active: true, query: 'rev' });
  });

  it('keeps open while the caret is inside the word, querying the whole word', () => {
    expect(detectSlashCommand('/review fix', 4)).toEqual({ active: true, query: 'review' });
  });

  it('closes once the caret moves out into the argument', () => {
    expect(detectSlashCommand('/review fix', 11)).toEqual({ active: false, query: '' });
  });

  // Issue 1: a "/command" typed after existing draft text (start of a word)
  // must still open the menu — the old `value.startsWith("/")` check missed it.
  it('opens for a "/" that starts a word mid-draft', () => {
    expect(detectSlashCommand('fix this /rev', 13)).toEqual({ active: true, query: 'rev' });
  });

  it('ignores a "/" in the middle of a word (paths, and/or)', () => {
    expect(detectSlashCommand('src/app', 7)).toEqual({ active: false, query: '' });
    expect(detectSlashCommand('and/or', 6)).toEqual({ active: false, query: '' });
  });

  it('opens on a new line that starts with "/"', () => {
    expect(detectSlashCommand('line1\n/rev', 10)).toEqual({ active: true, query: 'rev' });
  });

  // Issue 2: the "+" → "Skills or Commands" action seeds "/ <draft>" and parks
  // the caret at 1; typing to filter must keep the menu open (the old
  // whole-remainder search term closed it immediately).
  it('opens for the "+" menu seed "/ <draft>" with the caret after the slash', () => {
    expect(detectSlashCommand('/ fix the bug', 1)).toEqual({ active: true, query: '' });
    expect(detectSlashCommand('/rev fix the bug', 4)).toEqual({ active: true, query: 'rev' });
  });
});

describe('applySlashCommandSelection', () => {
  it('inserts a command into an empty-ish "/word" with a trailing space', () => {
    expect(applySlashCommandSelection('/com', '/compact', 4)).toEqual({
      value: '/compact ',
      cursor: 9,
    });
  });

  it('turns a seeded draft into the command argument', () => {
    expect(applySlashCommandSelection('/ fix the bug', '/review', 1)).toEqual({
      value: '/review fix the bug',
      cursor: 7,
    });
  });

  it('replaces the command word in place, keeping surrounding text', () => {
    expect(applySlashCommandSelection('fix /rev now', '/review', 8)).toEqual({
      value: 'fix /review now',
      cursor: 11,
    });
  });

  it('does not double a space when one already follows the word', () => {
    expect(applySlashCommandSelection('/rev arg', '/review', 4)).toEqual({
      value: '/review arg',
      cursor: 7,
    });
  });

  it('inserts a Codex skill token verbatim', () => {
    expect(applySlashCommandSelection('/dep', '$deploy', 4)).toEqual({
      value: '$deploy ',
      cursor: 8,
    });
  });
});

describe('slashCommandMatches', () => {
  it('matches case-insensitively on the name without the leading slash', () => {
    expect(slashCommandMatches(cmd('/Review'), 'rev')).toBe(true);
    expect(slashCommandMatches(cmd('/review'), '')).toBe(true);
    expect(slashCommandMatches(cmd('/compact'), 'rev')).toBe(false);
  });
});
