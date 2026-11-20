import { describe, expect, it } from 'vitest';

import {
  activeMentions,
  agentMentionMarkdown,
  agentsToWake,
  isNoteComment,
  mentionRanges,
  mentionedAgentIds,
  parseAgentMentionHref,
  parseUserMentionHref,
  serializeMentions,
  stripNotePrefix,
} from './task-mentions';

const A = '11111111-1111-4111-8111-111111111111';
const B = '22222222-2222-4222-8222-222222222222';
const top = { inThread: false, threadAgentId: null, assigneeAgentId: A };

describe('agent mentions', () => {
  it('writes and reads back the picker link', () => {
    const md = agentMentionMarkdown('review[er]', A);
    expect(md).toBe(`[@reviewer](vicoa://agent/${A})`);
    expect(mentionedAgentIds(`hey ${md}`)).toEqual([A]);
    expect(parseAgentMentionHref(`vicoa://agent/${A}`)).toBe(A);
    expect(parseAgentMentionHref('https://example.com')).toBeNull();
  });

  it('lists each mentioned agent once, in order', () => {
    const body = `[@B](vicoa://agent/${B}) [@A](vicoa://agent/${A}) [@B](vicoa://agent/${B})`;
    expect(mentionedAgentIds(body)).toEqual([B, A]);
  });

  it('ignores a typed @name', () => {
    expect(mentionedAgentIds('@reviewer please look')).toEqual([]);
  });
});

describe('agentsToWake (mirrors the server routing)', () => {
  it('a note wakes nobody', () => {
    expect(agentsToWake('/note thinking', top)).toEqual([]);
    expect(isNoteComment('  /NOTE x')).toBe(true);
    expect(isNoteComment('/note: later')).toBe(true);
    expect(isNoteComment('/notebook is open')).toBe(false);
  });

  it('a mention wakes only the mentioned agent', () => {
    expect(agentsToWake(`[@B](vicoa://agent/${B}) review?`, top)).toEqual([B]);
  });

  it('a top-level comment wakes the agent assignee', () => {
    expect(agentsToWake('also check mobile', top)).toEqual([A]);
    expect(agentsToWake('x', { ...top, assigneeAgentId: null })).toEqual([]);
  });

  it('a reply wakes the agent in the thread, never the assignee', () => {
    const thread = { inThread: true, threadAgentId: B, assigneeAgentId: A };
    expect(agentsToWake('A', thread)).toEqual([B]);
    expect(agentsToWake('A', { ...thread, threadAgentId: null })).toEqual([]);
  });

  it('on a Done or Cancelled task only a mention wakes anyone', () => {
    const closed = { ...top, taskClosed: true };
    expect(agentsToWake('also check mobile', closed)).toEqual([]);
    expect(
      agentsToWake('A', { inThread: true, threadAgentId: B, assigneeAgentId: null, taskClosed: true }),
    ).toEqual([]);
    expect(agentsToWake(`[@B](vicoa://agent/${B}) review?`, closed)).toEqual([B]);
  });
});

describe('composer mentions', () => {
  const bot = { id: '11111111-1111-1111-1111-111111111111', name: 'bot' };
  const bot2 = { id: '22222222-2222-2222-2222-222222222222', name: 'bot2' };
  const spaced = { id: '33333333-3333-3333-3333-333333333333', name: 'Claude Haiku' };

  it('finds picked names on word boundaries, longest first', () => {
    const text = 'hi @bot2 and @bot, not email@bot or @botty';
    expect(mentionRanges(text, [bot, bot2]).map((r) => [text.slice(r.start, r.end), r.id])).toEqual([
      ['@bot2', bot2.id],
      ['@bot', bot.id],
    ]);
  });

  it('handles names with spaces', () => {
    const text = 'ask @Claude Haiku please';
    expect(mentionRanges(text, [spaced]).map((r) => text.slice(r.start, r.end))).toEqual([
      '@Claude Haiku',
    ]);
  });

  it('drops a pick whose name was edited away', () => {
    expect(activeMentions([bot, bot2], 'only @bot2 now')).toEqual([bot2]);
  });

  it('serializes picked names into mention links on send', () => {
    expect(serializeMentions('@bot can you look? cc @bot2.', [bot, bot2])).toBe(
      `[@bot](vicoa://agent/${bot.id}) can you look? cc [@bot2](vicoa://agent/${bot2.id}).`,
    );
    expect(serializeMentions('no picks @bot', [])).toBe('no picks @bot');
  });

  it('strips the /note prefix for display', () => {
    expect(stripNotePrefix('/note remember the edge case')).toBe('remember the edge case');
    expect(stripNotePrefix('  /note: done')).toBe('done');
  });
});

describe('questions and people', () => {
  const C = '33333333-3333-4333-8333-333333333333';
  const askers = [{ id: B, name: 'Codex' }];

  it('an answer wakes the agent that asked, wherever it is written', () => {
    expect(
      agentsToWake('B', { inThread: true, threadAgentId: null, assigneeAgentId: null, askers }),
    ).toEqual([B]);
    expect(agentsToWake('B', { inThread: true, threadAgentId: A, assigneeAgentId: null, askers })).toEqual([
      B,
      A,
    ]);
  });

  it('a top-level answer does not also wake the assignee', () => {
    expect(agentsToWake('B', { ...top, askers })).toEqual([B]);
    expect(agentsToWake(`B, [@A](vicoa://agent/${A}) too`, { ...top, askers })).toEqual([B, A]);
  });

  it('alongside an explicit mention', () => {
    expect(agentsToWake(`[@C](vicoa://agent/${C}) help`, { ...top, askers })).toEqual([B, C]);
  });

  it('a note answers nobody', () => {
    expect(agentsToWake('/note later', { ...top, askers })).toEqual([]);
  });

  it('a person mention wakes no agent', () => {
    const body = `[@Ada](vicoa://user/${C}) look`;
    expect(mentionedAgentIds(body)).toEqual([]);
    expect(agentsToWake(body, { inThread: false, threadAgentId: null, assigneeAgentId: null })).toEqual(
      [],
    );
    expect(parseUserMentionHref(`vicoa://user/${C}`)).toBe(C);
    expect(parseAgentMentionHref(`vicoa://user/${C}`)).toBeNull();
  });

  it('a picked person is sent as a user link', () => {
    const picks = [
      { id: C, name: 'Ada', kind: 'user' as const },
      { id: A, name: 'bot', kind: 'agent' as const },
    ];
    expect(serializeMentions('@Ada and @bot', picks)).toBe(
      `[@Ada](vicoa://user/${C}) and [@bot](vicoa://agent/${A})`,
    );
  });
});
