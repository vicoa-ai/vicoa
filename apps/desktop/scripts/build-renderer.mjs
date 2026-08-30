#!/usr/bin/env node
/**
 * Build the Next.js renderer for the desktop app and stage it into
 * `apps/desktop/renderer-dist/`.
 *
 * Desktop builds must bake desktop env at BUILD time — `NEXT_PUBLIC_*` vars
 * are inlined into the bundles by `next build`. This script:
 *
 *   1. Runs `pnpm build` in the worktree root with:
 *        NEXT_PUBLIC_VICOA_DESKTOP=1            (desktop layout + middleware bypass)
 *        NEXT_PUBLIC_BACKEND_API_URL=<cloud>    (default https://api.vicoa.ai)
 *        NEXT_PUBLIC_VICOA_WS_URL=<cloud>       (default wss://agents.vicoa.ai/ws)
 *      Cloud URL defaults can be overridden via the same env var names when
 *      invoking this script. All other NEXT_PUBLIC_* (Supabase publics,
 *      PostHog, …) come from the repo's `.env` exactly as `next build` reads
 *      them normally — nothing is hardcoded here.
 *   2. Stages the standalone server per Next's documented layout:
 *        .next/standalone/*  -> renderer-dist/
 *        .next/static        -> renderer-dist/.next/static
 *        public/             -> renderer-dist/public
 *   3. Strips any `.env*` files Next copied into the standalone output
 *      (they contain server-only secrets that must NOT ship in the app) and
 *      writes a sanitized `.env` containing only the baked NEXT_PUBLIC_* keys
 *      so server-side code that reads them at runtime still works.
 *
 * Run: node apps/desktop/scripts/build-renderer.mjs   (from anywhere)
 */
import { execFileSync } from 'node:child_process';
import * as fs from 'node:fs';
import * as path from 'node:path';
import { fileURLToPath } from 'node:url';

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const desktopDir = path.dirname(scriptDir);
// The renderer is the sibling web app (apps/web), a peer of apps/desktop.
const webRoot = path.resolve(desktopDir, '..', 'web');
const stagingDir = path.join(desktopDir, 'renderer-dist');

// --- Desktop build env -------------------------------------------------------
const CLOUD_DEFAULTS = {
  NEXT_PUBLIC_BACKEND_API_URL: 'https://api.vicoa.ai',
  NEXT_PUBLIC_VICOA_WS_URL: 'wss://agents.vicoa.ai/ws',
};

/** Minimal .env parser (KEY=VALUE lines, # comments, optional quotes). */
function parseDotEnv(file) {
  const out = {};
  if (!fs.existsSync(file)) return out;
  for (const line of fs.readFileSync(file, 'utf8').split('\n')) {
    const m = /^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$/.exec(line);
    if (!m) continue;
    let value = m[2];
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    out[m[1]] = value;
  }
  return out;
}

const dotEnv = parseDotEnv(path.join(webRoot, '.env'));

// Effective public env baked into the build. Sources, low → high precedence:
//   repo .env (local dev)  <  process.env (CI secrets / caller overrides).
// BOTH must be harvested: locally the NEXT_PUBLIC_* publics come from the .env
// file, but in CI there is NO .env file — they arrive purely as workflow
// secrets in process.env. (Harvesting only .env is why the first release run
// aborted with "missing NEXT_PUBLIC_SUPABASE_URL" despite the env being set.)
const bakedPublicEnv = {};
for (const [key, value] of Object.entries(dotEnv)) {
  if (key.startsWith('NEXT_PUBLIC_')) bakedPublicEnv[key] = value;
}
for (const [key, value] of Object.entries(process.env)) {
  if (key.startsWith('NEXT_PUBLIC_') && value !== undefined) bakedPublicEnv[key] = value;
}
// The two backend URLs always default to cloud unless the caller overrides
// them — a dev's local .env points them at localhost, which must NOT bake in.
for (const [key, fallback] of Object.entries(CLOUD_DEFAULTS)) {
  bakedPublicEnv[key] = process.env[key] ?? fallback;
}
bakedPublicEnv.NEXT_PUBLIC_VICOA_DESKTOP = '1';

for (const required of ['NEXT_PUBLIC_SUPABASE_URL', 'NEXT_PUBLIC_SUPABASE_ANON_KEY']) {
  if (!bakedPublicEnv[required]) {
    console.error(
      `build-renderer: missing ${required} — set it in ${webRoot}/.env or the environment.`,
    );
    process.exit(1);
  }
}

