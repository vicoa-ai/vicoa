# AGENTS.md

Guidance for Claude Code, Codex, and other coding agents working in this
repository. Human contributors should start with `CONTRIBUTING.md`.

## Project overview

**Vicoa** (Vibe Code Anywhere) lets you run AI coding agents (Claude Code,
Codex, OpenCode) anywhere, on any device — start on your laptop, continue on
your phone, with real-time sync and notifications.

This repository is the complete, self-hostable stack: CLI, local daemon,
backend, web, desktop, and mobile app. It is
licensed **AGPLv3** (see `LICENSE`); contributions are accepted under the same
license (see `CONTRIBUTING.md`).

## Repository structure

```
vicoa/
├── backend/              # Python: FastAPI backend + MCP/REST servers + CLI/daemon
│   └── src/
│       ├── backend/      # user-facing REST API (web/mobile clients)
│       ├── servers/      # agent-facing REST + MCP + WebSocket
│       ├── shared/       # models, DB, config, auth, alembic migrations, hooks
│       ├── vicoa/        # the `vicoa` CLI and the local daemon
│       ├── protocol/     # wire contracts shared by daemon and servers
│       └── integrations/ # agent CLI wrappers (Claude Code, Codex, ACP, …)
├── apps/
│   ├── web/              # Next.js dashboard (also the desktop renderer) + docs
│   ├── desktop/          # Electron shell — bundles apps/web + the backend daemon
│   └── mobile/           # Flutter app (iOS/Android)
└── .github/workflows/    # CI + release workflows, path-filtered per component
```

The OpenCode plugin lives in its own repo:
[`vicoa-ai/opencode-vicoa`](https://github.com/vicoa-ai/opencode-vicoa).

`backend/src/integrations/cli_wrappers/codex` is a fork of the Codex CLI used
only by the backend's PyInstaller binary build; you do not need it for normal
development or for running from source.

## Component commands

### backend (Python / FastAPI)

```bash
cd backend
make dev-install           # deps + dev tools
make pre-commit-install    # git hooks

make lint                  # linters + type checking
make format                # auto-format
make typecheck             # pyright only

make test                  # all tests
make test-unit             # unit only
make test-integration      # needs Docker

cd src/shared && alembic upgrade head
cd src/shared && alembic revision --autogenerate -m "Description"
```

**Architecture.** Two processes share one codebase: `backend.main` serves the
user-facing REST API, `servers.app` serves the agent-facing REST + MCP + the
WebSocket endpoint. PostgreSQL via SQLAlchemy. Dual authentication — human users
hold a token from the configured `AuthProvider` (Supabase, or the built-in
provider for self-hosting; `src/shared/auth/`), agents hold a Vicoa-signed RS256
API key of which only a SHA256 hash is stored. All messaging flows through the
`messages` table.

Run it locally with `./dev-start.sh` / `./dev-stop.sh`, or in Docker with
`docker compose up`.

### apps/web (Next.js)

```bash
cd apps/web
pnpm install
pnpm dev                   # dev server (turbopack); pnpm dev:no-turbo to disable
pnpm build && pnpm start   # production
```

Next.js 15 + React 19, shadcn/ui, provider-aware auth (`lib/auth/`: Supabase SSR,
or the built-in session cookie). Product documentation is a
Fumadocs collection under `content/docs/`.

### apps/desktop (Electron)

```bash
cd apps/desktop
pnpm install
pnpm dev                   # tsc && electron . (loads the apps/web dev server)
pnpm run package           # build renderer -> stage daemon -> package the app
```

An Electron shell that boots the `apps/web` renderer as a Next standalone
server and supervises a bundled backend daemon. See `apps/desktop/README.md`.

### apps/mobile (Flutter)

```bash
cd apps/mobile
flutter pub get
flutter run
flutter test && flutter analyze
```

FlutterFlow-generated base with heavy customization: Provider state
(`FFAppState`), Supabase auth with social login, custom actions in
`lib/custom_code/actions/`.

## Cross-component integration

**Auth.** Web dashboard and mobile authenticate with a token from the deployment's
identity provider — Supabase on the hosted service, the built-in email/password
provider when `AUTH_PROVIDER=builtin`. Agents (daemon, plugins) authenticate with
a Vicoa-signed RS256 API key, of which only a SHA256 hash is stored; it is checked
against `api_keys` on every request so a revoked key stops working immediately.

**Messages.** A client posts a message → the backend persists it in `messages`
→ the daemon/plugin picks it up → the agent's output is posted back → the
backend broadcasts to every connected client over WebSocket.

**Source of truth** is the backend's PostgreSQL. Web caches with SWR; mobile is
local-first with background sync.

## Working on a feature

1. Decide which components change.
2. Data-model changes go first: SQLAlchemy models in `src/shared/database/`,
   then an Alembic migration, then the API in `src/backend/api/` or
   `src/servers/api/`.
3. Update the API clients (web / mobile / daemon).
4. Then the UI.
5. Each component has its own test suite — run the relevant ones.

## House rules

- **Type safety** — avoid `any` in TypeScript and untyped Python; annotate.
- **User scoping is mandatory** — every query filters by `user_id`.
- **Migrations** — always generate one for a schema change, review the
  autogenerated file, test `alembic upgrade head`, and never edit an applied
  migration; add a new one instead.
- **Lint before pushing** — `make lint` (backend) or `pnpm lint` (web) must
  exit 0.
- **Never commit secrets** — use `.env` files (gitignored). No keys, keystores,
  certs or service-account JSON in the tree.
- **Ask via the question tool** if your agent harness has one, rather than
  asking in prose.

## Extension points (why some code looks indirect)

Vicoa's hosted service adds closed features — billing, its marketing site, and
growth campaigns — as a **separate overlay package that is not part of this
repository**. The open code must never depend on it, so a few seams exist:

- `backend/src/shared/hooks.py` — additive hook registry (user-created,
  user-delete, app setup, lifespan). The core declares hooks; something else may
  register into them.
- `backend/src/backend/main.py` — a guarded optional import
  (`importlib.util.find_spec("cloud")`). Absent overlay → the log line
  `Cloud overlay absent; running open-source core`, and everything else runs
  normally.
- `backend/Dockerfile` — `BASE_DIR` / `OVERLAY_SRC` build args. Both default to
  the plain open build (`OVERLAY_SRC` points at an empty directory), so
  `docker build backend/` needs no arguments.
- Vicoa-specific strings (support inbox, mailing-list name) are read from env,
  with generic defaults.

When you touch these files, keep the rule: **the open build must work with the
overlay absent, and no file may import it unconditionally.**

## Code review checklist

- [ ] Backend: migration included for schema changes
- [ ] Backend: type hints on all functions
- [ ] Backend: every query scoped by `user_id`
- [ ] Web: TypeScript types defined; loading/error states handled
- [ ] Mobile: `FFAppState` updated where needed
- [ ] No hardcoded secrets; auth checks in place
- [ ] Open build still boots with no overlay present
