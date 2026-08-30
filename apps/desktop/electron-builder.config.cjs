/**
 * electron-builder config for the Vicoa desktop app
 * (macOS arm64 + Intel x64; Windows x64; Linux x64 AppImage).
 *
 * WINDOWS IS UNSIGNED (deliberate — see below).
 * Since June 2023 a publicly-trusted code-signing key must live on a FIPS
 * 140-2 L2+ HSM, so there is no Windows equivalent of the mac CSC_LINK
 * .p12-in-a-secret pattern — it needs a paid cloud-signing subscription.
 * Until we buy one, Windows users get SmartScreen's "Windows protected your
 * PC" click-through on first install. This does NOT block auto-update:
 * unlike Squirrel.Mac (which refuses to apply an update whose code
 * requirement doesn't match), electron-updater's NSIS path only verifies a
 * publisher when the INSTALLED app is itself signed. Going unsigned now and
 * signed later is therefore a safe sequence — but once we do sign, keep the
 * certificate subject stable or list every historical name in
 * win.publisherName, or existing installs will reject the update.
 *
 * The mac signing modes below are gated on the VICOA_MAC_RELEASE env var:
 *
 *   unset  — local dogfood packaging (`pnpm run package`). Ships un-notarized
 *            with no real identity: electron-builder's own signing stays off
 *            (identity: null) and after-pack.cjs ad-hoc deep-signs the bundle so
 *            UNUserNotificationCenter keys notification records to a coherent
 *            signature. Right-click Open / `xattr -d com.apple.quarantine` still
 *            required on other machines. Builds only the HOST arch (fast).
 *   =1     — CI / distribution release (`pnpm run package:release`). Developer
 *            ID Application signing + hardened runtime + notarization — the
 *            combination Squirrel.Mac requires to APPLY an auto-update (see
 *            src/updater.ts). The signing identity is auto-discovered from the
 *            keychain locally, or from CSC_LINK/CSC_KEY_PASSWORD in CI;
 *            notarization uses the App Store Connect API key via the
 *            APPLE_API_KEY / APPLE_API_KEY_ID / APPLE_API_ISSUER env vars.
 *            Builds BOTH arm64 + x64 in ONE invocation (see mac.target note).
 *
 * Inputs staged by `pnpm run package[:release]`:
 *   dist/           compiled main + preload (tsc)
 *   renderer-dist/  Next standalone server (scripts/build-renderer.mjs)
 *   daemon-dist/<arch>/  per-arch PyInstaller onedir frozen daemon
 *                   (scripts/stage-daemon.mjs). after-pack.cjs copies the
 *                   arch matching each pack into Resources/daemon; may be empty
 *                   for an arch — the app then falls back to `vicoa` on PATH.
 *   resources/icon.icns / icon.ico  app icon (`pnpm make:icon`, from
 *                   resources/icon-512.png)
 */
const path = require('node:path');

// Which platform this invocation targets. electron-builder evaluates this
// config ONCE, before it exposes a resolved target list, so argv is the only
// signal available here — and it is a reliable one because every one of our
// package scripts passes an explicit --mac / --win / --linux.
const targetsWin = process.argv.includes('--win');
const targetsLinux = process.argv.includes('--linux');

const isMacRelease = process.env.VICOA_MAC_RELEASE === '1';
// Local pre-flight (`pnpm package:release:local`): VICOA_SKIP_NOTARIZE=1 keeps
// real Developer ID signing ON but skips the ~5-7 min Apple notarization AND the
// second arch — a fast local build to catch signing/packaging bugs before a CI
// tag. A "full release" is signed AND notarized (CI only).
const skipNotarize = process.env.VICOA_SKIP_NOTARIZE === '1';
const isFullRelease = isMacRelease && !skipNotarize;

// A full (CI) release ships both Apple Silicon and Intel; local dogfood and the
// local pre-flight build only the host arch (fast — an x64 dmg is only meaningful
// tested on Intel). CRITICAL: both archs are built in this ONE config / ONE
// electron-builder invocation. Splitting into two `--publish` runs would make
// each run's latest-mac.yml overwrite the other's, silently breaking auto-update
// for one arch. Never split the release build per-arch.
const macArchs = isFullRelease
  ? ['arm64', 'x64']
  : [process.arch === 'x64' ? 'x64' : 'arm64'];

