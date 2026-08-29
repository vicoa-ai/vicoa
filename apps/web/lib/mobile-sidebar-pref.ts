'use client';

/**
 * Visibility preference for the "Vicoa Mobile" sidebar entry. Persisted via the
 * desktop settings bridge (falls back to localStorage on web). A same-document
 * event lets the sidebar and the page/settings toggle stay in sync live — the
 * native `storage` event only fires cross-tab, so we dispatch our own.
 */

import { useEffect, useState } from 'react';
import { getPref, setPref } from './desktop-prefs';

const MOBILE_HIDDEN_KEY = 'sidebar-mobile-hidden';
const CHANGE_EVENT = 'vicoa:mobile-sidebar-pref';

export function isMobileSidebarHidden(): boolean {
  return getPref<boolean>(MOBILE_HIDDEN_KEY) === true;
}

export function setMobileSidebarHidden(hidden: boolean): void {
  // Store `true` when hidden; clear the key when shown (the default is shown).
  setPref(MOBILE_HIDDEN_KEY, hidden ? true : null);
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event(CHANGE_EVENT));
  }
}

/** Reactive read: re-renders when the preference changes in this document. */
export function useMobileSidebarHidden(): boolean {
  const [hidden, setHidden] = useState(false);
  useEffect(() => {
    const read = () => setHidden(isMobileSidebarHidden());
    read(); // post-mount so SSR stays consistent
    window.addEventListener(CHANGE_EVENT, read);
    return () => window.removeEventListener(CHANGE_EVENT, read);
  }, []);
  return hidden;
}
