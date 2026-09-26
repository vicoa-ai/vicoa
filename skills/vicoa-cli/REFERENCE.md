# Vicoa CLI — full reference

Complete flag tables for `vicoa`'s management commands. Enums, defaults, and
behaviours are taken from the CLI source in this repository
(`backend/src/vicoa/cli.py` and `backend/src/vicoa/commands/`). The
human-facing version of the same material is
[vicoa.ai/docs/cli-commands](https://vicoa.ai/docs/cli-commands).

Anything here can drift from the CLI you actually have installed — `vicoa
<group> <verb> --help` is always the ground truth for your version.

## Shared conventions

- `--json` — on **every** `session` / `task` / `project` / `label` /
  `automation` subcommand and on `vicoa ls`. Emits raw JSON instead of the human
  table. Prefer it for parsing.
- `--api-key` / `--base-url` — on every management subcommand. Key resolution:
  `--api-key` → `VICOA_API_KEY` → `~/.vicoa/credentials.json` (`write_key`).
  Default base URL: `VICOA_API_URL`, else `https://agents.vicoa.ai`. Browser
  sign-in uses `VICOA_AUTH_URL`, else `https://vicoa.ai`. Self-hosted
  deployments set both.
- Confirmation: `delete` prompts `[y/N]`; `-y`/`--yes` skips it. Run
  non-interactively (e.g. an agent) **without** `-y` and a delete aborts rather
  than guessing.
- 401 → key invalid/expired, run `vicoa --reauth`. Other non-2xx print the
  server's `detail` and exit non-zero.

## `vicoa ls` — local processes on this machine

Enumerates vicoa agent processes running on the current box (via `ps`), grouped
into **DAEMON SESSIONS** (headless) and **TUI SESSIONS**. Backend-stored names
are fetched and merged when a key is available.

| Flag | Meaning |
|---|---|
| `--json` | Raw JSON array of `{pid, agent, kind, session_id, name, project_path, age}` |

Table columns: `AGENT`, `NAME`, `PROJECT` (basename), `PID`, `AGE`, `ID` (the
full session id, or `pid:<n>` when there is none).

## `vicoa session ...` — sessions from the backend

Reads `/api/v1/agent-instances`. Covers every session the user owns — across
machines, cloud/mobile-started, and finished — and prints transcripts. Distinct
from `vicoa ls` (local processes only).

### `vicoa session ls`

| Flag | Default | Meaning |
|---|---|---|
| `--active` | off | Only sessions still running |
| `--rate-limited` | off | Only sessions currently blocked by a time-window rate limit |
| `--since WHEN` | — | Only sessions started at or after WHEN |
| `--until WHEN` | — | Only sessions started before WHEN |
| `--limit N` | 50 | Max sessions (1–100) |
| `--offset N` | 0 | Skip the newest N (page with `--limit`) |
| `--json` | | Raw JSON `{items: [...], total, limit, offset, has_more}` |

Columns: `AGENT`, `MODEL`, `STATUS`, `NAME`, `PROJECT`, `MSGS`, `STARTED`
(plus a `RESET` column when any listed session is rate-limited), then `ID`,
the full session id.

**`--since` / `--until` forms.** A date (`2026-09-20` = local midnight), a
datetime (`2026-09-20T14:30`, local unless it carries an offset or `Z`),
`today`, `yesterday`, or an age counted back from now (`30m`, `24h`, `7d`,
`2w`). The window is half-open on `started_at` — `[since, until)` — and a bare
date or `today`/`yesterday` on `--until` widens to include that whole day.
`total` counts the window, so a page can be smaller than `--limit` without
`has_more`.

**Rate limits.** Each item carries `rate_limited` (bool) and
`rate_limit_resets_at` (ISO, the binding reset instant). `--rate-limited`
returns only flagged rows and drops sessions whose reset is more than 24h in the
past (a permanently-dead session is not retried forever). When run inside an
automation-spawned session (the CLI sends `VICOA_AGENT_INSTANCE_ID` as
`caller_instance_id`), it also hides **that automation's own** sessions so the
auto-continue automation can't flag-and-continue its own runs; other
automations' rate-limited sessions and a manual `session ls` are unaffected.

### `vicoa session get <session_id>`

`session_id` is the full UUID `session ls` prints; every `session` command
takes only that. A short prefix is refused (`'<ref>' is not a session id`).

| Flag | Default | Meaning |
|---|---|---|
| `--limit N` | 50 | Newest N messages (ignored with `--all`) |
| `--all` | off | Full transcript (walks history backwards) |
| `--role {user,agent}` | both | Only one sender's messages |
| `--timestamps` | off | Timestamp on each message |
| `--emails` | off | Sender email on USER messages |
| `--control` | off | Include in-band control messages (hidden by default) |
| `--tool-content` | off | Include tool-use payloads/diffs (tool **names** always show) |
| `--full` | off | Everything: timestamps + emails + control + tool payloads |
| `--json` | | `{"instance": {...}, "messages": [...]}` |

Default view is a clean chat log: tool-use header lines appear, but payloads,
control envelopes, timestamps, and emails are suppressed. A footer notes how
many messages/payloads were hidden. `--limit` counts **all** senders before
`--role` filters, so pair `--role` with `--all`.

### `vicoa session update <session_id>`

Mirrors the web: rename, (un)link a task, or re-file the session under another
checkout. Linking drives the task's status from the session's status
server-side (a running linked session flips its task to `in_progress`).

| Flag | Meaning |
|---|---|
| `--title <text>` | Rename the session |
| `--task <TASK_UUID>` | Link to this task |
| `--unlink-task` | Clear the task link (mutually exclusive with `--task`) |
| `--worktree <BRANCH>` | File the session under the checkout of its repo with BRANCH checked out |

`--worktree` resolves the branch with **local git**, so run it on the machine
the session lives on. Pass the main checkout's branch to move it back. The agent
keeps running where it is; the sidebar group and the next resume follow the new
folder. Vicoa files a session under the folder it started in, so a session that
moves into a worktree mid-flight needs this or it stays filed under the original
checkout.

### `vicoa session start`

Starts a session on a machine running `vicoa daemon` — the CLI equivalent of the
dashboard's "New Session". Unlike the launch verbs below, the agent runs *there*,
not in this terminal.

| Flag | Default | Meaning |
|---|---|---|
| `--machine <ID\|NAME>` | this host's daemon | Target machine: full id, or a display-name/hostname substring (`--list-machines`) |
| `--dir <PATH>` | — (**required**) | Directory on the target machine |
| `--allow-offline` | off | Queue the request; it runs when the daemon reconnects |
| `--agent <name>` | `claude` | Agent to run — every supported agent **except `amp`**, which only runs locally. Also filters `--list-models` |
| `--agent-profile <NAME>` | — | Start from a saved agent (`vicoa agent ls`); explicit flags still win |
| `--model <slug>` | — | Model slug |
| `--effort <level>` | — | Reasoning effort (claude/codex) |
| `--permission-mode <mode>` | — | Permission mode (claude/codex/ACP agents) |
| `--opencode-mode <mode>` | — | OpenCode mode (`build`\|`plan`) |
| `--prompt <text>` | — | First user message; omit to start blank |
| `--name <text>` | — | Name for the new session |
| `--task <TASK_UUID>` | — | Link the new session to a task |
| `--wait` | off | Poll until the session leaves STARTING (needs the daemon online) |
| `--wait-timeout <SECS>` | 60 | Seconds to wait with `--wait` |
| `--list-machines` | | List registered machines and exit |
| `--list-models` | | List agents/models/efforts/modes and exit |

**Nothing is inherited from the calling session.** `--agent` defaults to
`claude` and the rest to that agent's defaults, regardless of what the session
running the command is configured with — only `--agent-profile` fills flags
from somewhere else. To start a copy of the current session, read its config
and pass the flags explicitly:

```bash
vicoa session get "$VICOA_AGENT_INSTANCE_ID" --json --limit 1 \
  | jq -r '.instance.session_config'
# {"agent":"claude","model":"claude-opus-5","current_model":"claude-opus-5",
#  "permission_mode":"auto","thinking_effort":"xhigh"}
```

`session_config.agent` is the catalog id `--agent` wants; the sibling
`agent_type_name` is a display label (`claude code`) and is **not** a valid
`--agent` value. `current_model` is the model the session is running now,
`model` only what it was spawned with. Efforts live under `thinking_effort`
(claude) or `reasoning_effort` (codex) — both map to the one `--effort` flag.
Carry model/effort/permission-mode only when the new session runs the **same**
agent; those vocabularies are per-agent.

### `vicoa session message <session_id> <text>`

Send a message into a session. Inserts a USER message, flips the session back to
`ACTIVE`, and delivers it to the running agent (the same primitive the web/app
use), scoped to the caller's own sessions. `session_id` is the full UUID. Fails if the target machine is offline (retry when it's back).

