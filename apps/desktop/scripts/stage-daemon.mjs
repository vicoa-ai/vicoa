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
 *   3. a pinned RELEASE       — VICOA_DAEMON_VERSION env (a tag), else
 *                               package.json "vicoaDaemonVersion". Each arch's
 *                               asset is downloaded (and cached under
 *                               apps/desktop/.daemon-cache/<version>/<arch>/) from
 *                               the vicoa-ai/vicoa GitHub release via
 *                               `gh`. This is the DEFAULT, and the only source
 *                               that can supply a non-host arch.
 *   4. local pyinstaller build — <repo>/backend/pyinstaller/dist/vicoa,
 *                               when no pin is set at all. HOST arch only.
 *
 * A pinned download that fails is a HARD error (loud, not a silent wrong
 * version). An arch with no available source (e.g. requesting x64 while only a
 * host-arch local build exists) succeeds with an EMPTY daemon-dist/<arch> — the
 * app then resolves `vicoa` from PATH (graceful degradation, see
 * apps/desktop/src/config.ts bundledDaemonPath), but WARNS loudly first.
 */
import { execFileSync } from 'node:child_process';
import * as fs from 'node:fs';
import * as path from 'node:path';
import { fileURLToPath } from 'node:url';

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const desktopDir = path.dirname(scriptDir);
const distRoot = path.join(desktopDir, 'daemon-dist');

const RELEASE_REPO = 'vicoa-ai/vicoa';
const RELEASE_ASSETS = {
  mac: { arm64: 'vicoa-macos-arm64.zip', x64: 'vicoa-macos-x64.zip' },
  win: { x64: 'vicoa-windows-x64.zip' },
  linux: { x64: 'vicoa-linux-x64.tar.gz' },
};

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

/** The pinned daemon release tag: env override, else the package.json field. */
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
 * Extract a release archive. macOS/Windows daemons ship as `.zip`; the Linux
 * daemon ships as a gzipped tarball (`vicoa-linux-x64.tar.gz`), so it takes the
 * `tar -xzf` path. Windows runners have no `unzip`, but every Windows 10+ ships
 * bsdtar as `tar.exe`, which reads zip archives — and macOS ships bsdtar too, so
 * the mac/win branch could collapse. It doesn't, deliberately: the `unzip` path
 * is what every shipped mac release has been built with, and this is not the
 * change to re-validate it under.
 */
function extractArchive(archivePath, destDir) {
  if (PLATFORM === 'linux') {
    execFileSync('tar', ['-xzf', archivePath, '-C', destDir], { stdio: 'inherit' });
    return;
  }
  const argv =
    PLATFORM === 'win'
      ? ['-xf', archivePath, '-C', destDir]
      : ['-q', '-o', archivePath, '-d', destDir];
  execFileSync(PLATFORM === 'win' ? 'tar' : 'unzip', argv, { stdio: 'inherit' });
}

/** Download + cache the pinned release for one arch; returns the `vicoa/` dir. */
function downloadRelease(version, arch) {
  const asset = RELEASE_ASSETS[PLATFORM][arch];
  // Platform is part of the cache key: `vicoa-macos-x64.zip` and
  // `vicoa-windows-x64.zip` are both "x64" and would otherwise collide.
  const cacheDir = path.join(desktopDir, '.daemon-cache', version, `${PLATFORM}-${arch}`);
  const daemonDir = path.join(cacheDir, 'vicoa');
  if (fs.existsSync(path.join(daemonDir, DAEMON_EXE))) {
    console.log(`[stage-daemon] using cached ${version}/${arch} daemon (${versionString(daemonDir)})`);
    return daemonDir;
  }
  fs.mkdirSync(cacheDir, { recursive: true });
  console.log(`[stage-daemon] downloading ${asset} from ${RELEASE_REPO} ${version} …`);
  try {
    execFileSync(
      'gh',
      ['release', 'download', version, '--repo', RELEASE_REPO, '--pattern', asset, '--dir', cacheDir, '--clobber'],
      { stdio: 'inherit' },
    );
  } catch (err) {
    throw new Error(
      `gh release download failed for ${version} (${asset}). Is gh installed + authed (with read on ${RELEASE_REPO}), ` +
        `and does the release ship ${asset}? Underlying: ${err.message}`,
    );
  }
  extractArchive(path.join(cacheDir, asset), cacheDir);
  if (!fs.existsSync(path.join(daemonDir, DAEMON_EXE))) {
    throw new Error(`downloaded ${asset} did not contain vicoa/${DAEMON_EXE}`);
  }
  const got = versionString(daemonDir);
  const want = version.replace(/^v/, '');
  if (!got.includes(want)) {
    // Known hazard: a release asset can be built off the default branch rather
    // than the tag, so verify loudly rather than trust the tag name.
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
function resolveSource(version, arch) {
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
    return { source: downloadRelease(version, arch), kind: `pinned release ${version}, ${arch}` };
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
    const { source, kind } = resolveSource(version, arch);
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
