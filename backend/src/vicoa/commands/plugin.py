"""``vicoa plugin`` — manage locally-installed Vicoa plugins.

Unlike most CLI subcommands (which hit the backend HTTP API), plugins are a
*machine-local* resource — files under ``~/.vicoa/plugins/`` read by the daemon
running on this same machine. So these handlers call ``vicoa.rpc.plugin_ops``
directly rather than going over the network; they work with no login and no
daemon connection.

    vicoa plugin init ./my-plugin [--template page]   scaffold a new plugin
    vicoa plugin install ./my-plugin       install from a local directory
    vicoa plugin add owner/repo --ref v1   install from a git repo (clone only)
    vicoa plugin link ./my-plugin          use a development directory in place
    vicoa plugin ls [--json]               list installed plugins
    vicoa plugin enable|disable <id>       toggle a single plugin
    vicoa plugin trust <id>                approve a plugin's current manifest
    vicoa plugin reload <id>               make open apps reload the plugin
    vicoa plugin logs <id> [-n N]          print the plugin's log
    vicoa plugin remove <id>               uninstall (or unlink) a plugin
"""

from __future__ import annotations

import html
import json as _json
import os
import sys
from pathlib import Path


def _print_list(payload: dict) -> None:
    plugins = payload.get("plugins", [])
    if not plugins:
        print("No plugins installed. Try `vicoa plugin init ./my-plugin`.")
        return
    if not payload.get("plugins_enabled", True):
        print(
            "(!) Plugins are globally disabled — enable them in Settings > Plugins.\n"
        )
    width = max((len(p.get("id", "")) for p in plugins), default=2)
    for p in plugins:
        flags = []
        flags.append("on " if p.get("enabled") else "off")
        if not p.get("valid", True):
            flags.append("INVALID")
        elif not p.get("trusted"):
            flags.append("untrusted")
        if p.get("linked"):
            flags.append("linked")
        contrib = p.get("contributes") or {}
        summary = ", ".join(f"{k}:{v}" for k, v in contrib.items() if v) or "-"
        print(f"{p.get('id', ''):<{width}}  {'/'.join(flags):<26}  {summary}")
        if p.get("linked") and p.get("link_target"):
            print(f"    -> {p['link_target']}")
        if p.get("requirement_error"):
            print(f"    ! {p['requirement_error']}")
        errors = p.get("errors") or []
        for err in errors:
            print(f"    ! {err}")


_SCAFFOLD_MANIFEST = {
    "id": "my-plugin",
    "apiVersion": 1,
    "name": "My Plugin",
    "description": "A starter Vicoa plugin.",
    "themes": [
        {
            "id": "example",
            "label": "My Plugin — Example",
            "base": "dark",
            "tokens": {
                "primary": "267 84% 81%",
                "sidebar-primary": "267 84% 81%",
            },
        }
    ],
    "sidebarItems": [
        {
            "id": "docs",
            "label": "Plugin Docs",
            "icon": "book-open",
            "action": {"type": "open-url", "url": "https://vicoa.ai", "external": True},
        }
    ],
    "composerActions": [
        {
            "id": "insert-signature",
            "label": "Insert signature",
            "icon": "sparkles",
            "placement": "menu",
            "behavior": {"type": "insert-text", "text": "\n\n— sent via My Plugin"},
        }
    ],
}


def _page_manifest(plugin_id: str, name: str) -> dict:
    """A v2 plugin with one page, opened from the sidebar."""
    return {
        "id": plugin_id,
        "apiVersion": 2,
        "name": name,
        "description": "A starter Vicoa plugin with its own page.",
        "permissions": ["tasks:read", "projects:read"],
        "surfaces": [
            {
                "id": "home",
                "kind": "page",
                "title": name,
                "entry": "pages/index.html",
                "icon": "layout-dashboard",
            }
        ],
        "sidebarItems": [
            {
                "id": "open",
                "label": name,
                "icon": "layout-dashboard",
                "action": {"type": "surface", "surfaceId": "home"},
            }
        ],
    }


