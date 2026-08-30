# Self-hosting Vicoa

Run the whole thing yourself: the backend, the realtime server, and the web
dashboard, with your machines' agents connecting to it instead of to
vicoa.ai. Nothing here is a stripped "community edition" — it is the same
multi-tenant stack Vicoa runs.

**Not included** (they are Vicoa's hosted business, not part of this repo):
billing, the marketing site, and Vicoa's own deployment configuration. A
self-hosted install has no plans and no limits.

---

## Architecture

A self-hosted install is **four services in Docker** plus the **CLI + daemon on
each of your machines**. The daemon is what actually runs your agents (Claude
Code, Codex, OpenCode); the Docker stack is the shared brain they talk to.

| Service | Port | Role |
|---|---|---|
| `web` | 3000 | Next.js dashboard — what browsers and phones load |
| `backend` | 8000 | user-facing REST for the web and mobile clients |
| `server` | 8080 | agent-facing REST + MCP + the WebSocket the daemon uses |
| `postgres` | — | your data — the source of truth (Docker volume `vicoa-postgres`) |

```
   browser / phone                       your machines (laptop, server, …)
        │                                CLI + daemon → Claude Code, Codex,
        │ HTTPS                                        OpenCode agents
        ▼                                                  │  API key
   ┌─────────┐         REST                                │  WebSocket + REST
   │   web   │ ──────────────┐                             │
   │  :3000  │               ▼                             ▼
   └─────────┘         ┌─────────┐   internal broadcast ┌─────────┐
   phone / browser ───►│ backend │ ───────────────────► │ server  │
        REST           │  :8000  │                       │  :8080  │
                       └────┬────┘                       └────┬────┘
                            └─────────────┬───────────────────┘
                                          ▼
                                    ┌───────────┐
                                    │ postgres  │
                                    └───────────┘
```

`backend` and `server` are the **same image running two processes**, mirroring
Vicoa's own deployment. They are split because only `server` may own the
WebSocket connection manager — it lives in process memory, so:

- Keep `server` to **one replica**.
- When a web user's action needs to reach a connected agent, `backend` POSTs it
  to `server` over an **internal broadcast** bridge (they share
  `INTERNAL_BROADCAST_TOKEN`). This is the single most common thing to
  misconfigure; see [Troubleshooting](#troubleshooting).

A one-shot `migrate` service runs `alembic upgrade head` before either process
starts.

## What you need

- **Docker** with Compose v2 (`docker compose version`).
- **No external services.** Accounts live in your own Postgres by default
  (`AUTH_PROVIDER=builtin`). Supabase is optional — see
  [Authentication](#authentication) if you want social login and MFA.
- **For access beyond localhost:** a domain and TLS. Phones and remote machines
  resolve the URLs you configure literally, so `localhost` only works for a
  single-machine trial.

## Setup

### Step 1 — Start the stack

```bash
git clone https://github.com/vicoa-ai/vicoa.git
cd vicoa

cp .env.example .env
$EDITOR .env                       # passwords, public URLs, INTERNAL_BROADCAST_TOKEN

./backend/scripts/generate-jwt-keys.sh selfhost/keys

docker compose -f docker-compose.selfhost.yml up -d
docker compose -f docker-compose.selfhost.yml logs -f backend
```

`migrate` runs first; once it exits, the four services from
[Architecture](#architecture) come up. Confirm with:

```bash
docker compose -f docker-compose.selfhost.yml ps
```

### Step 2 — Create your account

Open <http://localhost:3000> and sign up. The first account is created in your
own database. Then **lock the door behind you**:

```bash
# in .env
BUILTIN_ALLOW_SIGNUP=false
```

```bash
docker compose -f docker-compose.selfhost.yml up -d backend
```

While signup is open, anyone who can reach the server can register. The default
`builtin` provider needs nothing else; for social login / MFA, or to change how
sign-in works, see [Authentication](#authentication).

### Step 3 — Connect a machine

Install the CLI (`pip install vicoa`, or `npm i -g @vicoa/cli`) on any machine
whose agents you want to reach. It defaults to Vicoa's hosted service; two env
vars repoint it at your deployment:

```bash
# A localhost trial (the compose stack above):
export VICOA_API_URL=http://localhost:8080     # the `server` service
export VICOA_AUTH_URL=http://localhost:3000    # your web dashboard

# …or a reverse-proxied deployment:
# export VICOA_API_URL=https://agents.vicoa.example.com
# export VICOA_AUTH_URL=https://vicoa.example.com

vicoa --auth      # opens VICOA_AUTH_URL to sign in, saves an API key to ~/.vicoa
vicoa daemon      # the background daemon that keeps this machine connected
```

`vicoa --auth` opens the dashboard in your browser, mints an API key for this
machine, and writes it to `~/.vicoa/credentials.json`; running any `vicoa`
command with no key stored yet triggers the same flow. Per-command,
`--base-url` / `--auth-url` override the env. Put the exports in your shell
profile so every agent session inherits them.

> **One machine, one stored key.** `~/.vicoa/credentials.json` holds a single
> `write_key` — it is *not* scoped per deployment. Signing in against a second
> server replaces the key for the first, and the desktop app reads the very same
> file, so a CLI login can silently repoint the desktop app too. If this machine
> also uses hosted Vicoa (or another self-hosted instance), read
> [Trying self-hosting on a machine that already uses another deployment](#trying-self-hosting-on-a-machine-that-already-uses-another-deployment)
> before you run `vicoa --auth`.

### Step 4 — Verify it works

1. Reload the dashboard — the machine you ran `vicoa daemon` on now shows up as
   online.
2. Start a session on it: pick a folder, choose an agent (Claude Code, Codex, or
   OpenCode), and send a first message.
3. On that machine, `vicoa ls` lists the running session — proof the daemon,
   `server`, and Postgres are all wired together.

If the machine never appears or the session never updates, jump to
[Troubleshooting](#troubleshooting) — the two usual culprits are a mismatched
API key and a broken broadcast bridge.

## Authentication

Two providers, chosen with `AUTH_PROVIDER`. Agents (CLI, daemon, MCP clients)
are unaffected either way — they always authenticate with an API key this
deployment mints and signs with its own RS256 keypair.

### `builtin` (default)

Email and password, stored in your Postgres (`user_credentials`, scrypt-hashed).
Sessions are JWTs signed by the same keypair as the agent API keys, so there is
nothing extra to configure and no third party in the login path.

- `BUILTIN_ALLOW_SIGNUP` — leave on to create your accounts, then turn it off.
  While it is on, anyone who can reach the server can register.
- `BUILTIN_REQUIRE_EMAIL_VERIFICATION` — off by default, because it needs a mail
  provider (`MAILGUN_*` or `RESEND_API_KEY`). With no provider configured, codes
  for verification and password reset are written to the `backend` log instead
  of being sent — enough to recover an account on a single-operator instance.
- `BUILTIN_SESSION_TTL_HOURS` — session lifetime, default 720 (30 days). Tokens
  are stateless, so shortening this is the only way to bound a stolen session;
  signing out clears the browser cookie but does not revoke the token.

There is no rate limiting on sign-in. Password checks are deliberately slow
(~50 ms each), which is a throttle but not a substitute for one — put the
dashboard behind a proxy that rate-limits if it is exposed to the internet.

### `supabase`

Delegates identity to a Supabase project: social login, MFA and password
recovery you do not have to operate. This is what Vicoa's hosted service runs.

1. Create a project.
2. Set `AUTH_PROVIDER=supabase` and `NEXT_PUBLIC_AUTH_PROVIDER=supabase`.
3. Copy the project URL, the `anon` key and the `service_role` key into `.env`
   (both the `NEXT_PUBLIC_*` and the plain names — the browser and the backend
   each need their own copy).
4. In **Authentication → URL Configuration**, add your web URL
   (`PUBLIC_WEB_URL`) as a redirect URL.
5. Optionally set `SUPABASE_JWT_SECRET` (Settings → API → JWT Secret). With it,
   the backend verifies access tokens locally instead of calling Supabase on
   every request. A project with asymmetric signing keys enabled needs no secret
   — verification uses its published JWKS.

Switching provider on a running instance does not migrate accounts: the two
keep their identities in different places. Pick one before you create accounts.
`NEXT_PUBLIC_AUTH_PROVIDER` is baked into the browser bundle, so changing it
means a `build web` (see [Behind a reverse proxy](#behind-a-reverse-proxy)).

## Other clients

Step 3 covers the CLI and daemon — the only client you need. The desktop and
mobile apps are optional front-ends onto the same deployment.

### Desktop app

A downloaded build has Vicoa's endpoints compiled into it, so it reads an
override at startup — env vars, or `~/.vicoa/desktop.json`:

```json
{
  "apiUrl": "https://vicoa.example.com:8000",
  "wsUrl": "wss://vicoa.example.com:8080/ws",
  "authUrl": "https://vicoa.example.com"
}
```

`wsUrl` is derived from `apiUrl` when omitted. The same values also reach the
daemon the desktop app supervises. Building the app yourself instead? Set
`NEXT_PUBLIC_BACKEND_API_URL` and `NEXT_PUBLIC_VICOA_WS_URL` at build time.

### Mobile app

The published iOS/Android apps talk to Vicoa's backend only — a self-hosted
server needs your own build of `apps/mobile` (a runtime server switch is
planned). The web dashboard works fine in a mobile browser in the meantime.

### Trying self-hosting on a machine that already uses another deployment

Running two deployments from one machine — the common case being "I already use
hosted Vicoa and want to trial a self-hosted stack" — needs care, because the
stored credential is global. `vicoa --auth --base-url http://localhost:8080
--auth-url http://localhost:3000` overwrites `~/.vicoa/credentials.json` with a
key minted by the *local* server. The daemon for the other deployment keeps
running, keeps presenting the now-replaced key, gets a 401, and that machine
drops offline in the dashboard it used to appear in.

Two ways to avoid it:

**Don't store the second key.** Mint an API key in the self-hosted dashboard and
pass it explicitly, leaving `credentials.json` alone:

```bash
vicoa daemon --base-url http://localhost:8080 --api-key <key>
```

`--api-key` beats `VICOA_API_KEY`, which beats the stored credential, and no
path writes the key back to disk. `vicoa --auth` is the only thing that
replaces the stored key.

**Or switch deliberately.** Run `vicoa --auth` (with the env/flags for the
deployment you want) whenever you move between them, and expect the other
deployment's daemon to disconnect until you switch back.

Either way, `~/.vicoa/daemon_state.json` is the file to read when something
looks wrong — it *is* keyed per base URL, one entry each:

```json
{
  "daemons": {
    "https://agents.vicoa.example.com": {
      "machine_id": "6e2478eb-…",
      "api_key_fingerprint": "28d544d8…",
      "auth_invalid_at": "2026-08-27T05:09:33.906766+00:00"
    },
    "http://localhost:8080": {
      "machine_id": "2dcbcee1-…",
      "api_key_fingerprint": "ba690fb4…",
      "daemon_pid": 88063
    }
  }
}
```

`api_key_fingerprint` is the SHA-256 of the key that entry registered under, so
comparing the two entries tells you which deployment the stored key currently
belongs to. `auth_invalid_at` is stamped when that deployment answered 401; the
daemon then exits rather than retry, and `vicoa` prints `Vicoa is disconnected
(credential expired), run vicoa --auth`. A successful re-registration clears the
stamp. Starting a daemon with a key whose fingerprint differs from the stored
one is not an error: the entry is reset and the machine re-registers under the
new identity — which is why a machine can come back online with a *new*
`machine_id` and leave a stale row behind in the dashboard.

## Behind a reverse proxy

Everything above assumes localhost. For a real deployment, expose three
hostnames (or one host with paths — anything your proxy can do), and make sure
the WebSocket route passes `Upgrade`/`Connection` through:

| Public URL | Upstream | Set in `.env` |
|---|---|---|
| `https://vicoa.example.com` | `web:3000` | `PUBLIC_WEB_URL` |
| `https://api.vicoa.example.com` | `backend:8000` | `PUBLIC_BACKEND_URL` |
| `wss://agents.vicoa.example.com/ws` | `server:8080` | `PUBLIC_WS_URL` |

The three `PUBLIC_*` values are what browsers and agents are told to use, so they
must be the **externally reachable** URLs. `NEXT_PUBLIC_*` values are compiled
into the browser bundle, so after changing them:

```bash
docker compose -f docker-compose.selfhost.yml build web
docker compose -f docker-compose.selfhost.yml up -d web
```

## Operating it

**Upgrade** to a newer version:

```bash
git pull
docker compose -f docker-compose.selfhost.yml build
docker compose -f docker-compose.selfhost.yml up -d
```

`migrate` reruns automatically and applies any new Alembic revisions before the
processes restart.

**Back up** the Postgres volume — that is all your state:

```bash
docker compose -f docker-compose.selfhost.yml exec postgres \
  pg_dump -U vicoa vicoa > vicoa-$(date +%F).sql
```

Back up `selfhost/keys/` too: regenerating the JWT keypair invalidates every
issued agent API key.

**Watch logs:**

```bash
docker compose -f docker-compose.selfhost.yml logs -f <service>   # web | backend | server
```

**Stop or remove** the stack:

```bash
docker compose -f docker-compose.selfhost.yml down       # stop the services (data kept)
docker compose -f docker-compose.selfhost.yml down -v     # stop AND delete the Postgres volume
vicoa stop                                                # stop the daemon on a machine
```

## Optional integrations

Everything outside the required block in `.env.example` self-disables when its
key is empty — no stub accounts, no placeholder services. The ones people
usually want:

- **`ANTHROPIC_API_KEY` / `OPENROUTER_API_KEY`** — LLM-generated session titles
  (without them, titles fall back to a truncated first message).
- **`DEEPGRAM_API_KEY`** — voice input.
- **`AWS_*`** — image attachments in messages.
- **`RESEND_API_KEY`** or **`MAILGUN_*`** — transactional email.
- **`TWILIO_*`** — SMS/email when an agent is waiting on you.
- **`SENTRY_DSN`** — error tracking.

## Troubleshooting

**The dashboard loads but nothing updates live.** The realtime bridge is
misconfigured: `backend` POSTs to `server`, and both must share
`INTERNAL_BROADCAST_TOKEN`. A mismatch makes that endpoint 401. Check
`PUBLIC_WS_URL` reaches `server:8080` through your proxy with the upgrade
headers intact.

**Agents can't authenticate — 401 `credential rejected`.** Usually a key from a
*different* deployment. The CLI takes its key from `VICOA_API_KEY` first, then
`~/.vicoa/credentials.json` — and `VICOA_API_KEY` **overrides everything**, so if
it is set (e.g. to a hosted Vicoa key) the daemon presents that to your server and
its signature fails against your keypair. `unset VICOA_API_KEY`, then `vicoa --auth`
against this deployment to mint and store a key for it. Failing that, the two JWT
keys must be a matching pair and both present: `generate-jwt-keys.sh` writes them,
the compose file mounts them at `/keys` and sets `JWT_PRIVATE_KEY_FILE` /
`JWT_PUBLIC_KEY_FILE`.

**A machine that worked yesterday shows offline — in the *other* deployment's
dashboard.** The mirror image of the previous entry: signing in against this
deployment replaced the key the other one's daemon was using, because
`~/.vicoa/credentials.json` stores one key for all servers. Confirm it by
looking for `auth_invalid_at` on that base URL in `~/.vicoa/daemon_state.json`,
then either re-run `vicoa --auth` against the deployment you want to be logged
into, or keep the two apart with an explicit `--api-key`.

**Sign-in does nothing, or the dashboard bounces back to /sign-in.**
`AUTH_PROVIDER` and `NEXT_PUBLIC_AUTH_PROVIDER` must agree — the browser bundle
ships whichever sign-in screen it was built with, and `NEXT_PUBLIC_*` values are
baked in at build time (`docker compose -f docker-compose.selfhost.yml build web`
after changing one). `GET /api/v1/auth/config` reports what the backend
resolved. On `supabase`, also check your web URL is in the project's redirect
allowlist and that `PUBLIC_WEB_URL` matches it exactly.

**No verification / reset email arrives (builtin).** With no mail provider
configured, the code is logged instead:
`docker compose -f docker-compose.selfhost.yml logs backend | grep 'code for'`.

**`migrate` exits non-zero.** Read its logs; it is a plain `alembic upgrade
head` against `PRODUCTION_DB_URL`. Nothing else starts until it succeeds.

## Known limits

**Planned** — rough edges we intend to smooth:

- **Mobile app server switch.** The published iOS/Android apps authenticate
  against Supabase and can't yet be pointed at a self-hosted server. A runtime
  server-address setting is planned; until then, use your own build of
  `apps/mobile` or the web dashboard in a mobile browser.
- **Account admin UI.** The built-in provider has no screen for managing
  accounts yet — you create and remove them directly in Postgres. A basic admin
  UI is planned.
- **One stored credential per machine.** `~/.vicoa/credentials.json` holds a
  single key rather than one per server, so `vicoa --auth` against a second
  deployment disconnects the first. `daemon_state.json` is already keyed by base
  URL; making the credential store match it is planned. Until then, use an
  explicit `--api-key` to run two deployments side by side. We'll also improve the credentials part. 

**By design** — inherent to a self-hosted install, not something to wait for:

- The built-in provider has no social login or MFA. Switch to
  `AUTH_PROVIDER=supabase` if you need either.
- No billing and no plan limits — every account is unlimited.
- `server` runs as a single replica, because the WebSocket connection manager
  lives in process memory.

Questions and fixes are welcome — see `CONTRIBUTING.md`.
