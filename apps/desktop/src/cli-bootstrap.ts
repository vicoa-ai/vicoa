/**
 * First-run download + install of the frozen `vicoa` daemon. Used by DE-BUNDLED
 * builds (scripts/stage-daemon.mjs VICOA_DEBUNDLE_DAEMON) and, in the default
 * BUNDLED build, as a self-heal fallback when the bundled daemon is missing or
 * corrupt (main.ts usesManagedDaemon → bundledDaemonPath() === null).
 *
 * Why this exists: the frozen daemon is a ~130-330 MB PyInstaller onedir. Shipping
 * it inside the installer makes the Windows install slow (NSIS decompresses every
 * file, Defender scans each one) and bloats the download. Instead we ship the
 * installer WITHOUT the daemon and fetch it once, on first run, into userData —
 * the same model multica uses for its Go CLI.
 *
 * Source: the PUBLIC npm registry. `@vicoa/cli` publishes each platform's binary
 * as an aliased version of itself (`@vicoa/cli@<ver>-<platform>-<arch>`), whose
 * registry manifest carries `dist.tarball` + a `dist.integrity` sha512 we verify
 * the download against. This needs no npm CLIENT (a plain HTTPS GET of the .tgz),
 * so a user with neither npm nor Python installed is fully served — the ONLY new
 * requirement over a bundled build is network access on first launch. The private
 * `vicoa-ai/vicoa` GitHub release the desktop build staged from is NOT reachable
 * unauthenticated, which is exactly why the registry is the delivery channel here.
 *
 * The tarball unpacks to `package/bin/{vicoa|vicoa.exe}` + `package/bin/_internal/`
 * (the onedir). We move that `bin/` dir to userData/daemon/<version>/, so the exe
 * sits next to its `_internal/` just like the bundled layout — the rest of the app
 * (config.bundledDaemonPath, daemon-manager) treats bundled and managed the same.
 *
 * Version: EXACTLY the app's `vicoaDaemonVersion` pin — never "latest" — so an app
 * build is only ever paired with the daemon it was vetted against.
 */
import { app } from 'electron';
import { execFile } from 'node:child_process';
import { createHash } from 'node:crypto';
import { once } from 'node:events';
import * as fs from 'node:fs';
import { createWriteStream } from 'node:fs';
import * as fsp from 'node:fs/promises';
import * as os from 'node:os';
import * as path from 'node:path';
import { promisify } from 'node:util';

const execFileAsync = promisify(execFile);

const DEFAULT_REGISTRY = 'https://registry.npmjs.org';

/**
 * Registry base. `VICOA_NPM_REGISTRY` lets a user behind a slow/blocked public
 * npm (notably mainland China) point at a mirror such as
 * https://registry.npmmirror.com — the per-platform packages and their
 * integrity metadata mirror identically, so verification is unaffected.
 */
function registryBase(): string {
  const raw = process.env.VICOA_NPM_REGISTRY?.trim();
  return (raw && raw.length > 0 ? raw : DEFAULT_REGISTRY).replace(/\/+$/, '');
}

/** The platform-arch keys the CLI publishes a frozen binary for. */
const SUPPORTED_KEYS = new Set(['darwin-arm64', 'darwin-x64', 'linux-x64', 'win32-x64']);

export function platformKey(): string {
  return `${process.platform}-${process.arch}`;
}

export function isPlatformSupported(): boolean {
  return SUPPORTED_KEYS.has(platformKey());
}

/** Entry name inside the PyInstaller onedir. */
function daemonExeName(): string {
  return process.platform === 'win32' ? 'vicoa.exe' : 'vicoa';
}

/** `v1.7.6` → `1.7.6` — npm version tags carry no leading `v`. */
function bareVersion(version: string): string {
  return version.replace(/^v/i, '');
}

/**
 * The daemon version this app build is paired with: the `vicoaDaemonVersion`
 * field in the packaged package.json (the SAME pin stage-daemon.mjs bundles
 * from). Falls back to the app version — desktop releases bump the two in
 * lockstep — if the field is somehow absent.
 */
