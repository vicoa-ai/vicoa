import { describe, expect, it } from 'vitest';
import type { MessageResponse } from '@/lib/backend-api';
import { groupMessagesByDate } from '@/lib/message-grouping';
import {
  buildTranscriptItems,
  computeTranscriptTurns,
  hasTranscriptMessages,
  orderTranscriptMessages,
} from './session-transcript';

const base: MessageResponse = {
  id: 'x',
  content: '',
  sender_type: 'agent',
  created_at: '2026-01-01T00:00:00.000Z',
  requires_user_input: false,
  message_metadata: null,
};

let clock = 0;
const at = () => new Date(Date.UTC(2026, 0, 1, 0, 0, ++clock)).toISOString();

const agent = (id: string, content: string, meta: MessageResponse['message_metadata'] = null): MessageResponse => ({
  ...base,
  id,
  content,
  created_at: at(),
  message_metadata: meta,
});
const user = (id: string, content: string, meta: MessageResponse['message_metadata'] = null): MessageResponse => ({
  ...agent(id, content, meta),
  sender_type: 'user',
});
const tool = (id: string, path: string) => agent(id, `Using tool: **Read** - \`${path}\``);

function build(messages: MessageResponse[], showThinking = false) {
  return buildTranscriptItems(groupMessagesByDate(orderTranscriptMessages(messages)), {
    agentTypeName: 'claude code',
    showThinking,
  });
}

describe('buildTranscriptItems', () => {
  it('collapses a run of tool uses into one tool-group keyed on its first message', () => {
    const items = build([user('u1', 'go'), tool('t1', '/a'), tool('t2', '/b'), agent('a1', 'done')]);
    expect(items.map((it) => it.type)).toEqual(['separator', 'message', 'tool-group', 'message']);
    const group = items[2];
    expect(group.type === 'tool-group' && group.key).toBe('tools-t1');
    expect(group.type === 'tool-group' && group.messages.map((m) => m.id)).toEqual(['t1', 't2']);
  });

  it('keeps interactive and thinking rows out of tool groups', () => {
    const items = build([
      tool('t1', '/a'),
      agent('q1', 'Using tool: AskUserQuestion', { }),
      tool('t2', '/b'),
      agent('th', 'hmm', { thinking: { text: 'hmm' } }),
      tool('t3', '/c'),
    ]);
    // q1 has no ask-user payload so it is still a tool line; the thinking
    // row splits the run.
    expect(items.map((it) => it.type)).toEqual(['separator', 'tool-group', 'message', 'tool-group']);
    expect(items[2].type === 'message' && items[2].message.id).toBe('th');
  });

  it('buckets sub-agent children into their own group before collapsing', () => {
    const child = (id: string) =>
      agent(id, `Using tool: **Grep** - \`${id}\``, {
        subagent: { tool_use_id: 'tu-1', subagent_type: 'explore', description: 'Map it', role: 'step' },
      });
    const items = build([tool('t1', '/a'), child('c1'), tool('t2', '/b'), child('c2'), agent('a1', 'ok')]);
    expect(items.map((it) => it.type)).toEqual([
      'separator',
      'tool-group',
      'subagent-group',
      'tool-group',
      'message',
    ]);
    const sub = items[2];
    expect(sub.type === 'subagent-group' && sub.messages.map((m) => m.id)).toEqual(['c1', 'c2']);
  });

  it('appends the thinking indicator only when asked, and it does not count as content', () => {
    expect(hasTranscriptMessages(build([], true))).toBe(false);
    const items = build([user('u1', 'hi')], true);
    expect(items[items.length - 1]).toEqual({ type: 'thinking', key: 'thinking' });
    expect(hasTranscriptMessages(items)).toBe(true);
  });

  it('hides control messages and the legacy waiting placeholder', () => {
    const items = build([agent('w', 'Waiting for your input...'), user('u1', 'real')]);
    expect(items.map((it) => it.type)).toEqual(['separator', 'message']);
  });
});

describe('orderTranscriptMessages', () => {
  it('drops pending and cancelled queued user rows, keeps consumed ones', () => {
    const ordered = orderTranscriptMessages([
      user('q', 'queued', { queue: { status: 'queued' } }),
      user('c', 'cancelled', { queue: { status: 'cancelled' } }),
      user('k', 'consumed', { queue: { status: 'consumed' } }),
      agent('a', 'reply'),
    ]);
    expect(ordered.map((m) => m.id)).toEqual(['k', 'a']);
  });

  it('never hides agent rows on queue metadata', () => {
    const ordered = orderTranscriptMessages([agent('a', 'x', { queue: { status: 'queued' } })]);
    expect(ordered.map((m) => m.id)).toEqual(['a']);
  });
});

describe('computeTranscriptTurns', () => {
  it('anchors copy text on the last agent message of each turn', () => {
    const items = build([user('u1', 'q'), agent('a1', 'first'), agent('a2', 'second'), user('u2', 'again'), agent('a3', 'third')]);
    const turns = computeTranscriptTurns(items);
    expect(turns.has('a1')).toBe(false);
    expect(turns.get('a2')).toContain('second');
    expect(turns.get('a3')).toContain('third');
  });
});
