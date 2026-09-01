import { describe, it, expect } from 'vitest';
import {
  applyDraftToConfig,
  configToDraft,
  isDraftEmpty,
  type WorktreeConfigDraft,
} from './worktree-config-form';

describe('configToDraft', () => {
  it('reads array hooks as newline-joined text, kind array', () => {
    const d = configToDraft({ worktree: { setup: ['npm ci', 'npm run build'] } });
    expect(d.setupText).toBe('npm ci\nnpm run build');
    expect(d.setupKind).toBe('array');
    expect(d.teardownKind).toBe('missing');
  });

  it('reads a string hook as-is, kind string', () => {
    const d = configToDraft({ worktree: { teardown: 'rm -rf node_modules' } });
    expect(d.teardownText).toBe('rm -rf node_modules');
    expect(d.teardownKind).toBe('string');
  });

  it('missing / non-object config → empty draft', () => {
    expect(configToDraft(null).setupKind).toBe('missing');
    expect(configToDraft({}).setupKind).toBe('missing');
    expect(configToDraft('nope').setupText).toBe('');
  });
});

describe('applyDraftToConfig', () => {
  const draft = (over: Partial<WorktreeConfigDraft>): WorktreeConfigDraft => ({
    setupText: '',
    setupKind: 'missing',
    teardownText: '',
    teardownKind: 'missing',
    ...over,
  });

  it('writes new hooks as an array by default', () => {
    const out = applyDraftToConfig(draft({ setupText: 'a\nb' }), null);
    expect(out).toEqual({ worktree: { setup: ['a', 'b'] } });
  });

  it('a single new line becomes a bare string', () => {
    const out = applyDraftToConfig(draft({ setupText: 'npm ci' }), null);
    expect(out).toEqual({ worktree: { setup: 'npm ci' } });
  });

  it('preserves the original array shape on round-trip', () => {
    const base = { worktree: { setup: ['npm ci'] } };
    const d = configToDraft(base);
    d.setupText = 'npm ci\nnpm run build';
    expect(applyDraftToConfig(d, base)).toEqual({
      worktree: { setup: ['npm ci', 'npm run build'] },
    });
  });

  it('drops blank lines and empties the hook when cleared', () => {
    const base = { worktree: { setup: ['x'], teardown: 'y' } };
    const d = configToDraft(base);
    d.setupText = '  \n\n';
    expect(applyDraftToConfig(d, base)).toEqual({ worktree: { teardown: 'y' } });
  });

  it('preserves unrelated keys in the file', () => {
    const base = { worktree: { setup: ['x'], servicePorts: { range: '3000-3010' } }, other: 1 };
    const d = configToDraft(base);
    d.setupText = 'y';
    const out = applyDraftToConfig(d, base);
    expect(out.other).toBe(1);
    expect((out.worktree as Record<string, unknown>).servicePorts).toEqual({ range: '3000-3010' });
    // base setup was an array, so the round-trip keeps the array shape.
    expect((out.worktree as Record<string, unknown>).setup).toEqual(['y']);
  });

  it('drops the worktree object entirely when both hooks are empty', () => {
    const base = { worktree: { setup: ['x'] }, other: 2 };
    const d = configToDraft(base);
    d.setupText = '';
    expect(applyDraftToConfig(d, base)).toEqual({ other: 2 });
  });
});

describe('isDraftEmpty', () => {
  it('true only when both hooks are blank', () => {
    expect(isDraftEmpty(configToDraft(null))).toBe(true);
    expect(isDraftEmpty(configToDraft({ worktree: { setup: ['x'] } }))).toBe(false);
  });
});