### `vicoa session continue <session_id>`

Sugar for the 90% case — sends the literal `continue`. Intended for the
auto-continue automation: run it against a session once its rate-limit window
(`rate_limit_resets_at` from `session ls --rate-limited`) has passed.

### `vicoa session share [session_id]`

Mints a link that serves the session's transcript to whoever opens it. The
positional is optional — it defaults to the session the command runs in
(`VICOA_AGENT_INSTANCE_ID`), which is how an agent attaches its own transcript
to a pull request.

| Flag | Default | Meaning |
|---|---|---|
| `--audience {public,authenticated}` | `public` | Anyone with the URL, or signed-in Vicoa users only |
| `--expires <DAYS>` | never | Expire after DAYS (1–365) |
| `--show-owner` | off | Show your name and avatar on the shared page |
| `--show-branch` | off | Show the git branch/worktree on the shared page |
| `--new` | off | Always mint a new link, even if an equivalent live one exists |
| `--list` | | List the session's live links instead of creating one |
| `--web-url <URL>` | `VICOA_AUTH_URL` / vicoa.ai | Web origin used to print the URL |

On success it prints **only the URL**, so it drops straight into a `$(…)`:
`gh pr comment 123 --body "Session transcript: $(vicoa session share)"`.
Without `--new`, an equivalent live link is reused rather than duplicated — but
`--expires` always mints a fresh link. A shared page shows the transcript only:
never the machine, the working directory, or session secrets.

