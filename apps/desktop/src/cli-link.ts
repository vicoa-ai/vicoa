/**
 * "Install the `vicoa` terminal command" — expose the CLI that already ships
 * inside the desktop app on the user's shell PATH.
 *
 * The desktop app carries a FULL `vicoa` binary: the PyInstaller onedir frozen
 * build of the backend's `vicoa` package (entry point `vicoa.cli:main`), the
 * same one the app runs as its daemon. Because it is the whole CLI — not just
 * `vicoa daemon` — that binary already knows `vicoa task`, `vicoa automation`,
 * `vicoa ls`, etc. It lives at either
 *   - <app>/Contents/Resources/daemon/vicoa      (default BUNDLED build), or
 *   - userData/daemon/<version>/vicoa            (managed / de-bundled build).
 * Neither is on the user's shell PATH, so `vicoa task ls` in a terminal fails
 * out of the box.
 *
 * This module makes that binary reachable using the EXACT SAME on-disk layout as
 * the standalone `curl https://vicoa.ai/install.sh | sh` installer
 * (vicoa-web/public/install.sh) and its Windows sibling (install.ps1), so the
 * two mechanisms interoperate on a single launcher instead of fighting:
 *
 *   macOS / Linux
 *     ~/.vicoa/runtime/<version>   -> the app's daemon dir (symlink; the app
 *                                     already has the bits on disk — no copy)
 *     ~/.vicoa/runtime/current     -> <version>   (relative symlink)
 *     ~/.local/bin/vicoa           -> `exec "$HOME/.vicoa/runtime/current/vicoa" "$@"`
 *                                     (a wrapper, not a symlink, so the onedir exe
 *                                     runs in place next to its _internal/)
 *
 *   Windows
 *     %LOCALAPPDATA%\Vicoa\bin\vicoa.cmd  -> `"<app daemon>\vicoa.exe" %*`
 *     %LOCALAPPDATA%\Vicoa\bin            added to the user PATH
 *
 * Everything lives under $HOME / %LOCALAPPDATA%, so there is NO admin/sudo prompt.
 * Re-running (or the launch-time self-heal) just re-points the symlinks, so an
 * app update or a managed-daemon version bump is picked up for free.
 */
import { app } from 'electron';
import { execFile } from 'node:child_process';
import * as fs from 'node:fs';
import * as fsp from 'node:fs/promises';
import * as os from 'node:os';
import * as path from 'node:path';
import { promisify } from 'node:util';
import { bundledDaemonPath } from './config';
import { isManagedDaemonInstalled, managedDaemonExe, pinnedDaemonVersion } from './cli-bootstrap';
import { readLoginShellPath } from './resolve-path';

const execFileAsync = promisify(execFile);

const isWindows = process.platform === 'win32';

// ---------------------------------------------------------------------------
// Paths — mirror install.sh / install.ps1 exactly (honouring VICOA_INSTALL_DIR
// so a user who set it for the curl installer stays consistent).
// ---------------------------------------------------------------------------

function installRoot(): string {
  const override = process.env.VICOA_INSTALL_DIR?.trim();
  if (override !== undefined && override.length > 0) {
    return override;
  }
  if (isWindows) {
    const localAppData = process.env.LOCALAPPDATA ?? path.join(os.homedir(), 'AppData', 'Local');
    return path.join(localAppData, 'Vicoa');
  }
  return path.join(os.homedir(), '.vicoa');
}

/** Dir the launcher goes in. install.sh: ~/.local/bin. install.ps1: <root>\bin. */
function binDir(): string {
  return isWindows ? path.join(installRoot(), 'bin') : path.join(os.homedir(), '.local', 'bin');
}

/** Absolute path of the launcher shim (or where it would be installed). */
export function cliLinkPath(): string {
  return path.join(binDir(), isWindows ? 'vicoa.cmd' : 'vicoa');
}

function runtimeRoot(): string {
  return path.join(installRoot(), 'runtime');
}

/** `v1.7.6` → `1.7.6` (registry/version dirs carry no leading `v`). */
function bareVersion(version: string): string {
  return version.replace(/^v/i, '');
}

// ---------------------------------------------------------------------------
// Resolving the binary this app carries
// ---------------------------------------------------------------------------

