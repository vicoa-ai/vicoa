/**
 * Smoke checks for the daemon-manager pure helpers (`pnpm run check`).
 * No test framework — plain assertions; exits non-zero on failure.
 */
import * as assert from 'node:assert/strict';
import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { getWriteKey, normalizeBaseUrl, withoutWriteKey, withWriteKey } from './credentials';
import {
  backoffDelayMs,
  buildDaemonArgs,
  buildSpawnEnv,
  parseCloudStatus,
  resolveDaemonCommand,
} from './daemon-manager';
import {
  mergeDaemonPath,
  mergePathEntries,
  parseEnvBlock,
  readLoginShellEnv,
  readLoginShellPath,
  readSavedShellPath,
  resolveDaemonEnv,
  shellVarsForDaemon,
} from './resolve-path';

// --- resolveDaemonCommand ---------------------------------------------------
assert.deepEqual(resolveDaemonCommand({}), ['vicoa'], 'default command is vicoa on PATH');
assert.deepEqual(
  resolveDaemonCommand({ VICOA_DAEMON_CMD: '  ' }),
  ['vicoa'],
  'blank override falls back to vicoa',
);
assert.deepEqual(
  resolveDaemonCommand({}, '/Applications/Vicoa.app/Contents/Resources/daemon/vicoa'),
  ['/Applications/Vicoa.app/Contents/Resources/daemon/vicoa'],
  'bundled daemon preferred over PATH',
);
assert.deepEqual(
  resolveDaemonCommand(
    { VICOA_DAEMON_CMD: 'python -m vicoa.cli' },
    '/Applications/Vicoa.app/Contents/Resources/daemon/vicoa',
  ),
  ['python', '-m', 'vicoa.cli'],
  'VICOA_DAEMON_CMD overrides even the bundled daemon',
);
assert.deepEqual(
  resolveDaemonCommand({}, null),
  ['vicoa'],
  'null bundled path falls back to PATH',
);
assert.deepEqual(
  resolveDaemonCommand({
    VICOA_DAEMON_CMD:
      'conda run --no-capture-output -n dev312 --cwd /w/vicoa-backend/src python -m vicoa.cli',
  }),
  [
    'conda',
    'run',
    '--no-capture-output',
    '-n',
    'dev312',
    '--cwd',
    '/w/vicoa-backend/src',
    'python',
    '-m',
    'vicoa.cli',
  ],
  'VICOA_DAEMON_CMD splits on whitespace',
);

// --- buildDaemonArgs ----------------------------------------------------------
assert.deepEqual(
  buildDaemonArgs({ port: 4123, localOnly: true }),
  ['daemon', '--local-listener', '--local-port', '4123', '--local-only'],
  'local-only spawn args',
);
assert.deepEqual(
  buildDaemonArgs({ port: 4123, localOnly: false }),
  ['daemon', '--local-listener', '--local-port', '4123'],
  'authenticated spawn args omit --local-only',
);
assert.deepEqual(
  buildDaemonArgs({ port: 4123, localOnly: false, takeover: true }),
  ['daemon', '--local-listener', '--local-port', '4123', '--takeover'],
  'cloud mode adds --takeover when requested',
);
assert.deepEqual(
  buildDaemonArgs({ port: 4123, localOnly: true, takeover: false }),
  ['daemon', '--local-listener', '--local-port', '4123', '--local-only'],
  'local-only never gets --takeover',
);

// --- parseCloudStatus ---------------------------------------------------------
assert.equal(
  parseCloudStatus('{"status":"ok","mode":"local-only","machine_id":"local","cloud":null}'),
  null,
  'local-only daemon reports cloud=null',
);
assert.equal(
  parseCloudStatus('{"status":"ok","mode":"cloud","cloud":"connected"}'),
  'connected',
  'connected cloud status',
);
assert.equal(parseCloudStatus('{"cloud":"connecting"}'), 'connecting');
assert.equal(parseCloudStatus('{"cloud":"auth_failed"}'), 'auth_failed');
assert.equal(
  parseCloudStatus('{"status":"ok","mode":"cloud","machine_id":"m1"}'),
  undefined,
  'older daemon without the field -> undefined (fallback behavior)',
);
assert.equal(parseCloudStatus('{"cloud":"bogus-value"}'), undefined, 'unknown value -> undefined');
assert.equal(parseCloudStatus('not json'), undefined, 'malformed body -> undefined');