### `vicoa session unshare [session_id]`

| Flag | Meaning |
|---|---|
| `--link <LINK_ID>` | Revoke this link (its full id from `session share --list`) |
| `--all` | Revoke every live link on the session |
| `--web-url <URL>` | Web origin for listed URLs |

With neither `--link` nor `--all` it prints the session's live links and exits
without revoking anything. A revoked URL stops working everywhere it was
pasted.

## Starting / stopping sessions locally

These run the agent in the current terminal (not part of the `session` group).

### Launch verbs

- `vicoa` — default agent (Claude, or your `--set-default` choice)
- `vicoa claude` / `vicoa codex` / `vicoa opencode` — pick the agent explicitly
- `vicoa --agent <name>` — any supported agent; `vicoa --help` lists the current
  set
- `vicoa headless [--agent ...] [--prompt "..."]` — background, driven from the
  web/mobile dashboard (no local TUI)
- `vicoa daemon` — background daemon that accepts remote + scheduled spawns and
  registers this machine
- `vicoa mcp` — MCP stdio server

### Common launch flags

| Flag | Meaning |
|---|---|
| `--name <text>` | Display name for the registered session |
| `--task <TASK_UUID>` | Link this session to a task (status follows the session) |
| `--resume <SESSION_ID>` | Resume a previous session (sets it ACTIVE) |
| `--agent <name>` | Which agent to run |
| `--agent-instance-id <id>` | Register under a specific session id |
| `--no-daemon` | Don't auto-start the background daemon for this run |
| `--set-default [agent]` | Persist the default agent for future bare `vicoa` runs |

### `vicoa stop [target]`

| Target | Effect |
|---|---|
| `daemon` (default) | Stop the local background daemon(s) |
| `sessions` | Stop all local agent sessions |
| `all` | Daemon + sessions |
| `<session id>` | Stop that one session (the full id `vicoa ls` prints) |

Flags: `--agent <name>` — only `claude`, `codex`, `opencode`, `amp` here, a
narrower set than the launch verbs take — plus `-y`/`--yes` and `--base-url`
(scope `stop daemon` to one base URL; without it, a bare `stop daemon` stops
every running daemon). `vicoa disconnect` is an alias for `vicoa stop daemon`.

