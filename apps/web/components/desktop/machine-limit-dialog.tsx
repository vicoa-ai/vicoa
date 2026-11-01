'use client';

/**
 * "This computer isn't connected" — the plan has no room for another machine.
 *
 * Worth interrupting for: nothing else in the app says so. The window signs in
 * and shows the account's other machines and sessions, so the only other
 * symptom is this computer never appearing — and the "No machines connected"
 * empty state then tells the user to run the daemon, which is exactly what is
 * being refused.
 *
 * A Vicoa dialog, not Electron's native box: a native one is drawn in the
 * OS's own chrome and ignores the theme, the same reason `window.confirm` is
 * banned (see apps/web/AGENTS.md).
 *
 * Desktop-only by construction — the bridge is null on the web build, so the
 * status stays null and this renders nothing.
 */

import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { openUpgradeDialog } from '@/components/billing/upgrade-dialog';
import { useDaemonCloudState, restartDesktopDaemon } from '@/lib/desktop-daemon';

export function MachineLimitDialog() {
  const { status, detail } = useDaemonCloudState();
  const [dismissed, setDismissed] = useState(false);
  const [retrying, setRetrying] = useState(false);
  // Never open during the hydration render. The server knows nothing about
  // the daemon, so SSR draws no dialog; opening one on the first client pass
  // changes the attributes Radix puts on <body> and React reports a
  // hydration mismatch it "won't patch up". One tick later is invisible.
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  // A retry that succeeds clears the status, so the next refusal is a fresh
  // one and deserves to be seen again: "did that work?" is answered by the
  // dialog coming back, or not.
  useEffect(() => {
    if (status !== 'machine_limit') {
      setDismissed(false);
      setRetrying(false);
    }
  }, [status]);

  const open = mounted && status === 'machine_limit' && !dismissed;

  // The in-app plan picker, the same upgrade path as everywhere else in the
  // product. It is mounted by the dashboard shell, the shell this dialog lives
  // in, so it is always there when this is.
  const upgrade = () => {
    setDismissed(true);
    openUpgradeDialog();
  };

  const retry = async () => {
    setRetrying(true);
    await restartDesktopDaemon();
    // Leave `retrying` on: either the status clears and the effect above
    // resets it, or the daemon is refused again and the dialog stays with the
    // same reason. Flipping the button back to idle under an unchanged dialog
    // would read as "nothing happened".
  };

  return (
    <Dialog open={open} onOpenChange={(next) => !next && setDismissed(true)}>
      <DialogContent className="font-mono sm:max-w-md">
        <DialogHeader>
          {/* Names the way out, not the fault. "This computer isn't
              connected" read as something broken; this reads as something to
              do, which is also why the body no longer has to reassure anyone
              that the computer still works. */}
          <DialogTitle>Upgrade to connect this computer</DialogTitle>
          {detail ? (
            <DialogDescription className="text-foreground/90">{detail}</DialogDescription>
          ) : null}
          <DialogDescription>
            Free up a machine in Settings → Machines, or upgrade to connect this one.
          </DialogDescription>
        </DialogHeader>
        {/* Upgrade is the primary action and sits last, where the confirm
            button lives in every other dialog. Try again is secondary: it only
            helps once a machine has actually been freed somewhere else. */}
        <DialogFooter className="gap-2 sm:gap-2">
          <Button
            variant="ghost"
            className="cursor-pointer sm:mr-auto"
            onClick={() => setDismissed(true)}
          >
            Dismiss
          </Button>
          <Button
            variant="outline"
            className="cursor-pointer"
            onClick={retry}
            disabled={retrying}
          >
            {retrying ? 'Trying…' : 'Try again'}
          </Button>
          <Button className="cursor-pointer" onClick={upgrade}>
            Upgrade
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
