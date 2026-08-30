# Contributing to Vicoa

Thanks for your interest in improving Vicoa. This repository is the **complete,
self-hostable Vicoa stack**: CLI, backend,
web, desktop app, and mobile apps.

## Ways to contribute

You don't have to write code to help. All of these are real contributions:

- **Report a bug** with a clear reproduction — see [Reporting bugs](#reporting-bugs).
- **Propose a feature** as a workflow you're missing — see [Proposing features](#proposing-features).
- **Improve the docs** — everything under `apps/web/content/docs/`, the READMEs,
  and this guide are good.
- **Triage and reproduce** open issues
- **Fix a bug or build a feature** — start from an open issue, or open a new one

## Before you start

- By submitting a contribution to Vicoa, you agree to the terms in
  [License of your contributions](#license-of-your-contributions). 
  Vicoa is licensed under the AGPLv3, and your contributions are accepted under
  that same license. Opening a pull request means you agree to those terms.

- **Fork, branch, PR.** Fork the repo, create a topic branch off `main`, and open
  a pull request back to `main`. Keep each PR focused on one change.

## How the repo is laid out

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
│   ├── web/              # Next.js dashboard + docs
│   ├── desktop/          # Electron desktop app
│   └── mobile/           # Flutter app (iOS/Android)
└── .github/workflows/    # CI + release workflows
```

Each component has its own `AGENTS.md` / `README.md` with deeper, agent-oriented
notes on architecture and conventions — read the one for the area you're
touching. The top-level [`AGENTS.md`](./AGENTS.md) is the best map of the whole
stack, and [`SELF_HOSTING.md`](./SELF_HOSTING.md) covers running it end to end.

## Development setup

You only need to set up the component(s) you're changing. A docs typo needs
nothing but a text editor; a backend change needs Python + Docker; a full
cross-component feature might touch all four.

### Prerequisites

- **Python 3.11+** and a virtualenv — backend, CLI, daemon.
- **Node.js + [pnpm](https://pnpm.io/)** — web dashboard and desktop shell.
- **[Flutter](https://docs.flutter.dev/get-started/install) (via FVM)** — mobile app.
- **Docker** — Postgres for local runs, and required for backend integration tests.
- **Git**, with your name/email configured for DCO sign-off (see above).

Copy the example environment file before running anything that needs config:

```bash
cp .env.example .env
```

See [`backend/README.md`](./backend/README.md) and
[`SELF_HOSTING.md`](./SELF_HOSTING.md) for the full list of environment
variables and how to generate local auth keys.

### Backend · CLI · daemon (Python)

```bash
cd backend
make dev-install           # install deps + dev tools into your virtualenv
make pre-commit-install     # install git hooks (ruff lint/format)

./dev-start.sh              # Docker services + migrations + both API processes
./dev-stop.sh              # tear it all down
# or, all-in-one in Docker:
docker compose up

# quality gates (match CI)
make lint                  # ruff lint + format check + pyright
make format                # auto-fix formatting
make typecheck             # pyright only

# tests
make test                  # everything
make test-unit             # unit only (fast)
```

Two processes share this codebase: `backend.main` serves the user-facing REST
API, and `servers.app` serves the agent-facing REST + MCP + WebSocket endpoint.
PostgreSQL is accessed via SQLAlchemy.

**Database migrations.** Any schema change needs an Alembic migration in the same
PR:

```bash
cd src/shared
alembic revision --autogenerate -m "Describe the change"   # generate
# review the generated file by hand — autogen is a starting point, not the answer
alembic upgrade head                                        # apply and test it
```

Never edit a migration that has already shipped; add a new one instead.

### Auth providers in local development

The backend runs one of two identity providers, chosen at startup (full details
in [`SELF_HOSTING.md`](./SELF_HOSTING.md#authentication)):

- **`builtin`** — email/password against this stack's own Postgres, nothing
  external to configure. It's the `.env.example` default, so `docker compose up`
  and the self-host stack use it.
- **`supabase`** — delegates identity to a Supabase project. Selected when
  `AUTH_PROVIDER=supabase`, or *inferred* when `SUPABASE_URL` + `SUPABASE_ANON_KEY`
  are set and `AUTH_PROVIDER` is unset. (That inference is why a `backend/.env`
  carrying Supabase keys makes `./dev-start.sh` come up in `supabase` mode, while
  `docker compose ... -f docker-compose.selfhost.yml` — which reads the repo-root
  `.env` with its explicit `AUTH_PROVIDER=builtin` — comes up `builtin`.)

**Clients must match the backend's provider.** A web or mobile build made for
Supabase sends a Supabase token, and a `builtin` backend rejects it with `401`
(and vice versa) — the two keep their identities in different places, and each
backend's user table is separate. This is the usual cause of "I'm signed in, but
every request 401s": e.g. the prebuilt mobile app (Supabase) pointed at a
`builtin` self-host backend. Pick one provider for the backend and build the
clients for the same one.

### Web dashboard + docs (Next.js)

```bash
cd apps/web
pnpm install
pnpm dev                   # dev server (turbopack); pnpm dev:no-turbo to disable

# before you push
pnpm test                  # Vitest — this is what CI runs
pnpm build                 # production build; catches type errors CI's tests won't
```

Next.js 15 + React 19, shadcn/ui, provider-aware auth. Product documentation is a
Fumadocs collection under `content/docs/` — doc-only changes just need the pages
to build.

### Desktop shell (Electron)

```bash
cd apps/desktop
pnpm install
pnpm dev                   # tsc && electron . (loads the apps/web dev server)
pnpm run package           # build the destkop app
```

The desktop app is an Electron shell that boots the `apps/web` renderer and
supervises a bundled backend daemon. 

Running it in dev involves a few coordinated
processes — see [`apps/desktop/README.md`](./apps/desktop/README.md) for the
exact setup, packaging, and release notes.

### Mobile app (Flutter)

```bash
cd apps/mobile
flutter pub get
flutter run

# before you push
flutter analyze
flutter test
```

The mobile app is a FlutterFlow-generated base with heavy customization: Provider
state via `FFAppState`, Supabase auth with social login, and custom actions in
`lib/custom_code/actions/`. Do **not** regenerate from FlutterFlow without
preserving the custom code — see [`apps/mobile/AGENTS.md`](./apps/mobile/AGENTS.md).

**Pointing the app at your own backend.** The published app talks to Vicoa's
production backend over Supabase. To run a dev build against your own stack, edit
`getVicoaApiBaseUrl` / `getVicoaWsUrl` in
`lib/custom_code/actions/vicoa_api_config.dart` and build the app yourself. Your
backend must run the **same auth provider** the app authenticates with (see
[Auth providers in local development](#auth-providers-in-local-development)) — the
app uses Supabase, so run the backend in `supabase` mode against **your own
Supabase project** (the free tier is plenty), or add a `builtin` login path to
your build. Spin up your own project
rather than pointing dev builds at production identity.

### opencode plugin

The OpenCode plugin lives in
[`vicoa-ai/opencode-vicoa`](https://github.com/vicoa-ai/opencode-vicoa), not this
repo. `npm install` then `npm run build`; contribute there.

## Making a change

Most non-trivial changes flow through the stack in the same order. Working
outside-in from the data model keeps the API, clients, and UI consistent:

1. **Decide which components change.** A change might be backend-only, or ripple
   from the backend all the way to mobile.
2. **Data-model changes go first.** Edit SQLAlchemy models in
   `src/shared/database/`, then generate an Alembic migration, then implement the
   API in `src/backend/api/` (user-facing) or `src/servers/api/` (agent-facing).
3. **Update the API clients** — web (`apps/web`), mobile (`apps/mobile`), and/or
   the daemon — to match the new contract.
4. **Then build the UI.**
5. **Run the relevant test suites** and add tests for what you changed.

## House rules

These are enforced in review (and mostly in CI). Following them up front means a
faster merge:

- **Type safety** — no `any` in TypeScript, no untyped Python; annotate.
- **User scoping is mandatory** — every backend query filters by `user_id`.
- **Migrations** — always generate one for a schema change, review the
  autogenerated file, test `alembic upgrade head`, and never edit an applied
  migration.
- **Lint before pushing** — `make lint` (backend) must exit 0; run
  `flutter analyze` for mobile.
- **Never commit secrets** — use `.env` files (gitignored). No keys, keystores,
  certs, or service-account JSON in the tree.
- **Keep the open build working with the overlay absent.** Vicoa's hosted service
  adds closed features (billing, marketing, growth) as a **separate overlay
  package that is not in this repo**. A few seams exist so the open code never
  depends on it (see the "Extension points" section of [`AGENTS.md`](./AGENTS.md)).
  When you touch those files, the rule is: the open build must boot with no
  overlay present, and no file may import it unconditionally.
- **Match the surrounding code.** Follow existing patterns, naming, and structure
  in the file you're editing rather than introducing a new style.

## Branches and commits

- **Branch names** describe the change: `feat/session-resume`,
  `fix/ws-close-race`, `docs/contributing-guide`. Avoid vague names like `test`,
  `wip`, or `changes`.
- **Commit messages** follow [Conventional Commits](https://www.conventionalcommits.org/):
  `feat:`, `fix:`, `docs:`, `refactor:`, `chore:`, etc. Keep the subject
  imperative and under ~72 characters; put the "why" in the body.
- **Sign off every commit** with `git commit -s` (DCO — see
  [Before you start](#before-you-start)).
- **Keep commits coherent.** Group related changes; don't bundle an unrelated
  refactor into a bug fix.

## Opening a pull request

Open your PR against `main` and fill out the
[pull request template](./.github/PULL_REQUEST_TEMPLATE.md). A good PR:

- **Does one thing.** One focused change; no unrelated edits bundled in.
- **Explains what and why**, and links the issue or discussion it closes
  (`Closes #123`).
- **Includes tests** for behavior changes and bug fixes. Prefer tests that would
  actually catch a regression, not shallow happy-path coverage.
- **Includes the migration** for any database schema change.
- **Shows the UI.** For UI or interaction changes, attach **before/after**
  screenshots or a short video on each affected platform. If there's no visual
  change, say so.
- **States what you tested.** Vicoa runs across macOS, Windows, Linux, iOS, and
  Android — maintainers can't reproduce every environment, so list the platforms
  you tested and the ones you didn't.
- **Includes your X (Twitter) handle** in the PR template's Credit section — we
  shout out contributors on [@vicoaai](https://x.com/vicoaai) when we merge their
  work. Leave it blank if you'd rather not be tagged.

Make sure the checks a component runs pass locally before you request review:

| Component            | Lint / types                      | Tests                          |
| -------------------- | --------------------------------- | ------------------------------ |
| Backend · CLI · daemon | `make lint`                       | `make test`                    |
| Web (Next.js)        | `pnpm build` (type-checks)        | `pnpm test`                    |
| Mobile (Flutter)     | `flutter analyze`                 | `flutter test`                 |

CI is path-filtered per component, so it only runs the suites relevant to your
change. If CI is red, fix it before asking for review — a maintainer will
generally wait for green. Reviews are a conversation; expect questions and be
ready to iterate.

## Reporting bugs

Open a GitHub issue using the **Bug report** template. Include the smallest
reproduction you can, the component and platform/OS, versions, and — if an agent
helped you investigate — the raw evidence and repro steps, not just its
conclusion.

**Security vulnerabilities are different:** do NOT open a public issue. See
[Reporting security issues](#reporting-security-issues).

## Proposing features

Open a **Feature request** issue or a GitHub Discussion. Frame it as a workflow:
what are you trying to do, how do you do it today, and where does Vicoa get in
the way? Agreeing on the shape of a feature in an issue first is the fastest path
to a merged PR.

## Reporting security issues

Please **do not** open a public issue, discussion, or pull request for a security
vulnerability. Report it privately per [SECURITY.md](./SECURITY.md) (email
**hi@vicoa.ai**, or GitHub's private "Report a vulnerability"). We aim to
acknowledge reports within a few business days and will credit you when a fix
ships, unless you prefer to remain anonymous.

## Getting help

- **Discord:** join [Discord](https://discord.gg/mqz4qRPV4j) — questions,
  discussion, and help getting set up.
- **Issues & discussions:** for bugs and feature proposals (see above).
- **Docs:** [vicoa.ai/docs](https://vicoa.ai/docs) and the sources under
  `apps/web/content/docs/`.
- **Email:** hi@vicoa.ai for anything that doesn't fit the above.

Releases (version bumps, tags, publishing) are maintainer-managed — you don't
need to touch versions in a normal contribution.


## Code of Conduct

Read the [Code of Conduct](./CODE_OF_CONDUCT.md). It applies everywhere in the
project — issues, pull requests, discussions, Discord, and any other community
space. Report unacceptable behavior to **hi@vicoa.ai**.


## License of your contributions

By submitting a Contribution — a pull request, patch, or anything else — you
keep your copyright, and you agree that:

- your Contribution is licensed to the project and everyone who receives the
  code under the [AGPLv3](./LICENSE) — the same license as the rest of the
  codebase
- to the extent your Contribution is covered by patents you can license, you
  grant everyone the patent license the AGPLv3 requires to use it.
- your contributed code may be used for any purpose permitted by the AGPLv3,
  including commercial use as part of the maintainers' hosted service.