/**
 * The `vicoa` executable this install of the app carries, or null when none is
 * available yet (dev checkout with no staged daemon, or a managed build whose
 * daemon has not downloaded). Mirrors the daemon-manager's own precedence:
 * bundled first, then the managed (downloaded) one. We deliberately do NOT fall
 * back to a `vicoa` already on PATH — if one is there, this command is not
 * needed.
 */
export function cliBinaryPath(): string | null {
  const bundled = bundledDaemonPath();
  if (bundled !== null) {
    return bundled;
  }
  const version = pinnedDaemonVersion();
  if (isManagedDaemonInstalled(version)) {
    return managedDaemonExe(version);
  }
  return null;
}

/** Human-friendly path: abbreviate the home dir to `~` (macOS/Linux only). */
export function displayPath(p: string): string {
  if (isWindows) {
    return p;
  }
  const home = os.homedir();
  return home.length > 0 && (p === home || p.startsWith(home + path.sep))
    ? `~${p.slice(home.length)}`
    : p;
}

/** Same, but `$HOME` — safe to embed in a double-quoted shell command (`~` isn't). */
function withHomeVar(p: string): string {
  const home = os.homedir();
  return home.length > 0 && (p === home || p.startsWith(home + path.sep))
    ? `$HOME${p.slice(home.length)}`
    : p;
}

// ---------------------------------------------------------------------------
// Launcher content + "is this ours?" detection
// ---------------------------------------------------------------------------

/** POSIX single-quote a string for embedding in a /bin/sh command. */
function shSingleQuote(value: string): string {
  return `'${value.replace(/'/g, `'\\''`)}'`;
}

/** The Unix launcher — byte-identical in spirit to install.sh's. */
function unixLauncher(): string {
  const target = path.join(runtimeRoot(), 'current', 'vicoa');
  return `#!/bin/sh\nexec ${shSingleQuote(target)} "$@"\n`;
}

/** The Windows `.cmd` shim — points straight at the app's daemon exe. */
function windowsShim(exe: string): string {
  return `@echo off\r\n"${exe}" %*\r\n`;
}

/**
 * Is an existing launcher one WE (or the curl/ps1 installer) manage, and thus
 * safe to overwrite — versus a `vicoa` the user installed some other way (pip,
 * npm-global, a hand-rolled script) that we must not clobber? Pure, so it is
 * unit-testable. Both installers route through `<root>/runtime/.../vicoa[.exe]`,
 * which is the signature we look for.
 */
export function isManagedLauncher(contents: string): boolean {
  if (isWindows) {
    return /vicoa\.exe"\s*%\*/i.test(contents) && /runtime|Vicoa/i.test(contents);
  }
  return contents.includes('/runtime/current/vicoa') || contents.includes('/.vicoa/runtime/');
}

// ---------------------------------------------------------------------------
// Status
// ---------------------------------------------------------------------------

export interface CliLinkStatus {
  /** Absolute path the launcher lives (or would live) at. */
  path: string;
  /** A launcher we manage is present there. */
  installed: boolean;
  /** A file exists there that we do NOT manage (a user's own `vicoa`). */
  foreign: boolean;
  /** The binary this app can currently expose (null when it has none yet). */
  currentBinary: string | null;
}

export function getCliLinkStatus(): CliLinkStatus {
  const linkPath = cliLinkPath();
  let installed = false;
  let foreign = false;
  try {
    if (fs.existsSync(linkPath)) {
      const managed = isManagedLauncher(fs.readFileSync(linkPath, 'utf8'));
      installed = managed;
      foreign = !managed;
    }
  } catch {
    // unreadable — treat as absent; install() will surface the real error
  }
  return { path: linkPath, installed, foreign, currentBinary: cliBinaryPath() };
}

// ---------------------------------------------------------------------------
// Install
// ---------------------------------------------------------------------------

export interface CliLinkResult {
  ok: boolean;
  path: string;
  message: string;
  detail: string;
}

/**
 * Register the app's daemon dir as `~/.vicoa/runtime/<version>` and point
 * `current` at it (macOS/Linux). Symlinks only — the app already holds the bits,
 * so nothing is copied. A real dir already there (a curl install of the same
 * version) is left as-is; the binary is identical either way.
 */
