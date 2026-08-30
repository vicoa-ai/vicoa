import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';
import { createClient } from '@/lib/auth/supabase-middleware';
import { decodeBuiltinToken, isBuiltinAuth, BUILTIN_SESSION_COOKIE } from '@/lib/auth/auth-provider';

const protectedRoutes = '/dashboard';

/**
 * Route protection for the built-in auth provider.
 *
 * There is no session to refresh and no identity service to ask: the cookie
 * either carries an unexpired token this server signed, or it does not. The
 * signature is verified by the backend on the first API call — middleware only
 * decides whether to render the page or bounce to /sign-in.
 */
function builtinMiddleware(request: NextRequest, isProtectedRoute: boolean) {
  const claims = decodeBuiltinToken(
    request.cookies.get(BUILTIN_SESSION_COOKIE)?.value
  );
  if (isProtectedRoute && !claims) {
    const redirectUrl = new URL('/sign-in', request.url);
    const { pathname } = request.nextUrl;
    if (pathname !== '/sign-in') {
      redirectUrl.searchParams.set('redirect', pathname);
    }
    return NextResponse.redirect(redirectUrl);
  }
  return NextResponse.next();
}

export async function middleware(request: NextRequest) {
  // Desktop builds serve the renderer from their own local Next server; local
  // (logged-out) mode must reach /dashboard, so skip the auth redirect.
  if (process.env.NEXT_PUBLIC_VICOA_DESKTOP === '1') {
    // The bare dashboard home has no CLI/mobile onboarding to show on desktop;
    // open New Session by default instead of the "pick a session" empty state.
    const { pathname } = request.nextUrl;
    if (pathname === '/dashboard' || pathname === '/dashboard/') {
      return NextResponse.redirect(new URL('/dashboard/agents/new-session', request.url));
    }
    return NextResponse.next();
  }

  const { pathname } = request.nextUrl;
  const isProtectedRoute = pathname.startsWith(protectedRoutes);

  if (isBuiltinAuth()) {
    return builtinMiddleware(request, isProtectedRoute);
  }

  // Handle Supabase auth middleware
  try {
    const supabaseResponse = await createClient(request);
    
    // Get updated request and response from Supabase middleware
    const {
      data: { user },
      error
    } = await supabaseResponse.supabase.auth.getUser();

    // If accessing protected route without authentication, redirect to sign-in
    if (isProtectedRoute && (!user || error)) {
      const redirectUrl = new URL('/sign-in', request.url);
      if (pathname !== '/sign-in') {
        redirectUrl.searchParams.set('redirect', pathname);
      }
      return NextResponse.redirect(redirectUrl);
    }

    // Return the response from Supabase middleware (which handles cookie refresh)
    return supabaseResponse.response;
  } catch (error) {
    console.error('Middleware error:', error);
    
    // If there's an error and we're on a protected route, redirect to sign-in
    if (isProtectedRoute) {
      const redirectUrl = new URL('/sign-in', request.url);
      if (pathname !== '/sign-in') {
        redirectUrl.searchParams.set('redirect', pathname);
      }
      return NextResponse.redirect(redirectUrl);
    }
    
    // For non-protected routes, continue normally
    return NextResponse.next();
  }
}

export const config = {
  matcher: ['/((?!api|_next/static|_next/image|favicon.ico).*)']
};
