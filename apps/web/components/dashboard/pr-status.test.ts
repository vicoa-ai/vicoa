import { describe, expect, test } from 'vitest';
import { prForCheckout, type PrInfo } from './pr-status';

const pr = (number: number, state: PrInfo['state'], head?: string): PrInfo => ({
  number,
  title: `PR ${number}`,
  state,
  url: `https://github.com/o/r/pull/${number}`,
  checks: 'none',
  ...(head ? { head } : {}),
});

describe('prForCheckout', () => {
  test('finds the PR by the local branch', () => {
    const prs = { feat: pr(7, 'open') };
    expect(prForCheckout(prs, { branch: 'feat' })?.number).toBe(7);
  });

  test('a branch pushed under another name: the newer PR under its upstream wins', () => {
    // The worktree's first PR merged under the local name; the new work went up
    // as `cli-version` with `push -u origin HEAD:cli-version`.
    const prs = { 'happy-thistle': pr(204, 'merged'), 'cli-version': pr(208, 'open') };
    const found = prForCheckout(prs, { branch: 'happy-thistle', upstream: 'cli-version' });
    expect(found?.number).toBe(208);
    expect(found?.state).toBe('open');
  });

  test('the newest wins whichever name found it', () => {
    const prs = { local: pr(30, 'open'), remote: pr(12, 'merged') };
    expect(prForCheckout(prs, { branch: 'local', upstream: 'remote' })?.number).toBe(30);
  });

  test('pushed without -u: the PR whose head is this checkout\'s commit', () => {
    const prs = { 'happy-thistle': pr(204, 'merged', 'aaa'), 'cli-version': pr(208, 'open', 'bbb') };
    expect(prForCheckout(prs, { branch: 'happy-thistle', head: 'bbb' })?.number).toBe(208);
  });

  test('a detached checkout still matches by commit', () => {
    const prs = { feat: pr(9, 'draft', 'ccc') };
    expect(prForCheckout(prs, { branch: '', head: 'ccc' })?.number).toBe(9);
  });

  test('null when nothing ties a PR to the checkout', () => {
    const prs = { other: pr(5, 'open', 'ddd') };
    expect(prForCheckout(prs, { branch: 'feat', upstream: '', head: 'eee' })).toBeNull();
    expect(prForCheckout({}, { branch: 'feat' })).toBeNull();
  });

  test('an older daemon (no upstream, no head) behaves as before', () => {
    const prs = { feat: pr(7, 'merged'), other: pr(8, 'open') };
    expect(prForCheckout(prs, { branch: 'feat' })?.number).toBe(7);
  });
});