// --- full command assembly (what DaemonManager actually spawns) -------------
{
  const [cmd, ...leading] = resolveDaemonCommand({
    VICOA_DAEMON_CMD: 'conda run -n dev312 python -m vicoa.cli',
  });
  const argv = [cmd, ...leading, ...buildDaemonArgs({ port: 9100, localOnly: true })];
  assert.deepEqual(argv, [
    'conda',
    'run',
    '-n',
    'dev312',
    'python',
    '-m',
    'vicoa.cli',
    'daemon',
    '--local-listener',
    '--local-port',
    '9100',
    '--local-only',
  ]);
}

// --- buildSpawnEnv ------------------------------------------------------------
{
  const env = buildSpawnEnv(
    { PATH: '/usr/bin', HOME: '/home/u' },
    { nonce: 'abc123', origin: 'http://localhost:3000' },
  );
  assert.equal(env.VICOA_LOCAL_NONCE, 'abc123');
  assert.equal(env.VICOA_LOCAL_ORIGIN, 'http://localhost:3000');
  assert.equal(env.PATH, '/usr/bin', 'inherits base env');
  assert.equal(env.HOME, '/home/u', 'inherits base env');
}
{
  // pathOverride replaces PATH for the daemon child only.
  const env = buildSpawnEnv(
    { PATH: '/usr/bin', HOME: '/home/u' },
    { nonce: 'n', origin: 'o', pathOverride: '/opt/homebrew/bin:/usr/bin' },
  );
  assert.equal(env.PATH, '/opt/homebrew/bin:/usr/bin', 'pathOverride replaces PATH');
  assert.equal(env.HOME, '/home/u', 'other env untouched');
}
{
  // Empty pathOverride is a no-op (never blank PATH out).
  const env = buildSpawnEnv(
    { PATH: '/usr/bin' },
    { nonce: 'n', origin: 'o', pathOverride: '' },
  );
  assert.equal(env.PATH, '/usr/bin', 'empty pathOverride leaves PATH intact');
}
{
  // Login-shell vars layer over the inherited env; the contract vars still win.
  const env = buildSpawnEnv(
    { PATH: '/usr/bin', HOME: '/home/u', LANG: 'C' },
    {
      nonce: 'n',
      origin: 'o',
      pathOverride: '/shell/bin:/usr/bin',
      shellVars: { JAVA_HOME: '/jdk', LANG: 'en_US.UTF-8', VICOA_LOCAL_NONCE: 'shell' },
    },
  );
  assert.equal(env.JAVA_HOME, '/jdk', 'shell-only var reaches the daemon');
  assert.equal(env.LANG, 'en_US.UTF-8', 'shell value wins over launchd');
  assert.equal(env.VICOA_LOCAL_NONCE, 'n', 'contract var is not overridable');
  assert.equal(env.PATH, '/shell/bin:/usr/bin', 'PATH still comes from pathOverride');
}

// --- mergePathEntries (PATH merge/de-dup pure fn) -----------------------------
assert.equal(
  mergePathEntries(['/opt/homebrew/bin:/usr/bin', '/usr/bin:/bin', null, '/opt/homebrew/bin']),
  '/opt/homebrew/bin:/usr/bin:/bin',
  'de-dups across fragments, preserves first-seen order',
);
assert.equal(mergePathEntries([]), '', 'no fragments -> empty');
assert.equal(mergePathEntries([undefined, null, '']), '', 'nullish/empty fragments -> empty');
assert.equal(
  mergePathEntries(['/a::/b:', '', '/a:/c']),
  '/a:/b:/c',
  'drops empty segments and later duplicates',
);

