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
import { useDaemonCloudState, restartDesktopDaemon } from '@/lib/desktop-daemon';

export function MachineLimitDialog() {
  const { status, detail } = useDaemonCloudState();
  const [dismissed, setDismissed] = useState(false);
  const [retrying, setRetrying] = useState(false);

  // A retry that succeeds clears the status, so the next refusal is a fresh
  // one and deserves to be seen again: "did that work?" is answered by the
  // dialog coming back, or not.
  useEffect(() => {
    if (status !== 'machine_limit') {
      setDismissed(false);
      setRetrying(false);
    }
  }, [status]);

  const open = status === 'machine_limit' && !dismissed;

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
          <DialogTitle>This computer isn&apos;t connected to Vicoa</DialogTitle>
          {detail ? (
            <DialogDescription className="text-foreground/90">{detail}</DialogDescription>
          ) : null}
          <DialogDescription>
            You&apos;re signed in and everything on this computer keeps working, but it
            won&apos;t appear in the Vicoa app, so you can&apos;t start or resume its sessions
            from another device.
          </DialogDescription>
          <DialogDescription>
            Free up a machine in Settings → Machines, or upgrade, then try again.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button
            variant="outline"
            className="cursor-pointer"
            onClick={() => setDismissed(true)}
          >
            Dismiss
          </Button>
          <Button className="cursor-pointer" onClick={retry} disabled={retrying}>
            {retrying ? 'Trying…' : 'Try again'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
