import { describe, expect, test } from 'vitest';
import { computeTurnEnds, type TurnMessageEntry } from './agent-turns';

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