# The page runs in a sandboxed frame with no network, so everything is inline.
# `window.vicoa` is injected by the app; the --vicoa-* variables carry its theme.
_PAGE_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>__NAME__</title>
<style>
  body {
    margin: 0;
    padding: 32px;
    background: var(--vicoa-background, #0b0b0f);
    color: var(--vicoa-foreground, #ececf1);
    font: 14px/1.5 var(--vicoa-font-sans, system-ui, sans-serif);
  }
  h1 { margin: 0 0 4px; font-size: 20px; font-weight: 600; }
  .muted { color: var(--vicoa-muted-foreground, #9a9aa6); margin: 0 0 24px; }
  ul { list-style: none; margin: 0; padding: 0; max-width: 640px; }
  li { margin: 0 0 8px; }
  button {
    display: flex; gap: 12px; align-items: center; width: 100%;
    padding: 10px 14px; text-align: left; cursor: pointer;
    background: var(--vicoa-card, #16161d);
    color: inherit; font: inherit;
    border: 1px solid var(--vicoa-border, #2a2a33);
    border-radius: var(--vicoa-radius, 8px);
  }
  button:hover { border-color: var(--vicoa-primary, #a78bfa); }
  .status {
    flex: none; font-size: 12px;
    color: var(--vicoa-muted-foreground, #9a9aa6);
  }
  .title { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
</head>
<body>
<h1 id="name">__NAME__</h1>
<p class="muted" id="note">Loading your tasks...</p>
<ul id="tasks"></ul>
<script>
(async function () {
  var note = document.getElementById("note");
  var list = document.getElementById("tasks");
  try {
    var ctx = await vicoa.context.get();
    document.getElementById("name").textContent = (ctx && ctx.pluginName) || "__NAME__";

    var tasks = await vicoa.tasks.list({ limit: 5 });
    if (tasks.length === 0) {
      note.textContent = "No tasks yet.";
      return;
    }
    note.textContent = "Your latest tasks. Click one to open it.";
    tasks.slice(0, 5).forEach(function (task) {
      var item = document.createElement("li");
      var button = document.createElement("button");
      var title = document.createElement("span");
      var status = document.createElement("span");
      title.className = "title";
      title.textContent = task.title;
      status.className = "status";
      status.textContent = task.status;
      button.append(title, status);
      button.addEventListener("click", function () {
        vicoa.open.task(task.id);
      });
      item.append(button);
      list.append(item);
    });
  } catch (err) {
    note.textContent = "Could not load tasks: " + ((err && err.message) || err);
  }
})();
</script>
</body>
</html>
"""


def _title_from_id(plugin_id: str) -> str:
    words = plugin_id.replace("_", "-").split("-")
    return " ".join(w.capitalize() for w in words if w) or "My Plugin"


def _cmd_init(args) -> int:
    from protocol.plugin_manifest import is_valid_plugin_id

    target = Path(args.path).expanduser()
    if target.exists() and any(target.iterdir()):
        print(f"error: {target} exists and is not empty", file=sys.stderr)
        return 1
    template = getattr(args, "template", None) or "basic"
    plugin_id = args.id or "my-plugin"
    if not is_valid_plugin_id(plugin_id):
        print(
            f"error: '{plugin_id}' is not a valid plugin id (lowercase letters,"
            " digits, - and _)",
            file=sys.stderr,
        )
        return 1
    target.mkdir(parents=True, exist_ok=True)
    if template == "page":
        name = _title_from_id(plugin_id) if args.id else "My Plugin"
        manifest = _page_manifest(plugin_id, name)
        pages = target / "pages"
        pages.mkdir(exist_ok=True)
        (pages / "index.html").write_text(
            _PAGE_HTML.replace("__NAME__", html.escape(name)), encoding="utf-8"
        )
    else:
        manifest = dict(_SCAFFOLD_MANIFEST)
        manifest["id"] = plugin_id
    (target / "plugin.json").write_text(
        _json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Scaffolded plugin '{manifest['id']}' at {target}")
    if template == "page":
        print(f"Try it while you edit:  vicoa plugin link {target}")
    else:
        print(f"Install it with:  vicoa plugin install {target}")
    return 0


def _cmd_install(args) -> int:
    from vicoa.rpc import plugin_ops

    result = plugin_ops.install_plugin(source=args.source, overwrite=args.overwrite)
    return _report_install(result, args)


def _cmd_add(args) -> int:
    from vicoa.rpc import plugin_ops

    source = _expand_repo_shorthand(args.repo)
    result = plugin_ops.install_plugin(
        source=source, ref=args.ref, subdir=args.subdir, overwrite=args.overwrite
    )
    return _report_install(result, args)


def _expand_repo_shorthand(repo: str) -> str:
    """`owner/repo` -> a GitHub HTTPS URL; a full URL / local path is untouched."""
    r = repo.strip()
    if "://" in r or r.startswith("git@") or "/" not in r:
        return r
    # Treat a bare `owner/repo` (no scheme, exactly two segments) as GitHub.
    parts = r.split("/")
    if len(parts) == 2 and all(parts):
        return f"https://github.com/{parts[0]}/{parts[1]}"
    return r


def _report_install(result: dict, args) -> int:
    if getattr(args, "json", False):
        print(_json.dumps(result, indent=2))
        return 0 if "error" not in result else 1
    if "error" in result:
        detail = f": {result['detail']}" if result.get("detail") else ""
        print(f"error: {result['error']}{detail}", file=sys.stderr)
        return 1
    print(f"Installed '{result['id']}' -> {result['path']}")
    for w in result.get("warnings") or []:
        print(f"  warning: {w}")
    return 0


def _cmd_ls(args) -> int:
    from vicoa.rpc import plugin_ops

    payload = plugin_ops.plugin_list()
    if getattr(args, "json", False):
        print(_json.dumps(payload, indent=2))
    else:
        _print_list(payload)
    return 0


def _cmd_enable(args) -> int:
    return _toggle(args, True)


def _cmd_disable(args) -> int:
    return _toggle(args, False)


def _toggle(args, enabled: bool) -> int:
    from vicoa.rpc import plugin_ops

    result = plugin_ops.set_plugin_enabled(plugin_id=args.id, enabled=enabled)
    if "error" in result:
        print(f"error: {result['error']}", file=sys.stderr)
        return 1
    print(f"{'Enabled' if enabled else 'Disabled'} '{args.id}'")
    return 0


def _cmd_trust(args) -> int:
    from vicoa.rpc import plugin_ops

    result = plugin_ops.grant_plugin_trust(plugin_id=args.id)
    if "error" in result:
        print(f"error: {result['error']}", file=sys.stderr)
        return 1
    print(f"Trusted '{args.id}' (current manifest).")
    return 0


def _cmd_link(args) -> int:
    from vicoa.rpc import plugin_ops

    # Absolute, but not resolved: provenance keeps the path as the user knows it.
    source = os.path.abspath(os.path.expanduser(args.path))
    result = plugin_ops.link_plugin(path=source)
    if getattr(args, "json", False):
        print(_json.dumps(result, indent=2))
        return 0 if "error" not in result else 1
    if "error" in result:
        detail = result.get("detail") or result.get("message")
        suffix = f": {detail}" if detail else ""
        print(f"error: {result['error']}{suffix}", file=sys.stderr)
        return 1
    if result.get("already"):
        print(f"'{result['id']}' is already linked -> {result.get('target')}")
        return 0
    print(f"Linked '{result['id']}' -> {result.get('target')}")
    for w in result.get("warnings") or []:
        print(f"  warning: {w}")
    print(
        f"Approve it with `vicoa plugin trust {result['id']}`; after editing,"
        f" `vicoa plugin reload {result['id']}`."
    )
    return 0


def _cmd_reload(args) -> int:
    from vicoa.rpc import plugin_ops

    result = plugin_ops.reload_plugin(plugin_id=args.id)
    if "error" in result:
        print(f"error: {result['error']}", file=sys.stderr)
        return 1
    print(f"Reloading '{args.id}': open apps pick it up on their next catalog check.")
    return 0


def _cmd_logs(args) -> int:
    from vicoa.rpc import plugin_ops

    result = plugin_ops.plugin_logs_read(plugin_id=args.id, limit=args.lines)
    if "error" in result:
        print(f"error: {result['error']}", file=sys.stderr)
        return 1
    lines = result.get("lines") or []
    if not lines:
        print(f"No log entries for '{args.id}'.")
        return 0
    for line in lines:
        print(line)
    return 0


def _cmd_remove(args) -> int:
    from vicoa.rpc import plugin_ops

    result = plugin_ops.remove_plugin(plugin_id=args.id)
    if "error" in result:
        print(f"error: {result['error']}", file=sys.stderr)
        return 1
    print(f"Removed '{args.id}'")
    return 0


_HANDLERS = {
    "init": _cmd_init,
    "install": _cmd_install,
    "add": _cmd_add,
    "ls": _cmd_ls,
    "enable": _cmd_enable,
    "disable": _cmd_disable,
    "trust": _cmd_trust,
    "remove": _cmd_remove,
    "link": _cmd_link,
    "reload": _cmd_reload,
    "logs": _cmd_logs,
}


def run_plugin_command(args) -> int:
    """Entry point wired into ``cli.py``'s dispatch for ``vicoa plugin``."""
    sub = getattr(args, "plugin_command", None)
    handler = _HANDLERS.get(sub) if sub else None
    if handler is None:
        print(
            "usage: vicoa plugin"
            " {init,install,add,link,ls,enable,disable,trust,reload,logs,remove}"
            " ...\n"
            "Run `vicoa plugin --help` for details.",
            file=sys.stderr,
        )
        return 2
    return handler(args)


def add_plugin_subparser(subparsers) -> None:
    """Register the ``plugin`` subcommand tree on ``cli.py``'s subparsers."""
    plugin_parser = subparsers.add_parser(
        "plugin",
        help="Install and manage local Vicoa plugins (themes, pages, sidebar, composer)",
    )
    plugin_sub = plugin_parser.add_subparsers(dest="plugin_command")

    p_init = plugin_sub.add_parser("init", help="Scaffold a new plugin directory")
    p_init.add_argument("path", help="Directory to create the plugin in")
    p_init.add_argument("--id", help="Plugin id (lowercase slug); default 'my-plugin'")
    p_init.add_argument(
        "--template",
        choices=["basic", "page"],
        default="basic",
        help="basic: theme + sidebar link + composer action; page: a plugin page",
    )

    p_install = plugin_sub.add_parser(
        "install", help="Install a plugin from a local directory"
    )
    p_install.add_argument("source", help="Path to a directory containing plugin.json")
    p_install.add_argument(
        "--overwrite", action="store_true", help="Replace if already installed"
    )
    p_install.add_argument("--json", action="store_true", help="Output raw JSON")

    p_add = plugin_sub.add_parser(
        "add", help="Install a plugin from a git repo (clone only)"
    )
    p_add.add_argument("repo", help="owner/repo, a git URL, or a local path")
    p_add.add_argument("--ref", help="Branch or tag to clone")
    p_add.add_argument(
        "--subdir", help="Subdirectory within the repo holding plugin.json"
    )
    p_add.add_argument(
        "--overwrite", action="store_true", help="Replace if already installed"
    )
    p_add.add_argument("--json", action="store_true", help="Output raw JSON")

    p_ls = plugin_sub.add_parser("ls", help="List installed plugins")
    p_ls.add_argument("--json", action="store_true", help="Output raw JSON")

    p_enable = plugin_sub.add_parser("enable", help="Enable a plugin")
    p_enable.add_argument("id", help="Plugin id")

    p_disable = plugin_sub.add_parser("disable", help="Disable a plugin")
    p_disable.add_argument("id", help="Plugin id")

    p_trust = plugin_sub.add_parser("trust", help="Approve a plugin's current manifest")
    p_trust.add_argument("id", help="Plugin id")

    p_remove = plugin_sub.add_parser(
        "remove", help="Uninstall a plugin (a linked one is only unlinked)"
    )
    p_remove.add_argument("id", help="Plugin id")

    p_link = plugin_sub.add_parser(
        "link", help="Use a development directory as a plugin, without copying"
    )
    p_link.add_argument("path", help="Directory containing plugin.json")
    p_link.add_argument("--json", action="store_true", help="Output raw JSON")

    p_reload = plugin_sub.add_parser(
        "reload", help="Make open Vicoa apps reload a plugin"
    )
    p_reload.add_argument("id", help="Plugin id")

    p_logs = plugin_sub.add_parser("logs", help="Print a plugin's log")
    p_logs.add_argument("id", help="Plugin id")
    p_logs.add_argument(
        "-n",
        "--lines",
        type=int,
        default=200,
        help="How many of the latest lines to show (default 200, max 2000)",
    )
