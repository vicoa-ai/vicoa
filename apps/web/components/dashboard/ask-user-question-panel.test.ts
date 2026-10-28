import { describe, expect, it } from 'vitest';
import type { MessageResponse } from '@/lib/backend-api';
import { isGridPreview, parseAskUserQuestionPayload } from './ask-user-question-panel';

function msg(options: Array<Record<string, unknown>>): MessageResponse {
  return {
    id: 'm1',
    content: '🔧 Using tool: AskUserQuestion',
    sender_type: 'agent',
    created_at: '2026-10-28T00:00:00Z',
    requires_user_input: true,
    message_metadata: {
      ask_user_question: {
        tool_use_id: 'toolu_1',
        questions: [{ question: 'Which draft should go out?', header: 'Draft', options, multi_select: false }],
      },
    },
  };
}

describe('parseAskUserQuestionPayload', () => {
  it('keeps an option preview verbatim', () => {
    const payload = parseAskUserQuestionPayload(
      msg([
        { label: 'Short', description: 'Two bullets', preview: '## v1.9.13\n\n  - Fixes' },
        { label: 'Long', description: 'Every change' },
      ])
    );
    expect(payload?.questions[0].options).toEqual([
      { label: 'Short', description: 'Two bullets', preview: '## v1.9.13\n\n  - Fixes' },
      { label: 'Long', description: 'Every change' },
    ]);
  });

  it('drops a blank or non-string preview', () => {
    const payload = parseAskUserQuestionPayload(
      msg([
        { label: 'A', description: '', preview: '   ' },
        { label: 'B', description: '', preview: 42 },
      ])
    );
    expect(payload?.questions[0].options.map((option) => option.preview)).toEqual([undefined, undefined]);
  });
});

describe('isGridPreview', () => {
  it('keeps box drawings and markdown tables on one line per row', () => {
    expect(isGridPreview('┌──────┐\n│ Tile │\n└──────┘')).toBe(true);
    expect(isGridPreview('| Plan | Seats |\n| --- | --- |\n| Team | 48 |')).toBe(true);
  });

  it('lets prose and code wrap', () => {
    expect(isGridPreview('Lumen 2.4 makes search update as you type, and fixes exports.')).toBe(false);
    expect(isGridPreview('const total = a || b;\nif (x | y) return;')).toBe(false);
  });
});
