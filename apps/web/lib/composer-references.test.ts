import { describe, expect, it } from 'vitest';
import {
  activeReferences,
  addReference,
  buildReferenceBlock,
  candidateToComposerReference,
  composeOutgoingMessage,
  detectTriggerToken,
  replaceTriggerToken,
  taskLinkForSend,
  type ComposerReference,
} from './composer-references';

function ref(over: Partial<ComposerReference> = {}): ComposerReference {
  return {
    kind: 'task',
    id: 'task-1',
    token: 'VIC-42',
    label: 'Fix the diff editor',
    context: 'Task VIC-42 — Fix the diff editor',
    ...over,
  };
}

describe('detectTriggerToken', () => {
  it('finds the token the caret is inside', () => {
    const text = 'look at #VIC';
    expect(detectTriggerToken(text, text.length, '#')).toEqual({
      start: 8,
      end: 12,
      query: 'VIC',
    });
  });

  it('opens on a bare trigger', () => {
    expect(detectTriggerToken('#', 1, '#')).toEqual({ start: 0, end: 1, query: '' });
  });

  it('ignores a trigger glued to the previous word', () => {
    expect(detectTriggerToken('issue#42', 8, '#')).toBeNull();
  });

  it('ignores a token the caret has moved past', () => {
    const text = '#VIC-42 and then some more';
    expect(detectTriggerToken(text, text.length, '#')).toBeNull();
  });

  it('picks the token the caret is in, not the last one in the text', () => {
    const text = '#one #two';
    // Caret just after "#one".
    expect(detectTriggerToken(text, 4, '#')?.query).toBe('one');
  });

  it('lets @ and # claim different tokens in the same line', () => {
    const text = '@src/app.ts #VIC';
    expect(detectTriggerToken(text, text.length, '@')).toBeNull();
    expect(detectTriggerToken(text, text.length, '#')?.query).toBe('VIC');
  });
});

describe('replaceTriggerToken', () => {
  it('replaces the partial token and adds a trailing space', () => {
    const text = 'look at #VIC';
    const token = detectTriggerToken(text, text.length, '#')!;
    expect(replaceTriggerToken(text, token, '#', 'VIC-42')).toEqual({
      text: 'look at #VIC-42 ',
      cursor: 16,
    });
  });

  it('keeps the text that follows and does not double the space', () => {
    const text = 'see #VI next';
    const token = detectTriggerToken(text, 7, '#')!;
    expect(replaceTriggerToken(text, token, '#', 'VIC-42').text).toBe(
      'see #VIC-42 next',
    );
  });
});

describe('addReference', () => {
  it('replaces an earlier pick that slugified to the same token', () => {
    const first = ref({ id: 'a', token: 'fix-the-bug' });
    const second = ref({ id: 'b', token: 'fix-the-bug' });
    expect(addReference([first], second)).toEqual([second]);
  });

  it('keeps references with distinct tokens, in pick order', () => {
    const task = ref({ token: 'VIC-42' });
    const session = ref({ kind: 'session', id: 's', token: 'zesty-quartz' });
    expect(addReference([task], session).map((r) => r.token)).toEqual([
      'VIC-42',
      'zesty-quartz',
    ]);
  });
});

describe('activeReferences', () => {
  it('drops a reference whose token the user deleted', () => {
    const kept = ref({ token: 'VIC-42' });
    const removed = ref({ id: 'gone', token: 'zesty-quartz' });
    expect(activeReferences([kept, removed], 'work on #VIC-42 please')).toEqual([
      kept,
    ]);
  });

  it('requires the "#" too, so bare prose does not resurrect a reference', () => {
    expect(activeReferences([ref({ token: 'VIC-42' })], 'see VIC-42')).toEqual([]);
  });
});

describe('buildReferenceBlock', () => {
  it('joins each reference block under one header', () => {
    const block = buildReferenceBlock([
      ref({ context: 'Task VIC-42 — Fix it' }),
      ref({ kind: 'session', id: 's', token: 'z', context: 'Session "z"' }),
    ]);
    expect(block).toBe(
      'Referenced with # in Vicoa:\n\nTask VIC-42 — Fix it\n\nSession "z"',
    );
  });

  it('is empty when every expansion failed', () => {
    expect(buildReferenceBlock([ref({ context: '' })])).toBe('');
  });
});

describe('composeOutgoingMessage', () => {
  it('appends the block after the typed text', () => {
    expect(composeOutgoingMessage('continue #VIC-42', [ref()])).toBe(
      'continue #VIC-42\n\n---\nReferenced with # in Vicoa:\n\nTask VIC-42 — Fix the diff editor',
    );
  });

  it('leaves the message untouched when nothing is referenced', () => {
    expect(composeOutgoingMessage('plain text', [])).toBe('plain text');
  });
});

describe('taskLinkForSend', () => {
  it('links the first referenced task when the session has none', () => {
    const refs = [
      ref({ kind: 'session', id: 's', token: 'z' }),
      ref({ id: 'task-a', token: 'VIC-42' }),
      ref({ id: 'task-b', token: 'VIC-43' }),
    ];
    expect(taskLinkForSend(refs, null)).toBe('task-a');
  });

  it('never re-files a session that already belongs to a task', () => {
    expect(taskLinkForSend([ref({ id: 'task-a' })], 'task-b')).toBeNull();
  });

  it('is null when no task was referenced', () => {
    expect(taskLinkForSend([ref({ kind: 'automation', id: 'x' })], null)).toBeNull();
  });
});

describe('candidateToComposerReference', () => {
  it('stands in for the expansion until (or unless) it arrives', () => {
    const composed = candidateToComposerReference({
      kind: 'task',
      id: 'task-1',
      label: 'Fix the diff editor',
      token: 'VIC-42',
      meta: 'Vicoa',
      project: null,
      identifier: 'VIC-42',
      status: 'in_progress',
    });
    expect(composed.token).toBe('VIC-42');
    expect(composed.context).toBe('Task "Fix the diff editor"\nVicoa · id: task-1');
    // A send in the fetch window still carries something resolvable.
    expect(buildReferenceBlock([composed])).toContain('id: task-1');
  });
});
