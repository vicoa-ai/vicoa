'use client';

import { useEffect, useMemo, useState } from 'react';

import type BackendAPI from '@/lib/backend-api';
import type { UserProfile } from '@/lib/backend-api';
import type { Principal } from '@/lib/principals';

// One profile fetch per API client, however many surfaces ask: the sidebar
// and the session page both need to tell "me" from the other people in a
// shared session. Keyed by the client so signing in as someone else (a new
// client) never reads the previous account's profile.
const pending = new WeakMap<BackendAPI, Promise<UserProfile | null>>();

function currentUser(api: BackendAPI): Promise<UserProfile | null> {
  let request = pending.get(api);
  if (!request) {
    request = api.getCurrentUserProfile().catch(() => {
      // Let the next caller retry rather than caching a failure.
      pending.delete(api);
      return null;
    });
    pending.set(api, request);
  }
  return request;
}

function useCurrentUser(api: BackendAPI | null | undefined): UserProfile | null {
  const [profile, setProfile] = useState<UserProfile | null>(null);
  useEffect(() => {
    if (!api) return;
    let live = true;
    void currentUser(api).then((next) => {
      if (live) setProfile(next);
    });
    return () => {
      live = false;
    };
  }, [api]);
  return profile;
}

/** The signed-in user's id, or null until known (or when `api` is null). */
export function useCurrentUserId(api: BackendAPI | null | undefined): string | null {
  return useCurrentUser(api)?.id ?? null;
}

/** The signed-in user as a principal (name + avatar), for pickers that list
 *  them as "you". Their own email stands in for a missing display name. */
export function useCurrentUserPrincipal(api: BackendAPI | null | undefined): Principal | null {
  const profile = useCurrentUser(api);
  return useMemo(
    () =>
      profile
        ? {
            type: 'user',
            id: profile.id,
            name: profile.display_name ?? profile.email,
            avatarImageUri: profile.avatar_image_uri,
            emoji: profile.avatar_emoji,
            updatedAt: profile.updated_at,
          }
        : null,
    [profile],
  );
}
