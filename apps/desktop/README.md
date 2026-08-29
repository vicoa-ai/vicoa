# Vicoa Desktop — Electron shell

Electron main + preload for the Vicoa desktop app. The renderer is the
existing Next.js app in the sibling `apps/web/` directory. Two run modes:

- **Dev** (default from a checkout): the shell loads the **next dev server**
  (`VICOA_RENDERER_URL`, default `http://localhost:3000`).
- **Bundled** (`app.isPackaged`, or `VICOA_BUNDLED=1` to force from a
  checkout): the shell boots the packaged **Next standalone server** in an
  Electron `utilityProcess` and loads that (see Packaging below).

This is a standalone package: its own `package.json`, lockfile, and
`tsconfig.json`, separate from the sibling `apps/web` app so the two TS
projects don't cross-contaminate (different module systems, different
`@types/node` copies).

## What the shell does

1. Single-instance lock — a second launch focuses the existing window.
2. Generates a per-launch 32-byte hex nonce and picks a free localhost port.
3. Spawns and supervises the daemon:
   `vicoa daemon --local-listener --local-port <P> [--local-only]`
   with env `VICOA_LOCAL_NONCE=<nonce>`, `VICOA_LOCAL_ORIGIN=<renderer origin>`.
   `--local-only` is passed when `~/.vicoa/credentials.json` has no `write_key`.
4. Waits for `http://127.0.0.1:<P>/healthz` → 200 (30s deadline) before
   creating the window. Unexpected daemon exits restart with jittered
   exponential backoff (1s→30s); 5 consecutive rapid failures → "Daemon:
   failed" in the tray + an error dialog with a Restart button. On quit the
   daemon gets SIGTERM, then SIGKILL after 5s — never orphaned.
5. Injects runtime config into the renderer (see contract below), persists
   window bounds (validated against attached displays, debounced writes),
   opens external links in the default browser, and shows a tray with daemon
   status, Restart daemon, and Quit.

## Running in dev

Three processes/steps, in order:

### 1. Renderer: next dev server (the sibling `apps/web/`)

```bash
cd apps/web
NEXT_PUBLIC_VICOA_DESKTOP=1 pnpm dev
```

`NEXT_PUBLIC_VICOA_DESKTOP=1` is required — it enables the desktop middleware
bypass in the Next app.

### 2. Daemon command (backend, from source)

The shell resolves the daemon binary from `VICOA_DAEMON_CMD` (a full command
string, split on whitespace) when set, else `vicoa` on PATH. To run the
daemon against a backend checkout (see `backend/AGENTS.md` for the venv
setup):

```bash
cd backend && source .venv/bin/activate  # or `conda activate <your-env>`
export VICOA_DAEMON_CMD="python -m vicoa.cli"
```

Notes:

- The module entry is **`python -m vicoa.cli`** — the `vicoa` console script
  maps to `vicoa.cli:main` and `cli.py` has an `if __name__ == "__main__"`
  guard. `python -m vicoa` does **not** work (the package has no
  `__main__.py`).
- The shell appends `daemon --local-listener --local-port <P>
  [--local-only]` to whatever `VICOA_DAEMON_CMD` expands to.
- If you juggle multiple backend checkouts sharing one virtualenv, make sure
  `vicoa` is installed editable (`pip install -e .`) against the checkout you
  want the daemon to run from — the daemon process doesn't get an explicit
  `cwd`, so it resolves `vicoa` however that environment's install does.

### 3. Electron shell (this directory)

```bash
cd apps/desktop
pnpm install
pnpm dev          # tsc && electron .
```

Env vars read by the shell:

| Variable | Default | Meaning |
|---|---|---|
| `VICOA_RENDERER_URL` | `http://localhost:3000` | Renderer URL (next dev, dev mode only). The effective renderer origin is forwarded to the daemon as `VICOA_LOCAL_ORIGIN`. |
| `VICOA_DAEMON_CMD` | bundled daemon, else `vicoa` (PATH) | Full daemon command string, whitespace-split. Overrides even the bundled frozen daemon. |
| `VICOA_BUNDLED` | unset | `1` forces the bundled (production) boot path from a checkout: standalone renderer from `renderer-dist/`, frozen daemon from `daemon-dist/`. |

Scripts: `pnpm build` (tsc), `pnpm start` (electron without rebuild),
`pnpm run check` (tsc + assertion suite over the pure spawn-arg helpers in
`src/daemon-manager.ts`).

