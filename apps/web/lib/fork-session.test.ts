import { describe, expect, test } from 'vitest';
import {
  buildForkTranscript,
  extractEditedPaths,
  MAX_EDITED_PATHS,
  MAX_ENTRY_CHARS,
  MAX_TOTAL_CHARS,
} from './fork-session';
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

const user = (id: string, content: string) => message({ id, sender_type: 'user', content });
const agent = (id: string, content: string) => message({ id, content });

const transcript: MessageResponse[] = [
  user('m1', 'add a login page'),
  agent('m2', 'Using tool: **Read** - `app/page.tsx`\nfile contents here'),
  agent('m3', 'Here is the plan.'),
  user('m4', 'go ahead'),
  agent('m5', 'Done.'),
];

/** The body between the header's blank line and the closing tag. */
function bodyOf(text: string): string {
  return text.slice(text.indexOf('\n\n') + 2, text.lastIndexOf('\n</chat-history>'));
}

describe('buildForkTranscript', () => {
  test('stops at the boundary message, inclusive', () => {
    const { text, messageCount, omittedCount } = buildForkTranscript({
      messages: transcript,
      boundaryMessageId: 'm3',
      agentType: 'claude',
    });
    expect(text).toContain('User: add a login page');
    expect(text).toContain('Agent: Here is the plan.');
    expect(text).not.toContain('go ahead');
    expect(text).not.toContain('Done.');
    expect(messageCount).toBe(2);
    expect(omittedCount).toBe(0);
  });

  test('header carries the source and the tool-output caveat; tool rows leave no trace', () => {
    const { text } = buildForkTranscript({
      messages: transcript,
      boundaryMessageId: 'm5',
      agentType: 'claude',
      sourceTitle: 'Login work',
      sourceDirectory: '/Users/nick/app',
    });
    expect(text).toMatch(/^<chat-history>\n/);
    expect(text).toMatch(/<\/chat-history>$/);
    expect(text).toContain('Tool outputs are not included; re-read any file you need.');
    expect(text).toContain('Source session: Login work');
    expect(text).toContain('Source directory: /Users/nick/app');
    expect(text).not.toContain('Read');
    expect(text).not.toContain('app/page.tsx');
    expect(text).not.toContain('(tool)');
  });

  test('an unknown boundary falls back to the whole timeline', () => {
    const { messageCount } = buildForkTranscript({
      messages: transcript,
      boundaryMessageId: 'gone',
      agentType: 'claude',
    });
    expect(messageCount).toBe(4);
  });

  test('thinking rows and the input placeholder are skipped', () => {
    const { text, messageCount } = buildForkTranscript({
      messages: [
        message({ id: 't1', content: 'Reasoning: pondering', message_metadata: { thinking: { source: 'claude' } } }),
        user('t2', 'Waiting for your input...'),
        agent('t3', 'Ready.'),
      ],
      boundaryMessageId: 't3',
      agentType: 'claude',
    });
    expect(text).not.toContain('pondering');
    expect(text).not.toContain('Waiting for your input');
    expect(messageCount).toBe(1);
  });

  test('the full history feeds the block: 700 rows, boundary at 650, nothing omitted', () => {
    const rows: MessageResponse[] = [];
    for (let i = 1; i <= 700; i += 1) {
      const id = `r${i}`;
      if (i % 10 === 1) rows.push(user(id, `ask ${i}`));
      else if (i % 10 === 0) rows.push(agent(id, `reply ${i}`));
      else rows.push(agent(id, `🔧 Using tool: Bash - \`cat file${i}\`\noutput ${i}`));
    }
    const { text, messageCount, omittedCount } = buildForkTranscript({
      messages: rows,
      boundaryMessageId: 'r650',
      agentType: 'claude',
    });
    expect(text).toContain('User: ask 1');
    expect(text).toContain('Agent: reply 10');
    expect(text).toContain('User: ask 641');
    expect(text).toContain('Agent: reply 650');
    expect(text).not.toContain('ask 651');
    expect(text).not.toContain('reply 660');
    expect(text).not.toContain('cat file');
    expect(text).not.toContain('omitted');
    // 65 user asks + 65 agent replies up to row 650.
    expect(messageCount).toBe(130);
    expect(omittedCount).toBe(0);
  });

  test('edit-class tools from every agent fold into one deduped [edited:] line per turn', () => {
    const { text, messageCount } = buildForkTranscript({
      messages: [
        user('u1', 'fix it'),
        agent('a1', 'Using tool: **Edit** - `/repo/src/a.ts`\n```diff\n-x\n+y\n```'),
        agent('a2', 'Using tool: Read - `/repo/src/b.ts`'),
        agent('a3', '🔧 Using tool: Bash - `pnpm test`'),
        agent('a4', 'Using tool: Write - `/repo/src/new.ts`\n```ts\nexport {};\n```'),
        agent('a5', 'Using tool: **MultiEdit** - `/repo/src/a.ts`\n*Making 2 edits:*'),
        agent('a6', '✏️ Applying patch to 1 file (+3 -1)\n└ src/c.ts\n**src/c.ts**\n```diff\n+z\n```'),
        agent('a7', '🔧 Using tool: Edit - `Writing to src/d.ts`'),
        agent('a8', '🔧 Using tool: Grep - `foo` in `/repo`'),
        agent('a9', '🔧 Using tool: Task - `explore the repo`'),
        agent('a10', '🔧 Using tool: ApplyPatch - ➕ `/repo/src/e.ts`, ✏️ `/repo/src/f.ts`'),
        agent('a11', 'All done.'),
      ],
      boundaryMessageId: 'a11',
      agentType: 'claude',
      sourceDirectory: '/repo',
    });
    const body = bodyOf(text);
    expect(body).toBe(
      [
        'User: fix it',
        'Agent: All done.',
        '  [edited: src/a.ts, src/new.ts, src/c.ts, src/d.ts, src/e.ts, src/f.ts]',
      ].join('\n'),
    );
    expect(messageCount).toBe(2);
  });

  test('the [edited:] line lands after the turn’s last prose; a prose-less turn still gets one', () => {
    const { text, messageCount } = buildForkTranscript({
      messages: [
        user('u1', 'first'),
        agent('a1', 'Looking.'),
        agent('a2', 'Using tool: **Edit** - `/repo/x.ts`'),
        agent('a3', 'Changed x.'),
        user('u2', 'second'),
        agent('a4', 'Using tool: **Edit** - `/repo/y.ts`'),
        user('u3', 'third'),
        agent('a5', 'Using tool: **Edit** - `/repo/z.ts`'),
        agent('a6', 'Changed z.'),
      ],
      boundaryMessageId: 'a6',
      agentType: 'claude',
      sourceDirectory: '/repo',
    });
    expect(bodyOf(text)).toBe(
      [
        'User: first',
        'Agent: Looking.',
        'Agent: Changed x.',
        '  [edited: x.ts]',
        'User: second',
        '  [edited: y.ts]',
        'User: third',
        'Agent: Changed z.',
        '  [edited: z.ts]',
      ].join('\n'),
    );
    // Three asks + three replies; the standalone edited line is not a message.
    expect(messageCount).toBe(6);
  });

  test('more than MAX_EDITED_PATHS paths collapse into “+N more”', () => {
    const edits = Array.from({ length: MAX_EDITED_PATHS + 5 }, (_, i) =>
      agent(`e${i}`, `Using tool: **Edit** - \`/repo/f${i}.ts\``),
    );
    const { text } = buildForkTranscript({
      messages: [user('u1', 'go'), ...edits, agent('done', 'Done.')],
      boundaryMessageId: 'done',
      agentType: 'claude',
      sourceDirectory: '/repo',
    });
    const line = bodyOf(text).split('\n').at(-1) ?? '';
    expect(line.startsWith('  [edited: f0.ts, f1.ts, ')).toBe(true);
    expect(line).toContain(`f${MAX_EDITED_PATHS - 1}.ts, … +5 more]`);
    expect(line).not.toContain(`f${MAX_EDITED_PATHS}.ts`);
  });

  test('Codex Exec rows and unknown tool names never contribute a path', () => {
    const { text } = buildForkTranscript({
      messages: [
        user('u1', 'go'),
        agent('c1', '**Exec:** `sed -i s/a/b/ src/a.ts`\n**Status:** ok'),
        agent('c2', '🔧 Using tool: Rewrite - `/repo/src/b.ts`'),
        agent('c3', 'Done.'),
      ],
      boundaryMessageId: 'c3',
      agentType: 'codex',
      sourceDirectory: '/repo',
    });
    expect(bodyOf(text)).toBe('User: go\nAgent: Done.');
  });

  test('long entries are clamped at MAX_ENTRY_CHARS', () => {
    const { text } = buildForkTranscript({
      messages: [agent('big', 'x'.repeat(MAX_ENTRY_CHARS + 100))],
      boundaryMessageId: 'big',
      agentType: 'claude',
    });
    expect(text).toContain('… (truncated)');
    expect(text).not.toContain('x'.repeat(MAX_ENTRY_CHARS + 1));
  });

  test('the budget trims from the front, reports the omitted count, and keeps a turn’s edits with its prose', () => {
    const filler = 'y'.repeat(MAX_ENTRY_CHARS - 100);
    const rows: MessageResponse[] = [];
    const turns = Math.ceil(MAX_TOTAL_CHARS / MAX_ENTRY_CHARS) + 3;
    for (let i = 0; i < turns; i += 1) {
      rows.push(user(`u${i}`, `ask ${i}`));
      rows.push(agent(`e${i}`, `Using tool: **Edit** - \`/repo/t${i}.ts\``));
      rows.push(agent(`a${i}`, `${filler} reply ${i}`));
    }
    const last = `a${turns - 1}`;
    const { text, messageCount, omittedCount } = buildForkTranscript({
      messages: rows,
      boundaryMessageId: last,
      agentType: 'claude',
      sourceDirectory: '/repo',
    });
    expect(omittedCount).toBeGreaterThan(0);
    expect(text).toContain(`… ${omittedCount} earlier messages omitted …`);
    expect(text).not.toContain('User: ask 0');
    expect(text).not.toContain('[edited: t0.ts]');
    expect(text).toContain(`reply ${turns - 1}\n  [edited: t${turns - 1}.ts]`);
    expect(messageCount + omittedCount).toBe(turns * 2);
    expect(text.length).toBeLessThan(MAX_TOTAL_CHARS + 1000);
  });
});

describe('extractEditedPaths', () => {
  test('takes whitespace-free backtick spans as-is, all of them', () => {
    expect(extractEditedPaths('`/repo/a.ts`')).toEqual(['/repo/a.ts']);
    expect(extractEditedPaths('`/repo/a.ts` (cell: 3, mode: replace)')).toEqual(['/repo/a.ts']);
    expect(extractEditedPaths('➕ `/repo/a.ts`, ✏️ `/repo/b.ts`')).toEqual(['/repo/a.ts', '/repo/b.ts']);
    expect(extractEditedPaths('`Makefile` +3 -1')).toEqual(['Makefile']);
  });

  test('a span or bare description with spaces yields its first path-like token', () => {
    expect(extractEditedPaths('`Writing to src/a.ts`')).toEqual(['src/a.ts']);
    expect(extractEditedPaths('Create approved.txt with ok')).toEqual(['approved.txt']);
    expect(extractEditedPaths('Update the README')).toEqual([]);
    expect(extractEditedPaths('Fix the login flow.')).toEqual([]);
  });

  test('JSON argument dumps are not paths', () => {
    expect(extractEditedPaths('`{"content":"x"}`')).toEqual([]);
  });
});
