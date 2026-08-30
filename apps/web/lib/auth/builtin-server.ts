import { cookies } from 'next/headers';

import { BUILTIN_SESSION_COOKIE, decodeBuiltinToken, type BuiltinClaims } from './auth-provider';

/**
 * Server-side reads of the built-in provider's session cookie.
 *
 * Split from `builtin-client.ts` because `next/headers` cannot be imported into
 * a client component — the two halves share only `auth-provider.ts`.
 */

export async function getBuiltinTokenFromCookies(): Promise<string | null> {
  const store = await cookies();
  const token = store.get(BUILTIN_SESSION_COOKIE)?.value ?? null;
  return decodeBuiltinToken(token) ? token : null;
}

export async function getBuiltinClaimsFromCookies(): Promise<BuiltinClaims | null> {
  return decodeBuiltinToken(await getBuiltinTokenFromCookies());
}