async function registerUnixRuntime(daemonDir: string, version: string): Promise<void> {
  await fsp.mkdir(runtimeRoot(), { recursive: true });
  const versionDir = path.join(runtimeRoot(), version);
  const versionIsRealDir =
    fs.existsSync(versionDir) && !fs.lstatSync(versionDir).isSymbolicLink();
  if (!versionIsRealDir) {
    await fsp.rm(versionDir, { recursive: true, force: true });
    await fsp.symlink(daemonDir, versionDir);
  }
  const current = path.join(runtimeRoot(), 'current');
  await fsp.rm(current, { recursive: true, force: true });
  await fsp.symlink(version, current); // relative target, exactly like install.sh
}

/** Is `dir` on the user's *login shell* PATH (not the app's launchd PATH)? */
function binDirOnPath(dir: string): boolean {
  const shellPath = readLoginShellPath() ?? process.env.PATH ?? '';
  return shellPath.split(path.delimiter).includes(dir);
}

/**
 * Best-effort: add `dir` to the Windows *user* PATH so a new terminal finds the
 * shim. Untested on the Mac-only dev box — failures are swallowed (the shim
 * still works when invoked by full path).
 */
async function ensureWindowsPathEntry(dir: string): Promise<boolean> {
  const ps =
    `$d=${JSON.stringify(dir)};` +
    `$p=[Environment]::GetEnvironmentVariable('Path','User');if(-not $p){$p=''};` +
    `$parts=$p.Split(';')|Where-Object{$_ -ne ''};` +
    `if($parts -notcontains $d){[Environment]::SetEnvironmentVariable('Path',(($parts+$d) -join ';'),'User')}`;
  try {
    await execFileAsync('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', ps]);
    return true;
  } catch {
    return false;
  }
}

/**
 * Install (or refresh) the `vicoa` terminal command. Idempotent. No privilege
 * prompt — everything is under the user's home dir.
 */
export async function installCliLink(): Promise<CliLinkResult> {
  const binary = cliBinaryPath();
  const linkPath = cliLinkPath();
  if (binary === null) {
    return {
      ok: false,
      path: linkPath,
      message: 'Could not locate the bundled Vicoa CLI.',
      detail:
        'The app has not finished setting up its agent runtime yet. Open a session once (which ' +
        'downloads it if needed), then try again.',
    };
  }

  const status = getCliLinkStatus();
  if (status.foreign) {
    return {
      ok: false,
      path: linkPath,
      message: `A different "vicoa" already exists at ${linkPath}.`,
      detail:
        'It was not installed by Vicoa (looks like a pip/npm install). Leaving it untouched — ' +
        'remove it first if you want the desktop app to manage this command.',
    };
  }

  const daemonDir = path.dirname(binary);

  try {
    await fsp.mkdir(binDir(), { recursive: true });

    if (isWindows) {
      await fsp.writeFile(linkPath, windowsShim(binary));
      const onPath = await ensureWindowsPathEntry(binDir());
      return {
        ok: true,
        path: linkPath,
        message: 'The "vicoa" command is installed.',
        detail: onPath
          ? `Installed at ${displayPath(linkPath)}. Open a new terminal to use it.`
          : `Installed at ${displayPath(linkPath)}. Add ${displayPath(binDir())} to your PATH, then open a new terminal.`,
      };
    }

    await registerUnixRuntime(daemonDir, bareVersion(pinnedDaemonVersion()));
    await fsp.writeFile(linkPath, unixLauncher(), { mode: 0o755 });
    await fsp.chmod(linkPath, 0o755);

    const onPath = binDirOnPath(binDir());
    return {
      ok: true,
      path: linkPath,
      message: 'The "vicoa" command is installed.',
      detail: onPath
        ? `Installed at ${displayPath(linkPath)}. Open a new terminal to use it.`
        : `Installed at ${displayPath(linkPath)}.\nAdd this to your shell profile, then open a new terminal:\n  export PATH="${withHomeVar(binDir())}:$PATH"`,
    };
  } catch (err) {
    return {
      ok: false,
      path: linkPath,
      message: 'Could not install the vicoa command.',
      detail: err instanceof Error ? err.message : String(err),
    };
  }
}

/**
 * Silent self-heal on launch. If we manage the launcher but its runtime pointer
 * has gone stale — a managed-daemon version bump left `current` dangling, or the
 * app moved — re-register this build's binary. Never prompts; a no-op for the
 * common bundled case (the daemon dir path is version-stable, so `current`
 * survives app updates untouched). Safe to call on every boot.
 */
