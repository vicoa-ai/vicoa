/**
 * Spawn + supervise the `vicoa daemon --local-listener` child process.
 *
 * Wire contract (plans/todos/desktop-app-v1-implementation.md):
 *   vicoa daemon --local-listener --local-port <P> [--local-only]
 *   env: VICOA_LOCAL_NONCE=<32-byte hex>  VICOA_LOCAL_ORIGIN=<renderer origin>
 *
 * Readiness = GET http://127.0.0.1:<P>/healthz returns 200 (no auth).
 * Supervision: unexpected exits restart with jittered exponential backoff
 * (1s -> 30s); 5 consecutive rapid failures flip the manager to 'failed'.
 * On stop: SIGTERM, escalate to SIGKILL after 5s — never orphan the child.
 */
import { spawn, type ChildProcess } from 'node:child_process';
import * as fs from 'node:fs';
import * as http from 'node:http';
import * as path from 'node:path';
import { resolveDaemonPath } from './resolve-path';

export type DaemonStatus =
  | 'idle' // never started
  | 'starting' // spawned, waiting for healthz
  | 'running' // healthz green
  | 'restarting' // exited unexpectedly, backoff timer pending
  | 'failed' // gave up after too many rapid failures
  | 'stopped'; // deliberately stopped (sign-out swap, quit)

/**
 * Cloud connection status from the daemon's /healthz `cloud` field
 * (null | "connecting" | "connected" | "auth_failed"). `undefined` = the
 * daemon didn't report one (older daemon without the field) — callers fall
 * back to pre-cloud-status behavior.
 */
export type CloudStatus = 'connecting' | 'connected' | 'auth_failed' | null;

export interface DaemonState {
  status: DaemonStatus;
  /** True when the current/desired daemon run has --local-only (not authenticated). */
  localOnly: boolean;
  /** Latest /healthz `cloud` value; undefined when the daemon doesn't report it. */
  cloudStatus?: CloudStatus;
  /** Present when status === 'failed'. */
  lastError?: string;
}

export interface DaemonManagerOptions {
  port: number;
  nonce: string;
  /** Renderer origin, e.g. http://localhost:3000 — forwarded as VICOA_LOCAL_ORIGIN. */
  origin: string;
  /** Bundled frozen daemon executable; preferred over PATH when set (VICOA_DAEMON_CMD still wins). */
  bundledDaemonPath?: string | null;
  /**
   * Downloaded (managed) daemon executable — the de-bundled builds' daemon,
   * fetched to userData on first run (see cli-bootstrap.ts). Preferred over
   * `vicoa` on PATH so a de-bundled app always runs its pinned, vetted daemon;
   * a VICOA_DAEMON_CMD override and a bundled binary both still win over it.
   */
  managedDaemonPath?: string | null;
  env?: NodeJS.ProcessEnv;
  log?: (line: string) => void;
}

const HEALTHZ_TIMEOUT_MS = 30_000;
const HEALTHZ_POLL_INTERVAL_MS = 250;
const BACKOFF_BASE_MS = 1_000;
const BACKOFF_MAX_MS = 30_000;
/** An exit within this window of the spawn counts as a "rapid failure". */
const RAPID_FAILURE_WINDOW_MS = 15_000;
const MAX_RAPID_FAILURES = 5;
const SIGKILL_ESCALATION_MS = 5_000;

/**
 * Resolve the daemon executable. Precedence:
 *   1. VICOA_DAEMON_CMD (full command string, split on whitespace) — dev override
 *   2. the bundled frozen binary (packaged app), when provided
 *   3. the managed (downloaded) frozen binary — de-bundled builds, staged to
 *      userData on first run (cli-bootstrap.ts)
 *   4. `vicoa` from PATH
 * Returns [cmd, ...leadingArgs].
 */