// --- 1. next build -----------------------------------------------------------
console.log('[build-renderer] baked public env:');
for (const key of Object.keys(bakedPublicEnv).sort()) {
  const value = bakedPublicEnv[key];
  const shown = /KEY|TOKEN|SECRET/i.test(key) ? `${value.slice(0, 8)}…` : value;
  console.log(`  ${key}=${shown}`);
}
// Remove .next build OUTPUTS so the packaged bundle can never ship stale
// CSS/chunks: Next reuses compiled route output across builds, so an
// incremental `pnpm build` left an old globals.css (fonts, tokens) baked into
// a fresh dmg. KEEP `.next/cache` (the webpack pack cache): it is safe — env
// changes invalidate affected modules via DefinePlugin valueCacheVersions —
// and a fully cold compile spikes several extra GB of RAM, enough to get the
// build SIGKILLed ("Killed: 9") on a memory-loaded machine.
const nextDir = path.join(webRoot, '.next');
console.log(`[build-renderer] cleaning ${nextDir} outputs (keeping cache/) …`);
if (fs.existsSync(nextDir)) {
  for (const entry of fs.readdirSync(nextDir)) {
    if (entry === 'cache') continue;
    fs.rmSync(path.join(nextDir, entry), { recursive: true, force: true });
  }
}

console.log(`[build-renderer] running pnpm build in ${webRoot} …`);
// `pnpm` is `pnpm.cmd` on Windows, and since the CVE-2024-27980 fix Node
// refuses to spawn a .cmd/.bat WITHOUT a shell — even when the .cmd file is
// named explicitly — throwing EINVAL (observed on the windows-latest runner's
// Node v22.23.1). So on Windows we must run it through a shell. That is safe
// here: the only argument is the static literal 'build', and every dynamic
// value flows through the `env` option (never the command line), so there is
// no shell-injection surface.
const isWindows = process.platform === 'win32';
execFileSync(isWindows ? 'pnpm.cmd' : 'pnpm', ['build'], {
  cwd: webRoot,
  stdio: 'inherit',
  shell: isWindows,
  // Process env wins over .env inside next build, so setting the overrides
  // here is sufficient; everything else still flows from .env as usual.
  env: { ...process.env, ...bakedPublicEnv },
});

// --- 2. stage per Next's documented standalone layout -------------------------
const standaloneDir = path.join(webRoot, '.next', 'standalone');
if (!fs.existsSync(path.join(standaloneDir, 'server.js'))) {
  console.error(
    `build-renderer: ${standaloneDir}/server.js not found — is output:'standalone' set in next.config.ts?`,
  );
  process.exit(1);
}

console.log(`[build-renderer] staging into ${stagingDir} …`);
fs.rmSync(stagingDir, { recursive: true, force: true });
fs.mkdirSync(stagingDir, { recursive: true });
fs.cpSync(standaloneDir, stagingDir, { recursive: true });
fs.cpSync(path.join(webRoot, '.next', 'static'), path.join(stagingDir, '.next', 'static'), {
  recursive: true,
});
fs.cpSync(path.join(webRoot, 'public'), path.join(stagingDir, 'public'), { recursive: true });

// --- 2b. flatten node_modules to a symlink-free hoisted layout ----------------
// With pnpm, Next's standalone output builds node_modules out of symlinks:
// top-level names AND .pnpm sibling deps are ABSOLUTE links back into
// <webRoot>/.next/standalone/node_modules/.pnpm/… . Shipping that breaks
// twice over: the links dangle on any other machine, and electron-builder
// drops node_modules trees from extraResources. Rebuild it as a flat,
// real-file, npm-style hoisted tree: every real package dir found under
// .pnpm/<id>/node_modules/<name> is copied to node_modules/<name>. The
// traced dependency set is small and single-versioned; we fail loudly if two
// different versions of one name ever collide.
flattenPnpmNodeModules(path.join(stagingDir, 'node_modules'));

function readVersion(pkgDir) {
  try {
    return JSON.parse(fs.readFileSync(path.join(pkgDir, 'package.json'), 'utf8')).version ?? '?';
  } catch {
    return '?';
  }
}

