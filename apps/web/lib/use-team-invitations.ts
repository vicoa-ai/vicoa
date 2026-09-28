'use client';

/**
 * Pending team invitations addressed to the signed-in user — one SWR read
 * shared by the account-menu dot, the account-menu rows and Settings → Teams,
 * so accepting in any of them clears all three at once.
 *
 * Invitations live on the cloud backend, so the logged-out desktop (local
 * daemon only) has nothing to ask; the key goes null there and SWR never
 * fetches. Callers also pass `enabled: false` while nobody is signed in.
 */

import { useCallback } from 'react';
import useSWR, { useSWRConfig } from 'swr';

import { getBackendAPI, type TeamInvitation, type TeamSummary } from '@/lib/backend-api';
import { isDesktopLocal } from '@/lib/runtime-config';

export const TEAM_INVITATIONS_KEY = 'team-invitations';
/** SWR key of the caller's teams list (Settings → Teams). Accepting an
 *  invitation revalidates it so a new team shows up without a reload. */
export const TEAMS_KEY = 'teams';

const REFRESH_INTERVAL_MS = 60_000;

export function useTeamInvitations({ enabled = true }: { enabled?: boolean } = {}): {
  invitations: TeamInvitation[];
  isLoading: boolean;
  accept: (teamId: string) => Promise<TeamSummary>;
  decline: (teamId: string) => Promise<void>;
  mutate: () => Promise<TeamInvitation[] | undefined>;
} {
  const { mutate: globalMutate } = useSWRConfig();
  const key = enabled && !isDesktopLocal() ? TEAM_INVITATIONS_KEY : null;
  const { data, isLoading, mutate } = useSWR<TeamInvitation[]>(
    key,
    () => getBackendAPI(true).listTeamInvitations(),
    {
      refreshInterval: REFRESH_INTERVAL_MS,
      revalidateOnFocus: true,
      // A 401 or an older backend without teams would otherwise retry in a
      // tight backoff loop; the interval above already re-polls.
      shouldRetryOnError: false,
    },
  );

  const drop = useCallback(
    (teamId: string) =>
      mutate((current) => (current ?? []).filter((inv) => inv.team_id !== teamId), {
        revalidate: true,
      }),
    [mutate],
  );

  const accept = useCallback(
    async (teamId: string) => {
      const team = await getBackendAPI(true).acceptTeamInvitation(teamId);
      await drop(teamId);
      void globalMutate(TEAMS_KEY);
      return team;
    },
    [drop, globalMutate],
  );

  const decline = useCallback(
    async (teamId: string) => {
      await getBackendAPI(true).declineTeamInvitation(teamId);
      await drop(teamId);
    },
    [drop],
  );

  return {
    invitations: data ?? [],
    isLoading,
    accept,
    decline,
    mutate: () => mutate(),
  };
}