export function resolveDaemonCommand(
  env: NodeJS.ProcessEnv,
  bundledDaemonPath?: string | null,
  managedDaemonPath?: string | null,
): string[] {
  const override = env.VICOA_DAEMON_CMD;
  if (typeof override === 'string' && override.trim().length > 0) {
    return override.trim().split(/\s+/);
  }
  if (typeof bundledDaemonPath === 'string' && bundledDaemonPath.length > 0) {
    return [bundledDaemonPath];
  }
  if (typeof managedDaemonPath === 'string' && managedDaemonPath.length > 0) {
    return [managedDaemonPath];
  }
  return ['vicoa'];
}

/**
 * Can the resolved command plausibly be spawned? Explicit paths are stat'ed;
 * bare names are searched on PATH. Used to distinguish "the Vicoa CLI is not
 * installed" (install dialog, degraded window) from a crash-looping daemon.
 */
export function daemonCommandAvailable(cmd: string, env: NodeJS.ProcessEnv): boolean {
  if (cmd.includes(path.sep)) {
    try {
      return fs.existsSync(cmd);
    } catch {
      return false;
    }
  }
  const pathVar = env.PATH ?? '';
  // On Windows an executable on PATH is `vicoa.exe` / `vicoa.cmd`, never the
  // bare name — probing only `vicoa` would report the CLI as missing and push
  // the user into the "install the CLI" dialog while it is installed.
  const names =
    process.platform === 'win32'
      ? [cmd, ...(env.PATHEXT ?? '.EXE;.CMD;.BAT').split(';').map((ext) => cmd + ext.toLowerCase())]
      : [cmd];
  for (const dir of pathVar.split(path.delimiter)) {
    if (dir.length === 0) {
      continue;
    }
    try {
      if (names.some((name) => fs.existsSync(path.join(dir, name)))) {
        return true;
      }
    } catch {
      // unreadable PATH entry — keep scanning
    }
  }
  return false;
}

/**
 * Build the daemon subcommand args per the wire contract.
 * `--takeover` (replace an already-running daemon for the same base URL
 * non-interactively) is only meaningful for credentialed runs — local-only
 * daemons skip the cloud registration that collides — so callers pass
 * takeover only in cloud mode.
 */
export function buildDaemonArgs(options: {
  port: number;
  localOnly: boolean;
  takeover?: boolean;
}): string[] {
  const args = ['daemon', '--local-listener', '--local-port', String(options.port)];
  if (options.localOnly) {
    args.push('--local-only');
  }
  if (options.takeover === true) {
    args.push('--takeover');
  }
  return args;
}

/**
 * Defensive parse of the /healthz body's `cloud` field. Returns undefined for
 * older daemons that don't send it (or malformed bodies) so callers can keep
 * pre-cloud-status behavior.
 */
export function parseCloudStatus(body: string): CloudStatus | undefined {
  try {
    const data: unknown = JSON.parse(body);
    if (typeof data !== 'object' || data === null || !('cloud' in data)) {
      return undefined;
    }
    const cloud = (data as Record<string, unknown>).cloud;
    if (cloud === null) {
      return null;
    }
    if (cloud === 'connecting' || cloud === 'connected' || cloud === 'auth_failed') {
      return cloud;
    }
    return undefined;
  } catch {
    return undefined;
  }
}

/**
 * Inherited env + the two contract variables. When `pathOverride` is a
 * non-empty string it replaces PATH for the daemon child ONLY (the login-shell
 * PATH resolved at startup so the daemon can exec user-installed `claude` /
 * `codex`). Omitted/empty leaves the inherited PATH untouched.
 */
export function buildSpawnEnv(
  base: NodeJS.ProcessEnv,
  options: { nonce: string; origin: string; pathOverride?: string },
): NodeJS.ProcessEnv {
  const env: NodeJS.ProcessEnv = {
    ...base,
    VICOA_LOCAL_NONCE: options.nonce,
    VICOA_LOCAL_ORIGIN: options.origin,
  };
  if (typeof options.pathOverride === 'string' && options.pathOverride.length > 0) {
    env.PATH = options.pathOverride;
  }
  return env;
}

/** Jittered exponential backoff: base 1s doubling per attempt, capped at 30s, ±20% jitter. */
export function backoffDelayMs(attempt: number, random: () => number = Math.random): number {
  const exp = Math.min(BACKOFF_BASE_MS * 2 ** Math.max(0, attempt), BACKOFF_MAX_MS);
  const jitter = 1 + (random() * 0.4 - 0.2);
  return Math.round(exp * jitter);
}

