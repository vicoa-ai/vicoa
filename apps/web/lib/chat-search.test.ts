import { describe, expect, test } from 'vitest';
import { getChatItemSearchText, getMessageSearchText } from './chat-search';
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

const readTool = message({
  id: 't1',
  content: 'Using tool: **Read** - `app/dashboard/page.tsx`\nexport const SECRET_TOKEN = 1;',
});
const bashTool = message({
  id: 't2',
  content: 'Using tool: **Bash** - `pnpm test`\n```\n2 tests failed in worktree-selection\n```',
});

describe('getMessageSearchText', () => {
  test('includes the detail a collapsed tool use hides', () => {
    const text = getMessageSearchText(readTool, 'claude');
    expect(text).toContain('SECRET_TOKEN');
    expect(text).toContain('app/dashboard/page.tsx');
    expect(text).toContain('Read');
  });

  test('plain prose is unchanged', () => {
    expect(getMessageSearchText(message({ id: 'm1', content: 'Here is the plan.' }), 'claude')).toBe(
      'Here is the plan.',
    );
  });

  test('unparseable tool-ish content falls back to the raw text', () => {
    const odd = message({ id: 'm2', content: '🔧 nothing parseable here' });
    expect(getMessageSearchText(odd, 'claude')).toBe('🔧 nothing parseable here');
  });
});

describe('getChatItemSearchText', () => {
  test('a collapsed tool group is searched across all of its tool uses', () => {
    const text = getChatItemSearchText({ type: 'tool-group', messages: [readTool, bashTool] }, 'claude');
    expect(text).toContain('SECRET_TOKEN');
    expect(text).toContain('2 tests failed in worktree-selection');
  });

  test('a sub-agent group covers its header and its children', () => {
    const text = getChatItemSearchText(
      {
        type: 'subagent-group',
        subagentType: 'Explore',
        description: 'find the search code',
        messages: [readTool, message({ id: 'c1', content: 'found it in chat-search.ts' })],
      },
      'claude',
    );
    expect(text).toContain('Explore');
    expect(text).toContain('find the search code');
    expect(text).toContain('SECRET_TOKEN');
    expect(text).toContain('found it in chat-search.ts');
  });

  test('separators and the thinking indicator carry nothing', () => {
    expect(getChatItemSearchText({ type: 'separator' }, 'claude')).toBe('');
    expect(getChatItemSearchText({ type: 'thinking' }, 'claude')).toBe('');
  });
});
