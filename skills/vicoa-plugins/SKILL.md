---
name: vicoa-plugins
description: Build or change a Vicoa plugin, especially a plugin page (a dashboard or any custom view inside the Vicoa app), and keep a Dashboard plugin's per-project snapshot file up to date. Use when the user asks for a Vicoa plugin, a dashboard or page in Vicoa, a custom view of their tasks, sessions or automations, or to update the numbers the Dashboard plugin shows.
---

# Vicoa plugins

A plugin is a folder with a `plugin.json`, installed on one of the user's
machines. Version 2 plugins add **pages**: one HTML file each, run by Vicoa in
a sandbox, reaching Vicoa only through `window.vicoa`. Full reference:
https://vicoa.ai/docs/plugins (in the Vicoa repo: `apps/web/content/docs/plugins.mdx`).

## Never on the user's behalf

- **Don't approve or enable a plugin for the user.** Don't run `vicoa plugin trust`
  or `vicoa plugin enable`, and don't edit `~/.vicoa/daemon_state.json` or
  `~/.vicoa/config.json`. Vicoa asks the user to approve a plugin and lists what
  it can reach; that decision is theirs. Tell them it is waiting for approval.
- Don't put keys, tokens or personal data in a plugin folder or a page. A page
  can't use secrets safely; it runs in the user's browser.

## Build a page

1. Start from a template:
   - `vicoa plugin init <dir> --template page` for a small page, or
   - copy `examples/plugins/dashboard/` from the Vicoa repo for a full one.
2. Declare only what the page uses in `plugin.json`:
   - `permissions`: `projects:read`, `tasks:read`, `tasks:write`, `sessions:read`,
     `sessions:write`, `sessions:start`, `automations:read`. Prefer read-only;
     writes the user does in Vicoa's own panel (`vicoa.open.task`) need no write
     permission.
   - `files`: `~/` globs of local files the page reads. Keep them narrow.
   - `network`: leave it empty unless the page loads a library from a CDN; then
     list just that origin.
3. `vicoa plugin link <dir>`: links the folder without copying, so edits show on
   reload. Tell the user to approve it when Vicoa asks.
4. Write the page in plain HTML, CSS and JavaScript (no build step). Use
   `window.vicoa` for data and for opening things:
   - read: `vicoa.tasks.list({ label, status })`, `vicoa.sessions.list({ since })`,
     `vicoa.automations.list()`, `vicoa.automations.runs(id)`, `vicoa.files.readJson(path)`;
   - open in Vicoa: `vicoa.open.task(id, { siblings })` and `vicoa.open.session(id, { siblings })`
     show it in the side panel; `vicoa.open.newSession({ projectId, prompt })`;
   - chrome: `vicoa.ui.setHeader({ title, crumbs, tabs, actions })` plus
     `vicoa.events.on('header', …)`; keep the page's place with `vicoa.route.set()`;
   - style with the `--vicoa-*` CSS variables, or any style the user wants.
5. Check it: reload from the page's title bar, then `vicoa plugin logs <id>` for
   errors. Changing `plugin.json` makes the user approve the plugin again, so
   batch those changes.

Only use what Vicoa itself knows (tasks, comments, sessions, automations, runs)
plus files the user's agents write. Don't make a page depend on how one
particular agent words its messages.

## Dashboard snapshots

The Dashboard plugin shows each project's numbers from
`<project folder>/.vicoa/dashboard.local.json`. The format is in
`examples/plugins/dashboard/README.md`. When asked to update it:

- Write only numbers you actually read, with `asOf` set to when you read them.
  A number you couldn't get is `null` (shown as Unknown), never `0` or a guess.
- Values are display text: `"$1,240"`, `"140/week"`. Say what a number covers
  next to it (`"web only"`), in `note`.
- Make sure `.vicoa/*.local.json` is in the project's `.gitignore` before
  writing the file.
- Rewrite the whole file each time; keep `series` short (a few weeks of points,
  oldest first).
