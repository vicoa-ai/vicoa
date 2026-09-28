'use client';

/**
 * The account menu's way into teams, shared by the web user menu
 * (`app/dashboard/dashboard-layout.tsx`) and the desktop `CloudAccountArea`
 * (`components/dashboard/desktop-sidebar.tsx`):
 *
 * - `<AccountMenuInvitations />` goes inside an open `DropdownMenuContent`: a
 *   "Teams" item, then, while any are pending, the invitations addressed to
 *   the signed-in user with inline Join / Decline.
 * - `<InvitationDot />` sits on the avatar trigger (a `relative` box) while
 *   any invitation is pending, so the menu is worth opening.
 *
 * Both read `useTeamInvitations`, so they share one request and clear
 * together. Teams are groups you share work with, not workspaces: there is no
 * switcher here.
 */

import { useState, type MouseEvent } from 'react';
import Link from 'next/link';
import { Loader2, Users } from 'lucide-react';

import { SeatLimitNotice } from '@/components/billing/seat-limit-notice';
import { DropdownMenuItem, DropdownMenuLabel } from '@/components/ui/dropdown-menu';
import { PrincipalAvatar } from '@/components/ui/principal-avatar';
import { seatLimitFromError, type TeamInvitation } from '@/lib/backend-api';
import { invitedYouLine, teamsSettingsHref } from '@/lib/team-settings';
import { useTeamInvitations } from '@/lib/use-team-invitations';
import { cn } from '@/lib/utils';

export function AccountMenuInvitations({
  itemClassName,
  rowClassName,
}: {
  /** Classes for the "Teams" item, to match the host menu's items. */
  itemClassName?: string;
  /** Horizontal padding for the label and invitation rows, to line them up
   *  with the host menu's items. */
  rowClassName?: string;
}) {
  const { invitations, accept, decline } = useTeamInvitations();

  return (
    <>
      <DropdownMenuItem asChild className={cn('cursor-pointer', itemClassName)}>
        <Link href={teamsSettingsHref()} className="flex w-full items-center gap-2">
          <Users className="h-4 w-4" />
          <span>Teams</span>
        </Link>
      </DropdownMenuItem>
      {invitations.length > 0 && (
        <>
          <DropdownMenuLabel
            className={cn('pt-2 pb-1 text-[0.8rem] font-normal text-muted-foreground', rowClassName)}
          >
            Pending invitations
          </DropdownMenuLabel>
          {invitations.map((invitation) => (
            <InvitationRow
              key={invitation.team_id}
              invitation={invitation}
              className={rowClassName}
              onAccept={() => accept(invitation.team_id)}
              onDecline={() => decline(invitation.team_id)}
            />
          ))}
        </>
      )}
    </>
  );
}

/**
 * Plain buttons in a plain div, not menu items: selecting a Radix item closes
 * the menu, and a Join that shuts the menu before its row can say what
 * happened (or a seat limit) reads as nothing happening.
 */
function InvitationRow({
  invitation,
  className,
  onAccept,
  onDecline,
}: {
  invitation: TeamInvitation;
  className?: string;
  onAccept: () => Promise<unknown>;
  onDecline: () => Promise<unknown>;
}) {
  const [busy, setBusy] = useState<'accept' | 'decline' | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [seatLimit, setSeatLimit] = useState<string | null>(null);

  const run = (which: 'accept' | 'decline', action: () => Promise<unknown>) =>
    async (event: MouseEvent<HTMLButtonElement>) => {
      event.preventDefault();
      event.stopPropagation();
      if (busy) return;
      setBusy(which);
      setError(null);
      setSeatLimit(null);
      try {
        await action();
      } catch (err) {
        const limit = seatLimitFromError(err);
        if (limit) setSeatLimit(limit.detail);
        else setError(err instanceof Error ? err.message : 'Something went wrong');
        setBusy(null);
      }
    };

  return (
    <div className={cn('px-2 py-1.5', className)}>
      <div className="flex items-center gap-2">
        <PrincipalAvatar
          principal={{
            type: 'team',
            id: invitation.team_id,
            name: invitation.name,
            avatarImageUri: invitation.avatar_image_uri,
          }}
          size="sm"
        />
        <div className="min-w-0 flex-1">
          <div className="truncate text-xs text-foreground" title={invitation.name}>
            {invitation.name}
          </div>
          <div className="truncate text-[11px] text-muted-foreground">
            {invitedYouLine(invitation.invited_by_display_name, invitation.role)}
          </div>
        </div>
      </div>
      <div className="mt-1.5 flex items-center gap-1.5 pl-8">
        <button
          type="button"
          disabled={busy !== null}
          onClick={run('accept', onAccept)}
          className="inline-flex h-6 cursor-pointer items-center gap-1 rounded-md bg-primary px-2 text-[11px] text-primary-foreground transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {busy === 'accept' && <Loader2 className="h-3 w-3 animate-spin" />}
          Join
        </button>
        <button
          type="button"
          disabled={busy !== null}
          onClick={run('decline', onDecline)}
          className="inline-flex h-6 cursor-pointer items-center gap-1 rounded-md px-2 text-[11px] text-muted-foreground transition-colors hover:bg-foreground/[0.06] hover:text-foreground disabled:cursor-not-allowed disabled:opacity-60 dark:hover:bg-foreground/10"
        >
          {busy === 'decline' && <Loader2 className="h-3 w-3 animate-spin" />}
          Decline
        </button>
      </div>
      {error && <p className="mt-1 pl-8 text-[11px] text-destructive">{error}</p>}
      {seatLimit !== null && <SeatLimitNotice detail={seatLimit} className="mt-1.5" />}
    </div>
  );
}

/** A small dot on the account avatar while any invitation is pending. The
 *  parent must be `relative`. */
export function InvitationDot({ className }: { className?: string }) {
  const { invitations } = useTeamInvitations();
  if (invitations.length === 0) return null;
  const label = `${invitations.length} pending team ${invitations.length === 1 ? 'invitation' : 'invitations'}`;
  return (
    <span
      role="status"
      aria-label={label}
      title={label}
      className={cn(
        'pointer-events-none absolute -top-0.5 -right-0.5 size-2 rounded-full bg-primary ring-2 ring-background',
        className,
      )}
    />
  );
}
