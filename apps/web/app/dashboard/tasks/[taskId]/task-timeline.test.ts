import { describe, expect, it } from 'vitest';

import { describeReactors } from './task-timeline';
import type { PrincipalResponse, TaskReactionSummary } from '@/lib/backend-api';
import type { Principal } from '@/lib/principals';

const viewer: Principal = { type: 'user', id: 'u1', name: 'test1@gmail.com' };

const person = (id: string, name: string | null): PrincipalResponse => ({
  type: 'user',
  id,
  name,
  avatar_image_uri: null,
  emoji: null,
  updated_at: null,
});

const reaction = (
  over: Partial<TaskReactionSummary> = {},
): TaskReactionSummary => ({
  emoji: '👍',
  count: 1,
  reacted: false,
  reactors: [],
  ...over,
});

describe('describeReactors', () => {
  it('names a single reactor', () => {
    expect(
      describeReactors(reaction({ reactors: [person('u2', 'Ada')] }), viewer),
    ).toBe('Ada reacted with 👍');
  });

  it('calls the signed-in user "You" and puts them first', () => {
    // Slack and GitHub both front-load you in your own reactions; seeing your
    // own display name in a list you are part of reads as someone else.
    const out = describeReactors(
      reaction({
        count: 2,
        reactors: [person('u2', 'Ada'), person('u1', null)],
      }),
      viewer,
    );
    expect(out).toBe('You and Ada reacted with 👍');
  });

  it('joins three with commas and a final "and"', () => {
    const out = describeReactors(
      reaction({
        count: 3,
        reactors: [person('u2', 'Ada'), person('u3', 'Bo'), person('u4', 'Cy')],
      }),
      viewer,
    );
    expect(out).toBe('Ada, Bo and Cy reacted with 👍');
  });

  it('collapses the reactors the server did not name', () => {
    // The list is capped server-side but `count` stays true, so the tooltip
    // must not quietly under-report how many people are on a pill.
    const out = describeReactors(
      reaction({ count: 5, reactors: [person('u2', 'Ada'), person('u3', 'Bo')] }),
      viewer,
    );
    expect(out).toBe('Ada, Bo and 3 others reacted with 👍');
  });

  it('says "1 other" when exactly one is unnamed', () => {
    const out = describeReactors(
      reaction({ count: 2, reactors: [person('u2', 'Ada')] }),
      viewer,
    );
    expect(out).toBe('Ada and 1 other reacted with 👍');
  });
});
