/**
 * Login-shell environment resolution for the daemon child process.
 *
 * THE "not responding" root cause: when the app is double-clicked from Finder,
 * the Electron process inherits launchd's minimal environment
 * (`PATH=/usr/bin:/bin:...`), NOT the user's interactive shell environment. The
 * daemon we spawn then can't find the user-installed `claude` / `codex` binary,
 * the headless agent fails to exec, and sessions never respond. Everything else
 * the daemon runs for the user has the same gap: the agents' own tool calls,
 * and worktree setup's `pnpm install`.
 *
 * Fix: run the user's login shell at startup to print its environment, and hand
 * that to the daemon child (and only the daemon child — see
 * daemon-manager.buildSpawnEnv), with PATH merged over the inherited one plus a
 * fallback list.
 *
 * The probe is defensive and never throws:
 *  - the env block is fenced by a random marker, so whatever a profile prints
 *    around it (a banner, a conda notice) can't leak into it;
 *  - an interactive login shell first (where nvm/pnpm/conda usually put
 *    themselves on PATH), then a non-interactive one if that printed nothing
 *    (an rc that `exec`s tmux, …);
 *  - a 15s budget for both. A heavy profile takes ~1.5s on an idle machine and
 *    several times that on one busy launching apps; the old 2s budget lost that
 *    race now and then and left the daemon on the bare launchd PATH until the
 *    next relaunch;
 *  - when it still fails, the PATH the last good probe returned (saved on disk)
 *    stands in for it, so one slow launch doesn't strip the user's tools.
 *
 * It is ASYNC on purpose: sourcing a real zsh/bash profile (nvm, conda, oh-my-
 * zsh, …) routinely takes 1-1.5s, and a synchronous spawn would block the
 * Electron main thread for that long — nothing paints, the window can't open.
 * Callers start it early (boot) so it overlaps the renderer-server start.
 */
import { spawn } from 'node:child_process';
import { randomBytes } from 'node:crypto';
import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';

/** Budget for the whole probe, both attempts together. */
const SHELL_RESOLVE_TIMEOUT_MS = 15_000;
/** The interactive attempt's share of the budget; the fallback gets the rest. */
const INTERACTIVE_ATTEMPT_SHARE = 2 / 3;

/**
 * Set in the probe shell's env so a profile can skip slow or interactive-only
 * work: `[[ -n $VICOA_RESOLVING_ENVIRONMENT ]] && return`.
 */
const PROBE_FLAG = 'VICOA_RESOLVING_ENVIRONMENT';

/**
 * Login-shell variables that never reach the daemon: per-shell bookkeeping,
 * Electron's own switches, and the Vicoa contract the desktop owns (an export
 * meant for the CLI must not reconfigure the desktop's daemon).
 */
const DROPPED_SHELL_VARS = new Set(['SHLVL', 'PWD', 'OLDPWD', '_']);
const DROPPED_SHELL_VAR_PREFIXES = ['VICOA_', 'ELECTRON_'];

const PROBE_ATTEMPTS: ReadonlyArray<{ mode: LoginShellMode; args: string[] }> = [
  { mode: 'interactive', args: ['-l', '-i', '-c'] },
  { mode: 'login', args: ['-l', '-c'] },
];

/**
 * Dirs always worth having on PATH for finding user-installed agent CLIs, even
 * when the login shell couldn't be probed. Ordered least-surprising-first.
 */
export function fallbackPathDirs(env: NodeJS.ProcessEnv = process.env): string[] {
  const home = env.HOME ?? os.homedir();
  return [
    '/opt/homebrew/bin',
    '/usr/local/bin',
    `${home}/.local/bin`,
    `${home}/.npm-global/bin`,
    '/usr/bin',
    '/bin',
  ];
}

/**
 * Merge PATH-like fragments into a single de-duplicated, colon-joined PATH,
 * preserving first-seen order and dropping empty segments. Pure — no I/O.
 * Each fragment may itself be a colon-joined PATH or a single dir.
 */
