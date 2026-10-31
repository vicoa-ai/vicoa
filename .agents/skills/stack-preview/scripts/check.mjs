#!/usr/bin/env node
// Browser check for a running stack-preview: sign in as a seeded account in
// headless Chromium at the public URL, visit pages, and print only what is
// broken. Run it through `stack-preview.sh check`, which passes the account
// and URL in PREVIEW_CHECK_* variables.
//
//   stack-preview.sh check /dashboard /dashboard/tasks      # status + problems per page
//   stack-preview.sh check --script flow.mjs                # your interactions, no boilerplate
//
// Screenshots are off unless --shot is given: an image costs an agent far more
// to read than the line of text that says whether the page is right.
//
// A --script file exports one async function. It gets a signed-in page:
//
//   export default async ({ page, go, shot, url }) => {
//     await go('/dashboard/tasks');                 // goto + wait for the page to settle
//     await page.getByText('Fix login').click();
//     await shot('task-open', { selector: 'main' }); // no-op without --shot
//     return await page.locator('main').last().innerText(); // printed as JSON; the dashboard nests two <main>
//   };
//
// Zero dependencies of its own; Playwright is looked up (PREVIEW_PLAYWRIGHT,
// apps/web, the npx cache, the global npm root) so nothing is added to the repo.

import { createRequire } from 'node:module';
import { execFileSync } from 'node:child_process';
import { existsSync, mkdirSync, readdirSync, statSync } from 'node:fs';
import { homedir } from 'node:os';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const env = process.env;
const base = (env.PREVIEW_URL ?? '').replace(/\/$/, '');
const email = env.PREVIEW_CHECK_EMAIL ?? '';
const password = env.PREVIEW_CHECK_PASSWORD ?? '';
const shotsDir = env.PREVIEW_CHECK_SHOTS ?? '';
const script = env.PREVIEW_CHECK_SCRIPT ?? '';
const paths = process.argv.slice(2);

function fail(message) {
  console.error(`check: error: ${message}`);
  process.exit(2);
}

if (!base || !email || !password) fail('run this through stack-preview.sh check');
const badPath = paths.find((p) => !p.startsWith('/'));
if (badPath) fail(`paths start with / (got ${badPath})`);
const viewportMatch = /^(\d+)x(\d+)$/.exec(env.PREVIEW_CHECK_VIEWPORT || '1280x800');
if (!viewportMatch) fail('--viewport expects WIDTHxHEIGHT, e.g. 390x844');
const viewport = { width: Number(viewportMatch[1]), height: Number(viewportMatch[2]) };

function loadPlaywright() {
  const roots = [];
  if (env.PREVIEW_PLAYWRIGHT) roots.push(env.PREVIEW_PLAYWRIGHT);
  if (env.PREVIEW_REPO) roots.push(join(env.PREVIEW_REPO, 'apps/web'));
  const npx = join(homedir(), '.npm/_npx');
  if (existsSync(npx)) {
    const newestFirst = readdirSync(npx)
      .map((name) => join(npx, name))
      .filter((dir) => existsSync(join(dir, 'node_modules/playwright')))
      .sort((a, b) => statSync(b).mtimeMs - statSync(a).mtimeMs);
    roots.push(...newestFirst);
  }
  try {
    roots.push(execFileSync('npm', ['root', '-g'], { encoding: 'utf8' }).trim());
  } catch {
    // no npm on PATH; the other roots may still work
  }
  for (const root of roots) {
    try {
      return createRequire(`${resolve(root)}/`)('playwright');
    } catch {
      // not installed under this root
    }
  }
  fail(
    'Playwright not found. Run `npx -y playwright install chromium` once (it fills the npx cache ' +
      'this looks in), or set PREVIEW_PLAYWRIGHT to a directory that has node_modules/playwright.',
  );
}

const { chromium } = loadPlaywright();

// What the open build is expected to say; hiding it keeps real errors visible.
const knownNoise = (status, pathname) =>
  (status === 404 && pathname.startsWith('/api/v1/billing/')) ||
  (status === 401 && pathname === '/api/supabase-user');

const clip = (text, max = 240) => {
  const line = String(text).split('\n')[0];
  return line.length > max ? `${line.slice(0, max)}…` : line;
};

let current = '(sign-in)';
let collecting = false;
let ignored = 0;
let shotsSkipped = false;
let shotCount = 0;
const problems = []; // { path, text }
const visits = []; // { path, status, landed, title }

const note = (text) => {
  if (collecting) problems.push({ path: current, text: clip(text) });
};

const browser = await chromium.launch();
for (const signal of ['SIGINT', 'SIGTERM']) {
  process.on(signal, () => void browser.close().finally(() => process.exit(130)));
}

