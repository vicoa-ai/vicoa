/**
 * Windows GPU crash → software-render fallback marker (Orca pattern, adapted).
 *
 * The desktop app launches with hardware acceleration ON so healthy Windows GPUs
 * keep it. On a machine with a genuinely broken GPU stack (some VMs, stale/old
 * drivers) the renderer can crash in a tight loop that no reload recovers — a
 * Chromium ANGLE → Direct3D GPU crash. When the renderer's bounded auto-reload
 * gives up (onRendererRecoveryExhausted in main.ts) the shell persists this marker
 * and relaunches with acceleration disabled; the marker makes the choice stick
 * across later manual launches and updates, so a bad machine only ever "flaps"
 * once instead of on every start.
 *
 * NOTE: this is a DEFENSIVE net for real GPU faults only. The `-36861` renderer
 * crash that first prompted a Windows GPU workaround was NOT a GPU crash — it was a
 * packaging bug (an empty Windows `locales/` dir produced by
 * `electronLanguages: ['en']`, which deletes every `.pak` since Windows paks are
 * named `en-US.pak`; fixed in electron-builder.config.cjs — see
 * electron/electron#45251). Forcing acceleration off never fixed it. Keep this
 * fallback purely as a net for genuine GPU crash loops, and do NOT read a `-36861`
 * exit code as "the GPU" again.
 *
 * The marker is read synchronously BEFORE app.whenReady (disableHardwareAcceleration
 * must run before `ready`), so it is a tiny standalone JSON file in userData — not
 * the async settings store. Deliberately NOT build-scoped: once a machine falls
 * back it stays software-rendered (a VM's GPU won't improve on an app update).
 * A future "re-enable GPU acceleration" setting can call clearGpuFallback() to
 * give the hardware another try.
 */
import * as fs from 'node:fs';
import * as path from 'node:path';

/**
 * argv flag passed on the crash-triggered relaunch — the loop-proof signal that
 * THIS launch must be software-rendered. argv survives the relaunch exactly and
 * can't be misread the way a file path could, so a fallback relaunch can never
 * loop back into hardware acceleration.
 */
export const GPU_FALLBACK_ARG = '--gpu-fallback';

const MARKER_FILE = 'gpu-fallback.json';

function markerPath(userDataPath: string): string {
  return path.join(userDataPath, MARKER_FILE);
}

/** True if a prior run engaged the software-render fallback on this machine. */
export function isGpuFallbackEngaged(userDataPath: string): boolean {
  try {
    return fs.existsSync(markerPath(userDataPath));
  } catch {
    return false;
  }
}

/** Persist the fallback so future launches start software-rendered. */
export function engageGpuFallback(userDataPath: string, reason: string): void {
  fs.writeFileSync(
    markerPath(userDataPath),
    JSON.stringify({ engagedAt: new Date().toISOString(), reason }, null, 2),
  );
}

/** Clear the fallback so the next launch tries hardware acceleration again. */
export function clearGpuFallback(userDataPath: string): void {
  try {
    fs.rmSync(markerPath(userDataPath), { force: true });
  } catch {
    // best effort
  }
}