Each session is asked to shut down gracefully and force-stopped if it doesn't exit
in a short grace period.

## `vicoa task ...` — task backlog

Endpoints: `/api/v1/tasks`. **Enums** (server-enforced):

- Status: `backlog` `todo` `in_progress` `in_review` `done` `blocked` `cancelled`
- Priority: `urgent` `high` `medium` `low` `none`

### `vicoa task ls`

Columns: `KEY` (`VIC-42`, or `—` for a task older than the identifiers),
`STATUS`, `PRIO`, `PROJECT`, `TITLE`, `ID` (full UUID).

| Flag | Meaning |
|---|---|
| `--project <REF>` | Only tasks in this project — key, name, or id; `none` = No project |
| `--status <status>` | Filter by status (enum above) |
| `--priority <priority>` | Filter by priority (enum above) |
| `--label <NAME>` | Only tasks carrying this label (repeatable; **every** one must match) |
| `--json` | Raw JSON — a bare array; rows carry `project_id` and `project_name` |

### Task references

Anywhere a task is named — the positional argument on `get`, `update`, `delete`,
`comment`, `comments`, and the `--parent` flag — you may pass either:

- the **identifier**, `VIC-42` (project key + per-project number), matched
  case-insensitively and scoped to the caller's own tasks; or
- the **full UUID**.

The server resolves both on the path (`GET /api/v1/tasks/VIC-42` works).
`--parent` is resolved client-side with one extra GET, because `parent_task_id`
travels in the request body as a typed UUID.

Keys are unique **per owner**, not globally: `VIC-1` names a different task in a
different account, and neither can reach the other.

Not every task has one. An identifier is a **project key + per-project number**,
so a task filed under **No project** has none — and moving a task to `none`
drops its identifier, just as moving it between projects renumbers it
(`VIC-20 → VIC2-2`). A task predating identifiers has none either. Both print
`—` in the `KEY` column; use the UUID.

### `vicoa task get <task_ref>`

Full detail (id, identifier, title, status, priority, project, parent, labels,
start/due dates, timestamps, description). `--json` supported.

### `vicoa task create "<title>"`

| Flag | Default | Meaning |
|---|---|---|
| `--description <text>` | — | Longer body |
| `--project <REF>` | No project | Project to file under — key, name, or id; `none` is explicit |
| `--status <status>` | `backlog` | Initial status |
| `--priority <priority>` | `none` | Priority |
| `--parent <TASK>` | — | Make it a subtask (`VIC-42` or UUID) |
| `--label <NAME>` | — | Label to apply, by name (repeatable) |
| `--start <ISO8601>` | — | Start date, e.g. `2026-08-01` |
| `--due <ISO8601>` | — | Due date, e.g. `2026-08-01T17:00:00Z` |
| `--json` | | Raw JSON of the created task |

### `vicoa task update <TASK> [TASK ...]`

Takes **one or more** task refs and applies the same change to each. Only the
flags you pass change (PATCH with exclude-unset); passing none is an error.

| Flag | Meaning |
|---|---|
| `--title` / `--description` | New title / body |
| `--project <REF>` | Move to this project (`none` = No project). A move **reassigns the identifier** — printed as `VIC-20 → VIC2-2` |
| `--status` / `--priority` | New status / priority (enums above) |
| `--parent <TASK>` | New parent task |
| `--start` / `--due` | New start / due date |
| `--label <NAME>` | Set the labels to **exactly** these (repeatable) |
| `--add-label <NAME>` | Add a label, keeping the rest (repeatable) |
| `--remove-label <NAME>` | Remove a label, keeping the rest (repeatable) |
| `--json` | Raw JSON — one object for one ref, a list for several |

With several refs, a ref that fails (typo, 404) is reported on stderr and the
rest still run; the exit code is `1` if any failed.

### `vicoa task delete <task_ref>`

`-y`/`--yes` to skip the confirm prompt.

### `vicoa task comments <task_ref>`

Prints the thread — author, timestamp, comment id, body, reaction counts. Replies
are indented one step under the root they answer; there is never a second step,
because the server keeps threads one level deep. `--activity` appends the
generated change log (status/priority/assignee/label/date/parent changes).
`--json` returns the whole timeline payload (`comments`, `activity`, task-level
`reactions`) — the same object the web task-detail page renders.

