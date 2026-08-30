import { describe, expect, it } from 'vitest';
import type { MessageResponse } from '@/lib/backend-api';
import { parseQueuePayload } from './queue-status';

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
