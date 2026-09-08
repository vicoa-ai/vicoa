import { NextRequest, NextResponse } from 'next/server';
import { getSupabaseToken } from '@/lib/auth/supabase-helpers';

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * Stream a principal's avatar bytes through cookie-authenticated Next.js, so a
 * plain <img src="/api/users/{id}/avatar"> works without the client ever
 * holding the backend bearer token — the exact mirror of
 * /api/projects/[projectId]/icon. The backend URL is stable across
 * replacements, so callers cache-bust with the row's updated_at
 * (see lib/principals.ts).
 */
export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ userId: string }> }
) {
  try {
    const { userId } = await params;
    if (!UUID_PATTERN.test(userId)) {
      return NextResponse.json({ error: 'Invalid user id' }, { status: 400 });
    }

    const accessToken = await getSupabaseToken(true);
    if (!accessToken) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const backendUrl = process.env.NEXT_PUBLIC_BACKEND_API_URL || 'http://localhost:8000';
    const response = await fetch(`${backendUrl}/api/v1/users/${userId}/avatar`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    });

    if (!response.ok || !response.body) {
      return NextResponse.json(
        { error: `Backend responded with ${response.status}` },
        { status: response.status }
      );
    }

    return new NextResponse(response.body, {
      status: 200,
      headers: {
        'Content-Type': response.headers.get('content-type') ?? 'application/octet-stream',
        'Cache-Control': 'private, max-age=300',
        'X-Content-Type-Options': 'nosniff',
      },
    });
  } catch (error) {
    console.error('User avatar fetch failed:', error);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Unknown error' },
      { status: 500 }
    );
  }
}