Endpoint: `GET /api/v1/tasks/{id}/timeline`.

### `vicoa task comment <task_ref> "<body>"`

| Flag | Meaning |
|---|---|
| `body` positional | Markdown body. Pass `-` to read it from **stdin** instead. |
| `--reply-to <COMMENT_UUID>` | Reply into that comment's thread |
| `--json` | Raw timeline JSON instead of the confirmation line |

Endpoint: `POST /api/v1/tasks/{id}/comments`. Returns the whole timeline, not
just the new row, so a reply comes back already spliced under its root.

**Authorship.** The CLI sends `VICOA_AGENT_INSTANCE_ID` when it is set (it is,
inside any Vicoa-spawned session). If that session was started from an **agent
profile**, the comment is authored by the profile and renders as the agent in
the web/mobile timeline; otherwise it is authored by the user who owns the API
key. An unknown or foreign session id degrades to the user rather than failing
the write.

**Not exposed:** edit, delete, and reactions. They exist in the human-facing API
only — an agent silently revising or removing its own comment rewrites the record
the human is reading.

## `vicoa project ...` — projects

Read-only from the CLI; projects are created in the web/desktop app (or
automatically, from the folder a session runs in).

| Command | Meaning |
|---|---|
| `project ls [--include-archived] [--json]` | Columns `KEY`, `NAME`, `PATH`, `TASKS`, `ID` — `KEY`/`NAME`/`ID` are the refs `--project` takes |
| `project get <REF> [--json]` | One project's detail — including every machine's checkout path; `<REF>` is a key, name, or id |

`PATH` is this machine's checkout; `TASKS` counts **open** tasks (everything but
`done` and `cancelled`). `none` is not a project — it is the sentinel
`--project` accepts for **No project** (the unfiled tasks).

## `vicoa label ...` — task labels

Labels are one vocabulary per account, shared across every project (there are no
per-project labels).

| Command | Meaning |
|---|---|
| `label ls [--json]` | Columns `NAME`, `COLOR`, `ID` — `NAME` is what `--label` takes |
| `label create <name> [--color '#RRGGBB'] [--json]` | Create one; colour defaults to the one the web would pick from the name |

`create` refuses a name that already exists (case-insensitively), so a
`--label <name>` reference is never ambiguous. Rename, recolour, and delete
stay in the apps.

## `vicoa automation ...` — scheduled automations

Endpoints: `/api/v1/automations`. An automation stores a prompt + session config
+ machine/directory + schedule. **CRUD only** — the server scheduler fires it;
there is no run-now.

### `vicoa automation ls` / `get <id>` / `runs <id>` / `delete <id>`

- `ls` — table (ID, TITLE, ON=enabled, SCHEDULE summary, NEXT RUN). `--json`.
- `get <AUTOMATION_UUID>` — full detail incl. `machine_id`, `directory`,
  `worktree`, `frequency`, `timezone`, `next_run_at`, `last_run_at`,
  `last_run_status`, `session_config`, and the prompt. `--json`.
- `runs <AUTOMATION_UUID>` — run history (STATUS, FIRED AT, DETAIL, and the
  full SESSION id each run started). `--json` adds the run ids.
- `delete <AUTOMATION_UUID>` — `-y`/`--yes` to skip confirm.

Automation ids are always **full UUIDs**, like every other id the CLI takes.

### `vicoa automation create "<title>"`

Requires `--prompt`, **exactly one schedule**, and a session config.

**Schedule selectors** (mutually exclusive on create; on update, passing one
re-times the automation, passing none leaves it alone):

| Flag | Meaning |
|---|---|
| `--at <ISO8601>` | Run once at this UTC instant, e.g. `2026-08-10T09:00:00Z` |
| `--daily` | Every day at `--time` |
| `--hourly` | Every hour at `--minute` |
| `--weekdays` | Mon–Fri at `--time` |
| `--weekly <DAYS>` | Weekly on these weekdays, `0=Sun…6=Sat`, e.g. `--weekly 1,3,5` |
| `--frequency-json <JSON>` | Raw frequency object for custom/interval schedules |

Schedule modifiers: `--time HH:MM` (default `09:00`, for daily/weekdays/weekly),
`--minute M` (default `0`, for hourly), `--timezone <IANA>` (default UTC, applies
to recurring schedules — sending it alone on update re-times the next run).

