/** Placeholder origin a relative target is resolved against to see where it lands. */
const RELATIVE_BASE = 'http://relative.invalid';

/**
 * Resolve where to send a user after sign-in, from a caller-supplied
 * `redirect` / `next` param: the already-authenticated bounce off /sign-in and
 * /sign-up, the post-login server actions, the OAuth callback and the built-in
 * provider's client-side sign-in all route through here.
 *
 * The desktop browser-handoff (`/desktop-auth?state=…`) round-trips through
 * /sign-in with `redirect=<absolute desktop-auth URL>`; dropping the param
 * (the old behavior always went to /dashboard) strands the desktop app on its
 * waiting screen. Relative paths are honored when they stay on this site;
 * absolute URLs only when their origin is allowlisted, so the param can't be
 * abused as an open redirect (or a `javascript:` URL) after login.
 *
 * The result is the URL as the parser read it, not the raw param, so whatever
 * parses it next lands exactly where it was validated.
 */
export function resolveAuthedRedirect(
  redirectParam: string | null | undefined,
  allowedOrigins: readonly string[]
): string {
  const fallback = '/dashboard';
  if (!redirectParam) return fallback;
  const target = redirectParam.trim();
  if (target === '') return fallback;

  // Relative path: resolve it and require it to stay on this site. A plain
  // `startsWith('//')` check is not enough: the URL parser (browser and Node
  // alike) reads `/\evil.com` and `/<tab>/evil.com` as `//evil.com`.
  if (target.startsWith('/')) {
    try {
      const url = new URL(target, RELATIVE_BASE);
      if (url.origin !== RELATIVE_BASE) return fallback;
      const path = `${url.pathname}${url.search}${url.hash}`;
      // Dot segments can normalize to a scheme-relative path
      // (`/..//evil.com` -> `//evil.com`), which would leave the site when
      // parsed again.
      return path.startsWith('//') ? fallback : path;
    } catch {
      return fallback;
    }
  }

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
    return allowed ? url.href : fallback;
  } catch {
    return fallback;
  }
}

/**
 * Origins an absolute `redirect` param may point at: BASE_URL, the prod web,
 * and `currentOrigin`, the origin this request or page is being served from.
 *
 * Pass `currentOrigin` wherever it is known. The desktop and CLI handoffs send
 * their own absolute same-origin URL (`window.location.href`), and outside
 * prod that origin is often in no env var: a dev server on another port, or
 * client code, where the server-only BASE_URL is not available.
 */
export function authedRedirectAllowedOrigins(currentOrigin?: string | null): string[] {
  const origins = [
    process.env.BASE_URL,
    process.env.NEXT_PUBLIC_VICOA_WEB_URL,
    'https://vicoa.ai',
    'https://www.vicoa.ai',
    currentOrigin ?? undefined,
  ];
  if (process.env.NODE_ENV === 'development') {
    origins.push('http://localhost:3000');
  }
  return origins.filter((origin): origin is string => !!origin);
}
