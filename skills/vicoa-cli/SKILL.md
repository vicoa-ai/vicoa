---
name: vicoa-cli
description: Operate Vicoa from the terminal with the `vicoa` CLI — list and inspect agent sessions (and their transcripts) across machines, start/resume/stop sessions, manage the task backlog with projects and labels, share a session by link, and schedule automations. Use when the user asks to check or control their Vicoa sessions, machines, tasks, or scheduled automations, read a session transcript, or create/update/delete Vicoa tasks or automations from the command line.
---

# Vicoa CLI

The `vicoa` command lets a coding agent operate the user's Vicoa account on
their behalf: their agent **sessions** (across every machine), their **task**
backlog, and their scheduled **automations**.

Every management subcommand (`session`, `task`, `project`, `label`,
`automation`, and `ls`) takes `--json` for machine-parseable output — **always
pass `--json` when you need to read a field programmatically**, and parse it
rather than scraping the table.

## Auth

`session`, `task`, `project`, `label`, and `automation` resolve the API key in
this order and **never open a browser** (they fail fast so an agent isn't
blocked):

1. `--api-key <key>` flag
2. `VICOA_API_KEY` environment variable
3. stored credential `~/.vicoa/credentials.json` (the `write_key` field)

If none is found, or a call returns 401, tell the user to run `vicoa --auth`
(first-time browser sign-in) or `vicoa --reauth` (refresh an expired key) —
these **open a browser, so never run them yourself on the user's behalf**; ask
the user to. They save the key to `~/.vicoa/credentials.json`.

Requests hit the agent-facing server `https://agents.vicoa.ai` by default. For a
self-hosted deployment, point the CLI at your own server with `--base-url <url>`
on any subcommand, or once for the shell with `VICOA_API_URL` (browser sign-in
follows `VICOA_AUTH_URL`).

## Safety & side effects

**Inspect before you mutate.** The read verbs (`vicoa ls`, `vicoa session
ls/get`, `vicoa task ls/get/comments`, `vicoa project ls/get`, `vicoa label ls`,
`vicoa automation ls/get/runs`) are safe and free — run them first to get the
exact id and current state. These verbs change real state or start real work, so
confirm intent before running them:

- `task create/update/delete/comment` — edits the user's backlog. A comment is
  visible to the user immediately in the web/mobile task detail. `task update`
  takes several task refs and applies the same change to each, so a wrong filter
  edits a lot at once. `session update --task` **flips the linked task's status**
  to follow the session (a running session ⇒ `in_progress`).
- `session share` — mints a **link that serves the session's transcript to
  anyone who has the URL**. Publishing a transcript is not reversible in the
  "nobody saw it" sense; confirm first, and pass `--audience authenticated` when
  the user means "a teammate" rather than "the internet". `session unshare
  --all` revokes every live link.
- `automation create/update/delete` — an **enabled** automation *will fire on its
  schedule* and dispatch a real agent session. Create with `--disabled` if you
  only want to stage it.
- `vicoa` / `vicoa codex` / `vicoa daemon` / `vicoa headless` / `vicoa session
  start` — start real processes and register sessions. `session start` spends
  tokens on a machine that may not be the one you are on.
- `vicoa stop [sessions|all|<id>]` — kills live agents; don't stop sessions you
  didn't start without confirming. **Never stop a session as automatic cleanup**
  — including sessions you started this turn (e.g. a headless smoke-test or a
  session you launched to demo something). Stop *only* when the user explicitly
  asks. Otherwise leave it running; an idle session simply sits in
  `AWAITING_INPUT` and costs nothing until continued.

`delete` prompts `[y/N]`; run non-interactively **without** `-y` and it aborts
rather than guessing. Pass `-y`/`--yes` only when the user has confirmed.

## When to use each

| Goal | Command |
|---|---|
| What agents are running **on this machine right now** | `vicoa ls` |
| **All** the user's sessions (any machine, incl. finished) | `vicoa session ls` |
| Read a session's **message transcript** | `vicoa session get <id>` |
| Start / resume / stop an agent session here | `vicoa`, `vicoa --resume`, `vicoa stop` |
| Start a session **on another machine** | `vicoa session start --machine <id\|name>` |
| Publish a transcript (e.g. to attach to a PR) | `vicoa session share` |
| The user's to-do backlog | `vicoa task ...` |
| The projects and labels tasks are filed under | `vicoa project ls`, `vicoa label ls` |
| A **scheduled**, auto-firing agent session | `vicoa automation ...` |

