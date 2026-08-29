import { describe, expect, it } from 'vitest';
import type { MessageResponse } from '@/lib/backend-api';
import { groupSubagents, parseSubagentPayload } from './subagent-grouping';

const base: MessageResponse = {
  id: 'x',
  content: '',
  sender_type: 'agent',
  created_at: '2026-01-01T00:00:00.000Z',
  requires_user_input: false,
  message_metadata: null,
};

const plain = (id: string, content = `content-${id}`): MessageResponse => ({
  ...base,
  id,
  content,
});

const subagentMsg = (
  id: string,
  toolUseId: string,
  opts: { subagentType?: string; description?: string; content?: string } = {},
): MessageResponse => ({
  ...base,
  id,
  content: opts.content ?? `content-${id}`,
  message_metadata: {
    subagent: {
      tool_use_id: toolUseId,
      subagent_type: opts.subagentType ?? 'explore',
      description: opts.description ?? 'Map the codebase',
      role: 'step',
    },
  },
});

describe('parseSubagentPayload', () => {
  it('reads a well-formed payload', () => {
    const msg = subagentMsg('m1', 'task-1', { subagentType: 'explore', description: 'Find X' });
    expect(parseSubagentPayload(msg)).toEqual({
      toolUseId: 'task-1',
      subagentType: 'explore',
      description: 'Find X',
    });
  });

  it('returns null when there is no subagent metadata', () => {
    expect(parseSubagentPayload(plain('m1'))).toBeNull();
    expect(parseSubagentPayload({ ...base, id: 'm2', message_metadata: {} })).toBeNull();
    expect(
      parseSubagentPayload({ ...base, id: 'm3', message_metadata: { subagent: { tool_use_id: '' } } }),
    ).toBeNull();
  });

  it('defaults subagent_type to "agent" and description to "" when missing', () => {
    const msg: MessageResponse = {
      ...base,
      id: 'm1',
      message_metadata: { subagent: { tool_use_id: 'task-1' } },
    };
    expect(parseSubagentPayload(msg)).toEqual({
      toolUseId: 'task-1',
      subagentType: 'agent',
      description: '',
    });
  });
});

describe('groupSubagents', () => {
  it('groups a single sub-agent under one item, anchored at the first message', () => {
    const messages = [
      plain('m1'),
      subagentMsg('m2', 'task-1'),
      subagentMsg('m3', 'task-1'),
      subagentMsg('m4', 'task-1'),
      plain('m5'),
    ];

    const items = groupSubagents(messages);

    expect(items).toHaveLength(3);
    expect(items[0]).toEqual({ type: 'message', message: messages[0], key: 'm1' });
    expect(items[1]).toMatchObject({
      type: 'subagent-group',
      subagentType: 'explore',
      description: 'Map the codebase',
      key: 'subagent-task-1',
    });
    if (items[1].type === 'subagent-group') {
      expect(items[1].messages.map((m) => m.id)).toEqual(['m2', 'm3', 'm4']);
    }
    expect(items[2]).toEqual({ type: 'message', message: messages[4], key: 'm5' });
  });

  it('forms two separate groups for two interleaved sub-agents, each anchored at its first occurrence, leaving other messages in place', () => {
    // A, B, A, B pattern with a plain message threaded in between/around.
    const messages = [
      plain('u1'), // user kicks things off
      subagentMsg('a1', 'task-A', { subagentType: 'explore', description: 'Explore A' }),
      subagentMsg('b1', 'task-B', { subagentType: 'plan', description: 'Plan B' }),
      plain('mid'), // an unrelated message threaded between the two runs
      subagentMsg('a2', 'task-A'),
      subagentMsg('b2', 'task-B'),
      plain('u2'),
    ];

    const items = groupSubagents(messages);

    // Order: u1, [group A anchored at a1], [group B anchored at b1], mid, u2
    expect(items.map((i) => i.key)).toEqual([
      'u1',
      'subagent-task-A',
      'subagent-task-B',
      'mid',
      'u2',
    ]);

    const groupA = items.find((i) => i.key === 'subagent-task-A');
    const groupB = items.find((i) => i.key === 'subagent-task-B');
    expect(groupA?.type).toBe('subagent-group');
    expect(groupB?.type).toBe('subagent-group');
    if (groupA?.type === 'subagent-group') {
      expect(groupA.messages.map((m) => m.id)).toEqual(['a1', 'a2']);
      expect(groupA.subagentType).toBe('explore');
    }
    if (groupB?.type === 'subagent-group') {
      expect(groupB.messages.map((m) => m.id)).toEqual(['b1', 'b2']);
      expect(groupB.subagentType).toBe('plan');
    }
  });

  it('leaves messages with no subagent metadata untouched, in order', () => {
    const messages = [plain('m1'), plain('m2'), plain('m3')];
    const items = groupSubagents(messages);
    expect(items).toEqual([
      { type: 'message', message: messages[0], key: 'm1' },
      { type: 'message', message: messages[1], key: 'm2' },
      { type: 'message', message: messages[2], key: 'm3' },
    ]);
  });
});