export function mergePathEntries(fragments: Array<string | null | undefined>): string {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const fragment of fragments) {
    if (fragment === null || fragment === undefined || fragment.length === 0) {
      continue;
    }
    for (const dir of fragment.split(path.delimiter)) {
      if (dir.length === 0 || seen.has(dir)) {
        continue;
      }
      seen.add(dir);
      out.push(dir);
    }
  }
  return out.join(path.delimiter);
}

/**
 * First executable named `name` on the given colon-joined PATH, or null. Pure
 * except for the fs.access probe. Mirrors what the daemon will actually be able
 * to exec (a real binary on PATH), so it doubles as the "claude found?" signal.
 */
export function findExecutableOnPath(name: string, pathStr: string): string | null {
  for (const dir of pathStr.split(path.delimiter)) {
    if (dir.length === 0) {
      continue;
    }
    const candidate = path.join(dir, name);
    try {
      fs.accessSync(candidate, fs.constants.X_OK);
      return candidate;
    } catch {
      // not here / not executable — keep scanning
    }
  }
  return null;
}

export type LoginShellMode = 'interactive' | 'login';
export type LoginShellFailure = 'timeout' | 'spawn-error' | 'no-output' | 'unsupported';

export type LoginShellProbe =
  | { ok: true; env: Record<string, string>; mode: LoginShellMode; durationMs: number }
  | { ok: false; reason: LoginShellFailure; durationMs: number };

/**
 * Parse `env -0` output fenced by `marker` on both sides. Pure. Null when the
 * fence isn't complete or the block has no PATH (the command never ran).
 */
export function parseEnvBlock(stdout: string, marker: string): Record<string, string> | null {
  const start = stdout.indexOf(marker);
  if (start === -1) {
    return null;
  }
  const end = stdout.indexOf(marker, start + marker.length);
  if (end === -1) {
    return null;
  }
  const env: Record<string, string> = {};
  for (const entry of stdout.slice(start + marker.length, end).split('\0')) {
    const eq = entry.indexOf('=');
    if (eq <= 0) {
      continue;
    }
    env[entry.slice(0, eq)] = entry.slice(eq + 1);
  }
  return typeof env.PATH === 'string' && env.PATH.length > 0 ? env : null;
}

type AttemptResult = { env: Record<string, string> } | { failure: LoginShellFailure };

function runProbeAttempt(
  shell: string,
  args: string[],
  env: NodeJS.ProcessEnv,
  marker: string,
  timeoutMs: number,
): Promise<AttemptResult> {
  const command = `printf '%s' '${marker}'; /usr/bin/env -0; printf '%s' '${marker}'`;
  return new Promise((resolve) => {
    let child: ReturnType<typeof spawn>;
    try {
      child = spawn(shell, [...args, command], {
        env: { ...env, [PROBE_FLAG]: '1' },
        stdio: ['ignore', 'pipe', 'ignore'],
        // Own process group, so the timeout can take out anything the profile
        // itself spawned (an `nvm` init, a slow `brew shellenv`, …) — killing
        // just the shell would leave those holding our stdout pipe open.
        detached: true,
      });
    } catch {
      resolve({ failure: 'spawn-error' });
      return;
    }
    const chunks: Buffer[] = [];
    let settled = false;
    const finish = (result: AttemptResult): void => {
      if (settled) {
        return;
      }
      settled = true;
      clearTimeout(timer);
      resolve(result);
    };
    const parsed = (): Record<string, string> | null =>
      parseEnvBlock(Buffer.concat(chunks).toString('utf8'), marker);
    // A profile that hangs (prompting, network) must not gate the daemon spawn.
    const timer = setTimeout(() => {
      // One more turn of the event loop first: if the main thread was busy past
      // the deadline, the shell's output may already be queued behind this timer.
      setImmediate(() => {
        if (settled) {
          return;
        }
        try {
          if (child.pid !== undefined) {
            process.kill(-child.pid, 'SIGKILL'); // the whole group (see `detached`)
          } else {
            child.kill('SIGKILL');
          }
        } catch {
          // already gone
        }
        finish({ failure: 'timeout' });
      });
    }, timeoutMs);
    child.stdout?.on('data', (chunk: Buffer) => {
      chunks.push(chunk);
      // Done once the closing marker is in: something the profile started in
      // the background may hold stdout open long after the shell has answered.
      const env = parsed();
      if (env !== null) {
        child.stdout?.destroy();
        child.unref();
        finish({ env });
      }
    });
    child.on('error', () => finish({ failure: 'spawn-error' }));
    child.on('close', () => {
      // Exit status is deliberately ignored: a noisy rc file can leave `$?`
      // non-zero while the env it printed is perfectly good.
      const env = parsed();
      finish(env !== null ? { env } : { failure: 'no-output' });
    });
  });
}