`vicoa ls` reads local OS processes; `vicoa session ls` reads the backend. Use
`session ls` for anything that isn't "processes alive on this box."

## Sessions

```bash
# Agents running on THIS machine (DAEMON + TUI sections)
vicoa ls
vicoa ls --json

# Every session the user owns, across machines and history
vicoa session ls                     # newest 50
vicoa session ls --active --limit 20 # only still-running
vicoa session ls --since 7d          # started in the last week
vicoa session ls --since 2026-09-20 --until yesterday
vicoa session ls --rate-limited      # only sessions blocked by a rate limit (adds a RESET column)
vicoa session ls --limit 50 --offset 50   # page back through history
vicoa session ls --json

# Inspect one session + its transcript (accepts full UUID or 8-char prefix)
vicoa session get 3f9c1a2b           # last 50 messages, clean chat view
vicoa session get 3f9c1a2b --all     # full transcript
vicoa session get 3f9c1a2b --all --role user   # only what the human asked for
vicoa session get 3f9c1a2b --full    # + timestamps, emails, control msgs, tool payloads
vicoa session get 3f9c1a2b --json    # {"instance": {...}, "messages": [...]}

# Rename a session / link it to a task (task status then follows the session)
vicoa session update 3f9c1a2b --title "Refactor auth"
vicoa session update 3f9c1a2b --task <TASK_UUID>
vicoa session update 3f9c1a2b --unlink-task

# Send input into a running session (delivered to the agent; flips it ACTIVE)
vicoa session message 3f9c1a2b "run the tests and fix failures"
vicoa session continue 3f9c1a2b      # sugar: sends the literal "continue"
```

`--since` / `--until` take a date (`2026-09-20`, local midnight), a datetime, an
age (`30m` / `24h` / `7d` / `2w`), or `today` / `yesterday`, and filter on
`started_at`. A bare date on `--until` includes that whole day.

