/**
 * Smoke checks for the daemon-manager pure helpers (`pnpm run check`).
 * No test framework — plain assertions; exits non-zero on failure.
 */
import * as assert from 'node:assert/strict';
import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import {
  backoffDelayMs,
  buildDaemonArgs,
  buildSpawnEnv,
  parseCloudStatus,
  resolveDaemonCommand,
} from './daemon-manager';
import { mergeDaemonPath, mergePathEntries, readLoginShellPath } from './resolve-path';

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

// --- readLoginShellPath (async; the probe must never block or reject) ------------
async function checkLoginShellProbe(): Promise<void> {
  if (process.platform === 'win32') {
    return; // POSIX shells only
  }
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'vicoa-check-'));
  try {
    // A stand-in "shell" that ignores its -lic flags and prints a PATH: the
    // probe must hand it back verbatim, trimmed.
    const fakeShell = path.join(tmp, 'fake-shell');
    fs.writeFileSync(fakeShell, '#!/bin/sh\nprintf "%s\\n" "/fake/one:/fake/two"\n', { mode: 0o755 });
    assert.equal(
      await readLoginShellPath({ SHELL: fakeShell, PATH: '/usr/bin:/bin' }),
      '/fake/one:/fake/two',
      'probe returns the shell-printed PATH',
    );

    // A shell that never answers must resolve null at the 2s deadline, not hang
    // the boot (this used to be a synchronous spawn on the main thread).
    const hungShell = path.join(tmp, 'hung-shell');
    fs.writeFileSync(hungShell, '#!/bin/sh\nsleep 10\n', { mode: 0o755 });
    const started = Date.now();
    assert.equal(
      await readLoginShellPath({ SHELL: hungShell, PATH: '/usr/bin:/bin' }),
      null,
      'hung shell -> null',
    );
    const elapsed = Date.now() - started;
    assert.ok(elapsed >= 1_500 && elapsed < 4_000, `hung shell cut off at the deadline (${elapsed}ms)`);

    // A missing shell binary resolves null (spawn ENOENT), never throws.
    assert.equal(
      await readLoginShellPath({ SHELL: path.join(tmp, 'nonexistent'), PATH: '/usr/bin:/bin' }),
      null,
      'missing shell -> null',
    );
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
