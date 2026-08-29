'use client';

import { useEffect, useRef, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { getWsClient } from '@/lib/ws-client';
import { getDesktopConfig } from '@/lib/runtime-config';

// Grace before surfacing a disconnect: the shared client reports `false`
// during its initial handshake and across sub-second reconnect blips; only a
// sustained outage (daemon down / restarting) should show the banner.
const SHOW_DELAY_MS = 2_000;

/**
 * Desktop-local daemon-down banner. In local mode the shared WS client IS the
 * daemon's local socket (ws-client.ts `getWsClient`), and the dashboard keeps
 * it retained via its instance stream — so `onConnectionChange` directly
 * tracks daemon liveness. In cloud mode the main socket is the cloud WS and
 * the local socket is only retained while terminal/files RPC is active, so a
 * "disconnected" reading there would mostly mean "idle"; the banner stays out
 * of cloud mode for v1 (RPC surfaces its own errors in the panes).
 */
export function DesktopConnectionBanner() {
  const [show, setShow] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const config = getDesktopConfig();
    if (!config || config.mode !== 'local') return;

    const client = getWsClient();
    const unsubscribe = client.onConnectionChange((connected) => {
      if (connected) {
        if (timerRef.current) {
          clearTimeout(timerRef.current);
          timerRef.current = null;
        }
        setShow(false);
      } else if (!timerRef.current) {
        timerRef.current = setTimeout(() => {
          timerRef.current = null;
          setShow(true);
        }, SHOW_DELAY_MS);
      }
    });
    return () => {
      unsubscribe();
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };
  }, []);

  if (!show) return null;

  return (
    <div className="flex items-center justify-center gap-2 border-b border-amber-500/30 bg-amber-500/10 px-3 py-1 text-xs font-mono text-amber-600 dark:text-amber-500">
      <Loader2 className="h-3 w-3 animate-spin" />
      Local daemon disconnected — reconnecting…
    </div>
  );
}
