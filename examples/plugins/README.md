# Example Vicoa plugins

Declarative **Tier 1** plugins — a single `plugin.json`, no code, cross-platform.
They customize the app through three contribution types:

- **`themes`** — remap shadcn color tokens (HSL triplets); shown in the theme picker.
- **`sidebarItems`** — a labeled row in the dashboard sidebar (`open-url` / `rpc`).
- **`composerActions`** — a "+" menu row (`placement: "menu"`) or a toolbar icon
  button (`placement: "toolbar"`) that inserts text / opens a picker.

Icon names and theme token names are allow-listed
(`backend/src/protocol/plugin_manifest.py`); anything else is dropped.

## Try it

```bash
# Install this example (copies it into ~/.vicoa/plugins/<id>/ — runs no scripts)
vicoa plugin install examples/plugins/hello-vicoa

# Approve it (or accept the trust prompt the app shows on first sight)
vicoa plugin trust hello-vicoa

vicoa plugin ls           # see it + what it contributes
vicoa plugin disable hello-vicoa
vicoa plugin remove hello-vicoa
```

Then, in the app: pick **Hello Vicoa — Emerald** in the theme picker, see the
**Vicoa Docs** row in the sidebar, and the two composer actions (a row in the
"+" menu and a toolbar button). Manage everything in **Settings → Plugins**.

> The daemon serving the app must be built from a branch that has the plugin
> RPCs (P1). Themes registered as built-in examples show up client-side without
> any daemon.

## Make your own

```bash
vicoa plugin init ./my-plugin --id my-plugin   # scaffolds a full example
vicoa plugin install ./my-plugin
```
