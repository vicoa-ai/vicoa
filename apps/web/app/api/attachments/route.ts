import { NextRequest, NextResponse } from 'next/server';
import { getSupabaseToken } from '@/lib/auth/supabase-helpers';

/**
 * Proxy an image attachment upload to the FastAPI backend.
 *
 * The browser posts multipart form data (`file` + `agent_instance_id`); we
 * re-attach the user's bearer token server-side (same pattern as
 * /api/agent-dashboard/direct) and forward the backend's JSON verbatim —
 * including validation errors (400 unsupported image, 413 too large).
 */
export async function POST(request: NextRequest) {
  try {
    const accessToken = await getSupabaseToken(true);

    if (!accessToken) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const formData = await request.formData();
    const backendUrl = process.env.NEXT_PUBLIC_BACKEND_API_URL || 'http://localhost:8000';
    const response = await fetch(`${backendUrl}/api/v1/attachments`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${accessToken}`,
      },
      body: formData,
    });

    const body = await response.text();
    return new NextResponse(body, {
      status: response.status,
      headers: { 'Content-Type': 'application/json' },
    });
  } catch (error) {
    console.error('Attachment upload failed:', error);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Unknown error' },
      { status: 500 }
    );
  }
}
