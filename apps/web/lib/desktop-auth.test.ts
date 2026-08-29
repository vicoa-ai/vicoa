import { describe, expect, it } from 'vitest';
import { parseDesktopAuthCallback, pruneNonceHistory } from './desktop-auth';

describe('pruneNonceHistory', () => {
  const NOW = 1_700_000_000_000;
  const HOUR = 60 * 60 * 1000;

  it('keeps fresh entries and drops expired ones', () => {
    const history = [
      { n: 'old', t: NOW - 25 * HOUR },
      { n: 'fresh', t: NOW - 1 * HOUR },
      { n: 'now', t: NOW },
    ];
    expect(pruneNonceHistory(history, NOW).map((e) => e.n)).toEqual(['fresh', 'now']);
  });

  it('caps the list to the most recent entries', () => {
    const history = Array.from({ length: 15 }, (_, i) => ({ n: `n${i}`, t: NOW - i }));
    const pruned = pruneNonceHistory(history, NOW, 24 * HOUR, 10);
    expect(pruned).toHaveLength(10);
    expect(pruned[pruned.length - 1].n).toBe('n14');
  });

  it('drops malformed entries', () => {
    const history = [
      { n: '', t: NOW },
      { n: 'ok', t: NOW },
      { n: 'no-time' } as never,
      null as never,
    ];
    expect(pruneNonceHistory(history, NOW).map((e) => e.n)).toEqual(['ok']);
  });
});

describe('parseDesktopAuthCallback', () => {
  it('ignores non-callback deep links', () => {
    expect(parseDesktopAuthCallback('vicoa://open/session/123')).toBeNull();
    expect(parseDesktopAuthCallback('https://vicoa.ai/desktop-auth')).toBeNull();
  });

  it('parses the token_hash handoff shape', () => {
    const parsed = parseDesktopAuthCallback(
      'vicoa://auth/callback?api_key=K1&state=nonce-1&token_hash=th-abc'
    );
    expect(parsed).toEqual({
      apiKey: 'K1',
      state: 'nonce-1',
      tokenHash: 'th-abc',
      accessToken: null,
      refreshToken: null,
    });
  });

  it('parses the legacy token handoff shape', () => {
    const parsed = parseDesktopAuthCallback(
      'vicoa://auth/callback?api_key=K1&state=nonce-1&access_token=AT&refresh_token=RT'
    );
    expect(parsed?.apiKey).toBe('K1');
    expect(parsed?.tokenHash).toBeNull();
    expect(parsed?.accessToken).toBe('AT');
    expect(parsed?.refreshToken).toBe('RT');
  });

  it('handles a callback without a query string', () => {
    const parsed = parseDesktopAuthCallback('vicoa://auth/callback');
    expect(parsed).toEqual({
      apiKey: null,
      state: null,
      tokenHash: null,
      accessToken: null,
      refreshToken: null,
    });
  });

  it('decodes url-encoded values', () => {
    const state = encodeURIComponent('a b+c');
    const parsed = parseDesktopAuthCallback(`vicoa://auth/callback?api_key=K&state=${state}`);
    expect(parsed?.state).toBe('a b+c');
  });
});
