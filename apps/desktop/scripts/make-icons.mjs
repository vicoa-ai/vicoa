// Generates every platform's app icon from one master: icon-src/master-1024.png.
//
// Why per-platform art instead of one shared image: the rounded "squircle" is a
// macOS convention with a generous transparent margin (Apple's grid: an 824x824
// body centred on a 1024 canvas, 185.4pt continuous-curvature radius). Windows
// wants the SAME rounded look so the brand mark isn't a hard-cornered square
// next to the macOS icon — but nearly full-bleed: reuse the continuous-curvature
// shape with a much smaller inset (Apple's ~10% margin would leave the Windows
// taskbar icon looking shrunken beside its neighbours). Linux stays square,
// full-bleed — the icon theme applies its own shaping.
//
// macOS 26 (Tahoe) masks legacy .icns icons at render time, which hides a
// square master on Tahoe while it renders hard-cornered on macOS 15 and
// earlier, and on the dev dock icon (app.dock.setIcon) on every version.
// Baking the shape is what makes the icon consistent everywhere.
//
// Outputs (all generated — do not hand-edit):
//   resources/icon.icns      mac app icon, 16 -> 1024, squircle
//   resources/icon-512.png   dev dock icon; MUST match the .icns shape
//   resources/icon.ico       windows, rounded (continuous-curvature), near full-bleed
//   resources/icon-linux.png linux, square full-bleed
//
// Requires sips + iconutil + swift (macOS toolchain, already required by
// build-notification-status.mjs).

import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const desktopDir = path.dirname(scriptDir);
const resDir = path.join(desktopDir, 'resources');
const master = path.join(desktopDir, 'icon-src', 'master-1024.png');

// Apple's macOS icon grid, on a 1024 canvas.
const CANVAS = 1024;
const INSET = 100;
const RADIUS = 185.4;

const run = (cmd, args) => execFileSync(cmd, args, { stdio: ['ignore', 'pipe', 'pipe'] });

if (!fs.existsSync(master)) {
  console.error(`make-icons: master not found at ${master}`);
  console.error('make-icons: expected a 1024x1024 square, full-bleed PNG.');
  process.exit(1);
}

const tmpDir = fs.mkdtempSync(path.join(desktopDir, '.icon-build-'));
const cleanup = () => fs.rmSync(tmpDir, { recursive: true, force: true });

try {
  // --- macOS: bake the squircle, then derive every size from the shaped 1024.
  const shaped = path.join(tmpDir, 'shaped-1024.png');
  run('swift', [
    path.join(scriptDir, 'icon-shape.swift'),
    master, shaped, String(CANVAS), String(INSET), String(RADIUS),
  ]);

  const iconset = path.join(tmpDir, 'icon.iconset');
  fs.mkdirSync(iconset);
  // Every size macOS asks for, including the 1024 (512x512@2x) the old
  // 512-only pipeline could not produce.
  const macSizes = [
    [16, 'icon_16x16.png'], [32, 'icon_16x16@2x.png'],
    [32, 'icon_32x32.png'], [64, 'icon_32x32@2x.png'],
    [128, 'icon_128x128.png'], [256, 'icon_128x128@2x.png'],
    [256, 'icon_256x256.png'], [512, 'icon_256x256@2x.png'],
    [512, 'icon_512x512.png'], [1024, 'icon_512x512@2x.png'],
  ];
  for (const [size, name] of macSizes) {
    run('sips', ['-z', String(size), String(size), shaped, '--out', path.join(iconset, name)]);
  }
  run('iconutil', ['-c', 'icns', iconset, '-o', path.join(resDir, 'icon.icns')]);

  // The dev dock icon is set at runtime from this PNG, and runtime dock icons
  // are never auto-masked — so it has to carry the shape itself.
  run('sips', ['-z', '512', '512', shaped, '--out', path.join(resDir, 'icon-512.png')]);

  // --- Windows: rounded (continuous-curvature) square, near full-bleed, .ico.
  // Same squircle curve as macOS so the mark reads as "rounded like mac", but a
  // much smaller inset than Apple's grid — Windows taskbar tiles want the art
  // nearly edge-to-edge, or it looks shrunken next to its neighbours.
  const WIN_INSET = 24; //  ~2.3% margin on the 1024 canvas (vs macOS's 100)
  const WIN_RADIUS = 205; // ~21% of the 976px body — a Win11-style rounded square
  const shapedWin = path.join(tmpDir, 'shaped-win-1024.png');
  run('swift', [
    path.join(scriptDir, 'icon-shape.swift'),
    master, shapedWin, String(CANVAS), String(WIN_INSET), String(WIN_RADIUS),
  ]);
  const icoSizes = [16, 24, 32, 48, 64, 128, 256];
  const icoPngs = icoSizes.map((size) => {
    const out = path.join(tmpDir, `ico-${size}.png`);
    run('sips', ['-z', String(size), String(size), shapedWin, '--out', out]);
    return { size, data: fs.readFileSync(out) };
  });
  fs.writeFileSync(path.join(resDir, 'icon.ico'), buildIco(icoPngs));

  // --- Linux: square, full-bleed; the icon theme applies any shaping itself.
  run('sips', ['-z', '1024', '1024', master, '--out', path.join(resDir, 'icon-linux.png')]);

  console.log('make-icons: wrote icon.icns, icon-512.png, icon.ico, icon-linux.png');
} finally {
  cleanup();
}

/**
 * Pack PNGs into an .ico. Windows Vista+ reads PNG-compressed entries
 * directly, so each image embeds as-is — no BMP re-encoding needed.
 */
function buildIco(images) {
  const HEADER = 6;
  const ENTRY = 16;
  const header = Buffer.alloc(HEADER);
  header.writeUInt16LE(0, 0); // reserved
  header.writeUInt16LE(1, 2); // type: icon
  header.writeUInt16LE(images.length, 4);

  let offset = HEADER + ENTRY * images.length;
  const entries = [];
  for (const { size, data } of images) {
    const entry = Buffer.alloc(ENTRY);
    entry.writeUInt8(size >= 256 ? 0 : size, 0); // 0 means 256
    entry.writeUInt8(size >= 256 ? 0 : size, 1);
    entry.writeUInt8(0, 2); // palette size
    entry.writeUInt8(0, 3); // reserved
    entry.writeUInt16LE(1, 4); // color planes
    entry.writeUInt16LE(32, 6); // bits per pixel
    entry.writeUInt32LE(data.length, 8);
    entry.writeUInt32LE(offset, 12);
    entries.push(entry);
    offset += data.length;
  }
  return Buffer.concat([header, ...entries, ...images.map((i) => i.data)]);
}
