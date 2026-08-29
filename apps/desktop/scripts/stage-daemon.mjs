#!/usr/bin/env node
/**
 * Stage the frozen `vicoa` daemon into apps/desktop/daemon-dist/<arch>/ for the
 * afterPack hook (scripts/after-pack.cjs copies daemon-dist/<arch> ->
 * <app>/Contents/Resources/daemon, per arch).
 *
 * The daemon is native code, so this stages for the HOST platform — a Windows
 * app is built on a Windows runner and a mac app on a mac runner. There is no
 * cross-platform staging path.
 *
 * Which archs get staged:
 *   - Windows / Linux: x64 only — the sole arch the frozen daemon ships there.
 *   - VICOA_MAC_RELEASE=1 (CI mac release): BOTH arm64 + x64. This mirrors
 *     electron-builder.config.cjs's mac.target, which builds both archs on a
 *     release. A two-arch app needs each .app to carry its OWN arch-native
 *     daemon — Rosetta translates x64 -> arm64 only, never the reverse.
 *   - otherwise (local dogfood): the HOST arch only (fast iteration).
 *
 * Source resolution per arch (first match wins):
 *   1. VICOA_DAEMON_DIST      — explicit path to an unzipped onedir `vicoa/`
 *                               dir. HOST arch only (a local build is one arch).
 *   2. VICOA_DAEMON_VERSION=local — the repo's backend/ local PyInstaller
 *                               build (case 4 path). HOST arch only.
 *   3. a pinned VERSION       — VICOA_DAEMON_VERSION env (a version), else
 *                               package.json "vicoaDaemonVersion". Each arch's
 *                               frozen daemon is fetched from the PUBLIC npm
 *                               registry — `@vicoa/cli` publishes each platform's
 *                               binary as an aliased version of itself
 *                               (`@vicoa/cli@<ver>-<os>-<arch>`) whose manifest
 *                               carries `dist.tarball` + a `dist.integrity`
 *                               sha512 we verify against. This is the DEFAULT,
 *                               the only source that can supply a non-host arch,
 *                               and mirrors the app's own runtime download
 *                               (src/cli-bootstrap.ts) — a plain HTTPS GET, no
 *                               npm client and no `gh`/GitHub-release auth (the
 *                               vicoa-ai/vicoa release is private + zip-only, and
 *                               the CLI no longer even cuts one). Cached under
 *                               apps/desktop/.daemon-cache/<version>/<os>-<arch>/.
 *   4. local pyinstaller build — <repo>/backend/pyinstaller/dist/vicoa,
 *                               when no pin is set at all. HOST arch only.
 *
 * A pinned download that fails (or fails its checksum) is a HARD error (loud,
 * not a silent wrong version). An arch with no available source (e.g. requesting
 * x64 while only a host-arch local build exists) succeeds with an EMPTY
 * daemon-dist/<arch> — the app then resolves `vicoa` from PATH (graceful
 * degradation, see apps/desktop/src/config.ts bundledDaemonPath), but WARNS
 * loudly first.
 */
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import * as fs from 'node:fs';
import * as path from 'node:path';
import { fileURLToPath } from 'node:url';

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const desktopDir = path.dirname(scriptDir);
const distRoot = path.join(desktopDir, 'daemon-dist');

const DEFAULT_REGISTRY = 'https://registry.npmjs.org';
/**
 * Registry base. `VICOA_NPM_REGISTRY` lets a build behind a slow/blocked public
 * npm point at a mirror (e.g. https://registry.npmmirror.com); the per-platform
 * packages + their integrity metadata mirror identically. Mirrors
 * src/cli-bootstrap.ts's registryBase().
 */
function registryBase() {
  const raw = process.env.VICOA_NPM_REGISTRY?.trim();
  return (raw && raw.length > 0 ? raw : DEFAULT_REGISTRY).replace(/\/+$/, '');
}

/** stage-daemon PLATFORM (mac/win/linux) -> npm `os` token (process.platform). */
const NPM_OS = { mac: 'darwin', win: 'win32', linux: 'linux' };

const PLATFORM =
  process.platform === 'win32' ? 'win' : process.platform === 'linux' ? 'linux' : 'mac';
/** Entrypoint name inside the PyInstaller onedir tree (vicoa.exe on Windows). */
const DAEMON_EXE = PLATFORM === 'win' ? 'vicoa.exe' : 'vicoa';

const HOST_ARCH = process.arch === 'x64' ? 'x64' : 'arm64';
// Match electron-builder.config.cjs: a FULL mac release (signed + notarized in
// CI) builds both archs; local dogfood and the local pre-flight
// (VICOA_SKIP_NOTARIZE=1) stage the host arch only. Windows and Linux ship a
// single x64 daemon (the only arch their frozen daemon builds for).
const isFullRelease =
  process.env.VICOA_MAC_RELEASE === '1' && process.env.VICOA_SKIP_NOTARIZE !== '1';
const BUILD_ARCHS =
  PLATFORM === 'win' || PLATFORM === 'linux'
    ? ['x64']
    : isFullRelease
      ? ['arm64', 'x64']
      : [HOST_ARCH];

