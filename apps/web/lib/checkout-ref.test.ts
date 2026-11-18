import { describe, expect, it } from 'vitest';

import {
  checkoutRefBranch,
  checkoutRefLabel,
  checkoutRefOf,
  checkoutRefOfStatus,
  checkoutRefTag,
} from './checkout-ref';

const SHA = '760f39ad1ee1e86e966bd721ca1e65ed6d3f4f70';

describe('checkoutRefOf', () => {
  it('labels a branch by name, with no tag', () => {
    const ref = checkoutRefOf({ branch: 'feat/x', head: SHA, rebasingBranch: '' });
    expect(ref).toEqual({ kind: 'branch', branch: 'feat/x' });
    expect(checkoutRefLabel(ref)).toBe('feat/x');
    expect(checkoutRefTag(ref)).toBeNull();
  });

  it('labels a detached HEAD by its short commit and tags it', () => {
    const ref = checkoutRefOf({ branch: '', head: SHA });
    expect(checkoutRefLabel(ref)).toBe('760f39a');
    expect(checkoutRefBranch(ref)).toBe('');
    const tag = checkoutRefTag(ref);
    expect(tag?.text).toBe('detached');
    expect(tag?.title).toContain('Detached HEAD at 760f39a');
  });

  it('still reads as detached when an older daemon sent no commit', () => {
    const ref = checkoutRefOf({ branch: '' });
    expect(checkoutRefLabel(ref)).toBe('HEAD');
    expect(checkoutRefTag(ref)?.text).toBe('detached');
    expect(checkoutRefTag(ref)?.title.startsWith('Detached HEAD:')).toBe(true);
  });

  it('keeps the branch of a checkout mid-rebase and tags it rebasing', () => {
    const ref = checkoutRefOf({ branch: '', head: SHA, rebasingBranch: 'feat/x' });
    expect(checkoutRefLabel(ref)).toBe('feat/x');
    expect(checkoutRefBranch(ref)).toBe('feat/x');
    const tag = checkoutRefTag(ref);
    expect(tag?.text).toBe('rebasing');
    expect(tag?.title).toContain('detached at 760f39a');
  });
});

describe('checkoutRefOfStatus', () => {
  it('reads the short commit git status puts in `branch` when detached', () => {
    const ref = checkoutRefOfStatus({ branch: '760f39a', detached_head: true });
    expect(ref).toEqual({ kind: 'detached', head: '760f39a' });
  });

  it('reads a rebase in progress', () => {
    const ref = checkoutRefOfStatus({
      branch: '760f39a',
      detached_head: true,
      rebasing_branch: 'main',
    });
    expect(ref).toEqual({ kind: 'rebasing', branch: 'main', head: '760f39a' });
  });

  it('reads a branch', () => {
    expect(checkoutRefOfStatus({ branch: 'main' })).toEqual({ kind: 'branch', branch: 'main' });
  });
});
