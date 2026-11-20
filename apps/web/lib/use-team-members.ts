'use client';

/**
 * The people of a team, as principals: who a task on that team's project can
 * be assigned to besides you and the agents.
 *
 * Reads `GET /teams/{id}`, which any member may call, under the key the
 * Teams settings page uses, so the two share one cache and a member added
 * there shows up here. Only active members with an account are listed: an
 * invite still waiting has nobody to assign yet.
 */

import { useMemo } from 'react';
import useSWR from 'swr';

import { getBackendAPI, type TeamDetail } from '@/lib/backend-api';
import type { Principal } from '@/lib/principals';
import { isDesktopLocal } from '@/lib/runtime-config';

export function useTeamMembers(teamId: string | null | undefined): Principal[] {
  const { data } = useSWR<TeamDetail>(
    // Teams live on the cloud backend; the signed-out desktop has none.
    teamId && !isDesktopLocal() ? ['team', teamId] : null,
    () => getBackendAPI(true).getTeam(teamId!),
    { revalidateOnFocus: false, shouldRetryOnError: false },
  );
  return useMemo(
    () =>
      (data?.members ?? [])
        .filter((member) => member.status === 'active' && member.user_id)
        .map((member) => ({
          type: 'user' as const,
          id: member.user_id,
          name: member.display_name,
          avatarImageUri: member.avatar_image_uri,
        })),
    [data],
  );
}