/** `v1.7.6` -> `1.7.6` — npm version tags carry no leading `v`. */
function bareVersion(version) {
  return version.replace(/^v/i, '');
}

/** The npm platform-arch key the CLI publishes each frozen binary under. */
function npmKey(arch) {
  return `${NPM_OS[PLATFORM]}-${arch}`;
}

/** The pinned daemon version: env override, else the package.json field. */
function pinnedVersion() {
  if (process.env.VICOA_DAEMON_VERSION) return process.env.VICOA_DAEMON_VERSION;
  try {
    const pkg = JSON.parse(fs.readFileSync(path.join(desktopDir, 'package.json'), 'utf8'));
    return pkg.vicoaDaemonVersion || null;
  } catch {
    return null;
  }
}

/**
 * De-bundle only: ensure the PACKAGED package.json's `vicoaDaemonVersion` equals
 * the version this build targets, so the runtime first-run download pins to the
 * same daemon the release intended. No-op when they already match, when there is
 * no real pin, or for the `local` sentinel (not a downloadable npm version).
 */
function syncPackagedDaemonPin(version) {
  if (!version || version === 'local') {
    console.warn(
      `[stage-daemon] de-bundle: no downloadable daemon version pin (got "${version ?? 'none'}"); ` +
        'the app will fall back to its own version at runtime.',
    );
    return;
  }
  const pkgPath = path.join(desktopDir, 'package.json');
  try {
    const pkg = JSON.parse(fs.readFileSync(pkgPath, 'utf8'));
    if (pkg.vicoaDaemonVersion === version) return;
    const prev = pkg.vicoaDaemonVersion;
    pkg.vicoaDaemonVersion = version;
    fs.writeFileSync(pkgPath, JSON.stringify(pkg, null, 2) + '\n');
    console.log(`[stage-daemon] de-bundle: set package.json vicoaDaemonVersion ${prev ?? '(unset)'} -> ${version}`);
  } catch (err) {
    throw new Error(`failed to sync vicoaDaemonVersion in ${pkgPath}: ${err.message}`);
  }
}

function versionString(daemonDir) {
  try {
    return execFileSync(path.join(daemonDir, DAEMON_EXE), ['--version'], { encoding: 'utf8' }).trim();
  } catch {
    return '(version unknown)';
  }
}

/**
 * Stream the tarball to `dest`, sha512-hashing as we go. Returns the computed
 * `sha512-<base64>` digest — the exact shape npm publishes in `dist.integrity`,
 * so the compare is a plain string equality (mirrors cli-bootstrap.ts).
 */
async function downloadTarball(url, dest) {
  const res = await fetch(url);
  if (!res.ok || res.body === null) {
    throw new Error(`daemon tarball download failed: ${res.status} ${res.statusText}`);
  }
  const buf = Buffer.from(await res.arrayBuffer());
  fs.writeFileSync(dest, buf);
  return `sha512-${createHash('sha512').update(buf).digest('base64')}`;
}

/**
 * Download + cache the pinned frozen daemon for one arch from the npm registry;
 * returns the `package/bin/` onedir dir. The tarball unpacks to
 * `package/bin/{vicoa|vicoa.exe}` + `package/bin/_internal/` (build_npm_package.py
 * copies the whole onedir into `bin/`), the same layout cli-bootstrap.ts stages
 * from at runtime.
 */
async function downloadFromNpm(version, arch) {
  const bare = bareVersion(version);
  const key = npmKey(arch);
  // Platform is part of the cache key: `1.7.13-win32-x64` and `1.7.13-linux-x64`
  // are both "x64" and would otherwise collide.
  const cacheDir = path.join(desktopDir, '.daemon-cache', version, `${PLATFORM}-${arch}`);
  const daemonDir = path.join(cacheDir, 'package', 'bin');
  if (fs.existsSync(path.join(daemonDir, DAEMON_EXE))) {
    console.log(`[stage-daemon] using cached ${version}/${arch} daemon (${versionString(daemonDir)})`);
    return daemonDir;
  }
  fs.mkdirSync(cacheDir, { recursive: true });

  const manifestUrl = `${registryBase()}/@vicoa%2Fcli/${bare}-${key}`;
  console.log(`[stage-daemon] resolving @vicoa/cli@${bare}-${key} from ${registryBase()} …`);
  let dist;
  try {
    const res = await fetch(manifestUrl);
    if (!res.ok) {
      throw new Error(`registry manifest ${res.status} ${res.statusText}`);
    }
    const body = await res.json();
    const tarball = body?.dist?.tarball;
    const integrity = body?.dist?.integrity;
    if (typeof tarball !== 'string' || typeof integrity !== 'string') {
      throw new Error('manifest is missing dist.tarball / dist.integrity');
    }
    dist = { tarball, integrity };
  } catch (err) {
    throw new Error(
      `Failed to resolve the frozen daemon @vicoa/cli@${bare}-${key} from the npm ` +
        `registry (${registryBase()}). Is that version published for this platform? ` +
        `Underlying: ${err.message}`,
    );
  }

  const tgz = path.join(cacheDir, 'daemon.tgz');
  const digest = await downloadTarball(dist.tarball, tgz);
  if (digest !== dist.integrity) {
    throw new Error(
      `Daemon tarball for ${key} failed its checksum — refusing to stage. ` +
        `Expected ${dist.integrity}, got ${digest}.`,
    );
  }
  // `tar -xf` autodetects gzip on every platform we target: bsdtar ships as
  // tar.exe on Windows 10+, GNU/bsd tar handle .tgz on macOS/Linux.
  execFileSync('tar', ['-xf', tgz, '-C', cacheDir], { stdio: 'inherit' });
  if (!fs.existsSync(path.join(daemonDir, DAEMON_EXE))) {
    throw new Error(`daemon tarball for ${key} did not contain package/bin/${DAEMON_EXE}`);
  }
  const got = versionString(daemonDir);
  if (!got.includes(bare)) {
    // Defence in depth: the published binary should report the pinned version.
    console.warn(`[stage-daemon] WARNING: pinned ${version} but the ${arch} binary reports "${got}".`);
  }
  console.log(`[stage-daemon] downloaded ${arch} ${got}`);
  return daemonDir;
}

