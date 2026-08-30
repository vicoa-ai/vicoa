import { describe, expect, it } from 'vitest';
import { resolveAuthedRedirect } from './redirect-target';

const ALLOWED = ['https://vicoa.ai', 'http://localhost:3000'];

describe('resolveAuthedRedirect', () => {
  it('falls back to /dashboard without a redirect param', () => {
    expect(resolveAuthedRedirect(undefined, ALLOWED)).toBe('/dashboard');
    expect(resolveAuthedRedirect(null, ALLOWED)).toBe('/dashboard');
    expect(resolveAuthedRedirect('', ALLOWED)).toBe('/dashboard');
    expect(resolveAuthedRedirect('   ', ALLOWED)).toBe('/dashboard');
  });

  it('honors relative paths', () => {
    expect(resolveAuthedRedirect('/desktop-auth?state=abc', ALLOWED)).toBe(
      '/desktop-auth?state=abc'
    );
    expect(resolveAuthedRedirect('/dashboard/settings', ALLOWED)).toBe('/dashboard/settings');
  });

  it('rejects scheme-relative URLs', () => {
    expect(resolveAuthedRedirect('//evil.com/phish', ALLOWED)).toBe('/dashboard');
  });

  it('honors absolute URLs on allowed origins (the desktop handoff shape)', () => {
    const target = 'https://vicoa.ai/desktop-auth?state=abc-123&resume=1';
    expect(resolveAuthedRedirect(target, ALLOWED)).toBe(target);
    expect(resolveAuthedRedirect('http://localhost:3000/desktop-auth?state=x', ALLOWED)).toBe(
      'http://localhost:3000/desktop-auth?state=x'
    );
  });

  it('rejects absolute URLs on other origins', () => {
    expect(resolveAuthedRedirect('https://evil.com/desktop-auth', ALLOWED)).toBe('/dashboard');
    expect(resolveAuthedRedirect('https://vicoa.ai.evil.com/x', ALLOWED)).toBe('/dashboard');
  });

  it('rejects non-http(s) schemes', () => {
    expect(resolveAuthedRedirect('javascript:alert(1)', ALLOWED)).toBe('/dashboard');
    expect(resolveAuthedRedirect('vicoa://auth/callback', ALLOWED)).toBe('/dashboard');
  });

  it('rejects garbage', () => {
    expect(resolveAuthedRedirect('not a url at all %%%', ALLOWED)).toBe('/dashboard');
  });
});
