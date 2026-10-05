# How stack-preview works

## Processes

Started in this order by `up`:

| Name | Command | Binds |
|---|---|---|
| postgres | `docker run postgres:16-alpine`, container `vicoa-preview-<slug>` | `127.0.0.1:base` |
| proxy | `node scripts/proxy.mjs` | `127.0.0.1:base+4` |
| tunnel | `cloudflared tunnel --url http://127.0.0.1:<proxy>` (or `ngrok http`) | public |
| server | `uvicorn servers.app:app` with `ENABLE_WEBSOCKET=true` | `127.0.0.1:base+2` |
| backend | `uvicorn backend.main:app` | `127.0.0.1:base+1` |
| web | `next dev --turbopack` in `apps/web` | `127.0.0.1:base+3` |

The tunnel is opened **before** the services because both need its URL:
`NEXT_PUBLIC_*` values are inlined into the browser bundle when `next dev`
starts, and the server checks a browser WebSocket's `Origin` against
`FRONTEND_URLS`.

`base` comes from a hash of the checkout path (20000–29990, step 10), so a
worktree gets the same ports every time. Five busy ports move it to the next
block. `<slug>` is `<parent-dir>-<dir>` of the checkout, e.g. `swift-cedar-vicoa`.

## Routing (proxy.mjs)

| Path | Goes to |
|---|---|
| `/ws` (WebSocket) | server |
| `/api/v1/...` | backend |
| everything else, including Next's `/api/*` route handlers and the `/_next/webpack-hmr` socket | web |

The proxy passes the `Host` header through unchanged, so Next and the backend
see the public hostname, exactly as with a direct tunnel. Responses carry
`x-vicoa-preview: <service>`, which shows which upstream answered.

## State dir

`/tmp/vicoa-stack-preview/<slug>/` (override the root with `VICOA_PREVIEW_STATE_ROOT`):

| File | What |
|---|---|
| `ports`, `public` | ports; public URL and provider |
| `accounts` | Ada's and Bea's passwords (mode 600, created once) |
| `backend.env` | the variables backend and server run with (mode 600) |
| `env_file` | path of the `--env-file` in use, reused by `restart` |
| `keys/` | RS256 keypair from `backend/scripts/generate-jwt-keys.sh` |
| `<name>.pid` / `.start` / `.log` | per process; `.start` is `ps -o lstart`, so `down` never kills a recycled PID |
| `extra/` | the same files for `run NAME -- CMD` side processes |
| `run/` | empty working directory for the Python processes |
| `seeded` | marker: the accounts exist in this database |

## What backend and server run with

`env -i` (only `HOME`, a system `PATH` and `LANG` survive), then `--env-file`,
then `backend.env`:

| Variable | Value | Why |
|---|---|---|
| `ENVIRONMENT` | `preview` | `development` ignores `FRONTEND_URLS` for CORS; only `production` turns on Sentry |
| `AUTH_PROVIDER` | `builtin` | email and password stored in the preview's own database, no Supabase |
| `BUILTIN_ALLOW_SIGNUP` | `true` while seeding, then `false` | the link is public; `--allow-signup` keeps it open |
| `DATABASE_URL` | the container | never the shared dev database |
| `JWT_*_KEY_FILE` | `keys/` | fresh keys per state dir |
| `FRONTEND_URLS`, `WEB_APP_URL` | the public URL | WebSocket origin allowlist; links in emails |
| `INTERNAL_BROADCAST_URL` / `_TOKEN` | the local server, a random token | backend → server realtime fan-out |
| `CLIENT_IP_HEADER` | `Cf-Connecting-Ip` (ngrok: `X-Forwarded-For`) | the default `Fly-Client-IP` header can be forged by the client |

The web server runs with `env -i` too. Every key that `apps/web/.env*` defines is
set to an empty string: Next never overrides a variable that is already set, so
the hosted Supabase, PostHog and Stripe values in those files can't leak in. On
top of that it gets `NEXT_PUBLIC_AUTH_PROVIDER=builtin`,
`NEXT_PUBLIC_BACKEND_API_URL=<public URL>`,
`NEXT_PUBLIC_VICOA_WS_URL=wss://<host>/ws`,
`BACKEND_INTERNAL_URL=http://127.0.0.1:<backend>` (used by server-side code) and
`NEXT_TELEMETRY_DISABLED=1`.

## Traps this works around

- **CORS in development mode.** With `ENVIRONMENT=development` the backend
  allows only localhost origins and ignores `FRONTEND_URLS`, so a tunnelled
  sign-in fails its preflight with 400. With one origin there is no preflight
  anyway; `preview` keeps a direct-to-backend setup working too.
- **The WebSocket origin allowlist.** Browser connections to `/ws` are refused
  unless `Origin` is in `FRONTEND_URLS` or is loopback. With two tunnels the
  realtime socket usually stayed local-only and the dashboard never updated
  live; here the one public origin is the allowlist.
- **`.env` from the working directory.** `Settings` reads `.env` relative to
  the working directory and forbids unknown keys. Started from `backend/`, the
  backend loads that checkout's real credentials, or crashes on a stale key.
  Python always starts in `run/`; alembic has to run from `backend/src/shared`,
  so `up` refuses if a `.env` sits there.
- **Two `next dev` servers in one `apps/web`** fight over `.next/`. `up`
  refuses and names the other PID instead of touching it.
- **Quick tunnels.** `trycloudflare.com` links need no account and die with
  the process. They have no uptime guarantee and allow about 200 requests in
  flight, which is fine for a review and not for a load test. Cloudflare
  answers 530 for a few seconds after the URL first appears; the checks wait
  through it.
- **ngrok free** shows a browser warning page once per visitor. Because
  everything is on one origin, the cookie that dismisses it covers the API and
  WebSocket calls too. ngrok needs `ngrok config add-authtoken` first, and only
  one free ngrok session runs per account.
- **Next 16** blocks cross-origin requests to dev assets unless
  `allowedDevOrigins` lists the tunnel host (Next 15 only warns). After that
  upgrade, add `*.trycloudflare.com` (and the ngrok domain) to
  `allowedDevOrigins` in `next.config.ts`.

## Extending

- Private backend config (billing test keys, an overlay on `PYTHONPATH`):
  `--env-file`. The file is sourced with `set -a`, so plain `KEY=value` lines work.
- Extra processes that should live and die with the preview:
  `stack-preview.sh run NAME -- CMD...`. The command gets the `PREVIEW_*`
  variables, so it can target `127.0.0.1:$PREVIEW_BACKEND_PORT`.
