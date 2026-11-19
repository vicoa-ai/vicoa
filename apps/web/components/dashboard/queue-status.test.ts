import { describe, expect, it } from 'vitest';
import type { MessageResponse } from '@/lib/backend-api';
import { isPendingQueueStatus, parseQueuePayload, queueDrainedBefore } from './queue-status';

function msg(message_metadata: Record<string, unknown> | null | undefined): MessageResponse {
  return {
    id: 'm1',
    content: 'hello',
    sender_type: 'user',
    created_at: '2026-07-10T00:00:00Z',
    requires_user_input: false,
    message_metadata,
  };
}

describe('parseQueuePayload', () => {
  it('parses a queued status', () => {
    expect(parseQueuePayload(msg({ queue: { status: 'queued' } }))).toEqual({ status: 'queued' });
  });

  it('parses a consumed status', () => {
    expect(parseQueuePayload(msg({ queue: { status: 'consumed', consumed_at: '2026-07-10T00:01:00Z' } })))
      .toEqual({ status: 'consumed' });
  });

  it('parses a steer status (Steer pressed, daemon delivering)', () => {
    expect(parseQueuePayload(msg({ queue: { status: 'steer', steer_requested_at: '2026-07-10T00:01:00Z' } })))
      .toEqual({ status: 'steer' });
  });

  it('carries the steered flag on a consumed message', () => {
    expect(parseQueuePayload(msg({ queue: { status: 'consumed', steered: true } })))
      .toEqual({ status: 'consumed', steered: true });
  });

  it('ignores a non-boolean steered value', () => {
    expect(parseQueuePayload(msg({ queue: { status: 'consumed', steered: 'yes' } })))
      .toEqual({ status: 'consumed' });
  });

  it('parses a cancelled status', () => {
    expect(parseQueuePayload(msg({ queue: { status: 'cancelled', cancelled_at: '2026-07-10T00:02:00Z' } })))
      .toEqual({ status: 'cancelled' });
  });

  it('returns null when message_metadata is absent', () => {
    expect(parseQueuePayload(msg(undefined))).toBeNull();
  });

  it('returns null when message_metadata is null', () => {
    expect(parseQueuePayload(msg(null))).toBeNull();
  });

  it('returns null when queue key is missing', () => {
    expect(parseQueuePayload(msg({ ask_user_question: {} }))).toBeNull();
  });

  it('returns null when queue is not an object', () => {
    expect(parseQueuePayload(msg({ queue: 'queued' }))).toBeNull();
  });

  it('returns null when status is an unrecognized value', () => {
    expect(parseQueuePayload(msg({ queue: { status: 'bogus' } }))).toBeNull();
  });

  it('returns null when status is missing from queue', () => {
    expect(parseQueuePayload(msg({ queue: {} }))).toBeNull();
  });
});

describe('isPendingQueueStatus', () => {
  it('treats queued and steer as still in the bar', () => {
    expect(isPendingQueueStatus('queued')).toBe(true);
    expect(isPendingQueueStatus('steer')).toBe(true);
  });

  it('treats terminal states and no status as not pending', () => {
    expect(isPendingQueueStatus('consumed')).toBe(false);
    expect(isPendingQueueStatus('cancelled')).toBe(false);
    expect(isPendingQueueStatus(undefined)).toBe(false);
  });
});

describe('queueDrainedBefore', () => {
  const isUser = (m: MessageResponse) => m.sender_type === 'user';
  function row(
    id: string,
    minute: number,
    queue: Record<string, unknown> | null,
    sender_type = 'user',
  ): MessageResponse {
    return {
      id,
      content: id,
      sender_type,
      created_at: `2026-07-10T00:0${minute}:00Z`,
      requires_user_input: false,
      message_metadata: queue ? { queue } : null,
    };
  }

  it('is the newest consumed user message', () => {
    const messages = [
      row('a', 1, { status: 'consumed', consumed_at: '2026-07-10T00:05:00Z' }),
      row('b', 2, { status: 'consumed', consumed_at: '2026-07-10T00:06:00Z' }),
      row('c', 3, { status: 'queued' }),
    ];
    expect(queueDrainedBefore(messages, isUser)).toBe('2026-07-10T00:02:00Z');
  });

  it('is null while nothing has been consumed', () => {
    expect(queueDrainedBefore([row('a', 1, { status: 'queued' }), row('b', 2, null)], isUser)).toBeNull();
  });

  it('skips a steered message, so the ones queued ahead of it stay in the bar', () => {
    // Three queued, the second steered into the running turn: the first is
    // still waiting for the turn to end and must not count as drained.
    const messages = [
      row('first', 1, { status: 'queued' }),
      row('second', 2, { status: 'consumed', steered: true, consumed_at: '2026-07-10T00:04:00Z' }),
      row('third', 3, { status: 'queued' }),
    ];
    expect(queueDrainedBefore(messages, isUser)).toBeNull();
  });

  it('still counts an in-order consume made after a steer', () => {
    const messages = [
      row('first', 1, { status: 'consumed', consumed_at: '2026-07-10T00:06:00Z' }),
      row('second', 2, { status: 'consumed', steered: true, consumed_at: '2026-07-10T00:04:00Z' }),
      row('third', 3, { status: 'queued' }),
    ];
    expect(queueDrainedBefore(messages, isUser)).toBe('2026-07-10T00:01:00Z');
  });

  it('ignores agent messages and messages still being steered', () => {
    const messages = [
      row('agent', 4, { status: 'consumed' }, 'agent'),
      row('steering', 3, { status: 'steer' }),
      row('cancelled', 2, { status: 'cancelled' }),
    ];
    expect(queueDrainedBefore(messages, isUser)).toBeNull();
  });
});
