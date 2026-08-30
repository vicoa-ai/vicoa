/**
 * Login-shell PATH resolution for the daemon child process.
 *
 * THE "not responding" root cause: when the app is double-clicked from Finder,
 * the Electron process inherits launchd's minimal PATH (`/usr/bin:/bin:...`),
 * NOT the user's interactive shell PATH. The daemon we spawn then can't find
 * the user-installed `claude` / `codex` binary, the headless agent fails to
 * exec, and sessions never respond.
 *
 * Fix: run the user's login shell once at startup to print its PATH, merge it
 * with the current process PATH plus a fallback list, and hand that PATH to the
 * daemon child (and only the daemon child — see daemon-manager.buildSpawnEnv).
 *
 * The resolver is deliberately defensive: a 2s timeout, falls back to the
 * inherited PATH on any error, and never throws.
 */
import { spawnSync } from 'node:child_process';
import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';

const SHELL_RESOLVE_TIMEOUT_MS = 2_000;

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

/**
 * Probe the user's login shell for its interactive PATH. Returns null on any
 * failure (missing shell, timeout, non-zero exit, empty output). Never throws.
 *
 * `-lic <cmd>` = login + interactive + run a command: this sources the same
 * rc/profile files the user's terminal does (nvm, asdf, homebrew shellenv, …),
 * which is exactly where user-installed CLIs get onto PATH.
 */
export function readLoginShellPath(env: NodeJS.ProcessEnv = process.env): string | null {
  const shell = env.SHELL !== undefined && env.SHELL.length > 0 ? env.SHELL : '/bin/zsh';
  try {
    const result = spawnSync(
      shell,
      ['-lic', 'command -v claude >/dev/null 2>&1; printf "%s" "$PATH"'],
      {
        encoding: 'utf8',
        timeout: SHELL_RESOLVE_TIMEOUT_MS,
        env,
        stdio: ['ignore', 'pipe', 'ignore'],
      },
    );
    if (result.error !== undefined && result.error !== null) {
      return null;
    }
    const out = typeof result.stdout === 'string' ? result.stdout.trim() : '';
    return out.length > 0 ? out : null;
  } catch {
    return null;
  }
}

export interface ResolvedDaemonPath {
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
 * Resolve the PATH the daemon child should run with:
 *   loginShellPath ∪ process.env.PATH ∪ fallback dirs  (de-duped, ordered)
 *
 * `path` is only non-null when the merge actually adds a dir the inherited PATH
 * lacked — we never override PATH just to reorder it, and never blank it out.
 * Defensive: never throws; falls back to leaving PATH alone on any error.
 */
export function resolveDaemonPath(env: NodeJS.ProcessEnv = process.env): ResolvedDaemonPath {
  const currentPath = env.PATH ?? '';
  let shellPath: string | null = null;
  try {
    shellPath = readLoginShellPath(env);
  } catch {
    shellPath = null;
  }

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
