#!/usr/bin/env node
/**
 * Theme-color guard.
 *
 * Fails if a themeable app-chrome file reintroduces a hardcoded hex color in a
 * Tailwind arbitrary-value utility (e.g. `bg-[#2D2D2D]`, `text-[#161C24]`).
 * Chrome must read semantic tokens (`bg-menu`, `text-muted-foreground`, …) so
 * it flips with the light/dark/plugin theme. See app/globals.css for the token
 * set and plans/todos/theming-tokenization.md for the rationale.
 *
 * Deliberately NOT matched: inline-style hex in JS objects (e.g. label-swatch
 * data) — this only flags the `-[#…]` Tailwind class form. Exempt paths below
 * are either intentionally-fixed-dark panels (VS-Code-style editor + terminal),
 * marketing pages with their own styling, or platform conventions.
 *
 * Run: `node scripts/check-theme-colors.mjs` (wired into `pnpm lint`).
 */

import { readdirSync, readFileSync, statSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join, relative } from 'node:path';

const WEB_ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');

// Directories to scan for themeable chrome.
const SCAN_DIRS = ['components', 'app'];

// Prefixes (relative to apps/web/) that are exempt from the rule.
const EXEMPT_PREFIXES = [
  // Plane B — intentionally fixed-dark surfaces (editor + terminal), always
  // dark in every theme by design.
  'components/files-git-panel/',
  'components/terminal-pane/',
  // Marketing / public pages: own always-on styling, not app chrome.
  'components/landing/',
  'components/vs/',
  'app/(marketing)/',
];

// Individual files that are exempt (platform conventions / decorative).
const EXEMPT_FILES = new Set([
  'components/desktop/window-chrome.tsx', // Windows close-button system red (#c42b1c)
  'components/onboarding/intro-slides.tsx', // decorative onboarding gradient
]);

// Tailwind color utilities that take an arbitrary hex value.
const HARDCODED_HEX =
  /\b(?:bg|text|border|ring|fill|stroke|from|via|to|shadow|decoration|outline|caret|accent|divide|placeholder)-\[#[0-9a-fA-F]{3,8}\b/;

/** @param {string} abs @returns {string[]} */
function walk(abs) {
  const out = [];
  for (const entry of readdirSync(abs)) {
    if (entry === 'node_modules' || entry === '.next') continue;
    const full = join(abs, entry);
    if (statSync(full).isDirectory()) out.push(...walk(full));
    else if (/\.(tsx?|jsx?)$/.test(entry)) out.push(full);
  }
  return out;
}

function isExempt(rel) {
  if (EXEMPT_FILES.has(rel)) return true;
  return EXEMPT_PREFIXES.some((p) => rel.startsWith(p));
}

const violations = [];
for (const dir of SCAN_DIRS) {
  const abs = join(WEB_ROOT, dir);
  let files;
  try {
    files = walk(abs);
  } catch {
    continue; // dir absent — skip
  }
  for (const file of files) {
    const rel = relative(WEB_ROOT, file);
    if (isExempt(rel)) continue;
    const lines = readFileSync(file, 'utf8').split('\n');
    lines.forEach((line, i) => {
      const m = line.match(HARDCODED_HEX);
      if (m) violations.push(`${rel}:${i + 1}  ${m[0]}`);
    });
  }
}

if (violations.length > 0) {
  console.error(
    `\n✖ Hardcoded theme colors found in app chrome (use a semantic token from globals.css instead):\n`,
  );
  for (const v of violations) console.error(`  ${v}`);
  console.error(
    `\n  If a surface is intentionally fixed (e.g. an always-dark editor panel),` +
      ` add its path to EXEMPT_PREFIXES/EXEMPT_FILES in scripts/check-theme-colors.mjs.\n`,
  );
  process.exit(1);
}

console.log('✓ No hardcoded theme colors in app chrome.');
