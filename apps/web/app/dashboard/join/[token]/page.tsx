'use client';

/**
 * Join a team from an invite link (collaboration §3.3).
 *
 * Lives under /dashboard so middleware bounces a signed-out visitor through
 * sign-in and back here; the token is in the path, so it survives the bounce.
 * It renders inside the normal dashboard shell (the segment layout wraps every
 * /dashboard page), with the card centred in the main area.
 *
 * Exactly three states: loading, a valid invite, or "invalid or expired". The
 * backend answers one uniform 404 for unknown, revoked, expired and used-up
 * tokens, and this page does not try to tell them apart.
 *
 * The account line and Log out stay pinned at the top: the commonest failure
 * is being signed in as the wrong person, and that is the way out.
 */

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import useSWR, { useSWRConfig } from 'swr';
import { ArrowLeft, Link2Off, Loader2, LogOut } from 'lucide-react';

import { SeatLimitNotice } from '@/components/billing/seat-limit-notice';
import { Button } from '@/components/ui/button';
import { PrincipalAvatar } from '@/components/ui/principal-avatar';
import { signOutBrowser } from '@/lib/auth/sign-out';
import type { AuthUser } from '@/lib/auth/user';
import { getBackendAPI, type TeamInvitePreview, type UserProfile } from '@/lib/backend-api';
import { getDesktopAuthBridge } from '@/lib/desktop-auth';
import {
  errorStatus,
  memberCountLabel,
  roleWithArticle,
  teamJoinPath,
  teamsSettingsHref,
  toTeamActionError,
  type TeamActionError,
} from '@/lib/team-settings';
import { TEAMS_KEY } from '@/lib/use-team-invitations';
import { cn } from '@/lib/utils';

// Compile-time constant (same signal the dashboard shell uses), so it is
// identical on server and client.
const IS_DESKTOP = process.env.NEXT_PUBLIC_VICOA_DESKTOP === '1';

const userFetcher = (url: string): Promise<AuthUser | null> =>
  fetch(url).then((res) => (res.ok ? res.json() : null));