// --- backoffDelayMs -----------------------------------------------------------
{
  // Deterministic mid-point jitter (random=0.5 => factor 1.0).
  const mid = (): number => 0.5;
  assert.equal(backoffDelayMs(0, mid), 1_000, 'first retry ~1s');
  assert.equal(backoffDelayMs(1, mid), 2_000);
  assert.equal(backoffDelayMs(4, mid), 16_000);
  assert.equal(backoffDelayMs(10, mid), 30_000, 'capped at 30s');
  for (let attempt = 0; attempt < 12; attempt += 1) {
    for (const r of [0, 0.25, 0.75, 0.999]) {
      const d = backoffDelayMs(attempt, () => r);
      assert.ok(d >= 800 && d <= 36_000, `jittered delay in bounds (attempt=${attempt}, r=${r}, d=${d})`);
    }
  }
}

// --- mergeDaemonPath ----------------------------------------------------------
{
  const env = { PATH: '/usr/bin:/bin', HOME: '/nonexistent-home' };
  const merged = mergeDaemonPath('/opt/tools/bin:/usr/bin', env);
  assert.ok(merged.path !== null, 'a shell dir the inherited PATH lacks -> override');
  assert.ok(
    merged.path?.startsWith('/opt/tools/bin:/usr/bin:/bin'),
    'shell PATH first, then inherited, then fallbacks',
  );
  const noShell = mergeDaemonPath(null, {
    PATH: '/opt/homebrew/bin:/usr/local/bin:/nonexistent-home/.local/bin:/nonexistent-home/.npm-global/bin:/usr/bin:/bin',
    HOME: '/nonexistent-home',
  });
  assert.equal(noShell.path, null, 'nothing new over the inherited PATH -> leave PATH alone');
}

// --- parseEnvBlock / shellVarsForDaemon -----------------------------------------
{
  const mark = '__M__';
  const block = `Welcome!\n${mark}PATH=/a:/b\0NOTE=x=y\0MULTI=one\ntwo\0${mark}bye\n`;
  assert.deepEqual(
    parseEnvBlock(block, mark),
    { PATH: '/a:/b', NOTE: 'x=y', MULTI: 'one\ntwo' },
    'only the fenced block; values keep "=" and newlines',
  );
  assert.equal(parseEnvBlock(`${mark}PATH=/a\0`, mark), null, 'unterminated fence -> null');
  assert.equal(parseEnvBlock('PATH=/a\0', mark), null, 'no fence -> null');
  assert.equal(parseEnvBlock(`${mark}HOME=/h\0${mark}`, mark), null, 'no PATH -> null');

  assert.deepEqual(
    shellVarsForDaemon({
      PATH: '/a',
      JAVA_HOME: '/jdk',
      SHLVL: '2',
      PWD: '/x',
      _: '/usr/bin/env',
      VICOA_API_URL: 'http://pinned',
      ELECTRON_RUN_AS_NODE: '1',
    }),
    { JAVA_HOME: '/jdk' },
    'PATH, shell bookkeeping, VICOA_* and ELECTRON_* never reach the daemon',
  );
}

