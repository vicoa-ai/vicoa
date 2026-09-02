import { NextRequest, NextResponse } from 'next/server';
import { getSupabaseToken } from '@/lib/auth/supabase-helpers';

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * Stream a project's icon bytes through cookie-authenticated Next.js, so plain
 * <img src="/api/projects/{id}/icon"> tags work without the client ever holding
 * the backend bearer token — mirrors /api/attachments/[attachmentId]. The
 * backend URL (projects.icon_image_uri) is stable across replacements, so
 * callers cache-bust with the project's updated_at (see lib/project-icons.ts).
 */
export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ projectId: string }> }
) {
  try {
    const { projectId } = await params;
    if (!UUID_PATTERN.test(projectId)) {
      return NextResponse.json({ error: 'Invalid project id' }, { status: 400 });
    }

    const accessToken = await getSupabaseToken(true);
    if (!accessToken) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const backendUrl = process.env.NEXT_PUBLIC_BACKEND_API_URL || 'http://localhost:8000';
    const response = await fetch(`${backendUrl}/api/v1/projects/${projectId}/icon`, {
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
    console.error('Project icon fetch failed:', error);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Unknown error' },
      { status: 500 }
    );
  }
}
