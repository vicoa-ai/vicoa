import { NextRequest, NextResponse } from 'next/server';
import { getSupabaseToken } from '@/lib/auth/supabase-helpers';

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * Stream a team's picture through cookie-authenticated Next.js, so a
 * plain <img src="/api/teams/{id}/avatar"> works without the client ever
 * holding the backend bearer token — the exact mirror of
 * /api/projects/[projectId]/icon. The backend URL is stable across
 * replacements, so callers cache-bust with the row's updated_at
 * (see lib/principals.ts).
 */
export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ teamId: string }> }
) {
  try {
    const { teamId } = await params;
    if (!UUID_PATTERN.test(teamId)) {
      return NextResponse.json({ error: 'Invalid team id' }, { status: 400 });
    }

    const accessToken = await getSupabaseToken(true);
    if (!accessToken) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const backendUrl = process.env.NEXT_PUBLIC_BACKEND_API_URL || 'http://localhost:8000';
    const response = await fetch(`${backendUrl}/api/v1/teams/${teamId}/avatar`, {
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
    console.error('Team avatar fetch failed:', error);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Unknown error' },
      { status: 500 }
    );
  }
}
