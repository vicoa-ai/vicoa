'use client';

import { useEffect, useState } from 'react';
import { Bell, X } from 'lucide-react';
import {
  NOTIFICATION_NUDGE_EVENT,
  dismissNotificationNudge,
  getDesktopNotificationsBridge,
  readNotificationAuthorization,
  shouldShowNotificationNudge,
} from '@/lib/desktop-notifications';

/**
 * One-time bar after the first real session banner: macOS notification
 * authorization isn't queryable from Electron, so we can't tell whether that
 * banner was actually displayed — this offers the System Settings jump once,
 * then stays dismissed forever. Users who saw the banner dismiss it in one
 * click; users who didn't get the fix-it path without digging.
 */
export function DesktopNotificationNudge() {
  const [show, setShow] = useState(false);

  useEffect(() => {
    if (getDesktopNotificationsBridge() === null) return;
    let cancelled = false;
    const sync = () => {
      if (!shouldShowNotificationNudge()) {
        setShow(false);
        return;
      }
      // Armed + undismissed: suppress anyway when macOS says notifications
      // are already allowed (the banner was really shown, no help needed).
      // null = no helper (dev) — stay conservative and show the nudge.
      void readNotificationAuthorization().then((status) => {
        if (!cancelled) setShow(status !== 'authorized');
      });
    };
    sync();
    window.addEventListener(NOTIFICATION_NUDGE_EVENT, sync);
    return () => {
      cancelled = true;
      window.removeEventListener(NOTIFICATION_NUDGE_EVENT, sync);
    };
  }, []);

  if (!show) return null;

  const openSettings = () => {
    void getDesktopNotificationsBridge()?.openNotificationSettings();
    dismissNotificationNudge();
  };

  return (
    <div className="flex items-center justify-center gap-2 border-b border-border/60 bg-muted/40 px-3 py-1 text-xs font-mono text-muted-foreground">
      <Bell className="h-3 w-3 shrink-0" />
      <span>Vicoa sent you a desktop notification. Didn&apos;t see it?</span>
      <button
        type="button"
        onClick={openSettings}
        className="cursor-pointer underline underline-offset-2 hover:text-foreground"
      >
        Enable in System Settings
      </button>
      <button
        type="button"
        aria-label="Dismiss"
        onClick={() => dismissNotificationNudge()}
        className="ml-1 flex h-4 w-4 cursor-pointer items-center justify-center rounded hover:bg-foreground/10 hover:text-foreground"
      >
        <X className="h-3 w-3" />
      </button>
    </div>
  );
}