export function pinnedDaemonVersion(): string {
  try {
    const pkgPath = path.join(app.getAppPath(), 'package.json');
    const pkg = JSON.parse(fs.readFileSync(pkgPath, 'utf8')) as { vicoaDaemonVersion?: unknown };
    if (typeof pkg.vicoaDaemonVersion === 'string' && pkg.vicoaDaemonVersion.trim().length > 0) {
      return pkg.vicoaDaemonVersion.trim();
    }
  } catch {
    // fall through to app version
  }
  return app.getVersion();
}

/** userData/daemon — parent of the per-version managed daemon dirs. */
export function managedDaemonRoot(): string {
  return path.join(app.getPath('userData'), 'daemon');
}

/** userData/daemon/<bare-version> — holds the exe + its `_internal/`. */
export function managedDaemonDir(version: string): string {
  return path.join(managedDaemonRoot(), bareVersion(version));
}

/** Absolute path to the managed daemon executable for `version`. */
export function managedDaemonExe(version: string): string {
  return path.join(managedDaemonDir(version), daemonExeName());
}

/** Is the managed daemon for `version` already installed and runnable? */
export function isManagedDaemonInstalled(version: string): boolean {
  try {
    return fs.existsSync(managedDaemonExe(version));
  } catch {
    return false;
  }
}

export interface DaemonProgress {
  phase: 'resolving' | 'downloading' | 'verifying' | 'extracting' | 'installing';
  /** 0..1 during 'downloading' when Content-Length is known; undefined otherwise. */
  fraction?: number;
  receivedBytes?: number;
  totalBytes?: number;
}

// ---------------------------------------------------------------------------
// Singleton install: one in-flight download shared by every awaiter (the
// background warm-up kicked at boot AND the splash-window await at daemon
// start), with a live listener set so both see progress.
// ---------------------------------------------------------------------------

let inFlight: Promise<string> | null = null;
const progressListeners = new Set<(p: DaemonProgress) => void>();

function emitProgress(p: DaemonProgress): void {
  for (const listener of progressListeners) {
    try {
      listener(p);
    } catch {
      // a broken UI listener must never abort the install
    }
  }
}

/**
 * Ensure the managed daemon for the app's pinned version is installed; returns
 * its exe path. Idempotent and single-flight: concurrent callers await the same
 * download. `onProgress` (optional) receives updates for as long as this caller
 * is awaiting.
 */
export function ensureManagedDaemon(onProgress?: (p: DaemonProgress) => void): Promise<string> {
  const version = pinnedDaemonVersion();

  if (isManagedDaemonInstalled(version)) {
    return Promise.resolve(managedDaemonExe(version));
  }
  if (!isPlatformSupported()) {
    return Promise.reject(new Error(`No frozen Vicoa daemon is published for ${platformKey()}.`));
  }

  if (onProgress) {
    progressListeners.add(onProgress);
  }
  if (inFlight === null) {
    inFlight = downloadAndInstall(version)
      .finally(() => {
        inFlight = null;
      });
  }
  const settle = inFlight;
  if (onProgress) {
    return settle.finally(() => progressListeners.delete(onProgress));
  }
  return settle;
}

interface DistInfo {
  tarball: string;
  integrity: string;
}

/** Fetch the per-platform package manifest for `dist.tarball` + `dist.integrity`. */
async function fetchDist(version: string): Promise<DistInfo> {
  const key = platformKey();
  const url = `${registryBase()}/@vicoa%2Fcli/${bareVersion(version)}-${key}`;
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(
      `Couldn't find the Vicoa daemon ${bareVersion(version)}-${key} on the registry ` +
        `(${res.status} ${res.statusText}).`,
    );
  }
  const body = (await res.json()) as { dist?: { tarball?: unknown; integrity?: unknown } };
  const tarball = body.dist?.tarball;
  const integrity = body.dist?.integrity;
  if (typeof tarball !== 'string' || typeof integrity !== 'string') {
    throw new Error(`The Vicoa daemon manifest for ${key} is missing its download URL or checksum.`);
  }
  return { tarball, integrity };
}

