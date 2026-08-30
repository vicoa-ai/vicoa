/**
 * Resolve where to send an already-authenticated user who landed on
 * /sign-in or /sign-up with a `redirect` query param.
 *
 * The desktop browser-handoff (`/desktop-auth?state=…`) round-trips through
 * /sign-in with `redirect=<absolute desktop-auth URL>`; dropping the param
 * (the old behavior always went to /dashboard) strands the desktop app on its
 * waiting screen. Relative paths are honored as-is; absolute URLs only when
 * their origin is allowlisted, so the param can't be abused as an open
 * redirect after login.
 */
export function resolveAuthedRedirect(
  redirectParam: string | null | undefined,
  allowedOrigins: readonly string[]
): string {
  const fallback = '/dashboard';
  if (!redirectParam) return fallback;
  const target = redirectParam.trim();
  if (target === '') return fallback;

  // Relative path: allow, but reject scheme-relative (`//evil.com`) forms.
  if (target.startsWith('/') && !target.startsWith('//')) return target;

  try {
    const url = new URL(target);
    if (url.protocol !== 'https:' && url.protocol !== 'http:') return fallback;
    const allowed = allowedOrigins.some((origin) => {
      try {
        return new URL(origin).origin === url.origin;
      } catch {
        return false;
      }
    });
    return allowed ? target : fallback;
  } catch {
    return fallback;
  }
}

/** Origins an absolute `redirect` param may point at (BASE_URL + prod web). */
export function authedRedirectAllowedOrigins(): string[] {
  const origins = [
    process.env.BASE_URL,
    process.env.NEXT_PUBLIC_VICOA_WEB_URL,
    'https://vicoa.ai',
    'https://www.vicoa.ai',
  ];
  if (process.env.NODE_ENV === 'development') {
    origins.push('http://localhost:3000');
  }
  return origins.filter((origin): origin is string => !!origin);
}
