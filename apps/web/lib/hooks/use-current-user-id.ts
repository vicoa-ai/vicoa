'use client';

import { useEffect, useState } from 'react';

import type BackendAPI from '@/lib/backend-api';

// One profile fetch per API client, however many surfaces ask: the sidebar
// and the session page both need to tell "me" from the other people in a
// shared session. Keyed by the client so signing in as someone else (a new
// client) never reads the previous account's id.
const pending = new WeakMap<BackendAPI, Promise<string | null>>();

function currentUserId(api: BackendAPI): Promise<string | null> {
  let request = pending.get(api);
  if (!request) {
    request = api
      .getCurrentUserProfile()
      .then((profile) => profile.id)
      .catch(() => {
        // Let the next caller retry rather than caching a failure.
        pending.delete(api);
        return null;
      });
    pending.set(api, request);
  }
  return request;
}

/** The signed-in user's id, or null until known (or when `api` is null). */
export function useCurrentUserId(api: BackendAPI | null | undefined): string | null {
  const [userId, setUserId] = useState<string | null>(null);
  useEffect(() => {
    if (!api) return;
    let live = true;
    void currentUserId(api).then((id) => {
      if (live) setUserId(id);
    });
    return () => {
      live = false;
    };
  }, [api]);
  return userId;
}
