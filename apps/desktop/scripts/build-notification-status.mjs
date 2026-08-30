#!/usr/bin/env node
// Builds the vicoa-notification-status helper binary (pattern adapted from
// Orca's build-notification-status-macos.mjs, MIT, Lovecast Inc.).
//
// The helper reads UNUserNotificationCenter settings for the app it ships
// inside (see native/notification-status/main.swift). The target
// CFBundleIdentifier is embedded as a __TEXT,__info_plist section so any
// later `codesign --force` pass (the after-pack ad-hoc deep sign, or a real
// identity later) derives the correct code identifier automatically — macOS
// keys notification records to that identifier.
import { execFileSync } from 'node:child_process';
import { mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const desktopDir = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const sourcePath = path.join(desktopDir, 'native', 'notification-status', 'main.swift');
const outputPath = path.join(
  desktopDir,
  'native',
  'notification-status',
  'dist',
  'vicoa-notification-status',
);

if (process.platform !== 'darwin') {
  process.exit(0);
}

// Must match electron-builder.yml appId — the packaged bundle's identity.
const bundleId = process.env.VICOA_MAC_BUNDLE_ID ?? 'ai.vicoa.desktop';
// Universal (arm64 + x86_64): the helper ships to BOTH the arm64 and x64 apps
// via electron-builder extraFiles, so the single binary must run natively on
// each. Build one slice per arch (the macOS SDK carries both, so this
// cross-compiles fine on either runner), then lipo them into a fat binary.
const SLICE_ARCHS = ['arm64', 'x86_64'];

const workDir = path.join(tmpdir(), `vicoa-notification-status-${process.pid}`);
mkdirSync(workDir, { recursive: true });
try {
  const plistPath = path.join(workDir, 'Info.plist');
  writeFileSync(plistPath, embeddedInfoPlist(bundleId), 'utf8');
  mkdirSync(path.dirname(outputPath), { recursive: true });
  const slicePaths = SLICE_ARCHS.map((arch) => {
    const slicePath = path.join(workDir, `vicoa-notification-status-${arch}`);
    execFileSync(
      'swiftc',
      [
        '-O',
        sourcePath,
        '-target',
        `${arch}-apple-macosx11.0`,
        '-o',
        slicePath,
        '-Xlinker',
        '-sectcreate',
        '-Xlinker',
        '__TEXT',
        '-Xlinker',
        '__info_plist',
        '-Xlinker',
        plistPath,
      ],
      { stdio: 'inherit' },
    );
    return slicePath;
  });
  execFileSync('lipo', ['-create', ...slicePaths, '-output', outputPath]);
  execFileSync('chmod', ['755', outputPath]);
  console.log(
    `[build-notification-status] built universal (${SLICE_ARCHS.join('+')}) ${outputPath} (bundle id ${bundleId})`,
  );
} finally {
  rmSync(workDir, { recursive: true, force: true });
}

function embeddedInfoPlist(identifier) {
  return `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleIdentifier</key>
  <string>${identifier}</string>
  <key>CFBundleName</key>
  <string>vicoa-notification-status</string>
</dict>
</plist>
`;
}
