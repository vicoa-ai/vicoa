import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { exchangeCodeForSession } = vi.hoisted(() => ({
  exchangeCodeForSession: vi.fn(),
}));

vi.mock('@/lib/auth/supabase-server', () => ({
  createClient: async () => ({ auth: { exchangeCodeForSession } }),
}));
vi.mock('@/lib/posthog-server', () => ({
  captureServerEvent: vi.fn(async () => undefined),
}));

import { GET } from './route';

const BASE = 'https://vicoa.example.com';

/** A signed-in user; `fresh` makes them look just created (new_user=1). */
function signedIn(fresh: boolean) {
  const now = new Date();
  const createdAt = fresh ? now : new Date(now.getTime() - 30 * 24 * 3600 * 1000);
  return {
    data: {
      user: {
        id: 'user-1',
        app_metadata: { provider: 'google' },
        created_at: createdAt.toISOString(),
        last_sign_in_at: now.toISOString(),
      },
    },
    error: null,
  };
}

async function landAfterCallback(next: string | null, fresh = false): Promise<string | null> {
  exchangeCodeForSession.mockResolvedValueOnce(signedIn(fresh));
  const url = new URL('/api/auth/callback', BASE);
  url.searchParams.set('code', 'oauth-code');
  if (next !== null) url.searchParams.set('next', next);
  const response = await GET(new Request(url));
  return response.headers.get('location');
}

beforeEach(() => {
  vi.stubEnv('BASE_URL', BASE);
});

afterEach(() => {
  vi.unstubAllEnvs();
  exchangeCodeForSession.mockReset();
});

describe('GET /api/auth/callback', () => {
  it('sends an off-site `next` to the dashboard instead', async () => {
    expect(await landAfterCallback('https://evil.com/phish')).toBe(`${BASE}/dashboard`);
    expect(await landAfterCallback('//evil.com/phish')).toBe(`${BASE}/dashboard`);
    expect(await landAfterCallback('/\\evil.com')).toBe(`${BASE}/dashboard`);
    expect(await landAfterCallback('javascript:alert(1)')).toBe(`${BASE}/dashboard`);
  });

  it('honors a same-site path, the desktop handoff included', async () => {
    expect(await landAfterCallback('/desktop-auth?state=abc&resume=1')).toBe(
      `${BASE}/desktop-auth?state=abc&resume=1`
    );
    expect(await landAfterCallback(`${BASE}/cli-auth?port=5000&state=s`)).toBe(
      `${BASE}/cli-auth?port=5000&state=s`
    );
  });

  it('defaults to the dashboard without `next`', async () => {
    expect(await landAfterCallback(null)).toBe(`${BASE}/dashboard`);
  });

  it('still marks a brand-new user, on the validated destination', async () => {
    expect(await landAfterCallback('/dashboard/upgrade', true)).toBe(
      `${BASE}/dashboard/upgrade?new_user=1`
    );
    expect(await landAfterCallback('/desktop-auth?state=abc', true)).toBe(
      `${BASE}/desktop-auth?state=abc&new_user=1`
    );
    expect(await landAfterCallback('https://evil.com/phish', true)).toBe(
      `${BASE}/dashboard?new_user=1`
    );
  });
});
