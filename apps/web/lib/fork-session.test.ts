import { describe, expect, test } from 'vitest';
import { buildForkTranscript } from './fork-session';
import type { MessageResponse } from '@/lib/backend-api';

function message(over: Partial<MessageResponse> & { id: string }): MessageResponse {
  return {
    content: '',
    sender_type: 'agent',
    created_at: '2026-09-07T10:00:00',
    requires_user_input: false,
    ...over,
  };
}

const transcript: MessageResponse[] = [
  message({ id: 'm1', sender_type: 'user', content: 'add a login page' }),
  message({ id: 'm2', content: 'Using tool: **Read** - `app/page.tsx`\nfile contents here' }),
  message({ id: 'm3', content: 'Here is the plan.' }),
  message({ id: 'm4', sender_type: 'user', content: 'go ahead' }),
  message({ id: 'm5', content: 'Done.' }),
];

describe('buildForkTranscript', () => {
  test('stops at the boundary message, inclusive', () => {
    const { text, messageCount } = buildForkTranscript({
      messages: transcript,
      boundaryMessageId: 'm3',
      agentType: 'claude',
    });
    expect(text).toContain('User: add a login page');
    expect(text).toContain('Agent: Here is the plan.');
    expect(text).not.toContain('go ahead');
    expect(text).not.toContain('Done.');
    expect(messageCount).toBe(3);
  });

  test('tool uses become a single action line, header carries the source', () => {
    const { text } = buildForkTranscript({
      messages: transcript,
      boundaryMessageId: 'm5',
      agentType: 'claude',
      sourceTitle: 'Login work',
      sourceDirectory: '/Users/nick/app',
    });
    expect(text).toMatch(/^<chat-history>\n/);
    expect(text).toMatch(/<\/chat-history>$/);
    expect(text).toContain('Source session: Login work');
    expect(text).toContain('Source directory: /Users/nick/app');
    expect(text).toContain('Agent (tool): Read app/page.tsx');
  });

  test('an unknown boundary falls back to the whole timeline', () => {
    const { messageCount } = buildForkTranscript({
      messages: transcript,
      boundaryMessageId: 'gone',
      agentType: 'claude',
    });
    expect(messageCount).toBe(5);
  });

  test('thinking rows and the input placeholder are skipped', () => {
    const { text, messageCount } = buildForkTranscript({
      messages: [
        message({ id: 't1', content: 'Reasoning: pondering', message_metadata: { thinking: { source: 'claude' } } }),
        message({ id: 't2', sender_type: 'user', content: 'Waiting for your input...' }),
        message({ id: 't3', content: 'Ready.' }),
      ],
      boundaryMessageId: 't3',
      agentType: 'claude',
    });
    expect(text).not.toContain('pondering');
    expect(text).not.toContain('Waiting for your input');
    expect(messageCount).toBe(1);
  });
});