function pollHealthzOnce(port: number): Promise<{ ok: boolean; body: string }> {
  return new Promise((resolve) => {
    const req = http.get(
      { host: '127.0.0.1', port, path: '/healthz', timeout: 2_000 },
      (res) => {
        const chunks: Buffer[] = [];
        res.on('data', (chunk: Buffer) => chunks.push(chunk));
        res.on('end', () =>
          resolve({ ok: res.statusCode === 200, body: Buffer.concat(chunks).toString() }),
        );
        res.on('error', () => resolve({ ok: false, body: '' }));
      },
    );
    req.on('timeout', () => {
      req.destroy();
      resolve({ ok: false, body: '' });
    });
    req.on('error', () => resolve({ ok: false, body: '' }));
  });
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

type StateListener = (state: DaemonState) => void;

const CLOUD_STATUS_POLL_INTERVAL_MS = 5_000;

export class DaemonManager {
  private readonly port: number;
  private readonly nonce: string;
  private readonly origin: string;
  private readonly bundledDaemonPath: string | null;
  private readonly managedDaemonPath: string | null;
  private readonly baseEnv: NodeJS.ProcessEnv;
  private readonly log: (line: string) => void;

  private child: ChildProcess | null = null;
  private status: DaemonStatus = 'idle';
  private localOnly = true;
  /** Login-shell PATH for the daemon child; resolved once, lazily, then cached. */
  private daemonPath: string | null = null;
  private daemonPathResolved = false;
  private cloudStatus: CloudStatus | undefined;
  private cloudPollTimer: NodeJS.Timeout | null = null;
  private lastError: string | undefined;

  /** Bumped on every deliberate lifecycle action so stale exit handlers become no-ops. */
  private generation = 0;
  private consecutiveRapidFailures = 0;
  private restartTimer: NodeJS.Timeout | null = null;
  private lastSpawnAt = 0;
  private stopping = false;

  private readonly listeners = new Set<StateListener>();

  constructor(options: DaemonManagerOptions) {
    this.port = options.port;
    this.nonce = options.nonce;
    this.origin = options.origin;
    this.bundledDaemonPath = options.bundledDaemonPath ?? null;
    this.managedDaemonPath = options.managedDaemonPath ?? null;
    this.baseEnv = options.env ?? process.env;
    this.log = options.log ?? ((line) => console.log(`[daemon] ${line}`));
  }

  get state(): DaemonState {
    return {
      status: this.status,
      localOnly: this.localOnly,
      cloudStatus: this.cloudStatus,
      lastError: this.lastError,
    };
  }

  /** The argv this manager would spawn right now (for availability checks + error messages). */
  resolvedCommand(): string[] {
    return resolveDaemonCommand(this.baseEnv, this.bundledDaemonPath, this.managedDaemonPath);
  }

  /**
   * Resolve (once) the login-shell PATH to hand the daemon child so it can find
   * user-installed `claude` / `codex` even when launched from Finder with a
   * minimal launchd PATH. Cached; safe across restarts. Never throws.
   */
  private ensureDaemonPath(): void {
    if (this.daemonPathResolved) {
      return;
    }
    this.daemonPathResolved = true;
    try {
      const resolved = resolveDaemonPath(this.baseEnv);
      this.daemonPath = resolved.path;
      this.log(
        `resolved PATH (${resolved.entryCount} entries; ` +
          `claude=${resolved.claudePath !== null ? 'found' : 'not-found'})`,
      );
    } catch (err) {
      this.daemonPath = null;
      this.log(`PATH resolution failed, using inherited PATH: ${errorMessage(err)}`);
    }
  }

  get isLocalOnly(): boolean {
    return this.localOnly;
  }

  /** Subscribe to state changes; returns an unsubscribe function. */
  onState(listener: StateListener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  /**
   * Spawn the daemon and wait for healthz. Resolves true when healthy within
   * 30s, false otherwise (state moves to 'failed' on spawn error/timeouts).
   */
  async start(localOnly: boolean): Promise<boolean> {
    this.stopping = false;
    this.localOnly = localOnly;
    this.consecutiveRapidFailures = 0;
    this.lastError = undefined;
    return this.spawnAndAwaitReady();
  }

  /** Stop (if running) and start again, optionally flipping --local-only. Same nonce + port. */
  async restart(localOnly?: boolean): Promise<boolean> {
    const nextLocalOnly = localOnly ?? this.localOnly;
    await this.stop();
    return this.start(nextLocalOnly);
  }

  /** Deliberate stop: SIGTERM, SIGKILL after 5s. Cancels supervision for the old child. */
  async stop(): Promise<void> {
    this.stopping = true;
    this.generation += 1;
    this.clearCloudPoll();
    this.cloudStatus = undefined;
    if (this.restartTimer !== null) {
      clearTimeout(this.restartTimer);
      this.restartTimer = null;
    }
    const child = this.child;
    this.child = null;
    if (child !== null && child.exitCode === null && child.signalCode === null) {
      await terminateChild(child, this.log);
    }
    this.setState('stopped');
  }

  private async spawnAndAwaitReady(): Promise<boolean> {
    this.generation += 1;
    const generation = this.generation;
    this.clearCloudPoll();
    this.cloudStatus = undefined;
    this.ensureDaemonPath();

    const [cmd, ...leadingArgs] = this.resolvedCommand();
    if (cmd === undefined) {
      this.lastError = 'Empty daemon command';
      this.setState('failed');
      return false;
    }
    const args = [
      ...leadingArgs,
      ...buildDaemonArgs({
        port: this.port,
        localOnly: this.localOnly,
        // --takeover only in cloud (credentialed) mode: replace a colliding
        // user-started daemon non-interactively. Local-only runs don't
        // register with the cloud, so there is nothing to take over.
        takeover: !this.localOnly,
      }),
    ];
    this.log(`spawning: ${cmd} ${args.join(' ')} (local-only=${this.localOnly})`);
    this.setState('starting');

    let child: ChildProcess;
    try {
      child = spawn(cmd, args, {
        env: buildSpawnEnv(this.baseEnv, {
          nonce: this.nonce,
          origin: this.origin,
          pathOverride: this.daemonPath ?? undefined,
        }),
        stdio: ['ignore', 'pipe', 'pipe'],
      });
    } catch (err) {
      this.lastError = `Failed to spawn daemon: ${errorMessage(err)}`;
      this.setState('failed');
      return false;
    }
    this.child = child;
    this.lastSpawnAt = Date.now();

    child.stdout?.on('data', (chunk: Buffer) => this.log(`stdout: ${chunk.toString().trimEnd()}`));
    child.stderr?.on('data', (chunk: Buffer) => this.log(`stderr: ${chunk.toString().trimEnd()}`));
    child.on('error', (err) => {
      // ENOENT etc. — 'exit' will not fire when spawn itself failed.
      if (generation !== this.generation) {
        return;
      }
      this.log(`spawn error: ${errorMessage(err)}`);
      this.child = null;
      this.lastError = `Daemon process error: ${errorMessage(err)}`;
      this.handleUnexpectedDeath(generation);
    });
    child.on('exit', (code, signal) => {
      if (generation !== this.generation) {
        return; // superseded by a deliberate stop/restart
      }
      this.log(`exited unexpectedly (code=${String(code)} signal=${String(signal)})`);
      this.child = null;
      this.lastError = `Daemon exited (code=${String(code)}${signal ? `, signal=${signal}` : ''})`;
      this.handleUnexpectedDeath(generation);
    });

    const healthy = await this.awaitHealthz(generation);
    if (generation !== this.generation) {
      return false; // superseded mid-wait
    }
    if (healthy) {
      this.setState('running');
      this.scheduleCloudPoll(generation);
      return true;
    }
    // Spawned but never became healthy within the deadline: treat as failure.
    if (this.status === 'starting') {
      this.lastError = this.lastError ?? 'Daemon did not become healthy within 30s';
      this.log(this.lastError);
      await this.stopChildOnly();
      if (generation === this.generation) {
        this.setState('failed');
      }
    }
    return false;
  }

  private async awaitHealthz(generation: number): Promise<boolean> {
    const deadline = Date.now() + HEALTHZ_TIMEOUT_MS;
    while (Date.now() < deadline) {
      if (generation !== this.generation || this.child === null) {
        return false;
      }
      const { ok, body } = await pollHealthzOnce(this.port);
      if (ok) {
        this.cloudStatus = parseCloudStatus(body);
        return true;
      }
      await sleep(HEALTHZ_POLL_INTERVAL_MS);
    }
    return false;
  }

  /**
   * While running, refresh the /healthz `cloud` field periodically — a
   * credentialed daemon moves connecting -> connected (or auth_failed) after
   * the window is already up, and the tray should follow. No-op signal for
   * daemons that don't report the field.
   */
  private scheduleCloudPoll(generation: number): void {
    this.clearCloudPoll();
    this.cloudPollTimer = setTimeout(() => {
      this.cloudPollTimer = null;
      if (generation !== this.generation || this.status !== 'running') {
        return;
      }
      void pollHealthzOnce(this.port).then(({ ok, body }) => {
        if (generation !== this.generation || this.status !== 'running') {
          return;
        }
        if (ok) {
          const next = parseCloudStatus(body);
          if (next !== this.cloudStatus) {
            this.cloudStatus = next;
            this.setState('running'); // re-notify listeners with the new cloud status
          }
        }
        this.scheduleCloudPoll(generation);
      });
    }, CLOUD_STATUS_POLL_INTERVAL_MS);
  }

  private clearCloudPoll(): void {
    if (this.cloudPollTimer !== null) {
      clearTimeout(this.cloudPollTimer);
      this.cloudPollTimer = null;
    }
  }

  private handleUnexpectedDeath(generation: number): void {
    this.clearCloudPoll();
    this.cloudStatus = undefined;
    if (this.stopping) {
      return;
    }
    const ranFor = Date.now() - this.lastSpawnAt;
    if (ranFor < RAPID_FAILURE_WINDOW_MS) {
      this.consecutiveRapidFailures += 1;
    } else {
      this.consecutiveRapidFailures = 1;
    }
    if (this.consecutiveRapidFailures >= MAX_RAPID_FAILURES) {
      this.log(`giving up after ${this.consecutiveRapidFailures} rapid failures`);
      this.setState('failed');
      return;
    }
    const delay = backoffDelayMs(this.consecutiveRapidFailures - 1);
    this.log(`restarting in ${delay}ms (rapid failures: ${this.consecutiveRapidFailures})`);
    this.setState('restarting');
    this.restartTimer = setTimeout(() => {
      this.restartTimer = null;
      if (this.stopping || generation !== this.generation) {
        return;
      }
      void this.spawnAndAwaitReady();
    }, delay);
  }

  /** Kill the current child without flipping public state (used by the never-healthy path). */
  private async stopChildOnly(): Promise<void> {
    this.generation += 1;
    const child = this.child;
    this.child = null;
    if (child !== null && child.exitCode === null && child.signalCode === null) {
      await terminateChild(child, this.log);
    }
  }

  private setState(status: DaemonStatus): void {
    this.status = status;
    const snapshot = this.state;
    for (const listener of this.listeners) {
      listener(snapshot);
    }
  }
}

function terminateChild(child: ChildProcess, log: (line: string) => void): Promise<void> {
  return new Promise((resolve) => {
    const killTimer = setTimeout(() => {
      log('SIGTERM grace period elapsed; sending SIGKILL');
      try {
        child.kill('SIGKILL');
      } catch {
        // already gone
      }
    }, SIGKILL_ESCALATION_MS);
    child.once('exit', () => {
      clearTimeout(killTimer);
      resolve();
    });
    try {
      child.kill('SIGTERM');
    } catch {
      clearTimeout(killTimer);
      resolve();
    }
  });
}

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}
