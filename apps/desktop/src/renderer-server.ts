/**
 * Boot the bundled Next standalone server (production renderer) inside an
 * Electron utilityProcess.
 *
 * The staged layout (electron/scripts/build-renderer.mjs) follows Next's
 * documented standalone shape: server.js + .next/{server,static} + public/ +
 * a sanitized .env with only the baked NEXT_PUBLIC_* values. We fork
 * server.js with PORT/HOSTNAME pinned to a fresh loopback port and wait for
 * an HTTP 200 before handing the URL to the window.
 *
 * utilityProcess (not child_process.spawn) so the server rides Electron's
 * bundled Node — the packaged app must not depend on a system `node`.
 */
import { utilityProcess, type UtilityProcess } from 'electron';
import * as fs from 'node:fs';
import * as http from 'node:http';
import * as path from 'node:path';
import { getStableRendererPort } from './config';

// 60s, not 30s: on the very first launch right after an NSIS install, Windows
// Defender real-time protection scans every freshly written file (Electron +
// the standalone server's node_modules), which can push the server's first
// successful response well past 30s — the boot-time "renderer error" some users
// hit when the installer runs the app immediately. The poll returns as soon as
// the server answers, so a warm start still proceeds in a few seconds; this only
// extends how long we wait before declaring failure.
const READY_TIMEOUT_MS = 60_000;
const READY_POLL_INTERVAL_MS = 250;

export interface RendererServer {
  url: string;
  /** Kill the utility process; resolves once it has exited. */
  stop: () => Promise<void>;
}

function pollOnce(port: number, pathname: string): Promise<boolean> {
  return new Promise((resolve) => {
    const req = http.get({ host: '127.0.0.1', port, path: pathname, timeout: 2_000 }, (res) => {
      res.resume();
      resolve(res.statusCode !== undefined && res.statusCode >= 200 && res.statusCode < 500);
    });
    req.on('timeout', () => {
      req.destroy();
      resolve(false);
    });
    req.on('error', () => resolve(false));
  });
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Fork the standalone server and wait until it answers on 127.0.0.1.
 * Rejects when the entry is missing, the process dies early, or the 30s
 * readiness deadline passes.
 */
export async function startRendererServer(
  serverJsPath: string,
  log: (line: string) => void = (line) => console.log(`[renderer] ${line}`),
): Promise<RendererServer> {
  if (!fs.existsSync(serverJsPath)) {
    throw new Error(
      `Bundled renderer not found at ${serverJsPath} — run electron/scripts/build-renderer.mjs first.`,
    );
  }

  // Stable across launches: the renderer's origin (localhost:<port>) keys
  // localStorage, so a random per-launch port would reset every preference.
  const port = await getStableRendererPort();
  const cwd = path.dirname(serverJsPath);
  log(`starting standalone server: ${serverJsPath} on 127.0.0.1:${port}`);

  const child = utilityProcess.fork(serverJsPath, [], {
    cwd,
    stdio: 'pipe',
    serviceName: 'vicoa-renderer',
    env: {
      ...process.env,
      NODE_ENV: 'production',
      PORT: String(port),
      HOSTNAME: '127.0.0.1',
    },
  });

  let exited = false;
  child.stdout?.on('data', (chunk: Buffer) => log(`stdout: ${chunk.toString().trimEnd()}`));
  child.stderr?.on('data', (chunk: Buffer) => log(`stderr: ${chunk.toString().trimEnd()}`));
  child.once('exit', (code) => {
    exited = true;
    log(`standalone server exited (code=${String(code)})`);
  });

  const stop = (): Promise<void> =>
    new Promise((resolve) => {
      if (exited) {
        resolve();
        return;
      }
      child.once('exit', () => resolve());
      if (!child.kill()) {
        resolve(); // already dead
      }
    });

  const deadline = Date.now() + READY_TIMEOUT_MS;
  while (Date.now() < deadline) {
    if (exited) {
      throw new Error('Renderer server exited before becoming ready');
    }
    // "/" is a PPR-prerendered route: a 2xx-4xx answer proves the HTTP server
    // is up (must not require auth or the daemon).
    if (await pollOnce(port, '/')) {
      // Report the URL as `localhost` (not `127.0.0.1`) so the window's page
      // Origin matches what the daemon is told to allow (VICOA_LOCAL_ORIGIN,
      // derived from this same URL). The server binds 127.0.0.1 and `localhost`
      // resolves there, so connectivity is unchanged — this only fixes the
      // local WS/REST Origin check, which is an exact string compare.
      const url = `http://localhost:${port}`;
      log(`ready at ${url}`);
      return { url, stop };
    }
    await sleep(READY_POLL_INTERVAL_MS);
  }
  await stop();
  throw new Error(`Renderer server did not become ready within ${READY_TIMEOUT_MS / 1000}s`);
}
