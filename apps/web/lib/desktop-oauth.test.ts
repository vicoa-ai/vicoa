import { describe, it, expect } from 'vitest';
import { parseOAuthCallbackUrl } from '@/lib/desktop-oauth';

describe('parseOAuthCallbackUrl', () => {
  it('extracts a PKCE code from the query string', () => {
    expect(parseOAuthCallbackUrl('vicoa://auth/callback?code=abc123')).toEqual({
      code: 'abc123',
    });
  });

  it('extracts a code alongside unrelated query params', () => {
    expect(
      parseOAuthCallbackUrl('vicoa://auth/callback?code=xyz&state=foo&other=1'),
    ).toEqual({ code: 'xyz' });
  });

  it('extracts a code from the URL fragment (implicit/hash form)', () => {
    expect(parseOAuthCallbackUrl('vicoa://auth/callback#code=frag789')).toEqual({
      code: 'frag789',
    });
  });

  it('prefers the query code over a fragment code when both are present', () => {
    expect(
      parseOAuthCallbackUrl('vicoa://auth/callback?code=fromquery#code=fromfragment'),
    ).toEqual({ code: 'fromquery' });
  });

  it('extracts error and error_description from the query string', () => {
    expect(
      parseOAuthCallbackUrl(
        'vicoa://auth/callback?error=access_denied&error_description=User%20denied%20access',
      ),
    ).toEqual({
      error: 'access_denied',
      errorDescription: 'User denied access',
    });
  });

  it('extracts an error from the URL fragment', () => {
    expect(
      parseOAuthCallbackUrl(
        'vicoa://auth/callback#error=server_error&error_description=boom',
      ),
    ).toEqual({
      error: 'server_error',
      errorDescription: 'boom',
    });
  });

  it('reports an error without a description as undefined description', () => {
    expect(parseOAuthCallbackUrl('vicoa://auth/callback?error=access_denied')).toEqual({
      error: 'access_denied',
      errorDescription: undefined,
    });
  });

  it('returns an empty object when there are no params', () => {
    expect(parseOAuthCallbackUrl('vicoa://auth/callback')).toEqual({});
  });

  it('returns an empty object for an unrelated deep link', () => {
    expect(parseOAuthCallbackUrl('vicoa://something/else?foo=bar')).toEqual({});
  });

  it('decodes plus-encoded spaces in the error description', () => {
    expect(
      parseOAuthCallbackUrl(
        'vicoa://auth/callback?error=access_denied&error_description=User+denied',
      ),
    ).toEqual({
      error: 'access_denied',
      errorDescription: 'User denied',
    });
  });
});
