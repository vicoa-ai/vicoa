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
project's folder, written by you or by one of your agents with this folder's
`snapshot.py`. The plugin never calls an outside service and needs no keys.

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
| Projects | Which projects get a card, in order, by key (`APP`) or name. Empty: every project with open work, recent runs or a snapshot. |
| Automation columns | Which column (Build, Growth or Ops) each automation's runs go in. Set it with the buttons under "Automation columns" on a project page, or let the project's `laneRules` (in its snapshot) sort them by title. A pick on the page wins over a rule. Runs of an automation with no column count under "not in a column". The list shows automations that are switched on, plus recurring ones that ran this week; spent one-off bookings are left out. |
| Agent runs | Show only runs started by automations (default) or every session. Kept per device. |

## The snapshot file

Each project's numbers come from `.vicoa/dashboard.local.json` in its folder, on the machine the plugin is
installed on. A project without the file still shows its tasks and runs.

**Write it with `snapshot.py`** (in this folder), not by hand. It checks what you send, keeps what you didn't
send, stamps the time, writes the file in one step, and adds it to the repo's local exclude list so numbers like
revenue never reach git. Agents that compute your numbers call it right after they do:

```bash
python3 ~/.vicoa/plugins/dashboard/snapshot.py write --by mybot <<'EOF'
{
  "headline": {"label": "Revenue, 30 d", "value": "$18,300", "tag": "partial",
               "note": "iOS and web; Android not in yet", "asOf": "2026-11-07",
               "goal": {"label": "$40k/month", "progress": 0.46, "by": "2027-06-30"}},
  "metrics": [
    {"label": "Paying users", "value": "1,420", "note": "85 new this week", "asOf": "2026-11-07", "series": [1290, 1340, 1420]},
    {"label": "Churn, 30 d", "value": null, "note": "The billing export failed", "asOf": "2026-11-08"}
  ],
  "flags": [{"text": "Certificate expires in 12 days", "tone": "warn"}]
}
EOF
python3 ~/.vicoa/plugins/dashboard/snapshot.py check     # what the page will show, and any problem
```

`snapshot.py --help` has the same rules in short, for an agent to read. A write that breaks a rule is refused,
with every problem listed, and the file is left as it was.

| Field | Rule |
|---|---|
| `value` | The figure with its unit, as text: `"$18,300"`, `"~2,300"`, `"2,310/week"`. At most 16 characters. A number you couldn't read is `null`, with the reason in `note`; it shows as Unknown, never as 0. |
| `note` | What the number covers, at most 80 characters: one line on the project page (the whole of it on hover), not on the overview card. The method and every caveat belong in your own notes. |
| `tag` | `partial` (a channel it should cover is missing, say Android not read) or `estimate` (approximated). Shown as a chip next to the number. |
| `asOf` | The last day the number covers, `YYYY-MM-DD` (or an ISO time with its zone). Required. Shown under the number, in the warning color once it is more than a week old. |
| `label` | At most 32 characters. The headline is the project's card on the overview, so give every project's headline the same label. |
| `goal` | `label`, `progress` from 0 to 1, optional `by` (`YYYY-MM-DD`). Headline only. |
| `metrics` | At most 6, in order: the smaller numbers next to the headline. |
| `flags` | At most 6, under Watch: what someone should act on (`text`, optional `detail`, `tone`). |
| `series` | Numbers, oldest first, drawn as a small line. |
| `tone` | `good`, `warn`, `bad`, `info` |

`headline`, `metrics` and `flags` are one set: a write that sends any of them replaces all three, so a number or
a flag you stop sending goes away. The keys below stay until you send them again (`null` removes one).
`version`, `updatedAt` and `updatedBy` are stamped by `snapshot.py`: when `updatedAt` is older than
`staleAfterDays` (default 3; set it to how often you write, plus a day), the page says so under Watch.

```jsonc
{
  "staleAfterDays": 5,

  // The two columns on a project page. Each has a one-line summary and groups of items.
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

  // Which column an automation's runs go in, by its title: the first rule whose pattern matches
  // (a regular expression, any case) wins. Saves clicking each of a project's many one-off runs.
  "laneRules": [
    { "lane": "build",  "match": "\\b(dev|release)\\b" },
    { "lane": "growth", "match": "growth|seo" },
    { "lane": "ops",    "match": "\\b(ops|plan)\\b" }
  ]
}
```

| Field | Values |
|---|---|
| item `state` | `done`, `active`, `waiting`, `paused`, `risk`, `blocked`, `todo` |
| group `layout` | `row` (side by side, for a few items) or a list (default) |
| `url` | an `https://` link the item opens |
| `laneRules[].lane` | `build`, `growth` or `ops` |

A full [sample](sample-snapshot.json) is in this folder. The page reads the file when it opens; its automatic
refresh every minute covers tasks and runs only.

## Make it yours

The whole page is `pages/index.html`: plain HTML, CSS and JavaScript, no build
step. Change anything. It talks to Vicoa only through `window.vicoa` (see the
[plugin docs](https://vicoa.ai/docs/plugins)); anything you add that needs more
data must also be declared in `plugin.json`, and changing that file asks you to
approve the plugin again.