let exitCode = 0;
try {
  const context = await browser.newContext({ viewport });
  const page = await context.newPage();
  page.setDefaultTimeout(15_000); // a wrong selector should fail in seconds, not 30 s

  page.on('pageerror', (error) => note(`pageerror: ${error.message}`));
  page.on('console', (message) => {
    // "Failed to load resource" carries no URL; the response handler reports it with one.
    if (message.type() === 'error' && !message.text().startsWith('Failed to load resource')) {
      note(`console: ${message.text()}`);
    }
  });
  page.on('response', (response) => {
    const request = response.request();
    if (response.status() < 400 || request.isNavigationRequest()) return;
    const pathname = new URL(response.url()).pathname;
    if (knownNoise(response.status(), pathname)) {
      if (collecting) ignored += 1;
      return;
    }
    note(`HTTP ${response.status()} ${request.method()} ${pathname}`);
  });
  page.on('requestfailed', (request) => {
    const reason = request.failure()?.errorText ?? '';
    if (reason.includes('ERR_ABORTED')) return; // a navigation cancelled the request
    note(`request failed: ${request.method()} ${new URL(request.url()).pathname} (${reason})`);
  });

  async function settle() {
    // Polling pages may never go idle; a short wait is enough.
    await page.waitForLoadState('networkidle', { timeout: 15_000 }).catch(() => {});
  }

  async function signIn() {
    for (const attempt of [1, 2]) {
      await page.goto(`${base}/sign-in`, { waitUntil: 'load', timeout: 120_000 });
      await settle();
      // Submitting before React hydrates does a native GET and puts the password in the URL.
      await page.waitForTimeout(attempt * 500);
      await page.locator('#email').fill(email);
      await page.locator('#password').fill(password);
      await page.getByRole('button', { name: 'Continue' }).click();
      await page
        .waitForURL((u) => !u.pathname.startsWith('/sign-in') || u.search.includes('password='), {
          timeout: 30_000,
        })
        .catch(() => {});
      if (!new URL(page.url()).pathname.startsWith('/sign-in')) return;
    }
    const said = await page
      .locator('body')
      .innerText({ timeout: 5_000 })
      .then((text) => clip(text.replace(/\s+/g, ' '), 200))
      .catch(() => '');
    throw new Error(`sign-in as ${email} did not leave /sign-in. The page says: ${said}`);
  }

  async function go(path) {
    current = path;
    const response = await page.goto(`${base}${path}`, { waitUntil: 'load', timeout: 120_000 });
    await settle();
    const status = response?.status() ?? 0;
    const landed = new URL(page.url()).pathname;
    visits.push({ path, status, landed, title: await page.title().catch(() => '') });
    return status;
  }

  async function shot(name, options = {}) {
    if (!shotsDir) {
      if (!shotsSkipped) console.log('shot skipped: screenshots are off (pass --shot when asked for one)');
      shotsSkipped = true;
      return null;
    }
    mkdirSync(shotsDir, { recursive: true });
    const file = join(shotsDir, `${String(name).replace(/[^\w.-]+/g, '-')}.png`);
    const target = options.selector ? page.locator(options.selector).first() : page;
    await target.screenshot({ path: file });
    shotCount += 1;
    console.log(`shot: ${file}`);
    return file;
  }

  try {
    await signIn();
    await settle(); // the landing page's own requests belong to sign-in, not to the first path
    collecting = true;

    if (script) {
      current = '(script)'; // until the script calls go()
      const mod = await import(pathToFileURL(resolve(script)).href);
      if (typeof mod.default !== 'function') fail(`${script} must export default an async function`);
      const result = await mod.default({ page, context, browser, url: base, go, shot });
      if (result !== undefined) console.log(JSON.stringify(result, null, 1));
    }
    for (const path of paths) {
      await go(path);
      if (shotsDir) await shot(`${String(visits.length).padStart(2, '0')}${path.replace(/[^\w]+/g, '-')}`);
    }
  } catch (error) {
    exitCode = 1;
    // Playwright's call log (the locator it waited for) is on the lines after the first.
    const message = error instanceof Error ? error.message : String(error);
    console.log(`error: ${message.split('\n').slice(0, 4).join('\n').slice(0, 600)}`);
  }

  for (const visit of visits) {
    const moved = visit.landed !== visit.path.split(/[?#]/)[0] ? `  -> ${visit.landed}` : '';
    const title = visit.title ? `  "${clip(visit.title, 60)}"` : '';
    console.log(`${visit.status} ${visit.path}${moved}${title}`);
    if (visit.status >= 400 || visit.landed.startsWith('/sign-in')) exitCode = 1;
  }
  const byPath = new Map();
  for (const { path, text } of problems) {
    const counts = byPath.get(path) ?? new Map();
    counts.set(text, (counts.get(text) ?? 0) + 1);
    byPath.set(path, counts);
  }
  for (const [path, counts] of byPath) {
    exitCode = 1;
    const lines = [...counts].map(([text, n]) => (n > 1 ? `${text} (x${n})` : text));
    console.log(`problems on ${path}:`);
    for (const line of lines.slice(0, 10)) console.log(`  ${line}`);
    if (lines.length > 10) console.log(`  +${lines.length - 10} more`);
  }
  if (!byPath.size && !exitCode) console.log('no console errors or failed requests');
  if (ignored) console.log(`ignored ${ignored} expected response(s): billing 404, supabase-user 401`);
  if (shotCount) console.log(`${shotCount} screenshot(s) in ${shotsDir}`);
} finally {
  await browser.close();
}
process.exit(exitCode);