/**
 * Stream the tarball to `dest`, hashing as we go so verification needs no second
 * read. Returns the computed `sha512-<base64>` — the exact shape npm publishes
 * in `dist.integrity`, so the compare is a plain string equality.
 */
async function downloadTarball(url: string, dest: string): Promise<string> {
  const res = await fetch(url);
  if (!res.ok || res.body === null) {
    throw new Error(`Download failed: ${res.status} ${res.statusText}.`);
  }
  const total = Number(res.headers.get('content-length')) || 0;
  const hash = createHash('sha512');
  const out = createWriteStream(dest);
  const reader = res.body.getReader();
  let received = 0;
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      const chunk = Buffer.from(value);
      hash.update(chunk);
      received += chunk.length;
      if (!out.write(chunk)) {
        await once(out, 'drain');
      }
      emitProgress({
        phase: 'downloading',
        receivedBytes: received,
        totalBytes: total > 0 ? total : undefined,
        fraction: total > 0 ? received / total : undefined,
      });
    }
  } finally {
    out.end();
  }
  await once(out, 'finish');
  return `sha512-${hash.digest('base64')}`;
}

/** Best-effort prune of managed daemon dirs for other (old) versions. */
async function pruneOtherVersions(keepBare: string): Promise<void> {
  try {
    const entries = await fsp.readdir(managedDaemonRoot(), { withFileTypes: true });
    await Promise.all(
      entries
        .filter((e) => e.isDirectory() && e.name !== keepBare)
        .map((e) => fsp.rm(path.join(managedDaemonRoot(), e.name), { recursive: true, force: true })),
    );
  } catch {
    // the root may not exist yet, or an entry may be busy — never fatal
  }
}

async function downloadAndInstall(version: string): Promise<string> {
  emitProgress({ phase: 'resolving' });
  const { tarball, integrity } = await fetchDist(version);

  const tmpRoot = await fsp.mkdtemp(path.join(os.tmpdir(), 'vicoa-daemon-'));
  try {
    const tgz = path.join(tmpRoot, 'daemon.tgz');
    const digest = await downloadTarball(tarball, tgz);

    emitProgress({ phase: 'verifying' });
    if (digest !== integrity) {
      throw new Error(
        `Downloaded Vicoa daemon failed its checksum — refusing to install. ` +
          `Expected ${integrity}, got ${digest}.`,
      );
    }

    emitProgress({ phase: 'extracting' });
    const extractDir = path.join(tmpRoot, 'x');
    await fsp.mkdir(extractDir, { recursive: true });
    // `tar -xf` autodetects gzip on every platform we target — bsdtar ships as
    // tar.exe on Windows 10+, and GNU/bsd tar handle .tgz on macOS/Linux.
    await execFileAsync('tar', ['-xf', tgz, '-C', extractDir]);

    const stagedBin = path.join(extractDir, 'package', 'bin');
    if (!fs.existsSync(path.join(stagedBin, daemonExeName()))) {
      throw new Error(`Vicoa daemon archive did not contain bin/${daemonExeName()}.`);
    }

    emitProgress({ phase: 'installing' });
    const finalDir = managedDaemonDir(version);
    await fsp.rm(finalDir, { recursive: true, force: true });
    await fsp.mkdir(path.dirname(finalDir), { recursive: true });
    try {
      await fsp.rename(stagedBin, finalDir);
    } catch {
      // Cross-device rename (tmp on a different volume than userData): copy then
      // drop the source. verbatimSymlinks keeps the onedir's relative dylib links
      // relative — the default would rewrite them to absolute temp paths.
      await fsp.cp(stagedBin, finalDir, { recursive: true, verbatimSymlinks: true });
    }
    if (process.platform !== 'win32') {
      await fsp.chmod(managedDaemonExe(version), 0o755).catch(() => {});
    }

    void pruneOtherVersions(bareVersion(version));
    return managedDaemonExe(version);
  } finally {
    await fsp.rm(tmpRoot, { recursive: true, force: true }).catch(() => {});
  }
}