/** Yield [name, realDir] for every real package dir under <id>/node_modules. */
function* realPackagesIn(nmDir) {
  for (const entry of fs.readdirSync(nmDir, { withFileTypes: true })) {
    if (entry.name.startsWith('.')) continue;
    const entryPath = path.join(nmDir, entry.name);
    if (entry.name.startsWith('@')) {
      if (!entry.isDirectory()) continue; // scope containers are real dirs
      for (const sub of fs.readdirSync(entryPath, { withFileTypes: true })) {
        if (sub.isDirectory() && !sub.isSymbolicLink()) {
          yield [`${entry.name}/${sub.name}`, path.join(entryPath, sub.name)];
        }
      }
    } else if (entry.isDirectory() && !entry.isSymbolicLink()) {
      yield [entry.name, entryPath];
    }
    // symlinks = references to sibling packages, not package sources: skip
  }
}

function flattenPnpmNodeModules(nodeModulesDir) {
  const pnpmDir = path.join(nodeModulesDir, '.pnpm');
  if (!fs.existsSync(pnpmDir)) {
    console.log('[build-renderer] node_modules has no .pnpm dir — leaving as-is');
    return;
  }
  const flatDir = nodeModulesDir + '.flat';
  fs.rmSync(flatDir, { recursive: true, force: true });
  fs.mkdirSync(flatDir, { recursive: true });

  const placed = new Map(); // name -> { version, from }
  // Real package sources all live at .pnpm/<pkg-id>/node_modules/<name>.
  // (.pnpm/node_modules — pnpm's hidden hoist dir — holds only symlinked
  // references to those same sources, so it needs no separate pass.)
  const containers = fs
    .readdirSync(pnpmDir, { withFileTypes: true })
    .filter((e) => e.isDirectory() && e.name !== 'node_modules')
    .map((e) => path.join(pnpmDir, e.name, 'node_modules'));
  for (const container of containers) {
    if (!fs.existsSync(container)) continue;
    for (const [name, realDir] of realPackagesIn(container)) {
      const version = readVersion(realDir);
      const existing = placed.get(name);
      if (existing !== undefined) {
        if (existing.version !== version) {
          console.error(
            `build-renderer: version conflict flattening node_modules: ` +
              `${name}@${existing.version} (${existing.from}) vs ${name}@${version} (${realDir})`,
          );
          process.exit(1);
        }
        continue;
      }
      const target = path.join(flatDir, name);
      fs.mkdirSync(path.dirname(target), { recursive: true });
      // dereference: .pnpm-internal files can themselves be links
      fs.cpSync(realDir, target, { recursive: true, dereference: true });
      placed.set(name, { version, from: realDir });
    }
  }
  fs.rmSync(nodeModulesDir, { recursive: true, force: true });
  fs.renameSync(flatDir, nodeModulesDir);
  console.log(`[build-renderer] flattened node_modules: ${placed.size} packages, symlink-free`);
}

// Guarantee self-containedness: no symlinks may survive staging.
const leftoverLinks = [];
(function findLinks(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, entry.name);
    if (entry.isSymbolicLink()) leftoverLinks.push(p);
    else if (entry.isDirectory()) findLinks(p);
  }
})(stagingDir);
if (leftoverLinks.length > 0) {
  console.error(`build-renderer: staging still contains symlinks:\n  ${leftoverLinks.join('\n  ')}`);
  process.exit(1);
}

// --- 3. strip secrets, write sanitized .env -----------------------------------
for (const entry of fs.readdirSync(stagingDir)) {
  if (entry === '.env' || entry.startsWith('.env.')) {
    fs.rmSync(path.join(stagingDir, entry), { force: true });
    console.log(`[build-renderer] stripped ${entry} from staging (server-only secrets)`);
  }
}
const sanitized =
  Object.entries(bakedPublicEnv)
    .map(([k, v]) => `${k}=${v}`)
    .join('\n') +
  '\n' +
  // lib/db/drizzle.ts throws at module load when POSTGRES_URL is unset, and
  // the root layout imports it (via lib/db/queries). No query ever runs
  // without a legacy `session` cookie — which the desktop app never has — and
  // postgres.js connects lazily, so a guaranteed-refused placeholder keeps
  // module init happy without ever opening a connection.
  'POSTGRES_URL=postgres://127.0.0.1:1/desktop-local-unused\n';
fs.writeFileSync(path.join(stagingDir, '.env'), sanitized);

console.log('[build-renderer] done. Boot it with:');
console.log(`  PORT=4000 HOSTNAME=127.0.0.1 node ${path.join(stagingDir, 'server.js')}`);