// --- credentials.json (mirror of backend/src/vicoa/credentials_state.py) ------
{
  const hosted = 'https://agents.vicoa.ai';
  const selfHost = 'http://vicoa.example.com:8080';
  const perDeployment = { keys: { [hosted]: { write_key: 'cli' } } };
  const mixed = { ...perDeployment, write_key: 'desktop' };

  assert.equal(normalizeBaseUrl(' https://Agents.Vicoa.AI// '), hosted, 'normalize: trim, trailing /, lowercase');

  assert.equal(getWriteKey({}, hosted), null, 'no file -> no key');
  assert.equal(getWriteKey({ write_key: '' }, hosted), null, 'empty key -> no key');
  assert.equal(getWriteKey({ write_key: 'flat' }, hosted), 'flat', 'legacy flat key belongs to the reader');
  assert.equal(getWriteKey(perDeployment, `${hosted}/`), 'cli', 'per-deployment lookup is normalized');
  assert.equal(getWriteKey(perDeployment, selfHost), null, 'another deployment has no key');
  assert.equal(getWriteKey(mixed, hosted), 'cli', 'keys map wins over a stray flat key');
  assert.equal(getWriteKey(mixed, selfHost), null, 'stray flat key is ignored once keys exist');

  assert.deepEqual(
    withWriteKey({ write_key: 'old', other: 1 }, hosted, 'new'),
    { other: 1, keys: { [hosted]: { write_key: 'new' } } },
    'save migrates a legacy file, keeps unknown fields, strips the flat key',
  );
  assert.deepEqual(
    withWriteKey({ keys: { [selfHost]: { write_key: 's' } } }, `${hosted}/`, 'h'),
    { keys: { [selfHost]: { write_key: 's' }, [hosted]: { write_key: 'h' } } },
    'save keeps other deployments and files under the normalized URL',
  );
  assert.deepEqual(
    withWriteKey(mixed, hosted, 'new'),
    { keys: { [hosted]: { write_key: 'new' } } },
    'save over a mixed file replaces the entry and strips the flat key',
  );
  assert.deepEqual(mixed, { keys: { [hosted]: { write_key: 'cli' } }, write_key: 'desktop' }, 'input not mutated');

  assert.deepEqual(
    withoutWriteKey({ keys: { [selfHost]: { write_key: 's' }, [hosted]: { write_key: 'h' } } }, hosted),
    { keys: { [selfHost]: { write_key: 's' } } },
    'remove drops only this deployment',
  );
  assert.deepEqual(withoutWriteKey({ write_key: 'flat' }, hosted), { keys: {} }, 'remove clears a legacy file');
  assert.deepEqual(withoutWriteKey(mixed, hosted), { keys: {} }, 'remove clears the entry and the flat key');
  assert.equal(withoutWriteKey(perDeployment, selfHost), null, 'nothing to remove -> null (no write)');
}

// --- readLoginShellEnv / resolveDaemonEnv (async; never block or reject) --------
/** A stand-in "shell": ignores its flags, runs the probe command (its last arg) with `body` around it. */
function writeFakeShell(dir: string, name: string, body: string): string {
  const file = path.join(dir, name);
  fs.writeFileSync(file, `#!/bin/sh\nfor a; do last="$a"; done\n${body}\n`, { mode: 0o755 });
  return file;
}

