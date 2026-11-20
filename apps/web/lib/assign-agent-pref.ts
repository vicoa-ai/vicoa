'use client';

/**
 * Whether picking an agent as a task's assignee asks first (Settings → Tasks,
 * and the assign dialog's "Don't ask again"). On by default: assigning an
 * agent starts it on one of your computers, so the dialog shows where before it
 * does. Off, picking the agent assigns and starts it right away with the
 * defaults (the agent's computer, the project's folder there).
 *
 * Kept on this device, like the archive preference next to it
 * (`archive-task-pref.ts`): the desktop app writes it to its settings file, the
 * web to localStorage. The server never reads it.
 */

import { useEffect, useState } from 'react';
import { getPref, setPref } from './desktop-prefs';

const KEY = 'confirm-agent-start';
const CHANGE_EVENT = 'vicoa:confirm-agent-start';

/** The stored answer; `true` (ask) when nothing is stored. */
export function confirmAgentStart(): boolean {
  return getPref<unknown>(KEY) !== false;
}

export function setConfirmAgentStart(confirm: boolean): void {
  // Asking is the default, so it is the absent key.
  setPref(KEY, confirm ? null : false);
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event(CHANGE_EVENT));
  }
}

/** Reactive read: re-renders when the preference changes in this document. */
export function useConfirmAgentStart(): boolean {
  // `true` on the first render so SSR and the first client paint agree; the
  // stored value lands post-mount.
  const [confirm, setConfirm] = useState(true);
  useEffect(() => {
    const read = () => setConfirm(confirmAgentStart());
    read();
    window.addEventListener(CHANGE_EVENT, read);
    return () => window.removeEventListener(CHANGE_EVENT, read);
  }, []);
  return confirm;
}
