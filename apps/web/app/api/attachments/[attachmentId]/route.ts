import { NextRequest, NextResponse } from 'next/server';
import { getSupabaseToken } from '@/lib/auth/supabase-helpers';

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * Stream an attachment's bytes through cookie-authenticated Next.js, so plain
 * <img src="/api/attachments/{id}"> tags (and file-download links) work without
 * the client ever holding the backend bearer token. Non-image files carry the
 * backend's Content-Disposition so they download under their original name.
 * Responses are immutable per id.
 */
export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ attachmentId: string }> }
) {
  try {
    const { attachmentId } = await params;
    if (!UUID_PATTERN.test(attachmentId)) {
      return NextResponse.json({ error: 'Invalid attachment id' }, { status: 400 });
    }

    const accessToken = await getSupabaseToken(true);

    if (!accessToken) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const backendUrl = process.env.NEXT_PUBLIC_BACKEND_API_URL || 'http://localhost:8000';
    const response = await fetch(`${backendUrl}/api/v1/attachments/${attachmentId}`, {
      headers: {
        'Authorization': `Bearer ${accessToken}`,
      },
    });

    if (!response.ok || !response.body) {
      return NextResponse.json(
        { error: `Backend responded with ${response.status}` },
        { status: response.status }
      );
    }

    const headers: Record<string, string> = {
      'Content-Type': response.headers.get('content-type') ?? 'application/octet-stream',
      'Cache-Control': 'private, max-age=31536000, immutable',
      'X-Content-Type-Options': 'nosniff',
    };
    // Forward the backend's attachment disposition (non-raster files) so they
    // download under their name and can't execute in the vicoa-web origin.
    const disposition = response.headers.get('content-disposition');
    if (disposition) headers['Content-Disposition'] = disposition;

    return new NextResponse(response.body, { status: 200, headers });
  } catch (error) {
    console.error('Attachment download failed:', error);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Unknown error' },
      { status: 500 }
    );
  }
}