async function checkLoginShellProbe(): Promise<void> {
  if (process.platform === 'win32') {
    return; // POSIX shells only
  }
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'vicoa-check-'));
  const base = { PATH: '/usr/bin:/bin', HOME: '/nonexistent-home' };
  try {
    // Output around the fenced block (a banner, a goodbye) is ignored, and the
    // probe flag is visible to the profile.
    const goodShell = writeFakeShell(
      tmp,
      'good-shell',
      'echo "Welcome!"\nPATH=/fake/one:/fake/two MULTI="one\ntwo" VICOA_API_URL=http://pinned /bin/sh -c "$last"\necho bye',
    );
    const good = await readLoginShellEnv({ ...base, SHELL: goodShell });
    assert.ok(good.ok, 'probe answers');
    if (good.ok) {
      assert.equal(good.mode, 'interactive', 'first attempt is the interactive login shell');
      assert.equal(good.env.PATH, '/fake/one:/fake/two', 'PATH from the fenced env block');
      assert.equal(good.env.MULTI, 'one\ntwo', 'multi-line values survive');
      assert.equal(good.env.VICOA_RESOLVING_ENVIRONMENT, '1', 'profile can tell it is being probed');
    }
    assert.equal(await readLoginShellPath({ ...base, SHELL: goodShell }), '/fake/one:/fake/two');

    // An interactive shell that prints nothing (an rc that execs tmux) -> the
    // non-interactive login shell answers instead.
    const noInteractive = writeFakeShell(
      tmp,
      'no-interactive-shell',
      '[ "$2" = "-i" ] && exit 0\nPATH=/fake/login /bin/sh -c "$last"',
    );
    const login = await readLoginShellEnv({ ...base, SHELL: noInteractive });
    assert.ok(login.ok && login.mode === 'login' && login.env.PATH === '/fake/login', 'falls back to -l -c');

    // A shell that answers but keeps stdout open (a background job the profile
    // started) is done at the closing marker, not when the pipe closes.
    const lingering = writeFakeShell(tmp, 'lingering-shell', 'PATH=/fake/one /bin/sh -c "$last"\nexec sleep 3');
    let started = Date.now();
    const lingered = await readLoginShellEnv({ ...base, SHELL: lingering });
    assert.ok(lingered.ok, 'lingering shell still answers');
    assert.ok(Date.now() - started < 2_000, `done at the marker (${Date.now() - started}ms)`);

    // A shell that never answers resolves a timeout at the budget, not a hang.
    const hungShell = writeFakeShell(tmp, 'hung-shell', 'exec sleep 10');
    started = Date.now();
    const hung = await readLoginShellEnv({ ...base, SHELL: hungShell }, 1_500);
    const elapsed = Date.now() - started;
    assert.ok(!hung.ok && hung.reason === 'timeout', 'hung shell -> timeout');
    assert.ok(elapsed >= 1_200 && elapsed < 4_000, `hung shell cut off at the budget (${elapsed}ms)`);

    // A missing shell binary fails fast, never throws.
    const missing = path.join(tmp, 'nonexistent');
    const gone = await readLoginShellEnv({ ...base, SHELL: missing });
    assert.ok(!gone.ok && gone.reason === 'spawn-error', 'missing shell -> spawn-error');

    // A good probe saves its PATH; a later failed one stands on it.
    const savedPathFile = path.join(tmp, 'state', 'login-shell-path.json');
    const fromShell = await resolveDaemonEnv({ ...base, SHELL: goodShell }, { savedPathFile });
    assert.equal(fromShell.source, 'shell');
    assert.ok(fromShell.path?.startsWith('/fake/one:/fake/two:/usr/bin:/bin'), 'shell PATH first');
    assert.equal(fromShell.shellVars.MULTI, 'one\ntwo', 'shell vars carried');
    assert.equal(fromShell.shellVars.VICOA_API_URL, undefined, 'VICOA_* dropped');
    assert.equal(readSavedShellPath(savedPathFile), '/fake/one:/fake/two', 'good PATH saved');

    const fromSaved = await resolveDaemonEnv({ ...base, SHELL: missing }, { savedPathFile });
    assert.equal(fromSaved.source, 'saved', 'failed probe -> saved PATH');
    assert.equal(fromSaved.detail, 'spawn-error');
    assert.ok(fromSaved.path?.startsWith('/fake/one:/fake/two:'), 'saved PATH first');
    assert.deepEqual(fromSaved.shellVars, {}, 'no shell vars without a probe');

    const fromNothing = await resolveDaemonEnv(
      { ...base, SHELL: missing },
      { savedPathFile: path.join(tmp, 'absent.json') },
    );
    assert.equal(fromNothing.source, 'inherited', 'no probe, nothing saved -> inherited + fallbacks');

    fs.writeFileSync(path.join(tmp, 'garbage.json'), 'not json');
    assert.equal(readSavedShellPath(path.join(tmp, 'garbage.json')), null, 'unreadable saved file -> null');
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
}

void checkLoginShellProbe().then(
  () => console.log('vicoa-desktop check: all assertions passed'),
  (err: unknown) => {
    console.error(err);
    process.exitCode = 1;
  },
);
