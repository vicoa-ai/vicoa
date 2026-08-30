/**
 * electron-builder afterPack hook: copy the staged Next standalone renderer
 * and the arch-native frozen daemon into the packed app's resources dir
 * (macOS: <app>/Contents/Resources, Windows/Linux: <appOutDir>/resources).
 *
 * This cannot be an extraResources fileset: electron-builder's directory
 * walker hard-skips any `node_modules` directory (even with an explicit
 * "**\/node_modules\/**" filter), and the standalone server is dead without
 * its flattened node_modules. afterPack runs after the app is assembled and
 * before the dmg/zip/nsis/AppImage targets are built, so the copied files land
 * in every artifact. renderer-dist is guaranteed symlink-free by
 * scripts/build-renderer.mjs.
 *
 * The macOS-only tail of this hook (framework canonicalization + ad-hoc
 * codesign) exists to satisfy codesign and UNUserNotificationCenter. Windows
 * and Linux need neither: no framework bundles, and both ship unsigned (see
 * electron-builder.config.cjs).
 */
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const { Arch } = require('electron-builder');

/**
 * Rewrite each PyInstaller `*.framework` under the bundled daemon into the
 * canonical macOS layout so codesign will sign it. PyInstaller ships a
 * non-conforming framework — the top-level `<Name>`/`Resources` and
 * `Versions/Current` are all REAL copies instead of symlinks — which makes
 * `codesign` fail with "bundle format is ambiguous (could be app or
 * framework)" when electron-builder signs the inner Mach-O. We collapse it to
 * the standard shape (top-level entries + Versions/Current become symlinks
 * into the real Versions/<ver>), which is what every valid framework uses (cf.
 * Electron's own Frameworks). Idempotent; symlinks are transparent to dlopen,
 * so the daemon still runs. Must run BEFORE electron-builder's signing pass —
 * afterPack does.
 */
function canonicalizeFrameworks(rootDir) {
  if (!fs.existsSync(rootDir)) return;
  const stack = [rootDir];
  let fixed = 0;
  while (stack.length > 0) {
    const dir = stack.pop();
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      if (!entry.isDirectory() || entry.isSymbolicLink()) continue;
      const full = path.join(dir, entry.name);
      if (entry.name.endsWith('.framework')) {
        if (canonicalizeFramework(full)) fixed += 1;
      } else {
        stack.push(full);
      }
    }
  }
  if (fixed > 0) console.log(`  • after-pack: canonicalized ${fixed} daemon framework(s) for codesign`);
}

function canonicalizeFramework(fw) {
  const versionsDir = path.join(fw, 'Versions');
  if (!fs.existsSync(versionsDir)) return false;
  const versions = fs.readdirSync(versionsDir).filter((n) => n !== 'Current');
  if (versions.length === 0) return false;
  const ver = versions.includes('A') ? 'A' : versions[0];
  // Versions/Current -> <ver>
  const current = path.join(versionsDir, 'Current');
  fs.rmSync(current, { recursive: true, force: true });
  fs.symlinkSync(ver, current);
  // Top-level entries (Python, Resources, …) -> Versions/Current/<name>
  for (const name of fs.readdirSync(path.join(versionsDir, ver))) {
    const top = path.join(fw, name);
    fs.rmSync(top, { recursive: true, force: true });
    fs.symlinkSync(path.join('Versions', 'Current', name), top);
  }
  return true;
}