## Renderer contract

The preload exposes two globals (contextIsolation on, nodeIntegration off,
sandboxed preload):

```ts
window.__VICOA_DESKTOP__ = {
  mode: 'local' | 'cloud',          // 'local' = daemon runs --local-only (logged out)
  wsUrl: 'ws://127.0.0.1:<P>/ws',
  apiBase: 'http://127.0.0.1:<P>',
  token: '<per-launch nonce>',
};

window.vicoaDesktopAuth = {
  setApiKey(key: string): Promise<{ ok: boolean; error?: string }>;
  signOut(): Promise<{ ok: boolean; error?: string }>;

  // Deep-link (OAuth callback) plumbing — see "Deep links" below.
  // Subscribe to vicoa:// URLs; cb gets the FULL url string. Returns unsubscribe.
  onDeepLink(cb: (url: string) => void): () => void;
  // Open a URL in the default browser (OAuth authorize step / external links).
  // Only http(s) + vicoa: schemes are honored.
  openExternal(url: string): Promise<void>;
};
```

Matches `lib/runtime-config.ts` (`DesktopRuntimeConfig`), the renderer's only
reader of the global.

### Deep links (`vicoa://`) — OAuth callback

The shell registers `vicoa` as its default protocol client
(`app.setAsDefaultProtocolClient`) and forwards every `vicoa://…` URL to the
renderer. The renderer owns the OAuth flow; the shell only carries the URL:

```ts
// Renderer OAuth flow (owned by the renderer agent):
const unsub = window.vicoaDesktopAuth.onDeepLink((url) => {
  // url is the full callback, e.g. "vicoa://auth/callback?code=…&state=…"
  const parsed = new URL(url);
  // …exchange code, then vicoaDesktopAuth.setApiKey(key)…
});
// later: unsub();

await window.vicoaDesktopAuth.openExternal(authorizeUrl); // opens the browser
```

Delivery is loss-free across timing: macOS callbacks arrive via `open-url`,
Windows/Linux via the single-instance `second-instance` argv (and initial argv
on cold start). A URL that arrives before a renderer is listening (cold start,
mid-reload) is buffered in main and replayed when `onDeepLink` subscribes — so
the callback is never dropped. `onDeepLink`'s subscribe is what drains the
buffer; call it from a component that mounts before you kick off the browser.

**Config injection** is a single `ipcRenderer.sendSync('vicoa:get-desktop-config')`
at preload init, not `additionalArguments`, because (a) the config is dynamic —
login/sign-out flips `mode` and a plain `webContents.reload()` re-runs the
preload and picks up fresh values, whereas `additionalArguments` are frozen at
window creation; and (b) `additionalArguments` land on the renderer's command
line, visible to any local user via `ps` — the nonce is a bearer secret and
stays off the process table.

**Login handoff:** the renderer signs into Supabase in-window, mints an API
key via `/api/cli-auth/generate-key`, then calls
`vicoaDesktopAuth.setApiKey(key)`. Main writes the key into
`~/.vicoa/credentials.json` (`{"write_key": ...}`, merged, mode 600), restarts
the daemon **without** `--local-only` (same nonce + port), waits for healthz,
then reloads the window — the injected config now reports `mode: 'cloud'`.
`signOut()` is the inverse: remove `write_key`, restart **with**
`--local-only`, reload.

## Behavior notes

- **macOS titlebar:** the window uses `titleBarStyle: 'hiddenInset'` with the
  traffic lights repositioned to `{ x: 16, y: 16 }` (macOS only; Windows/Linux
  keep the default OS frame). The frame is NOT removed — the renderer draws its
  own header and must reserve top-left space for the lights.
- **Daemon PATH (the "not responding" fix):** launched from Finder, Electron
  inherits launchd's minimal PATH, so the daemon couldn't find the
  user-installed `claude` / `codex` binary and headless sessions never
  responded. At startup the shell probes the login shell
  (`$SHELL -lic … $PATH`, 2s timeout, defensive), merges that with the current
  PATH plus a fallback list (`/opt/homebrew/bin`, `/usr/local/bin`,
  `~/.local/bin`, `~/.npm-global/bin`, `/usr/bin`, `/bin`), de-dups, and hands
  the result to the **daemon child only** (`buildSpawnEnv` `pathOverride`). PATH
  is only overridden when the merge adds a new dir; it is never blanked out.
  Startup logs `[daemon] resolved PATH (<n> entries; claude=<found|not-found>)`.
  See `src/resolve-path.ts`.
