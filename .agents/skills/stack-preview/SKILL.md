---
name: stack-preview
description: Run the whole Vicoa stack (Postgres, backend, realtime server, web dashboard) from the current checkout and publish it at one public tunnel URL, so a branch can be reviewed from another machine or in the Vicoa app. Use when asked for a full-stack or end-to-end preview link of a Vicoa branch or PR, or when /live-preview is not enough because the dashboard needs a backend.
argument-hint: "[up | status | restart | down [--purge]] [--env-file FILE] [--allow-signup]"
disable-model-invocation: true
allowed-tools: Read, Glob, Grep, Bash
---

# stack-preview

`/live-preview` tunnels one dev server. The Vicoa dashboard is not one: its
browser code calls the REST backend and holds a WebSocket to the agent-facing
server, so a tunnel to the web app alone cannot even sign in. This skill runs
every piece from the checkout and puts them behind **one** origin:

```
browser ──https──▶ tunnel ──▶ proxy :P ─┬─ /ws          → server   (uvicorn, realtime)
                                        ├─ /api/v1/...  → backend  (uvicorn, REST)
                                        └─ everything   → web      (next dev, hot reload)
                   backend + server ──▶ Postgres (throwaway Docker container)
```

One origin means one link to hand over, no CORS, and realtime works through the
tunnel. Everything binds `127.0.0.1`; only the tunnel is public.

The script is `scripts/stack-preview.sh` in this skill's directory. It previews
the git checkout of the **current directory** (a worktree is fine), or `--repo DIR`.

## 1. Start

```bash
<skill-dir>/scripts/stack-preview.sh up
```

It creates and migrates the database, opens the tunnel, starts server, backend
and web, seeds two accounts, closes sign-up, then checks the page, the API and
the WebSocket handshake **through the public URL**. About 30 s, longer on a
first web compile. The result is `* key: value` lines, the same contract as
`/live-preview`, so the Vicoa app opens the link in Live Preview.

- `status: error` means one of those public checks failed. Read the log it
  names under `state:`, fix the problem, `down`, `up`. Don't hand over a link
  that failed its own check.
- "a next dev server already serves apps/web": that server isn't yours. Don't
  stop it; ask the user.
- Running `up` again while the preview is up just prints its status.

Flags:

- `--env-file FILE`: `KEY=value` lines for backend and server, e.g. Stripe
  test keys, or a `PYTHONPATH` that adds an overlay package. The preview's own
  database, URLs and auth settings always win. Never pass a file that holds
  production credentials.
- `--allow-signup`: leave sign-up open (for reviewing the sign-up flow). By
  default it closes after seeding, because anyone with the link can reach the server.
- `--provider ngrok`: by default cloudflared is tried first, then ngrok.
- `--auth supabase`: only when the user asks to review the **mobile app**, which
  can only sign in with Supabase. Everything else uses the default (builtin),
  and every `up` without the flag is builtin again. It signs in with a hosted
  Supabase project instead of seeded accounts. Export
  `SUPABASE_URL` and `SUPABASE_ANON_KEY` first (`apps/mobile/env.json` has
  them). Identity only: the data stays in the preview's database. There are no
  Ada/Bea accounts, so seeds write rows for the person who signs in (find them
  in `users` by email after their first sign-in). Point the app at the preview
  in the debug branch of `apps/mobile/lib/custom_code/actions/vicoa_api_config.dart`
  (`https://<public_url>` and `wss://<public_url>/ws`), and never commit that file.

## 2. Seed what the change needs

A fresh database holds only Ada (`ada@example.com`, owner) and Bea
(`bea@example.com`, a second person for sharing and permissions). The passwords
are in the output. An empty dashboard reviews nothing, so read the diff
(`git diff origin/main...`), list the screens and states it touches, and seed
those:

- Put seed scripts in the state dir (`state:` in the output), never in the repo.
- Prefer the API, acting as a real user:
  `curl -H "Authorization: Bearer $OWNER_TOKEN" "$PREVIEW_BACKEND/api/v1/..."`.
  This runs the same code the reviewer will use.
- Write rows directly only for things no endpoint creates (agent sessions and
  their messages, automation runs). A `.py` seed can import the models from
  `shared.database`. On a branch older than the fix that registers
  `AgentProfile` there, flushing an `Automation` or `AgentInstance` fails with
  `NoReferencedTableError: agent_profiles`; add
  `import shared.database.agent_profile_models`.
- Session status `COMPLETED` means archived: default lists and share links
  hide it. For a session that looks finished, use `AWAITING_INPUT`.
- Run `stack-preview.sh seed FILE`. A `.py` runs in the backend venv with
  `PYTHONPATH` set; anything else runs under bash. Seeds get `PREVIEW_URL`,
  `PREVIEW_BACKEND`, `DATABASE_URL`, `OWNER_EMAIL/PASSWORD/TOKEN` and the
  `VIEWER_*` equivalents. `stack-preview.sh env` prints the same exports for ad-hoc curl.
- Use invented data only. The link is public.

## 3. Check it the way the reviewer will

Before handing over the link, open it in a headless browser (Playwright) at the
public URL: sign in on `/sign-in` as Ada, open each changed screen, take
screenshots, and check the console. Expected noise: `404 /api/v1/billing/*` (the
open build has no billing) and `401 /api/supabase-user` from the sign-in page
before login.

## 4. Hand over

Give the user the public URL, both logins, what you seeded and where to click,
and the stop command. Leave the preview running until they say they're done.

While it runs: web edits hot-reload by themselves. After backend changes, run
`stack-preview.sh restart` (default: server and backend; or
`restart backend|server|web`). `restart` keeps the tunnel, so the link stays
valid. `down` then `up` keeps the data but gives a **new** URL.

## Stop

`stack-preview.sh down` stops every process the script started (checked by
recorded PID and start time) and the database container; the data survives.
`down --purge` also deletes the container and the state dir. Side processes
started with `stack-preview.sh run NAME -- CMD...` (e.g. a `stripe listen`
forwarding to `127.0.0.1:$PREVIEW_BACKEND_PORT`) stop with it.

## Rules

- The script's own Postgres container is the only database. Never point a
  preview at the shared dev database or at production.
- Don't start the backend by hand from `backend/`: `backend/.env` holds real
  credentials, and the backend reads `.env` from its working directory. The script
  runs Python with an empty environment from an empty directory, and blanks
  every key in `apps/web/.env*` for the web server.
- Stop things only with `down` or `restart`. Never pattern-kill: every Next dev
  server on the machine is titled `next-server`.

Ports, state files, every variable the script sets, and the traps it works
around: [reference/how-it-works.md](reference/how-it-works.md).
