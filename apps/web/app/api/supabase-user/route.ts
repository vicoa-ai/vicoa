import { NextResponse } from 'next/server';
import { createClient } from '@/lib/auth/supabase-server';
import { isBuiltinAuth } from '@/lib/auth/auth-provider';
import { getBuiltinClaimsFromCookies } from '@/lib/auth/builtin-server';

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
      role: user.user_metadata?.role || 'member'
    };

    return NextResponse.json(userData);
  } catch (error) {
    console.error('Get supabase user error:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