**Session config** — either the convenience flags or a full JSON blob:

| Flag | Meaning |
|---|---|
| `--agent <name>` | Agent to run (e.g. `claude`, `codex`, `opencode`). Required unless `--session-config-json` |
| `--model <slug>` | Model slug for the agent |
| `--effort <level>` | Reasoning/thinking effort — **claude & codex only** (maps to `thinking_effort` / `reasoning_effort`) |
| `--permission-mode <mode>` | Agent permission mode (e.g. `plan`, `acceptEdits`) |
| `--session-config-json <JSON>` | Full config object; overrides the above; must include `"agent"` |

**Target** (where it runs):

| Flag | Default | Meaning |
|---|---|---|
| `--machine-id <id>` | this machine's registered daemon | Machine to run on |
| `--directory <path>` | current dir | Working directory on the machine |
| `--worktree-json <JSON>` | — | Worktree spec, e.g. `{"mode":"new"}` or `{"mode":"existing","path":"..."}` |

Other: `--disabled` creates it paused (`enabled=false`). If no machine can be
resolved (no `--machine-id` and no local daemon has registered), create fails —
run `vicoa daemon` on the target box first.

### `vicoa automation update <automation_id>`

Accepts all `create` flags (schedule, session config, target) plus `--title`,
`--prompt`, and an enable toggle. Only what you pass changes.

| Flag | Meaning |
|---|---|
| `--enable` | Enable (resume) the automation |
| `--disable` | Disable (pause) the automation |

`--enable`/`--disable` are mutually exclusive. Note: `update` has no `--agent`
convenience flag — change the agent via `--session-config-json` (which replaces
the config wholesale).

## `vicoa worktree setup [path]`

Runs the source repository's `worktree.setup` commands — from its committed
`.vicoa/config.json` (or root `vicoa.json`) — inside the checkout at `path`
(default: the current directory), echoing each command and streaming its
output. This is the same run the daemon performs automatically when it creates
a worktree for a new session, so it writes the same run record and the
dashboard's setup badge shows it.

| Flag | Meaning |
|---|---|
| `--dry-run` | List the commands that would run, without running them |
| `--trust` | Also mark the source repository as trusted on this machine, so the daemon sets up new worktrees automatically |
| `--force` | Run even if a setup run for this worktree is already in progress |

Each command runs in the worktree under a login shell with
`$VICOA_WORKTREE_PATH`, `$VICOA_ROOT_PATH` (the main checkout the config came
from) and `$VICOA_BRANCH_NAME` set. The run stops at the first failure and
returns that command's exit code. The config is always read from the **source**
repository's working tree, so a linked worktree runs the same setup as the
checkout it was forked from.

**Trust.** A cloned repository's config can contain arbitrary shell, so the
daemon only *auto-runs* setup for repositories approved on that machine. Typing
the command yourself is approval for that one run — nothing is gated — and
`--trust` records it for the future. Reach for this to re-run after a failed
automatic setup, or to bring up a worktree whose setup never ran.

## Machine-readable output

Every `session` / `task` / `project` / `label` / `agent` / `automation`
subcommand, plus `vicoa ls`, takes `--json`. The shapes are not uniform:

- **Paginated lists** (`session ls`) come wrapped:
  `{items, total, limit, offset, has_more}`.
- **Everything else** (`task ls`, `project ls`, `label ls`, `vicoa ls`) is the
  bare array the API returns.
- `task update --json` prints one object for a single ref, a list for several.

```bash
vicoa session ls --active --json | jq '.items[].id'
vicoa task ls --project VIC --json | jq '.[].identifier'
```

The "new version available" banner is written to **stderr** so it never lands
in a `--json` pipe — don't merge the streams with `2>&1` before parsing.

## Other groups

| Command | Meaning |
|---|---|
| `vicoa agent ls\|add\|rm` | Saved agent profiles (provider + model + config + instructions) reused by `session start --agent-profile` and the dashboard |
| `vicoa provider ...` | Add, check and manage the ACP coding agents this machine can run |
| `vicoa plugin ...` | Install and manage local Vicoa plugins (themes, sidebar, composer) |