export async function refreshCliLinkIfInstalled(): Promise<void> {
  const status = getCliLinkStatus();
  if (!status.installed || status.currentBinary === null) {
    return;
  }
  if (isWindows) {
    // The .cmd points straight at an exe; heal only if that exe is gone.
    try {
      const contents = await fsp.readFile(status.path, 'utf8');
      const target = /"([^"]+vicoa\.exe)"/i.exec(contents)?.[1];
      if (target !== undefined && fs.existsSync(target)) {
        return;
      }
      await fsp.writeFile(status.path, windowsShim(status.currentBinary));
    } catch {
      // best-effort
    }
    return;
  }
  // Unix: heal only when `current` cannot resolve to a runnable vicoa.
  const currentExe = path.join(runtimeRoot(), 'current', 'vicoa');
  try {
    if (fs.existsSync(currentExe)) {
      return;
    }
    await registerUnixRuntime(path.dirname(status.currentBinary), bareVersion(pinnedDaemonVersion()));
  } catch {
    // needs attention it can't get silently — leave it for the next manual run
  }
}

// ---------------------------------------------------------------------------
// Install-by-default (first run, exactly once)
// ---------------------------------------------------------------------------

/**
 * Marker recording that we've made our one-time auto-install attempt. It lives
 * in userData (app-scoped) on purpose: it SURVIVES app updates — so an existing
 * user who never had the CLI is auto-installed exactly once, on the first launch
 * after this ships — and is only cleared by a full uninstall, so a genuinely
 * fresh install re-attempts.
 */
function autoInstallFlagPath(): string {
  return path.join(app.getPath('userData'), '.cli-auto-install-attempted');
}

async function stampAutoInstallFlag(): Promise<void> {
  try {
    const flag = autoInstallFlagPath();
    await fsp.mkdir(path.dirname(flag), { recursive: true });
    await fsp.writeFile(flag, new Date().toISOString());
  } catch {
    // Best-effort: if we can't stamp, we simply re-attempt next boot — the
    // install itself is idempotent, so that is harmless.
  }
}

/**
 * Install the `vicoa` terminal command automatically on first run, once, so the
 * bundled CLI is reachable out of the box instead of requiring a click in
 * Settings. Silent, best-effort, and deliberately conservative:
 *
 *   - Mirrors the manual "Install" exactly (writes the launcher shim + runtime
 *     symlinks under $HOME / %LOCALAPPDATA%). It does NOT edit shell profiles,
 *     so on a macOS shell where ~/.local/bin isn't on PATH the user still adds
 *     it themselves — the Settings row already shows that hint. (The Windows
 *     user PATH is set by installCliLink itself.)
 *   - Never clobbers a user's own `vicoa` (pip/npm/hand-rolled): a foreign
 *     launcher is left untouched.
 *   - Runs at most once (see the marker), so it neither fights a user who
 *     deliberately deletes the shim nor re-installs on every launch. Version
 *     bumps are still healed by refreshCliLinkIfInstalled().
 *
 * When the app has no binary to expose yet (a de-bundled build whose daemon
 * hasn't downloaded), it returns WITHOUT stamping the marker, so a later call —
 * once the daemon is provisioned — completes the install. Safe to call multiple
 * times per launch.
 */
export async function autoInstallCliLinkOnce(): Promise<void> {
  try {
    if (fs.existsSync(autoInstallFlagPath())) {
      return; // one-time attempt already made
    }
  } catch {
    // Unreadable marker — fall through and treat as not-yet-attempted.
  }

  const status = getCliLinkStatus();

  // Nothing to expose yet (managed build whose daemon hasn't downloaded). Leave
  // the marker unset so a later / post-provision call retries.
  if (status.currentBinary === null) {
    return;
  }

  // Ours is already there, or a user's own `vicoa` occupies the slot — either
  // way there's nothing to install. Stamp so we stop probing.
  if (status.installed || status.foreign) {
    await stampAutoInstallFlag();
    return;
  }

  try {
    await installCliLink();
  } catch {
    // Best-effort; the manual Settings button remains the escape hatch.
  }
  await stampAutoInstallFlag();
}
