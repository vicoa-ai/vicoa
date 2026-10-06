import { afterEach, describe, expect, it, vi } from 'vitest';
import { authedRedirectAllowedOrigins, resolveAuthedRedirect } from './redirect-target';

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

  it('rejects paths the URL parser reads as another host', () => {
    // Each of these starts with a single `/`, yet resolves to https://evil.com
    // in a browser: a backslash counts as a slash, tabs/newlines are dropped.
    const sneakyPaths = [
      '/\\evil.com',
      '/\\/evil.com',
      '/\t/evil.com',
      '/\n/evil.com',
      '/\r/evil.com',
    ];
    for (const sneaky of sneakyPaths) {
      expect(resolveAuthedRedirect(sneaky, ALLOWED)).toBe('/dashboard');
    }
  });

  it('rejects dot segments that normalize to a scheme-relative path', () => {
    const sneakyPaths = ['/..//evil.com', '/.//evil.com', '/x/..//evil.com', '/%2e%2e//evil.com'];
    for (const sneaky of sneakyPaths) {
      expect(resolveAuthedRedirect(sneaky, ALLOWED)).toBe('/dashboard');
    }
  });

  it('keeps a same-site path whole: query, hash and an embedded URL', () => {
    expect(resolveAuthedRedirect('/desktop-auth?state=a%20b&resume=1#top', ALLOWED)).toBe(
      '/desktop-auth?state=a%20b&resume=1#top'
    );
    expect(resolveAuthedRedirect('/dashboard?next=//evil.com', ALLOWED)).toBe(
      '/dashboard?next=//evil.com'
    );
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
    expect(resolveAuthedRedirect('JavaScript:alert(1)', ALLOWED)).toBe('/dashboard');
    expect(resolveAuthedRedirect(' javascript:alert(1)', ALLOWED)).toBe('/dashboard');
    expect(resolveAuthedRedirect('java\tscript:alert(1)', ALLOWED)).toBe('/dashboard');
    expect(resolveAuthedRedirect('data:text/html,<script>alert(1)</script>', ALLOWED)).toBe(
      '/dashboard'
    );
    expect(resolveAuthedRedirect('vicoa://auth/callback', ALLOWED)).toBe('/dashboard');
  });

  it('returns an allowed absolute URL as parsed, so the next parser agrees', () => {
    // A backslash after the host is a path separator: the origin really is
    // vicoa.ai, and the normalized form says so unambiguously.
    expect(resolveAuthedRedirect('https://vicoa.ai\\@evil.com/x', ALLOWED)).toBe(
      'https://vicoa.ai/@evil.com/x'
    );
    expect(resolveAuthedRedirect('https://user@evil.com/x', ALLOWED)).toBe('/dashboard');
  });

  it('rejects garbage', () => {
    expect(resolveAuthedRedirect('not a url at all %%%', ALLOWED)).toBe('/dashboard');
  });
});

describe('authedRedirectAllowedOrigins', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('adds the serving origin, so a same-origin handoff URL survives off prod', () => {
    // The CLI/desktop handoff pages send `window.location.href`; on a dev
    // server on another port, or a self-host with no BASE_URL, that origin
    // is in no env var.
    vi.stubEnv('BASE_URL', '');
    vi.stubEnv('NEXT_PUBLIC_VICOA_WEB_URL', '');
    const target = 'http://localhost:3002/cli-auth?port=5000&state=s';

    expect(resolveAuthedRedirect(target, authedRedirectAllowedOrigins())).toBe('/dashboard');
    expect(
      resolveAuthedRedirect(target, authedRedirectAllowedOrigins('http://localhost:3002'))
    ).toBe(target);
  });

  it('ignores a missing serving origin', () => {
    vi.stubEnv('BASE_URL', 'https://vicoa.example.com');
    expect(authedRedirectAllowedOrigins(null)).toContain('https://vicoa.example.com');
    expect(authedRedirectAllowedOrigins(undefined)).not.toContain(undefined);
  });
});