/** The repo's backend/ local PyInstaller onedir output (host arch). */
function localBuildPath() {
  return path.join(desktopDir, '..', '..', 'backend', 'pyinstaller', 'dist', 'vicoa');
}

/**
 * Source for one arch (see file header). Explicit/local sources are single-arch
 * (whatever the host built), so they only apply to HOST_ARCH; a non-host arch
 * returns { source: null } and stages empty (warns).
 */
async function resolveSource(version, arch) {
  if (process.env.VICOA_DAEMON_DIST) {
    return arch === HOST_ARCH
      ? { source: process.env.VICOA_DAEMON_DIST, kind: `explicit (VICOA_DAEMON_DIST), ${arch}` }
      : { source: null, kind: `${arch}: VICOA_DAEMON_DIST is host-arch (${HOST_ARCH}) only` };
  }
  if (version === 'local') {
    return arch === HOST_ARCH
      ? { source: localBuildPath(), kind: `local pyinstaller build (VICOA_DAEMON_VERSION=local), ${arch}` }
      : { source: null, kind: `${arch}: local build is host-arch (${HOST_ARCH}) only` };
  }
  if (version) {
    return {
      source: await downloadFromNpm(version, arch),
      kind: `pinned npm @vicoa/cli@${bareVersion(version)}, ${arch}`,
    };
  }
  return arch === HOST_ARCH
    ? { source: localBuildPath(), kind: `local pyinstaller build (no pin), ${arch}` }
    : { source: null, kind: `${arch}: local build is host-arch (${HOST_ARCH}) only (no pin set)` };
}

const version = pinnedVersion();

// Fresh root each run so a dropped arch never leaves a stale daemon behind.
fs.rmSync(distRoot, { recursive: true, force: true });
fs.mkdirSync(distRoot, { recursive: true });

// DE-BUNDLE: ship the installer WITHOUT the frozen daemon (empty daemon-dist).
// The app then downloads the daemon at its pinned version on first run — see
// electron/src/cli-bootstrap.ts. This is the fast-install path: on Windows NSIS
// decompression + Defender scanning of the ~300-file onedir dominate install
// time; on macOS it also shrinks the notarized bundle (faster notarize/upload).
// Trade-off: first launch needs network. OPT-IN and NOT enabled by the release
// jobs today (the app ships bundled); set VICOA_DEBUNDLE_DAEMON=1 to build a
// de-bundled app.
if (process.env.VICOA_DEBUNDLE_DAEMON === '1') {
  console.log(
    '[stage-daemon] VICOA_DEBUNDLE_DAEMON=1 — shipping WITHOUT a bundled daemon; ' +
      'the app downloads it on first run (electron/src/cli-bootstrap.ts).',
  );
  // The runtime download pins to package.json's `vicoaDaemonVersion` (read from
  // the PACKAGED package.json — the build-time VICOA_DAEMON_VERSION env is gone
  // by then). If the env overrode the tag, persist it so the two never drift.
  syncPackagedDaemonPin(version);
} else {
  for (const arch of BUILD_ARCHS) {
    const { source, kind } = await resolveSource(version, arch);
    const target = path.join(distRoot, arch);
    fs.mkdirSync(target, { recursive: true });
    if (source && fs.existsSync(path.join(source, DAEMON_EXE))) {
      // verbatimSymlinks keeps PyInstaller's relative dylib links relative — the
      // default rewrites them to ABSOLUTE paths into this checkout, which breaks
      // the bundled daemon on any other machine and voids the code-signature seal.
      fs.cpSync(source, target, { recursive: true, verbatimSymlinks: true });
      console.log(`[stage-daemon] ${arch}: staged ${versionString(target)} (${kind})`);
    } else {
      console.warn(
        `[stage-daemon] WARNING: no frozen daemon for ${arch} (${kind}) — that arch will ` +
          'bundle WITHOUT a daemon; the app falls back to `vicoa` on PATH.',
      );
    }
  }
}