- **macOS lifecycle (v1 choice):** closing the window keeps the app, tray,
  and daemon alive (standard macOS convention); reopen via the dock icon or
  the tray's "Open Vicoa". On Windows/Linux, closing the window quits the app
  and stops the daemon.
- Window bounds persist to `<userData>/window-state.json`; rects that no
  longer meaningfully overlap an attached display are discarded (external
  monitor unplugged) — pattern adapted from Orca (MIT, Lovecast Inc.).
- The tray icon is a placeholder filled circle. `trayTemplate.png`'s
  `…Template` filename suffix makes macOS auto-tint it for light/dark menu
  bars. Regenerate/replace under `resources/` when there's a real glyph.

## Packaging (macOS arm64, unsigned)

```bash
cd apps/desktop
pnpm run package        # build renderer -> stage daemon -> icon -> tsc -> electron-builder
```

Artifacts land in `dist-app/`: `Vicoa-<version>-arm64.dmg` + `…-mac.zip` and
the raw bundle at `dist-app/mac-arm64/Vicoa.app`. Everything under
`renderer-dist/`, `daemon-dist/`, `build/`, `dist-app/` is a build artifact
and gitignored. v1 ships **unsigned/un-notarized** (`identity: null`): open
with right-click → Open, or `xattr -d com.apple.quarantine`. First launch is
slow (Gatekeeper scans the ~400 MB unsigned bundle); later launches are fast.

The pipeline, step by step:

1. **`scripts/build-renderer.mjs`** — runs `pnpm build` in the sibling `apps/web` app with
   `NEXT_PUBLIC_VICOA_DESKTOP=1` and cloud URLs
   (`https://api.vicoa.ai` / `wss://agents.vicoa.ai/ws`, overridable via the
   same env var names; Supabase publics come from the repo `.env`). Desktop
   env must be baked at **build** time — `NEXT_PUBLIC_*` is inlined. Stages
   `.next/standalone` + `.next/static` + `public/` into `renderer-dist/` per
   Next's documented layout, then:
   - **flattens `node_modules`** — pnpm's standalone output is absolute
     symlinks back into `.next/standalone`; the script rebuilds it as a
     symlink-free npm-style hoisted tree (fails the build if any symlink
     survives, or on a version conflict);
   - **strips `.env*`** that Next copied into standalone (server-only
     secrets!) and writes a sanitized `.env` with only the baked publics plus
     a guaranteed-refused placeholder `POSTGRES_URL` (lib/db/drizzle.ts
     throws at import when it's unset; no query ever runs without a legacy
     session cookie, which the desktop app never has).
2. **`scripts/stage-daemon.mjs`** — copies the PyInstaller onedir build
   (`<backend>/pyinstaller/dist/vicoa`, override `VICOA_DAEMON_DIST`)
   into `daemon-dist/`. Missing source ⇒ warns and packages without a
   bundled daemon (PATH fallback at runtime).
3. **`scripts/make-icons.mjs`** — every platform's icon from the one committed
   master, `icon-src/master-1024.png` (a 1024px square, full-bleed PNG), via
   sips + iconutil + `scripts/icon-shape.swift`. Outputs are committed under
   `resources/` and regenerate idempotently with `pnpm make:icon`:
   `icon.icns` (mac), `icon-512.png` (dev dock icon), `icon.ico` (win),
   `icon-linux.png` (linux). Edit the master, never the outputs.

   **macOS does not round app icons for you** — the squircle has to be baked
   into the art. macOS 26 (Tahoe) masks legacy `.icns` at render time, which
   makes a square master *look* right on Tahoe while rendering hard-cornered
   on macOS 15 and earlier, and on the dev dock icon (`app.dock.setIcon`,
   dev only — packaged builds use the `.icns`) on every version. So the mac
   art carries Apple's grid (an 824x824 body centred on a 1024 canvas, 185.4pt
   continuous-curvature radius) and the dev dock PNG is cut from that same
   shaped source. Windows and Linux stay square and full-bleed — the squircle
   is a macOS convention, and shipping it elsewhere looks wrong.
4. **electron-builder** (`electron-builder.config.cjs`) — appId `ai.vicoa.desktop`,
   dmg+zip, arm64-only, asar for the shell code. The daemon ships via
   `extraResources` (→ `Resources/daemon/`); the renderer is copied by
   **`scripts/after-pack.cjs`** (→ `Resources/renderer/`) because
   electron-builder's file walker hard-skips `node_modules` trees in
   `extraResources`.

