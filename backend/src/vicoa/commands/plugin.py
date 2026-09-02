"""``vicoa plugin`` — manage locally-installed Vicoa plugins.

Unlike most CLI subcommands (which hit the backend HTTP API), plugins are a
*machine-local* resource — files under ``~/.vicoa/plugins/`` read by the daemon
running on this same machine. So these handlers call ``vicoa.rpc.plugin_ops``
directly rather than going over the network; they work with no login and no
daemon connection.

    vicoa plugin init ./my-plugin          scaffold a new plugin
    vicoa plugin install ./my-plugin       install from a local directory
    vicoa plugin add owner/repo --ref v1   install from a git repo (clone only)
    vicoa plugin ls [--json]               list installed plugins
    vicoa plugin enable|disable <id>       toggle a single plugin
    vicoa plugin trust <id>                approve a plugin's current manifest
    vicoa plugin remove <id>               uninstall a plugin
"""

from __future__ import annotations

import json as _json
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
        contrib = p.get("contributes") or {}
        summary = ", ".join(f"{k}:{v}" for k, v in contrib.items() if v) or "-"
        print(f"{p.get('id', ''):<{width}}  {'/'.join(flags):<18}  {summary}")
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


def _cmd_init(args) -> int:
    target = Path(args.path).expanduser()
    if target.exists() and any(target.iterdir()):
        print(f"error: {target} exists and is not empty", file=sys.stderr)
        return 1
    target.mkdir(parents=True, exist_ok=True)
    manifest = dict(_SCAFFOLD_MANIFEST)
    if args.id:
        manifest["id"] = args.id
    (target / "plugin.json").write_text(
        _json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Scaffolded plugin '{manifest['id']}' at {target}")
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
}


def run_plugin_command(args) -> int:
    """Entry point wired into ``cli.py``'s dispatch for ``vicoa plugin``."""
    sub = getattr(args, "plugin_command", None)
    handler = _HANDLERS.get(sub) if sub else None
    if handler is None:
        print(
            "usage: vicoa plugin {init,install,add,ls,enable,disable,trust,remove} ...\n"
            "Run `vicoa plugin --help` for details.",
            file=sys.stderr,
        )
        return 2
    return handler(args)


def add_plugin_subparser(subparsers) -> None:
    """Register the ``plugin`` subcommand tree on ``cli.py``'s subparsers."""
    plugin_parser = subparsers.add_parser(
        "plugin",
        help="Install and manage local Vicoa plugins (themes, sidebar, composer)",
    )
    plugin_sub = plugin_parser.add_subparsers(dest="plugin_command")

    p_init = plugin_sub.add_parser("init", help="Scaffold a new plugin directory")
    p_init.add_argument("path", help="Directory to create the plugin in")
    p_init.add_argument("--id", help="Plugin id (lowercase slug); default 'my-plugin'")

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

    p_remove = plugin_sub.add_parser("remove", help="Uninstall a plugin")
    p_remove.add_argument("id", help="Plugin id")
