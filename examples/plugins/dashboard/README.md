# Dashboard plugin

A page in the Vicoa sidebar that answers, in this order: what needs you, what
your agents did, and how each project is doing.

- **Overview:** how many tasks need you (and how many you cleared today), a card
  per project, the Needs you list, agent runs from the last 24 hours, what is
  scheduled next, and anything to watch (missed runs, flags from snapshots).
- **Project page:** the project's numbers, its Needs you list, then two
  columns, Build and Growth, each with its own status and its latest runs; an
  ops line; and a Week tab that lays the runs out by day.
- Click a task or a run and it opens in Vicoa's side panel, next to the page:
  read the task, reply or reply and hand it back, start a session from it; read
  a run's report and continue the session. J and K move through the list.

Everything except the numbers comes from Vicoa itself: tasks, sessions,
automations and their runs. The numbers come from a **snapshot file** in each
project's folder that you (or one of your agents) write. The plugin never calls
an outside service and needs no keys.

## Install

```bash
# Copy it in (runs no scripts):
vicoa plugin install examples/plugins/dashboard
# or, to edit the page and see changes on reload:
vicoa plugin link examples/plugins/dashboard
```

Vicoa asks you to approve it the first time, listing what it can read. It
needs `projects:read`, `tasks:read`, `sessions:read`, `automations:read`, and
read access to `~/**/.vicoa/dashboard.local.json`. It can't change anything:
replies and hand-backs happen in Vicoa's own panel, by you.

## Settings

Settings › Plugins › Dashboard, or from the page itself:

| Setting | What it does |
|---|---|
| Needs-you label | Open tasks with this label (default `needs-human`) are listed under Needs you. Handing one back moves it to In Review, which takes it off the list. |
| Projects | Which projects get a card, in order, by key (`HAB`) or name. Empty: every project with open work, recent runs or a snapshot. |
| Automation columns | Which column (Build, Growth or Ops) each automation's runs go in. Set it with the buttons under "Automation columns" on a project page. Runs of an automation with no column count under "not in a column". |
| Agent runs | Show only runs started by automations (default) or every session. Kept per device. |

## The snapshot file

Put `.vicoa/dashboard.local.json` in a project's folder on the machine the
plugin is installed on. Every field is optional; a project without the file
still shows its tasks and runs.

**Keep it out of git**: add `.vicoa/*.local.json` to the project's
`.gitignore`. Numbers like revenue don't belong in a repository.

```jsonc
{
  "asOf": "2026-11-08T08:00:00Z",            // when these numbers were read

  // The big number at the top of the project page.
  "headline": {
    "label": "Monthly revenue, all channels",
    "value": "$1,240",                        // a string, shown as is; null shows "Unknown"
    "goal": { "label": "$5k", "progress": 0.25, "by": "by Mar 31" },
    "note": { "text": "Up $80 since last month", "tone": "good" }
  },

  // The overview card. Falls back to "headline" when missing.
  "card": { "label": "Monthly revenue", "value": "$1,240", "series": [1080, 1160, 1240] },

  // Smaller numbers next to the headline.
  "metrics": [
    { "label": "Paying users", "value": "62", "note": "6 new this week", "series": [54, 58, 62] }
  ],

  // The two columns. Each has a one-line summary and groups of items.
  "build": {
    "summary": "2.3 ships Nov 20",
    "groups": [
      { "title": "Releases", "layout": "row", "items": [
        { "title": "2.2", "detail": "Live since Oct 30", "state": "done" },
        { "title": "2.3", "detail": "Ships Nov 20", "state": "active" }
      ] },
      { "title": "Held", "items": [
        { "title": "PR #42", "detail": "Held for review", "state": "paused", "date": "Nov 18", "url": "https://github.com/…" }
      ] }
    ]
  },
  "growth": { "summary": "…", "groups": [] },

  // One line at the bottom of the project page.
  "ops": [ { "text": "Backups OK", "tone": "good" } ],

  // Shown under Watch on the overview and the project page.
  "flags": [ { "text": "Certificate expires in 12 days", "tone": "warn" } ]
}
```

| Field | Values |
|---|---|
| `tone` | `good`, `warn`, `bad`, `info`, `neutral` |
| item `state` | `done`, `active`, `waiting`, `paused`, `risk`, `blocked`, `todo` |
| group `layout` | `row` (side by side, for a few items) or a list (default) |
| `series` | numbers, oldest first; drawn as a small line |
| `url` | an `https://` link the item opens |

Values are text on purpose: write `"$1,240"`, `"140/week"` or `"~$90"`, and say
what a number covers right next to it (`"web only"`). A number you couldn't
read should be `null`, which shows as Unknown, never as 0.

A [sample](sample-snapshot.json) is in this folder.

## Make it yours

The whole page is `pages/index.html`: plain HTML, CSS and JavaScript, no build
step. Change anything. It talks to Vicoa only through `window.vicoa` (see the
[plugin docs](https://vicoa.ai/docs/plugins)); anything you add that needs more
data must also be declared in `plugin.json`, and changing that file asks you to
approve the plugin again.