`--rate-limited` returns only sessions a time-window rate limit is currently
blocking; each carries `rate_limited: true` and `rate_limit_resets_at` (also the
`RESET` column / a field in `--json`). A session is blocked until that instant —
`session continue` before it just re-hits the wall. The flag clears itself once
the session runs a turn under the limit again. If the target machine is offline,
`session message`/`continue` fails (retry once it's back). When `--rate-limited`
runs *inside* an automation-spawned session, it hides that automation's **own**
sessions (so the auto-continue automation below can't flag-and-continue its own
runs) — a different automation's rate-limited runs, and a manual `session ls`,
still see everything.

### Moving a session to a worktree

Vicoa files a session under the folder it started in. If the session creates or
switches to a git worktree mid-flight, re-file it or the app keeps showing (and
resuming) it under the original checkout:

```bash
vicoa session update "$VICOA_AGENT_INSTANCE_ID" --worktree <branch>
```

`<branch>` is the branch checked out in the target worktree (pass the main
checkout's branch to move it back). It is resolved with local git, so run it on
the machine the session lives on. The agent keeps running where it is; only the
sidebar group and the next resume follow.

### Starting a session

Locally, in this terminal:

```bash
vicoa                      # Claude Code (default agent)
vicoa codex                # Codex
vicoa opencode             # OpenCode
vicoa --agent amp          # any other supported agent
vicoa --name "Fix CI" --task <TASK_UUID>   # named, linked to a task
vicoa --resume <SESSION_ID>                # resume a previous session
vicoa daemon               # background daemon: accept remote/scheduled spawns
```

Or on any machine running a daemon — the CLI equivalent of the dashboard's "New
Session":

```bash
vicoa session start --list-machines
vicoa session start --machine <id|name> --dir ~/code/app \
  --agent claude --prompt "Triage the failing tests" --wait
```

`--dir` is **required** — there is no default working directory. `--machine`
defaults to this host's daemon and accepts an id, an id prefix, or a
display-name/hostname substring. Every agent except `amp` can be spawned this
way; `amp` only runs from a local `vicoa --agent amp`.

#### Match the session you're in

**`session start` does not inherit anything from you.** `--agent` falls back to
`claude` and model / effort / permission-mode to that agent's defaults, however
the session running this command is configured. So a Codex session on high
reasoning that shells out to a bare `vicoa session start` silently gets a
default-model Claude.

Unless the user asked for something different, start the new session as a copy
of this one — read your own config and pass it through:

```bash
CFG=$(vicoa session get "$VICOA_AGENT_INSTANCE_ID" --json --limit 1 \
  | jq -r '.instance.session_config')
vicoa session start --dir "$PWD" \
  --agent          "$(jq -rn --argjson c "$CFG" '$c.agent')" \
  --model          "$(jq -rn --argjson c "$CFG" '$c.current_model // $c.model')" \
  --effort         "$(jq -rn --argjson c "$CFG" '$c.thinking_effort // $c.reasoning_effort // empty')" \
  --permission-mode "$(jq -rn --argjson c "$CFG" '$c.permission_mode // empty')"
```

Three things to get right when reading that payload:

- **The agent id is `session_config.agent`** (`claude`, `codex`). The sibling
  `agent_type_name` is a *display label* — it reads `claude code` on most rows,
  which is not a value `--agent` accepts.
- **Prefer `current_model` over `model`.** `model` is what the session was
  spawned with; `current_model` is what it is running now, and the two diverge
  the moment anyone switches model mid-session.
- **Don't carry settings across a different agent.** Model slugs, efforts, and
  permission modes are per-agent vocabularies — if the user asked for a
  *different* agent, pass only `--agent` and let the rest default. A Claude
  model slug handed to Codex is worse than no inheritance at all.

Omit a flag whose value came back empty rather than passing an empty string.
`--effort` only applies to claude and codex; for other agents it's ignored with
a warning.

**Stopping:**

```bash
vicoa stop                 # stop the local background daemon (prompts)
vicoa stop sessions -y     # stop all local agent sessions, no prompt
vicoa stop 3f9c1a2b        # stop one session by id / 8-char prefix
```

### Share links

```bash
vicoa session share                       # the session this runs in
vicoa session share 3f9c1a2b --expires 7  # public link, gone in a week
vicoa session share 3f9c1a2b --audience authenticated --show-branch
vicoa session share 3f9c1a2b --list       # existing live links
vicoa session unshare 3f9c1a2b --all      # revoke
```

On success `share` prints **only the URL**, so it drops straight into a
`$(…)` — `gh pr comment 123 --body "Session: $(vicoa session share)"`. The link
is public by default and the owner's name is hidden unless `--show-owner`.
Re-running `share` reuses an equivalent live link rather than minting a second
one (`--new` forces a fresh one; `--expires` always mints a new link).
`unshare` with neither `--link` nor `--all` just lists the live links and
revokes nothing.

## Tasks

Statuses: `backlog` `todo` `in_progress` `in_review` `done` `blocked` `cancelled`
Priorities: `urgent` `high` `medium` `low` `none`

```bash
vicoa task ls                                  # all tasks
vicoa task ls --status todo --priority high --json
vicoa task ls --project VIC --label bug        # by project and label
vicoa task ls --project none                   # the unfiled ones
vicoa task get VIC-42                          # full detail

vicoa task create "Fix the flaky login test"
vicoa task create "Ship pricing page" --priority high --status todo \
  --project VIC --label design \
  --description "Localize copy first" --due 2026-08-25

vicoa task update VIC-42 --status in_progress
vicoa task update VIC-42 --priority urgent --title "New title"
vicoa task update VIC-42 VIC-43 VIC-44 --status done   # same change to each
vicoa task update VIC-42 --add-label regression        # keeps existing labels

vicoa task delete VIC-42 -y                    # -y skips the confirm prompt
```

`create` defaults to `status=backlog`, `priority=none`, and **No project** unless
`--project` is given. `update` changes only the flags you pass. Moving a task
between projects reassigns its identifier (the CLI prints `VIC-20 → VIC2-2`).

**Refer to a task by its identifier.** `VIC-42` — the thing shown in the KEY
column of `task ls`, in the task-detail header, and in what the user says out
loud — works everywhere a task reference is taken: the positional argument on
`get`/`update`/`delete`/`comment`/`comments`, and `--parent`. A full UUID still
works too. Prefer the identifier: it is the only handle you and the user both
have. Matching is case-insensitive.

Not every task has one: a task filed under **No project** has no identifier
(moving a task to `none` drops it), and so does a task created before
identifiers shipped. Both print `—` in the `KEY` column — use the UUID.
(`vicoa --task` and `session update --task` always want the UUID.)

### Projects and labels

```bash
vicoa project ls                  # KEY, NAME, ID — what --project accepts
vicoa project ls --include-archived
vicoa project get VIC

vicoa label ls                    # the names --label accepts
vicoa label create regression --color '#ef4444'
```

`--project` takes a key (`VIC`), a name, an id, or `none` for No project.
Labels are one vocabulary per account, shared across projects — `--label` on
`task ls` is repeatable and every one must match; on `task update`, `--label`
*sets* the list while `--add-label` / `--remove-label` adjust it.

### Comments

A task carries a comment thread (and a generated activity log). This is how an
agent reports back **on the task itself** rather than only inside a transcript
the user has to go find.

```bash
vicoa task comments VIC-42              # the thread; replies are indented
vicoa task comments VIC-42 --activity   # also the status/field change log

vicoa task comment VIC-42 "Fixed — the flake was a missing await."
vicoa task comment VIC-42 - < report.md          # body from stdin
vicoa task comment VIC-42 "Agreed" --reply-to <COMMENT_UUID>
```

- **Threads are one level deep.** `--reply-to` a reply lands in the same thread
  rather than nesting further, so a printed thread is never more than one indent.
- **Use `-` for anything multi-line.** Piping the body in beats fighting the
  shell over quoting and newlines.
- **Authorship is automatic.** Run inside a Vicoa session (`VICOA_AGENT_INSTANCE_ID`
  is set), a comment posted from a session started off an agent profile is signed
  by *that agent*; otherwise it is signed by the user whose key it is. Nothing to
  pass.
- Editing, deleting and reacting are deliberately **not** in the CLI — an agent
  revising its own words after the fact rewrites the record the human is reading.

## Automations

An automation is a saved **prompt + agent/model + machine/folder** that fires an
agent session on a schedule. This is **CRUD only** — the server's scheduler does
the firing, so there is no "run now."

```bash
vicoa automation ls
vicoa automation get <AUTOMATION_UUID>
vicoa automation runs <AUTOMATION_UUID>        # run history

# Create: pass exactly one schedule + a session config (--agent or --session-config-json)
vicoa automation create "Nightly triage" \
  --prompt "Triage new GitHub issues and label them" \
  --agent claude --daily --time 22:00 --timezone America/New_York

vicoa automation create "Hourly build check" \
  --prompt "Run the build and report failures" \
  --agent codex --hourly --minute 15         # add --model <slug> to pin a model

# Auto-continue rate-limited sessions: a plain hourly automation whose prompt
# drives the CLI. No special automation type — the spawned agent does the work.
vicoa automation create "Continue rate-limited sessions" \
  --agent claude --hourly \
  --prompt "Run \`vicoa session ls --rate-limited --json\`. For each session \
whose rate_limit_resets_at is in the past, run \`vicoa session continue <id>\`. \
Skip any that are already active."

vicoa automation update <AUTOMATION_UUID> --disable   # pause
vicoa automation update <AUTOMATION_UUID> --enable --prompt "New prompt"
vicoa automation delete <AUTOMATION_UUID> -y
```

The auto-continue automation runs on its **fixed cadence** (hourly), not a
precise wake at each session's reset — that's fine because `--rate-limited` is
indexed, so each run only fetches the handful of currently-blocked rows.

Schedules (choose **one** on create): `--at <ISO8601>` (once, UTC), `--daily`,
`--hourly`, `--weekdays` (Mon–Fri), `--weekly 1,3,5` (0=Sun…6=Sat),
`--frequency-json`. Automations need a machine to run on — run `vicoa daemon` on
the target box first (it auto-registers and becomes the default), or pass
`--machine-id`.

## Other command groups

Rarely what a question is about, but worth knowing they exist:

- `vicoa agent ls|add|rm` — saved agent profiles (provider + model + config +
  instructions) that `session start --agent-profile` and the dashboard reuse.
- `vicoa provider` — add and check the ACP coding agents this machine can run.
- `vicoa plugin` — install and manage local Vicoa plugins (themes, sidebar,
  composer).
- `vicoa worktree setup [path]` — run a worktree's committed setup commands from
  `.vicoa/config.json` (`--dry-run` to see them first). Useful when a worktree's
  automatic setup failed or never ran.

## Errors & recovery

| Message / symptom | Fix |
|---|---|
| `Authentication failed … run vicoa --reauth` (HTTP 401) | Key is invalid/expired — ask the user to run `vicoa --reauth` (opens a browser; you can't). |
| `No Vicoa API key found` | Set `VICOA_API_KEY`, pass `--api-key`, or have the user run `vicoa --auth`. |
| `No machine to run on` (automation create) | Run `vicoa daemon` on the target box first (it auto-registers), or pass `--machine-id`. |
| `--dir is required to start a session` | `session start` has no default directory — pass `--dir <PATH>`; `--list-machines` / `--list-models` first if you need to pick. |
| `Daemon on <machine> looks offline` (session start) | Start `vicoa daemon` there, or pass `--allow-offline` to queue the request until it reconnects. |
| `no project with key or name '…'` / `N projects are named '…'` | `--project` matches a key, name, or id exactly — check `vicoa project ls`; pass the key or id when two projects share a name. |
| `no label named '…'` | `--label` takes an existing name — `vicoa label ls`, or `vicoa label create <name>`. |
| `no session given and VICOA_AGENT_INSTANCE_ID is not set` | `session share`/`unshare` default to the session they run inside; outside one, pass the session id. |
| `'<ref>' is ambiguous` / `No session found matching` | The 8-char prefix collided or aged out — use more characters or the full UUID. |
| `404` on `task get/update/delete` | Use the `VIC-42` identifier or the **full UUID** — the 8-char prefix in the ID column is display-only. Automations still need their full UUID. |
| `Nothing to update — pass at least one field` | `update` is a PATCH; pass ≥1 flag (e.g. `--status done`). |
| `Aborted (pass --yes to delete non-interactively)` | Re-run `delete` with `-y` (only after the user confirms). |
| `pass only one schedule (… are mutually exclusive)` | `automation create` takes exactly one of `--at/--daily/--hourly/--weekdays/--weekly/--frequency-json`. |
| A verb or flag here doesn't exist | The installed CLI is older than this skill — `vicoa --version`, then `npm i -g @vicoa/cli@latest`. |

## Gotchas

- **`vicoa ls` ≠ `vicoa session ls`.** `ls` lists OS processes on *this* machine
  only; `session ls` reads the backend (all machines + finished sessions).
- **Id forms differ.** `session get/update` and `vicoa stop` accept an 8-char
  prefix; `task` takes `VIC-42` or a full UUID (not a prefix); `automation` ids
  must be the full UUID.
- **Task keys are per-owner, not global.** `VIC-1` names a different task in a
  different account, and a task that moves project is renumbered.
- **`--effort` is claude/codex only** (maps to `thinking_effort` /
  `reasoning_effort`); for other agents use `--session-config-json`.
- **`automation update` has no `--agent` flag** — change the agent by replacing
  the config wholesale with `--session-config-json '{"agent":"…"}'`.
- **Automations are CRUD-only — there is no "run now."** The server scheduler
  fires them; to run something immediately, use `vicoa session start` instead.
- **`session get` hides noise by default** (tool payloads, control messages,
  timestamps). Add `--tool-content` / `--control` / `--full` when you need them;
  a footer reports how much was hidden.
- **`--role` filters after `--limit`.** `--limit` counts both senders, so pair
  `--role` with `--all` or you'll get fewer rows than you asked for.
- **`--json` shapes differ.** `session ls` is wrapped —
  `{items, total, limit, offset, has_more}` — while `task ls`, `project ls`, and
  `label ls` return the bare array. `task update --json` prints one object for
  one ref and a list for several.
- **Don't merge streams before parsing.** The "new version available" banner
  goes to **stderr** precisely so it stays out of a `--json` pipe; `2>&1` puts
  it back in and breaks `jq`.
- **`vicoa stop <prefix>` stops every match.** A prefix that hits more than one
  session stops them all after a single confirmation — pass the full UUID when
  you mean one. `stop sessions --agent` takes only `claude`, `codex`,
  `opencode`, or `amp`.

See **[REFERENCE.md](REFERENCE.md)** for the complete flag tables (every session,
task, project, label, and automation option; transcript verbosity flags; schedule
details).
