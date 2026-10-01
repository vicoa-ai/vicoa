# Agent skills

Skills that teach a coding agent how to work with Vicoa.

A **skill** is a folder with a `SKILL.md` — a short operating guide the agent
loads on demand, plus optional reference files it only opens when it needs the
detail. The format originated with Claude Code but is plain markdown: any agent
that can read a file can use these.

| Skill | What it teaches |
|---|---|
| [`vicoa-cli/`](vicoa-cli/) | Operate Vicoa from the terminal with the `vicoa` CLI — sessions and transcripts across machines, the task backlog, projects and labels, share links, scheduled automations. |
| [`live-preview/`](live-preview/) | Start (or reuse) the project's dev server, expose it through a Cloudflare or ngrok tunnel, and return the public URL for the Vicoa app's Live Preview. Runs only when invoked as `/live-preview`. |

## Install

**With the skills installer** — [`skills`](https://github.com/vercel-labs/skills)
copies a skill into the right directory for Claude Code, Codex, OpenCode,
Cursor and other agents:

```bash
npx skills add vicoa-ai/vicoa --skill live-preview
# one agent only, user-wide:
npx skills add vicoa-ai/vicoa --skill vicoa-cli --agent claude-code -g
```

**Claude Code, by hand** — copy (or symlink) the folder into your skills
directory:

```bash
cp -R skills/vicoa-cli ~/.claude/skills/          # user-wide
# or, per project:
cp -R skills/vicoa-cli .claude/skills/
```

A symlink keeps you on the repo's copy as it is updated:

```bash
ln -s "$PWD/skills/vicoa-cli" ~/.claude/skills/vicoa-cli
```

**Agents without a skills directory** — point the agent at the file from your
`AGENTS.md` (or the equivalent project instructions) and it will read it when
relevant:

```markdown
To drive Vicoa from the terminal, read `skills/vicoa-cli/SKILL.md`.
```

## Writing style

`SKILL.md` is the whole skill for most invocations, so it stays short and
covers judgement: which verb answers which question, what is safe to run
unprompted, what changes real state. Flag tables, enums and output contracts
live in reference files (`REFERENCE.md`, `reference/`), which the agent opens
only when it needs them.

The human-facing version of the same material is the documentation site. Keep
the two in step when the behaviour changes:

- `vicoa-cli` — [vicoa.ai/docs/cli-commands](https://vicoa.ai/docs/cli-commands),
  sourced from `apps/web/content/docs/cli-commands.mdx`.
- `live-preview` — [vicoa.ai/docs/live-preview](https://vicoa.ai/docs/live-preview),
  sourced from `apps/web/content/docs/live-preview.mdx`. The mobile app opens
  `trycloudflare.com` and `ngrok` links in Live Preview, so the skill's
  `public_url` must stay on one of those providers.
