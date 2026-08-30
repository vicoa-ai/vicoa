/**
 * Desktop CLI install — renderer side of the preload bridge
 * (electron/src/cli-link.ts). Exposes the `vicoa` command the desktop app
 * already bundles onto the user's shell PATH.
 *
 * Null bridge on plain web / SSR — every consumer hides its affordance there
 * (a browser tab has no bundled binary and no way to write PATH).
 */

/** Trimmed status the main process reports (mirror of the IPC handler). */
export interface CliLinkStatus {
  /** A launcher Vicoa manages is already on PATH. */
  installed: boolean;
  /** A different `vicoa` (pip/npm/hand-rolled) is there — we won't clobber it. */
  foreign: boolean;
  /** The app currently has a binary it can expose. */
  available: boolean;
  /** Where the launcher lives (or would). */
  path: string;
}

export interface CliInstallResult {
  ok: boolean;
  path: string;
  message: string;
  detail: string;
}

interface DesktopCliBridge {
  getStatus: () => Promise<CliLinkStatus>;
  install: () => Promise<CliInstallResult>;
}

export function getDesktopCliBridge(): DesktopCliBridge | null {
  if (typeof window === 'undefined') return null;
  const bridge = (window as unknown as { vicoaDesktopCli?: DesktopCliBridge }).vicoaDesktopCli;
  return bridge && typeof bridge.install === 'function' ? bridge : null;
}

export async function getCliStatus(): Promise<CliLinkStatus | null> {
  const bridge = getDesktopCliBridge();
  if (!bridge) return null;
  try {
    return await bridge.getStatus();
  } catch {
    return null;
  }
}

export async function installCli(): Promise<CliInstallResult | null> {
  const bridge = getDesktopCliBridge();
  if (!bridge) return null;
  try {
    return await bridge.install();
  } catch (err) {
    return {
      ok: false,
      path: '',
      message: 'Could not install the vicoa command.',
      detail: err instanceof Error ? err.message : String(err),
    };
  }
}

/**
 * Pure: the one-line description under the "Terminal command" row, derived from
 * status. Unit-tested in desktop-cli.test.ts.
 */
export function cliRowDescription(status: CliLinkStatus | null): string {
  if (status?.foreign) {
    return `Another "vicoa" is already on your PATH (${status.path}) — remove it to let Vicoa manage this`;
  }
  if (status?.installed) {
    return `Installed at ${status.path}`;
  }
  if (status && !status.available) {
    return 'Finishing agent setup — open a session once, then install';
  }
  return 'Run vicoa daemon in the background and use task, automation, and session commands from your terminal';
}

/** Pure: the action button label for the current state. */
export function cliButtonLabel(status: CliLinkStatus | null, busy: boolean): string {
  if (busy) return 'Installing…';
  return status?.installed ? 'Reinstall' : 'Install';
}