module.exports = async function afterPack(context) {
  const platform = context.electronPlatformName;
  if (platform !== 'darwin' && platform !== 'win32' && platform !== 'linux') {
    throw new Error(`after-pack.cjs handles macOS, Windows and Linux only (got ${platform})`);
  }
  const isMac = platform === 'darwin';
  // The frozen daemon's entrypoint inside the PyInstaller onedir tree
  // (vicoa.exe on Windows; vicoa on macOS + Linux).
  const daemonExe = platform === 'win32' ? 'vicoa.exe' : 'vicoa';
  const appName = `${context.packager.appInfo.productFilename}.app`;
  // macOS buries resources inside the .app; Windows/Linux keep them beside the
  // executable at <appOutDir>/resources.
  const resourcesDir = isMac
    ? path.join(context.appOutDir, appName, 'Contents', 'Resources')
    : path.join(context.appOutDir, 'resources');
  const src = path.join(__dirname, '..', 'renderer-dist');
  const dst = path.join(resourcesDir, 'renderer');
  if (!fs.existsSync(path.join(src, 'server.js'))) {
    throw new Error(`after-pack: ${src}/server.js missing — run scripts/build-renderer.mjs first`);
  }
  fs.rmSync(dst, { recursive: true, force: true });
  fs.cpSync(src, dst, { recursive: true, verbatimSymlinks: true });
  const nodeModules = path.join(dst, 'node_modules');
  if (!fs.existsSync(nodeModules)) {
    throw new Error('after-pack: renderer node_modules did not copy');
  }
  console.log(`  • after-pack: staged renderer -> ${dst}`);

  // Stage the arch-native daemon. A multi-arch build needs each .app to carry
  // its OWN daemon (Rosetta translates x64 -> arm64 only, never the reverse),
  // and afterPack runs once per arch — so pick daemon-dist/<arch> by
  // context.arch. Produced by scripts/stage-daemon.mjs; missing = graceful
  // fallback to `vicoa` on PATH (see src/config.ts bundledDaemonPath).
  const archName = Arch[context.arch];
  const daemonSrc = path.join(__dirname, '..', 'daemon-dist', archName);
  const daemonDst = path.join(resourcesDir, 'daemon');
  fs.rmSync(daemonDst, { recursive: true, force: true });
  if (fs.existsSync(path.join(daemonSrc, daemonExe))) {
    // verbatimSymlinks: keep PyInstaller's relative dylib links relative.
    fs.cpSync(daemonSrc, daemonDst, { recursive: true, verbatimSymlinks: true });
    console.log(`  • after-pack: staged ${archName} daemon -> ${daemonDst}`);
  } else {
    console.warn(
      `  • after-pack: no ${archName} daemon at ${daemonSrc} — bundling without it ` +
        '(app falls back to `vicoa` on PATH)',
    );
  }

  // Everything below is code-signing plumbing, which is macOS-only: Windows and
  // Linux ship unsigned (see electron-builder.config.cjs) and their PyInstaller
  // trees have no .framework bundles to repair.
  if (!isMac) {
    return;
  }

  // Repair the bundled PyInstaller daemon's frameworks so electron-builder's
  // signing pass can sign them (no-op when no daemon is bundled).
  canonicalizeFrameworks(daemonDst);

  const appDir = path.join(context.appOutDir, appName);

  if (process.env.VICOA_MAC_RELEASE === '1') {
    // Release ordering bridge. electron-builder's Developer ID pass signs the
    // Contents/MacOS binaries in readdir order (@electron/osx-sign), and the
    // MAIN executable (Vicoa) — which seals the WHOLE bundle — can be signed
    // BEFORE its loose sibling helper. codesign then aborts:
    //   "…/MacOS/Vicoa: code object is not signed at all
    //    In subcomponent: …/MacOS/vicoa-notification-status"
    // Give the helper a throwaway ad-hoc signature now so that intermediate seal
    // succeeds. electron-builder immediately re-signs the helper with the
    // Developer ID identity (it is in the walked children + mac.binaries) and
    // re-seals the app bundle LAST, so the shipped signature is entirely
    // Developer ID — the ad-hoc placeholder leaves no trace. (afterPack runs
    // BEFORE signing, so this cannot touch the eventual Developer ID seal.)
    const helperPath = path.join(appDir, 'Contents', 'MacOS', 'vicoa-notification-status');
    if (fs.existsSync(helperPath)) {
      execFileSync('codesign', ['--force', '--sign', '-', helperPath], { stdio: 'inherit' });
      console.log('  • after-pack: ad-hoc pre-signed notification helper (release ordering bridge)');
    }
  } else if (process.env.VICOA_SKIP_ADHOC_SIGN !== '1') {
    // Local dogfood: electron-builder's own signing is off (mac.identity: null),
    // but a fully unsigned bundle is hard-rejected by UNUserNotificationCenter
    // (macOS keys notification records to the signing identity), so the app can
    // neither post banners nor appear in System Settings -> Notifications. Ad-hoc
    // deep-sign the whole bundle. Must run LAST — later writes break the seal.
    execFileSync('codesign', ['--force', '--deep', '--sign', '-', appDir], { stdio: 'inherit' });
    console.log('  • after-pack: ad-hoc deep-signed bundle');
  }
};
