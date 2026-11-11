# Example Vicoa plugins

A plugin is a folder with a `plugin.json`. It can:

- **`themes`**: remap the app's color tokens (HSL triplets); shown in the theme picker.
- **`sidebarItems`**: add a sidebar row that opens a URL (`open-url`: an `https://`
  link or an app route like `/dashboard/tasks`) or one of the plugin's pages
  (`surface`).
- **`composerActions`**: add a "+" menu row (`placement: "menu"`) or a toolbar
  button (`placement: "toolbar"`) that inserts text or opens a picker.
- **`surfaces`** (`apiVersion: 2`): add pages of its own. A page is a single
  HTML file that Vicoa runs in a sandbox; it reaches Vicoa only through
  `window.vicoa`, limited to what `plugin.json` declares in `permissions`,
  `files` and `network`. Its look is entirely up to you.

Icon names and theme token names are allow-listed
(`backend/src/protocol/plugin_manifest.py`); anything else is dropped. Full
reference: [Plugins](../../apps/web/content/docs/plugins.mdx).

| Example | What it shows |
|---|---|
| [`hello-vicoa/`](hello-vicoa/) | A theme, a sidebar link and two composer actions. No code. |
| [`hello-page/`](hello-page/) | A small page: your open tasks and recent sessions, with header tabs, settings and the side panel. |
| [`dashboard/`](dashboard/) | The Vicoa dashboard: what needs you, what your agents did, and each project's numbers. |

## Try one

```bash
# Copy it in (runs no scripts):
vicoa plugin install examples/plugins/hello-vicoa
# Or link a folder you are editing: changes show on reload, no reinstall.
vicoa plugin link examples/plugins/dashboard

vicoa plugin ls             # what is installed and what it adds
vicoa plugin reload dashboard
vicoa plugin logs dashboard # what its pages logged, and their errors
vicoa plugin disable dashboard
vicoa plugin remove dashboard   # a linked folder is left as it is
```

Vicoa asks you to approve a plugin the first time it sees it (and again
whenever its `plugin.json` changes), listing what it adds and what its pages
can reach. Manage everything in **Settings › Plugins**.

Plugin pages need the machine's Vicoa CLI to be at least the version that
added them; an older one shows "This machine needs a newer Vicoa".

## Make your own

```bash
vicoa plugin init ./my-plugin --template page   # a page that lists your tasks
vicoa plugin link ./my-plugin
```

`--template basic` scaffolds the declarative kind (a theme, a sidebar link, a
composer action) instead.
