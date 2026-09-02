import { describe, expect, it } from 'vitest';
import type { MessageResponse } from '@/lib/backend-api';
import { parseThinkingPayload } from './thinking-card';

const base: MessageResponse = {
  id: 'x',
  content: 'reasoning text',
  sender_type: 'agent',
  created_at: '2026-01-01T00:00:00.000Z',
  requires_user_input: false,
  message_metadata: null,
};

const withMetadata = (metadata: MessageResponse['message_metadata']): MessageResponse => ({
  ...base,
  message_metadata: metadata,
});

describe('parseThinkingPayload', () => {
  it('reads a well-formed thinking payload', () => {
    expect(parseThinkingPayload(withMetadata({ thinking: { source: 'claude' } }))).toEqual({
      source: 'claude',
    });
    expect(parseThinkingPayload(withMetadata({ thinking: { source: 'codex' } }))).toEqual({
      source: 'codex',
    });
  });

  it('defaults source to empty string when missing/non-string', () => {
    expect(parseThinkingPayload(withMetadata({ thinking: {} }))).toEqual({ source: '' });
    expect(parseThinkingPayload(withMetadata({ thinking: { source: 42 } }))).toEqual({ source: '' });
  });

  it('returns null when there is no thinking metadata', () => {
    expect(parseThinkingPayload(base)).toBeNull();
    expect(parseThinkingPayload(withMetadata({ subagent: { tool_use_id: 't' } }))).toBeNull();
    expect(parseThinkingPayload(withMetadata({ thinking: null } as never))).toBeNull();
  });
});
