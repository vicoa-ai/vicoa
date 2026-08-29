/**
 * Machine-bound RPC handle for the terminal pane (desktop-app v1).
 *
 * Wraps the terminal WebSocket client (`getTerminalRpcClient(machineId)` — the
 * local daemon socket when the target is this machine, otherwise a dedicated
 * per-machine terminal-scoped cloud connection) and binds `callRpc` to that
 * machine id, satisfying the `PtyRpc` seam the terminal pane consumes
 * (`createRpcPtyTransport` in components/terminal-pane/pty-transport.ts):
 * `pty-spawn {cwd, cols, rows, command?}` → `{pty_id}`, `pty-write {pty_id,
 * data(base64)}`, `pty-resize {pty_id, cols, rows}`, `pty-kill {pty_id}`.
 *
 * Output arrives as push frames, not RPC responses: `onPtyOutput` delivers
 * `pty-output {pty_id, data}` chunks (data stays base64-encoded, exactly as
 * on the wire) and `onPtyExit` delivers `pty-exit {pty_id, exit_code}`. Both
 * return unsubscribe functions and keep the socket retained while held.
 */

import type { PtyRpc } from '@/components/terminal-pane/pty-transport';
import { getTerminalRpcClient } from '@/lib/ws-client';

export type { PtyRpc };

/** A `PtyRpc` bound to `machineId` over the right socket for the current mode. */
export function getPtyRpc(machineId: string): PtyRpc {
  const client = getTerminalRpcClient(machineId);
  return {
    callRpc: (method, params) => client.callRpc(machineId, method, params),
    sendRpc: (method, params) => client.sendRpc(machineId, method, params),
    onPtyOutput: (listener) => client.onPtyOutput(listener),
    onPtyExit: (listener) => client.onPtyExit(listener),
  };
}