/**
 * Probe the user's login shell for its environment. Resolves a failure on any
 * error (missing shell, timeout, nothing printed). Never rejects.
 *
 * `-l -i -c <cmd>` = login + interactive + run a command: this sources the same
 * rc/profile files the user's terminal does (nvm, asdf, homebrew shellenv, …),
 * which is exactly where user-installed CLIs get onto PATH.
 */
export async function readLoginShellEnv(
  env: NodeJS.ProcessEnv = process.env,
  timeoutMs: number = SHELL_RESOLVE_TIMEOUT_MS,
): Promise<LoginShellProbe> {
  const started = Date.now();
  if (process.platform === 'win32') {
    return { ok: false, reason: 'unsupported', durationMs: 0 };
  }
  const shell = env.SHELL !== undefined && env.SHELL.length > 0 ? env.SHELL : '/bin/zsh';
  const marker = `__VICOA_ENV_${randomBytes(8).toString('hex')}__`;
  let reason: LoginShellFailure = 'no-output';
  for (const [index, attempt] of PROBE_ATTEMPTS.entries()) {
    const remainingMs = timeoutMs - (Date.now() - started);
    if (remainingMs <= 0) {
      break;
    }
    const budgetMs =
      index === 0 ? Math.min(remainingMs, Math.floor(timeoutMs * INTERACTIVE_ATTEMPT_SHARE)) : remainingMs;
    const result = await runProbeAttempt(shell, attempt.args, env, marker, budgetMs);
    if ('env' in result) {
      return { ok: true, env: result.env, mode: attempt.mode, durationMs: Date.now() - started };
    }
    reason = result.failure;
    if (reason === 'spawn-error') {
      break; // no shell binary to run; the next attempt would fail the same way
    }
  }
  return { ok: false, reason, durationMs: Date.now() - started };
}

/** The login shell's PATH alone, or null when the probe failed. */
export async function readLoginShellPath(env: NodeJS.ProcessEnv = process.env): Promise<string | null> {
  const probe = await readLoginShellEnv(env);
  return probe.ok ? (probe.env.PATH ?? null) : null;
}

/** The login-shell variables to layer over the daemon's inherited env. PATH is merged separately. */
export function shellVarsForDaemon(shellEnv: Record<string, string>): Record<string, string> {
  const vars: Record<string, string> = {};
  for (const [key, value] of Object.entries(shellEnv)) {
    if (
      key === 'PATH' ||
      DROPPED_SHELL_VARS.has(key) ||
      DROPPED_SHELL_VAR_PREFIXES.some((prefix) => key.startsWith(prefix))
    ) {
      continue;
    }
    vars[key] = value;
  }
  return vars;
}

/** The PATH the last good probe returned, or null when none was saved. */
export function readSavedShellPath(file: string): string | null {
  try {
    const raw: unknown = JSON.parse(fs.readFileSync(file, 'utf8'));
    if (typeof raw === 'object' && raw !== null) {
      const saved = (raw as { path?: unknown }).path;
      if (typeof saved === 'string' && saved.length > 0) {
        return saved;
      }
    }
  } catch {
    // missing or unreadable — no stand-in
  }
  return null;
}

/** Remember a good probe's PATH (only PATH: the rest of the env may hold secrets). Best-effort. */
export function saveShellPath(file: string, shellPath: string): void {
  if (readSavedShellPath(file) === shellPath) {
    return;
  }
  try {
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, `${JSON.stringify({ path: shellPath, savedAt: new Date().toISOString() }, null, 2)}\n`);
  } catch {
    // diagnostics-grade state; never break the boot over it
  }
}