function safeDecode(value: string): string {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

type PreviewState =
  | { kind: 'loading' }
  | { kind: 'valid'; preview: TeamInvitePreview }
  | { kind: 'invalid' };

export default function JoinTeamPage() {
  const params = useParams<{ token: string }>();
  const token = typeof params?.token === 'string' ? safeDecode(params.token) : '';
  const router = useRouter();
  const { mutate } = useSWRConfig();

  // Which account is signed in, so a wrong one is noticeable. The web reads
  // the same SWR entry as the dashboard chrome; the desktop renderer has no
  // Next-side session to read, so it asks the backend.
  const { data: webUser } = useSWR<AuthUser | null>(IS_DESKTOP ? null : '/api/supabase-user', userFetcher);
  const { data: desktopUser } = useSWR<UserProfile>(
    IS_DESKTOP ? 'join-page:me' : null,
    () => getBackendAPI(true).getCurrentUserProfile(),
    { shouldRetryOnError: false },
  );
  const email = (IS_DESKTOP ? desktopUser?.email : webUser?.email) || null;

  const [state, setState] = useState<PreviewState>({ kind: 'loading' });
  useEffect(() => {
    if (!token) {
      setState({ kind: 'invalid' });
      return;
    }
    let cancelled = false;
    setState({ kind: 'loading' });
    getBackendAPI(true)
      .previewTeamInviteLink(token)
      .then((preview) => {
        if (!cancelled) setState({ kind: 'valid', preview });
      })
      .catch(() => {
        if (!cancelled) setState({ kind: 'invalid' });
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  const [joining, setJoining] = useState(false);
  const [joinError, setJoinError] = useState<TeamActionError | null>(null);
  const [alreadyMember, setAlreadyMember] = useState(false);

  const join = async () => {
    if (joining || state.kind !== 'valid') return;
    setJoining(true);
    setJoinError(null);
    setAlreadyMember(false);
    try {
      const team = await getBackendAPI(true).acceptTeamInviteLink(token);
      void mutate(TEAMS_KEY);
      router.push(teamsSettingsHref(team.id));
    } catch (err) {
      const status = errorStatus(err);
      if (status === 404) {
        // Used up or revoked between the preview and the click.
        setState({ kind: 'invalid' });
      } else if (status === 409) {
        setAlreadyMember(true);
      } else {
        setJoinError(toTeamActionError(err, 'Failed to join the team'));
      }
      setJoining(false);
    }
  };

  const [loggingOut, setLoggingOut] = useState(false);
  const logOut = async () => {
    if (loggingOut) return;
    setLoggingOut(true);
    try {
      await signOutBrowser();
    } catch {
      // Best-effort, like the account menus: the redirect below still leaves.
    }
    if (IS_DESKTOP) {
      // The shell owns desktop sign-in; it restarts signed-out and reloads.
      const bridge = getDesktopAuthBridge();
      try {
        const result = await bridge?.signOut();
        if (result?.ok) return;
      } catch {
        // Fall through and re-enable the button.
      }
      setLoggingOut(false);
      return;
    }
    // Back through sign-in to this same link, so switching accounts keeps the invite.
    window.location.href = `/sign-in?redirect=${encodeURIComponent(teamJoinPath(token))}`;
  };

  return (
    <div className={cn('flex min-h-full flex-col font-mono', IS_DESKTOP && 'pt-8')}>
      <div className="flex items-center justify-between gap-3">
        <Link
          href="/dashboard"
          className="inline-flex shrink-0 cursor-pointer items-center gap-1.5 rounded-md px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-foreground/[0.06] hover:text-foreground dark:hover:bg-foreground/10"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Back
        </Link>
        <div className="flex min-w-0 items-center gap-2">
          {email && (
            <span className="min-w-0 truncate text-xs text-muted-foreground" title={email}>
              Signed in as {email}
            </span>
          )}
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-7 shrink-0 gap-1.5 px-2 text-xs text-muted-foreground hover:text-foreground"
            onClick={() => void logOut()}
            disabled={loggingOut}
          >
            {loggingOut ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <LogOut className="h-3.5 w-3.5" />}
            Log out
          </Button>
        </div>
      </div>

      <div className="flex flex-1 items-center justify-center py-10">
        <div className="w-full max-w-sm rounded-xl border border-border/60 bg-card px-6 py-8 text-center shadow-sm">
          {state.kind === 'loading' ? (
            <div className="flex items-center justify-center gap-2 py-6 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading invite…
            </div>
          ) : state.kind === 'invalid' ? (
            <div className="flex flex-col items-center">
              <span className="flex size-14 items-center justify-center rounded-full bg-muted text-muted-foreground">
                <Link2Off className="size-6" />
              </span>
              <h1 className="mt-4 text-lg font-light tracking-tight text-foreground">
                This invite link is invalid or has expired
              </h1>
              <p className="mt-2 text-sm text-muted-foreground">Ask whoever sent it for a new one.</p>
            </div>
          ) : (
            <div className="flex flex-col items-center">
              <PrincipalAvatar
                principal={{
                  type: 'team',
                  id: state.preview.team_id,
                  name: state.preview.name,
                  avatarImageUri: state.preview.avatar_image_uri,
                }}
                size="lg"
              />
              <h1 className="mt-4 max-w-full truncate text-xl font-light tracking-tight text-foreground">
                Join {state.preview.name}
              </h1>
              <p className="mt-2 text-sm text-muted-foreground">
                You&apos;ve been invited to join as {roleWithArticle(state.preview.role)}.
              </p>
              <p className="mt-1 text-xs text-muted-foreground">{memberCountLabel(state.preview.member_count)}</p>
              <Button type="button" className="mt-6 w-full" onClick={() => void join()} disabled={joining}>
                {joining && <Loader2 className="h-4 w-4 animate-spin" />}
                Join team
              </Button>
              {alreadyMember && (
                <p className="mt-3 text-xs text-muted-foreground">
                  You&apos;re already on this team.{' '}
                  <Link
                    href={teamsSettingsHref(state.preview.team_id)}
                    className="cursor-pointer text-foreground underline underline-offset-2 hover:text-foreground/80"
                  >
                    Open it
                  </Link>
                </p>
              )}
              {joinError?.kind === 'seat-limit' && (
                <SeatLimitNotice detail={joinError.detail} className="mt-3 w-full text-left" />
              )}
              {joinError?.kind === 'message' && (
                <p className="mt-3 text-xs text-destructive">{joinError.message}</p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
