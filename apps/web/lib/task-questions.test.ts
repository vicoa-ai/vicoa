import { describe, expect, it } from 'vitest';

import type { PrincipalResponse, TaskCommentResponse, TaskQuestionResponse } from './backend-api';
import {
  askersFromComments,
  askersFromTask,
  isWaitingOn,
  waitingOnLabel,
  waitingOnPeople,
} from './task-questions';

const principal = (type: 'user' | 'agent', id: string, name: string): PrincipalResponse => ({
  type,
  id,
  name,
  avatar_image_uri: null,
  emoji: null,
  updated_at: null,
});
const person = (id: string, name: string) => principal('user', id, name);
const agent = (id: string, name: string) => principal('agent', id, name);
const NICK = person('u-nick', 'Nick');
const ADA = person('u-ada', 'Ada');
const BOT = agent('a-bot', 'haiku-bot');

const question = (addressee: PrincipalResponse, asked_by = BOT): TaskQuestionResponse => ({
  comment_id: `c-${addressee.id}`,
  addressee,
  asked_by,
  asked_at: '2026-11-18T10:00:00Z',
});

const comment = (over: Partial<TaskCommentResponse>): TaskCommentResponse => ({
  id: 'c1',
  task_id: 't1',
  parent_comment_id: null,
  author: BOT,
  agent_instance_id: null,
  body: 'A or B?',
  kind: 'comment',
  reactions: [],
  created_at: '2026-11-18T10:00:00Z',
  edited_at: null,
  deleted_at: null,
  ...over,
});

describe('waitingOnLabel', () => {
  it('names the viewer as you', () => {
    expect(waitingOnLabel([NICK], 'u-nick')).toBe('Waiting on you');
    expect(waitingOnLabel([NICK], 'u-ada')).toBe('Waiting on Nick');
  });
  it('two people, the viewer first', () => {
    expect(waitingOnLabel([ADA, NICK], 'u-nick')).toBe('Waiting on you and Ada');
    expect(waitingOnLabel([NICK, ADA], null)).toBe('Waiting on Nick and Ada');
  });
  it('a count past two, and nothing for nobody', () => {
    expect(waitingOnLabel([NICK, ADA, person('u-3', 'Lin')], 'u-nick')).toBe(
      'Waiting on 3 people',
    );
    expect(waitingOnLabel([], 'u-nick')).toBeNull();
  });
});

describe('a task waiting on people', () => {
  const task = { open_questions: [question(NICK), question(ADA), question(NICK)] };
  it('lists each person once, oldest first', () => {
    expect(waitingOnPeople(task).map((p) => p.name)).toEqual(['Nick', 'Ada']);
  });
  it('knows whether it waits on the viewer', () => {
    expect(isWaitingOn(task, 'u-nick')).toBe(true);
    expect(isWaitingOn(task, 'u-lin')).toBe(false);
    expect(isWaitingOn(task, null)).toBe(false);
    expect(isWaitingOn({}, 'u-nick')).toBe(false);
  });
  it('the agents waiting on the viewer', () => {
    expect(askersFromTask(task, 'u-nick')).toEqual([{ id: 'a-bot', name: 'haiku-bot' }]);
    expect(askersFromTask(task, 'u-lin')).toEqual([]);
  });
});

describe('askersFromComments', () => {
  it('only open questions to the viewer, by agents', () => {
    const open = comment({
      id: 'q1',
      question: { addressee: NICK, closed_at: null, closed_reason: null },
    });
    const answered = comment({
      id: 'q2',
      author: agent('a-2', 'Codex'),
      question: { addressee: NICK, closed_at: '2026-11-18T11:00:00Z', closed_reason: 'answered' },
    });
    const toAda = comment({
      id: 'q3',
      author: agent('a-3', 'Other'),
      question: { addressee: ADA, closed_at: null, closed_reason: null },
    });
    expect(askersFromComments([open, answered, toAda], 'u-nick')).toEqual([
      { id: 'a-bot', name: 'haiku-bot' },
    ]);
    expect(askersFromComments([open], null)).toEqual([]);
  });
});
