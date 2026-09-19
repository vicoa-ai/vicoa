import { describe, expect, test } from 'vitest';
import { computeTurnEnds, groupTurns, type TurnMessageEntry } from './agent-turns';

const user = (id: string, text = 'ask'): TurnMessageEntry => ({ id, kind: 'user', text });
const agent = (id: string, text: string): TurnMessageEntry => ({ id, kind: 'agent', text });
const other = (id: string): TurnMessageEntry => ({ id, kind: 'other', text: 'Using tool: Read' });

describe('computeTurnEnds', () => {
  test('only the last agent message of a run anchors the footer', () => {
    const ends = computeTurnEnds([user('u1'), agent('a1', 'one'), agent('a2', 'two')]);
    expect([...ends.keys()]).toEqual(['a2']);
    expect(ends.get('a2')).toBe('one\n\ntwo');
  });

  test('a user message closes the turn, opening a new one', () => {
    const ends = computeTurnEnds([
      user('u1'),
      agent('a1', 'one'),
      user('u2'),
      agent('a2', 'two'),
      agent('a3', 'three'),
    ]);
    expect([...ends.keys()]).toEqual(['a1', 'a3']);
    expect(ends.get('a1')).toBe('one');
    expect(ends.get('a3')).toBe('two\n\nthree');
  });

  test('tool runs and reasoning stay inside the turn without anchoring it', () => {
    const ends = computeTurnEnds([
      user('u1'),
      agent('a1', 'plan'),
      other('t1'),
      agent('a2', 'done'),
      other('t2'),
    ]);
    expect([...ends.keys()]).toEqual(['a2']);
    expect(ends.get('a2')).toBe('plan\n\ndone');
  });

  test('empty agent messages drop out of the copied text', () => {
    const ends = computeTurnEnds([agent('a1', '  '), agent('a2', 'real')]);
    expect(ends.get('a2')).toBe('real');
  });

  test('no agent messages means no footers', () => {
    expect(computeTurnEnds([user('u1'), user('u2')]).size).toBe(0);
  });
});

describe('groupTurns', () => {
  test('each user entry opens a turn holding everything agent-side until the next', () => {
    const turns = groupTurns([user('u1'), agent('a1', 'one'), other('t1'), user('u2'), user('u3'), agent('a2', 'two')]);
    expect(turns.map((t) => [t.user?.id ?? null, t.entries.map((e) => e.id)])).toEqual([
      ['u1', ['a1', 't1']],
      ['u2', []],
      ['u3', ['a2']],
    ]);
  });

  test('a leading agent run gets a turn with no user', () => {
    const turns = groupTurns([agent('a1', 'hi'), user('u1'), agent('a2', 'two')]);
    expect(turns.map((t) => [t.user?.id ?? null, t.entries.map((e) => e.id)])).toEqual([
      [null, ['a1']],
      ['u1', ['a2']],
    ]);
  });
});
