import type { Metadata } from 'next';
import { notFound } from 'next/navigation';
import { getSupabaseToken } from '@/lib/auth/supabase-helpers';
import { fetchPublicShare } from '@/lib/public-share-api';
import type { PublicShareResponse } from '@/lib/backend-api';
import { ShareViewer } from './share-viewer';

// The token is the capability and the target is live — nothing here may be
// cached or prerendered.
export const dynamic = 'force-dynamic';
export const revalidate = 0;

/**
 * Resolve the share server-side, forwarding the visitor's own session token
 * when they have one so an `authenticated`-audience link renders on first
 * paint (and gets OG tags) instead of after a client round trip. Any failure
 * is the same `null`: the viewer shows one "not available" page (§10.5).
 */
async function loadShare(token: string): Promise<PublicShareResponse | null> {
  const accessToken = await getSupabaseToken(true).catch(() => null);
  try {
    return await fetchPublicShare(token, { accessToken });
  } catch {
    return null;
  }
}

function shareTitle(share: PublicShareResponse): string {
  if (share.kind === 'session') return share.session?.name || 'Shared session';
  if (share.kind === 'project_board') return `${share.project?.name ?? 'Project'} · Board`;
  return `${share.project?.name ?? 'Project'} · Sessions`;
}

function shareDescription(share: PublicShareResponse): string {
  const by = share.owner.name ? ` by ${share.owner.name}` : '';
  if (share.kind === 'session') {
    const agent = share.session?.agent_profile?.name ?? share.session?.agent_type_name ?? 'an agent';
    const count = share.session?.message_count ?? 0;
    return `A ${agent} session${by} — ${count} message${count === 1 ? '' : 's'}. Shared read-only via Vicoa.`;
  }
  if (share.kind === 'project_board') return `A task board${by}. Shared read-only via Vicoa.`;
  return `Agent sessions${by}. Shared read-only via Vicoa.`;
}

export async function generateMetadata({ params }: { params: Promise<{ token: string }> }): Promise<Metadata> {
  const { token } = await params;
  const share = await loadShare(token);
  const title = share ? shareTitle(share) : 'Shared via Vicoa';
  const description = share ? shareDescription(share) : 'This link is not available.';
  return {
    title: `${title} · Vicoa`,
    description,
    robots: { index: false, follow: false, googleBot: { index: false, follow: false } },
    openGraph: { title, description, type: 'website', siteName: 'Vicoa' },
    twitter: { card: 'summary', title, description },
  };
}

export default async function SharePage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  const share = await loadShare(token);
  // A real 404 (see app/s/not-found.tsx): the token space must not be an
  // oracle, so unknown, revoked, expired and wrong-audience all land here.
  if (!share) notFound();
  return <ShareViewer token={token} share={share} />;
}
