import { NextRequest, NextResponse } from 'next/server';
import { getSupabaseToken } from '@/lib/auth/supabase-helpers';
import { getBackendAPI } from '@/lib/backend-api';

export async function POST(_request: NextRequest) {
  try {
    // Check authentication
    const accessToken = await getSupabaseToken(true);

    if (!accessToken) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    // Use centralized backend API client to generate CLI key
    try {
      const backendAPI = getBackendAPI(false, accessToken); // Don't read the browser session; use the token resolved above
      const result = await backendAPI.createCliKey();
      
      return NextResponse.json({
        apiKey: result.api_key,
        message: 'API key generated successfully',
        expires: result.expires_at
      });
    } catch (apiError) {
      console.error('Failed to generate API key via backend API:', apiError);
      throw new Error(`CLI key generation failed: ${apiError instanceof Error ? apiError.message : 'Unknown error'}`);
    }

  } catch (error) {
    console.error('CLI auth API key generation failed:', error);
    return NextResponse.json(
      { 
        error: error instanceof Error ? error.message : 'Failed to generate API key',
        details: 'Local API key generation should work without external backend'
      },
      { status: 500 }
    );
  }
}