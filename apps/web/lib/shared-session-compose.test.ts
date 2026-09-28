import { describe, expect, it } from 'vitest';
import type { AgentInstanceDetail, MessageResponse } from './backend-api';
import {
  isPendingSend,
  mergeMessages,
  senderLabeler,
  sharedComposeState,
} from './shared-session-compose';

function session(overrides: Partial<AgentInstanceDetail> = {}): AgentInstanceDetail {
  return {
    id: 's1',
    agent_type_id: 't',
    agent_type_name: 'claude code',
    name: 'Fix it',
    status: 'ACTIVE',
    started_at: '',
    ended_at: null,
    git_diff: null,
    messages: [],
    last_read_message_id: null,
    access_level: 'WRITE',
    is_owner: false,
    live_state: 'live',
    ...overrides,
  };
}

function message(overrides: Partial<MessageResponse> = {}): MessageResponse {
  return {
    id: 'm1',
    content: 'hi',
    sender_type: 'USER',
    created_at: '',
    requires_user_input: false,
    ...overrides,
  };
}

describe('sharedComposeState', () => {
  it('draws no composer below editor', () => {
    expect(sharedComposeState(session({ access_level: 'READ' }))).toBeNull();
  });

  it('lets an editor send to a live session', () => {
    expect(sharedComposeState(session())).toEqual({ canSend: true, reason: null });
  });

  it('refuses when the session is over or its agent is not running', () => {
    expect(sharedComposeState(session({ status: 'COMPLETED' }))?.canSend).toBe(false);
    const stopped = sharedComposeState(session({ live_state: 'agent_stopped' }));
    expect(stopped?.canSend).toBe(false);
    expect(stopped?.reason).toMatch(/isn't running/);
    expect(sharedComposeState(session({ live_state: 'machine_offline' }))?.canSend).toBe(false);
  });

  it('has no em dashes in its copy', () => {
    for (const s of [session({ status: 'COMPLETED' }), session({ live_state: 'agent_stopped' })]) {
      expect(sharedComposeState(s)?.reason).not.toContain('—');
    }
  });
});

describe('isPendingSend', () => {
  it('reads the queue stamp', () => {
    expect(isPendingSend(message({ message_metadata: { queue: { status: 'queued' } } }))).toBe(true);
    expect(isPendingSend(message({ message_metadata: { queue: { status: 'consumed' } } }))).toBe(false);
    expect(isPendingSend(message())).toBe(false);
  });
});

describe('senderLabeler', () => {
  const ada = message({ id: 'a', sender_user_id: 'ada', sender_user_display_name: 'Ada' });
  const bo = message({ id: 'b', sender_user_id: 'bo', sender_user_display_name: 'Bo' });
  const agent = message({ id: 'c', sender_type: 'AGENT' });

  it('stays out of a solo session', () => {
    expect(senderLabeler([ada, agent, { ...ada, id: 'a2' }], 'ada')).toBeUndefined();
  });

  it('names every writer once there are two, and the viewer as You', () => {
    const label = senderLabeler([ada, bo, agent], 'bo');
    expect(label?.(ada)).toBe('Ada');
    expect(label?.(bo)).toBe('You');
    expect(label?.(agent)).toBeNull();
  });

  it('borrows a name from the same writer when a live row lacks one', () => {
    const live = message({ id: 'b2', sender_user_id: 'bo', sender_user_display_name: null });
    expect(senderLabeler([ada, bo, live], 'ada')?.(live)).toBe('Bo');
  });

  it('falls back to a neutral name, never an address', () => {
    const nameless = message({ id: 'n', sender_user_id: 'x', sender_user_display_name: null });
    expect(senderLabeler([ada, nameless], null)?.(nameless)).toBe('Vicoa user');
  });
});

describe('mergeMessages', () => {
  const queued = message({ id: 'q', message_metadata: { queue: { status: 'queued' } } });
  const consumed = { ...queued, message_metadata: { queue: { status: 'consumed' } } };
  const reply = message({ id: 'r', sender_type: 'AGENT', content: 'done' });

  it('keeps the same array when nothing changed', () => {
    const prev = [queued];
    expect(mergeMessages(prev, [queued])).toBe(prev);
    expect(mergeMessages(prev, [])).toBe(prev);
  });

  it('refreshes a row whose queue stamp moved on, and appends new rows', () => {
    const next = mergeMessages([queued], [consumed, reply]);
    expect(next.map((m) => m.id)).toEqual(['q', 'r']);
    expect(isPendingSend(next[0])).toBe(false);
  });
});