// Hardened-runtime entitlements Electron needs under notarization. Lives in a
// tracked dir (build/ is gitignored — it holds only packaging artifacts).
// Absolute path via __dirname so resolution never depends on cwd.
const entitlements = path.join(__dirname, 'signing', 'entitlements.mac.plist');

/** @type {import('electron-builder').Configuration} */
module.exports = {
  appId: 'ai.vicoa.desktop',
  productName: 'Vicoa',
  // Ship English only, but list BOTH the macOS and the Windows/Linux locale
  // names — electron-builder's language pruner matches by the platform's own
  // file naming, which differs. macOS keeps `en.lproj` (id `en`); Windows/Linux
  // keep `en-US.pak` (id `en-US`, hyphenated — there is NO `en.pak`). Listing
  // only `['en']` matched nothing on Windows and DELETED EVERY `.pak`, leaving an
  // empty `locales/` dir — a malformed Electron app whose renderer CRASHES with
  // exitCode -36861 the moment it creates an `<input type="file">` (the hidden
  // chat-composer file picker). See electron/electron#45251. Keep both names.
  electronLanguages: ['en', 'en-US'],
  // Register the vicoa:// URL scheme so the packaged app is launchable from an
  // OAuth callback redirect (declares CFBundleURLTypes in Info.plist on macOS).
  protocols: [{ name: 'Vicoa', schemes: ['vicoa'] }],
  directories: {
    output: 'dist-app',
    // NOTE: buildResources is NOT packed into the app. Runtime assets (tray
    // icon, dock icon, app icon source) live under resources/ instead and are
    // listed in `files` below so they ship inside the bundle.
    buildResources: 'build',
  },
  files: [
    'dist/**',
    'package.json',
    'resources/**',
    // Ship only the icon for the platform this invocation targets — electron-
    // builder reads the icon it needs from the source tree before packing, so
    // the other two (icon.icns mac / icon.ico win / icon-linux.png linux) are
    // dead weight inside the shipped app. Drop the two we aren't targeting.
    ...(targetsWin
      ? ['!resources/icon.icns', '!resources/icon-linux.png']
      : targetsLinux
        ? ['!resources/icon.icns', '!resources/icon.ico']
        : ['!resources/icon.ico', '!resources/icon-linux.png']),
  ],
  // The renderer (renderer-dist -> Resources/renderer) AND the per-arch daemon
  // (daemon-dist/<arch> -> Resources/daemon) are copied by the afterPack hook,
  // NOT extraResources. The renderer needs its flattened node_modules tree,
  // which electron-builder's walker hard-skips; the daemon must be arch-native
  // per .app, and afterPack runs once per arch with context.arch (extraResources
  // would copy one fixed dir into every arch).
  afterPack: 'scripts/after-pack.cjs',
  // Auto-update feed. electron-builder writes app-update.yml into the bundle
  // from this block and, on `--publish`, uploads latest-mac.yml + the .zip/.dmg
  // + .blockmap to a GitHub Release. electron-updater (src/updater.ts) reads
  // the bundled app-update.yml, then fetches the manifest from this public repo
  // (no token needed). releaseType 'draft' keeps a release invisible to the
  // updater until every asset has finished uploading — the CI workflow
  // un-drafts it as the last step.
  publish: {
    provider: 'github',
    owner: 'vicoa-ai',
    repo: 'vicoa',
    releaseType: 'draft',
  },
  mac: {
    // macOS-ONLY. Declared here rather than at the top level so a --win build
    // never tries to copy this Mach-O (which build-notification-status.mjs only
    // produces on a Mac) into the Windows app.
    //
    // UNUserNotificationCenter status helper (scripts/build-notification-status.mjs).
    // Built as a UNIVERSAL (arm64+x86_64) binary so the single file shipped here
    // runs natively in both the arm64 and x64 apps. Must live in Contents/MacOS:
    // NSBundle resolves the bundle by walking up from the executable path, and
    // macOS 26 aborts UNUserNotificationCenter for executables run from
    // Contents/Resources. (Orca pattern.)
    extraFiles: [
      {
        from: 'native/notification-status/dist/vicoa-notification-status',
        to: 'MacOS/vicoa-notification-status',
      },
    ],
    // Both entries share macArchs. On a release that is ['arm64','x64'], so this
    // one invocation emits both arch dmgs+zips and a SINGLE latest-mac.yml that
    // lists both — the only way to keep both archs' auto-update feeds intact.
    target: [
      { target: 'dmg', arch: macArchs },
      { target: 'zip', arch: macArchs },
    ],
    category: 'public.app-category.developer-tools',
    icon: 'resources/icon.icns',
    // The notification helper is a LOOSE Mach-O in Contents/MacOS (not a nested
    // .app/.framework), so electron-builder's signer doesn't discover it on its
    // own — and sealing the main executable then fails with "subcomponent … is
    // not signed at all". List it so it's signed (per arch) BEFORE the bundle is
    // sealed. Path resolves relative to the .app (MacTargetHelper), so it must
    // include Contents/. This is the universal binary from build-notification-status.
    binaries: ['Contents/MacOS/vicoa-notification-status'],
    // Release: auto-discover the Developer ID Application identity (keychain
    // locally, CSC_LINK in CI). Local: identity:null forces electron-builder's
    // signing off so after-pack.cjs ad-hoc signs instead (a fully unsigned
    // bundle is hard-rejected by UNUserNotificationCenter).
    identity: isMacRelease ? undefined : null,
    hardenedRuntime: isMacRelease,
    gatekeeperAssess: false,
    entitlements: isMacRelease ? entitlements : undefined,
    entitlementsInherit: isMacRelease ? entitlements : undefined,
    // Enable @electron/notarize on release; the App Store Connect API-key creds
    // come from APPLE_API_KEY / APPLE_API_KEY_ID / APPLE_API_ISSUER env vars
    // (electron-builder 26's notarize is a boolean — no teamId here; the team,
    // is implied by the Developer ID cert). Off for local dogfood
    // and for the local pre-flight (VICOA_SKIP_NOTARIZE=1).
    notarize: isFullRelease,
  },
  // Icons for all three platforms come from `pnpm make:icon` — mac gets the
  // baked squircle, win/linux stay square and full-bleed.
  win: {
    icon: 'resources/icon.ico',
    // x64 only: that is the sole Windows arch the frozen daemon ships
    // (vicoa-windows-x64.zip). An arm64 Windows app would run under emulation
    // but bundle no daemon, so don't offer one until the daemon does.
    target: [{ target: 'nsis', arch: ['x64'] }],
    // NO signing config on purpose — see the file header. electron-builder
    // skips signing (with a warning) when no certificate is configured, which
    // is exactly what we want; do not "fix" that warning by pointing this at a
    // self-signed cert, which buys nothing and confuses the SmartScreen story.
  },
  nsis: {
    // Assisted (not one-click) installer: users get a visible, cancellable
    // install with a directory choice, which reads as less malware-ish than a
    // silent one-click — worth the extra click while we're unsigned.
    oneClick: false,
    allowToChangeInstallationDirectory: true,
    // Per-USER install (%LOCALAPPDATA%). Critical for auto-update: a perMachine
    // install writes to Program Files and so needs a UAC elevation prompt on
    // EVERY update, which silently kills unattended updating.
    perMachine: false,
    createDesktopShortcut: true,
    shortcutName: 'Vicoa',
  },
  linux: {
    icon: 'resources/icon-linux.png',
    category: 'Development',
    // AppImage ONLY — it is the sole Linux target electron-updater can auto-
    // update: on `--publish` it writes latest-linux.yml (the analogue of
    // latest-mac.yml / latest.yml) and applies updates in place. .deb/.rpm/
    // .snap update through the system package manager instead, so shipping them
    // would fork the update story from the mac/win auto-update contract. x64
    // only: the frozen daemon ships just vicoa-linux-x64.tar.gz, so an arm64
    // AppImage would bundle no daemon (same rule as Windows).
    target: [{ target: 'AppImage', arch: ['x64'] }],
  },
  dmg: {
    // Release dmgs inherit the app's Developer ID signature; local dmgs have no
    // stable identity to sign against, so skip dmg signing there.
    sign: false,
  },
  npmRebuild: false,
};
