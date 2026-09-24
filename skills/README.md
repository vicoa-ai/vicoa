# Agent skills

Skills that teach a coding agent how to drive Vicoa itself.

A **skill** is a folder with a `SKILL.md` — a short operating guide the agent
loads on demand, plus optional reference files it only opens when it needs the
detail. The format originated with Claude Code but is plain markdown: any agent
that can read a file can use these.

| Skill | What it teaches |
|---|---|
| [`vicoa-cli/`](vicoa-cli/) | Operate Vicoa from the terminal with the `vicoa` CLI — sessions and transcripts across machines, the task backlog, projects and labels, share links, scheduled automations. |

## Install

**Claude Code** — copy (or symlink) the folder into your skills directory:

```bash
cp -R skills/vicoa-cli ~/.claude/skills/          # user-wide
# or, per project:
cp -R skills/vicoa-cli .claude/skills/
```

A symlink keeps you on the repo's copy as it is updated:

```bash
ln -s "$PWD/skills/vicoa-cli" ~/.claude/skills/vicoa-cli
```

**Codex, OpenCode, Cursor, and other agents** — there is no skills directory to
drop this into. Point the agent at the file from your `AGENTS.md` (or the
equivalent project instructions) and it will read it when relevant:

```markdown
To drive Vicoa from the terminal, read `skills/vicoa-cli/SKILL.md`.
```

## Writing style

`SKILL.md` is the whole skill for most invocations, so it stays short and
covers judgement: which verb answers which question, what is safe to run
unprompted, what changes real state. Flag tables and enums live in
`REFERENCE.md`, which the agent opens only when it needs them.

The human-facing version of the same material is the documentation site —
[vicoa.ai/docs/cli-commands](https://vicoa.ai/docs/cli-commands), sourced from
`apps/web/content/docs/cli-commands.mdx`. Keep the two in step when the CLI
changes.
