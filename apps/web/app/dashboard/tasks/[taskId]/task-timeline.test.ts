import { describe, expect, it } from 'vitest';

import { buildEntries, buildThreads, describeReactors } from './task-timeline';
import type {
  PrincipalResponse,
  TaskCommentResponse,
  TaskReactionSummary,
} from '@/lib/backend-api';
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

const comment = (
  id: string,
  createdAt: string,
  parent: string | null = null,
): TaskCommentResponse => ({
  id,
  task_id: 't1',
  parent_comment_id: parent,
  author: person('u1', 'Nick'),
  body: id,
  kind: 'comment',
  reactions: [],
  created_at: createdAt,
  edited_at: null,
  deleted_at: null,
});

describe('buildThreads', () => {
  it('hangs replies off their root, oldest first', () => {
    const threads = buildThreads([
      comment('root', '2026-09-01T10:00:00Z'),
      comment('r2', '2026-09-01T12:00:00Z', 'root'),
      comment('r1', '2026-09-01T11:00:00Z', 'root'),
    ]);
    expect(threads).toHaveLength(1);
    expect(threads[0].root.id).toBe('root');
    expect(threads[0].replies.map((r) => r.id)).toEqual(['r1', 'r2']);
  });

  it('orders threads by their root, not by their newest reply', () => {
    // Rule 4: a thread sits where it started, so an answer written a day later
    // stays next to the thing it answers instead of jumping to the bottom.
    const threads = buildThreads([
      comment('first', '2026-09-01T10:00:00Z'),
      comment('late-reply', '2026-09-03T10:00:00Z', 'first'),
      comment('second', '2026-09-02T10:00:00Z'),
    ]);
    expect(threads.map((t) => t.root.id)).toEqual(['first', 'second']);
  });

  it('promotes a reply whose root is missing rather than dropping it', () => {
    const threads = buildThreads([comment('orphan', '2026-09-01T10:00:00Z', 'gone')]);
    expect(threads.map((t) => t.root.id)).toEqual(['orphan']);
  });
});

const activityRow = (
  id: string,
  createdAt: string,
  details: Record<string, unknown> = {},
) => ({
  id,
  actor: person('u1', 'Nick'),
  action: 'status_changed',
  details,
  created_at: createdAt,
});

describe('buildEntries', () => {
  it('does not give a reply a timeline row of its own', () => {
    const entries = buildEntries(
      [
        comment('root', '2026-09-01T10:00:00Z'),
        comment('reply', '2026-09-01T11:00:00Z', 'root'),
      ],
      [],
      [],
    );
    expect(entries).toHaveLength(1);
    if (entries[0].kind !== 'thread') throw new Error('expected a thread entry');
    expect(entries[0].thread.replies.map((r) => r.id)).toEqual(['reply']);
  });

  it('gives each thread its own card', () => {
    // Rule 2: a thread owns its card because it owns its reply box. Merging two
    // threads into one surface would leave two reply boxes inside it.
    const entries = buildEntries(
      [
        comment('a', '2026-09-01T10:00:00Z'),
        comment('b', '2026-09-01T10:01:00Z'),
      ],
      [],
      [],
    );
    expect(entries.map((e) => e.kind)).toEqual(['thread', 'thread']);
  });

  it('keeps activity whose session is not linked to the task', () => {
    // It was bucketed against a session card that never renders, so the row —
    // a change that really happened — silently vanished from the timeline.
    const entries = buildEntries(
      [],
      [activityRow('a1', '2026-09-01T10:00:00Z', { agent_instance_id: 'gone' })],
      [],
    );
    expect(entries).toHaveLength(1);
    if (entries[0].kind !== 'activity') throw new Error('expected an activity entry');
    expect(entries[0].items.map((r) => r.id)).toEqual(['a1']);
  });

  it('still folds activity into the session that caused it', () => {
    const session = {
      id: 's1',
      started_at: '2026-09-01T09:00:00Z',
      status: 'ACTIVE',
    } as never;
    const entries = buildEntries(
      [],
      [activityRow('a1', '2026-09-01T10:00:00Z', { agent_instance_id: 's1' })],
      [session],
    );
    expect(entries).toHaveLength(1);
    if (entries[0].kind !== 'session') throw new Error('expected a session entry');
    expect(entries[0].absorbed.map((r) => r.id)).toEqual(['a1']);
  });
});