export interface MergedDaemonPath {
  /**
   * The merged PATH to hand the daemon child, or null when it adds nothing over
   * the inherited PATH (in which case the caller leaves PATH untouched).
   */
  path: string | null;
  /** Number of entries in the merged PATH (for the startup log line). */
  entryCount: number;
  /** Absolute path to `claude` on the merged PATH, or null if not found. */
  claudePath: string | null;
}

/**
 * Where the shell part of the daemon's env came from: this launch's probe, the
 * last good probe's saved PATH, or nowhere (inherited PATH + fallbacks only).
 */
export type DaemonEnvSource = 'shell' | 'saved' | 'inherited';

export interface ResolvedDaemonEnv extends MergedDaemonPath {
  /** Login-shell variables to layer over the inherited env; empty unless `source` is 'shell'. */
  shellVars: Record<string, string>;
  source: DaemonEnvSource;
  /** Which attempt answered when `source` is 'shell', else why the probe failed. */
  detail: string;
  durationMs: number;
}

/**
 * Resolve the env the daemon child should run with:
 *   PATH = loginShellPath (or the saved one) ∪ process.env.PATH ∪ fallback dirs
 *   plus the login shell's other variables (see shellVarsForDaemon).
 *
 * `savedPathFile` keeps the last good probe's PATH across launches: a good probe
 * refreshes it, a failed one falls back to it. Never rejects.
 */
export async function resolveDaemonEnv(
  env: NodeJS.ProcessEnv = process.env,
  options: { savedPathFile?: string; timeoutMs?: number } = {},
): Promise<ResolvedDaemonEnv> {
  let probe: LoginShellProbe;
  try {
    probe = await readLoginShellEnv(env, options.timeoutMs);
  } catch {
    probe = { ok: false, reason: 'spawn-error', durationMs: 0 };
  }
  if (probe.ok) {
    const shellPath = probe.env.PATH ?? null;
    if (options.savedPathFile !== undefined && shellPath !== null) {
      saveShellPath(options.savedPathFile, shellPath);
    }
    return {
      ...mergeDaemonPath(shellPath, env),
      shellVars: shellVarsForDaemon(probe.env),
      source: 'shell',
      detail: probe.mode,
      durationMs: probe.durationMs,
    };
  }
  const saved = options.savedPathFile !== undefined ? readSavedShellPath(options.savedPathFile) : null;
  return {
    ...mergeDaemonPath(saved, env),
    shellVars: {},
    source: saved !== null ? 'saved' : 'inherited',
    detail: probe.reason,
    durationMs: probe.durationMs,
  };
}

/** One log line: where the daemon's env came from and what it found. */
export function describeDaemonEnv(resolved: ResolvedDaemonEnv): string {
  const origin =
    resolved.source === 'shell'
      ? `login shell (${resolved.detail})`
      : `${resolved.source === 'saved' ? 'saved PATH' : 'inherited PATH only'}, login shell failed: ${resolved.detail}`;
  return (
    `daemon env from ${origin} in ${resolved.durationMs}ms; ` +
    `PATH ${resolved.entryCount} entries, ${Object.keys(resolved.shellVars).length} shell vars; ` +
    `claude=${resolved.claudePath !== null ? 'found' : 'not-found'}`
  );
}

/** The pure merge step of `resolveDaemonEnv`, split out so it is unit-testable. */
export function mergeDaemonPath(
  shellPath: string | null,
  env: NodeJS.ProcessEnv = process.env,
): MergedDaemonPath {
  const currentPath = env.PATH ?? '';
  const merged = mergePathEntries([shellPath, currentPath, ...fallbackPathDirs(env)]);
  const claudePath = findExecutableOnPath('claude', merged.length > 0 ? merged : currentPath);

  const currentSet = new Set(currentPath.split(path.delimiter).filter((d) => d.length > 0));
  const mergedDirs = merged.split(path.delimiter).filter((d) => d.length > 0);
  const addsSomething = mergedDirs.some((d) => !currentSet.has(d));

  return {
    path: addsSomething && merged.length > 0 ? merged : null,
    entryCount: mergedDirs.length,
    claudePath,
  };
}