Packaged boot path (`src/main.ts` + `src/renderer-server.ts`): pick a free
port, `utilityProcess.fork(Resources/renderer/server.js)` with
`PORT`/`HOSTNAME=127.0.0.1`/`NODE_ENV=production`, wait for HTTP 200, then
spawn the daemon (bundled `Resources/daemon/vicoa` → PATH `vicoa` →
`VICOA_DAEMON_CMD` overrides all) and load the window. If no daemon
executable exists anywhere, the app opens in a degraded state with an
"Install the Vicoa CLI" dialog instead of crashing. Credentialed (cloud)
daemon spawns add `--takeover`; the tray reflects the daemon's `/healthz`
`cloud` field (`connecting` / `connected` / `auth_failed`), falling back to
the legacy label for daemons that don't report it.

Pre-package test of the exact production code path from a checkout:

```bash
node scripts/build-renderer.mjs && node scripts/stage-daemon.mjs
pnpm build && VICOA_BUNDLED=1 pnpm start
```

## Auto-update / release (signed + notarized)

Auto-update is electron-updater against the **public** releases repo
`vicoa-ai/vicoa`. The shipped app carries an `app-update.yml` (written by
electron-builder from the `publish` block) and reads `latest-mac.yml` from that
repo — no token needed. Flow (`src/updater.ts` ↔ `lib/desktop-updates.ts`):
manual download, install-on-restart — `check → available → download →
downloaded → quitAndInstall` (Squirrel.Mac swaps the bundle and relaunches).
The top-of-window `DesktopUpdateBanner` and Settings → General → About drive it.

A **signed + notarized** build is mandatory: Squirrel.Mac only applies an update
whose signature matches the running app, so unsigned/ad-hoc dogfood builds error
at install time (everything up to that point still works).

Two build modes, gated on `VICOA_MAC_RELEASE` (see
`electron-builder.config.cjs`):

```bash
pnpm run package           # local dogfood: unsigned/ad-hoc (unchanged)
VICOA_MAC_RELEASE=1 \
CSC_LINK=<Developer-ID .p12 path or base64> CSC_KEY_PASSWORD=… \
APPLE_API_KEY=<AuthKey.p8 path> APPLE_API_KEY_ID=… APPLE_API_ISSUER=… \
GH_TOKEN=<PAT with contents:write on vicoa> \
pnpm run package:release   # Developer ID sign + hardened runtime + notarize + publish (draft)
```

Prerequisite (one-time): the Account Holder mints a **Developer ID Application**
certificate (Team `7H62R9F2CJ`) and exports it as `.p12`. Notarization reuses
the App Store Connect API key already used for the mobile app (`--apiKey`).

CI does the same via **`.github/workflows/desktop-release.yml`** (macOS-14
arm64, `workflow_dispatch` or a `desktop-v*` tag): it packages+signs+notarizes,
uploads to a **draft** release `v<version>` in vicoa, then un-drafts it so
the updater never sees a half-uploaded release. Required repo secrets are listed
at the top of that workflow. To cut a release: bump `version` in
`apps/desktop/package.json`, then run the workflow.

### Bundled daemon (self-contained)

The release bundles the `vicoa` CLI/daemon so a download needs no npm/python.
`stage-daemon.mjs` downloads the matching-arch frozen daemon from the **public
npm registry** (`@vicoa/cli@<vicoaDaemonVersion>-<os>-<arch>`, verifying its
published sha512) — the same source the app uses at runtime
(`src/cli-bootstrap.ts`), needing no `gh`/GitHub-release auth — then stages it,
and electron-builder signs + notarizes it inside the app. `after-pack.cjs` first
canonicalizes the daemon's PyInstaller `*.framework` dirs (their top-level binary
+ `Versions/Current` ship as real copies, which makes `codesign` reject them as
"ambiguous"). Pick the daemon version with the workflow's `daemon_version` input,
else the `vicoaDaemonVersion` pin in `apps/desktop/package.json`. For a local
self-contained build from a local daemon, pass `VICOA_DAEMON_DIST=<unzipped>/vicoa`
to `pnpm run package:release`.

Still TODO: Windows/Linux targets (+ their daemons), a branded
`releases.vicoa.ai` download URL for the marketing site.
