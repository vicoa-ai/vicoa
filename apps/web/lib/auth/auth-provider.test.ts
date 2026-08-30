import { describe, expect, it } from 'vitest';

import { decodeBuiltinToken, readSessionCookie } from './auth-provider';

function token(claims: Record<string, unknown>): string {
  const encode = (value: unknown) =>
    Buffer.from(JSON.stringify(value)).toString('base64url');
  return `${encode({ alg: 'RS256' })}.${encode(claims)}.signature`;
}

const inAnHour = Math.floor(Date.now() / 1000) + 3600;

describe('decodeBuiltinToken', () => {
  it('reads the identity out of a live session token', () => {
    const claims = decodeBuiltinToken(
      token({ sub: 'user-1', email: 'a@b.co', name: 'Ada', exp: inAnHour })
    );

    expect(claims).toEqual({
      sub: 'user-1',
      email: 'a@b.co',
      name: 'Ada',
      exp: inAnHour,
    });
  });

  it('treats an expired token as no session', () => {
    // Otherwise the app renders as signed-in and every request 401s, which
    // reads as "the server is broken" rather than "sign in again".
    expect(
      decodeBuiltinToken(token({ sub: 'user-1', exp: Math.floor(Date.now() / 1000) - 1 }))
    ).toBeNull();
  });

  it('rejects anything malformed rather than throwing', () => {
    expect(decodeBuiltinToken(null)).toBeNull();
    expect(decodeBuiltinToken('')).toBeNull();
    expect(decodeBuiltinToken('not-a-jwt')).toBeNull();
    expect(decodeBuiltinToken('a.!!!not-base64!!!.c')).toBeNull();
    expect(decodeBuiltinToken(token({ email: 'nobody@example.com' }))).toBeNull();
  });
});

describe('readSessionCookie', () => {
  it('finds the session among other cookies', () => {
    expect(readSessionCookie('theme=dark; vicoa_session=abc.def.ghi; x=1')).toBe(
      'abc.def.ghi'
    );
  });

  it('returns null when there is no session cookie', () => {
    expect(readSessionCookie('theme=dark')).toBeNull();
    expect(readSessionCookie('')).toBeNull();
    expect(readSessionCookie(null)).toBeNull();
  });
});
