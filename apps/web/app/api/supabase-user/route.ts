import { NextResponse } from 'next/server';
import { createClient } from '@/lib/auth/supabase-server';
import { isBuiltinAuth } from '@/lib/auth/auth-provider';
import { getBuiltinClaimsFromCookies } from '@/lib/auth/builtin-server';
import { getSupabaseToken } from '@/lib/auth/supabase-helpers';

/**
 * The backend's copy of the caller's identity — the avatar lives there, not in
 * Supabase (we re-host it rather than hot-link the IdP's CDN). Best-effort: a
 * backend hiccup must not sign the user out of the dashboard, it just means
 * `<PrincipalAvatar>` falls back to initials this render.
 */
async function fetchBackendAvatar(): Promise<{
  avatarImageUri: string | null;
  updatedAt: string | null;
}> {
  const empty = { avatarImageUri: null, updatedAt: null };
  try {
    const token = await getSupabaseToken(true);
    if (!token) return empty;
    const backendUrl = process.env.NEXT_PUBLIC_BACKEND_API_URL || 'http://localhost:8000';
    const response = await fetch(`${backendUrl}/api/v1/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: 'no-store',
    });
    if (!response.ok) return empty;
    const profile = await response.json();
    return {
      avatarImageUri: profile?.avatar_image_uri ?? null,
      updatedAt: profile?.updated_at ?? null,
    };
  } catch (error) {
    console.error('Failed to load backend profile avatar:', error);
    return empty;
  }
}

export async function GET() {
  try {
    if (isBuiltinAuth()) {
      // No profile table to consult — the session token already carries the
      // name and email the dashboard renders.
      const claims = await getBuiltinClaimsFromCookies();
      if (!claims) {
        return NextResponse.json({ error: 'Not authenticated' }, { status: 401 });
      }
      return NextResponse.json({
        id: claims.sub,
        name: claims.name ?? '',
        email: claims.email ?? '',
        role: 'member',
        ...(await fetchBackendAvatar()),
      });
    }

    const supabase = await createClient();
    const { data: { user }, error } = await supabase.auth.getUser();
    
    if (error || !user) {
      return NextResponse.json({ error: 'Not authenticated' }, { status: 401 });
    }

    let displayName = '';

    // Attempt to read the profile's display name from Supabase.
    const profileById = await supabase
      .from('profiles')
      .select('display_name')
      .eq('id', user.id)
      .maybeSingle();

    if (profileById.error) {
      console.error('Failed to load profile by id:', profileById.error.message);
    } else if (profileById.data) {
      displayName = profileById.data.display_name ?? '';
    }

    // Return user data in a format compatible with the dashboard
    const userData = {
      id: user.id,
      name: displayName || user.user_metadata?.name || '',
      email: user.email,
      createdAt: user.created_at,
      role: user.user_metadata?.role || 'member',
      ...(await fetchBackendAvatar()),
    };

    return NextResponse.json(userData);
  } catch (error) {
    console.error('Get supabase user error:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
