'use client';

/**
 * What archiving a session does to the task it works on, as a standing answer
 * (Settings → Tasks): `ask` (the archive dialog asks each time), `mark_done`
 * (the task follows the session, as it always has) or `leave` (the task keeps
 * its status).
 *
 * Kept on this device, like the sidebar and theme preferences: the desktop app
 * writes it to its settings file, the web to localStorage. The server never
 * reads it. The web puts it into each archive request (`archiveStatusBody`), so
 * every archive from here follows it, and a client that does not know about it
 * (the phone) archives as before.
 */

import { useEffect, useState } from 'react';
import { getPref, setPref } from './desktop-prefs';

export type ArchiveTaskAction = 'ask' | 'mark_done' | 'leave';

const KEY = 'archive-task-action';
const CHANGE_EVENT = 'vicoa:archive-task-action';
const ACTIONS: readonly ArchiveTaskAction[] = ['ask', 'mark_done', 'leave'];

/** The stored answer; `ask` when none is stored or the value is not one we know. */
export function archiveTaskAction(): ArchiveTaskAction {
  const stored = getPref<unknown>(KEY);
  return ACTIONS.find((action) => action === stored) ?? 'ask';
}

export function setArchiveTaskAction(action: ArchiveTaskAction): void {
  // `ask` is the default, so it is the absent key: a value added later does not
  // have to be migrated for anyone who never changed it.
  setPref(KEY, action === 'ask' ? null : action);
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event(CHANGE_EVENT));
  }
}

/** Reactive read: re-renders when the preference changes in this document. */
export function useArchiveTaskAction(): ArchiveTaskAction {
  // `ask` on the first render so SSR and the first client paint agree; the
  // stored value lands post-mount.
  const [action, setAction] = useState<ArchiveTaskAction>('ask');
  useEffect(() => {
    const read = () => setAction(archiveTaskAction());
    read();
    window.addEventListener(CHANGE_EVENT, read);
    return () => window.removeEventListener(CHANGE_EVENT, read);
  }, []);
  return action;
}
