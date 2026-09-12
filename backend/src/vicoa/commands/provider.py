"""``vicoa provider`` — add, check and manage the ACP agents this machine can run.

Machine-local like ``vicoa plugin``: everything here edits ``agents.providers``
in ``~/.vicoa/config.json`` through :mod:`vicoa.rpc.provider_ops`, with no
login and no daemon connection. A running daemon notices the file change on
its own (the spec table is keyed on the file's mtime), so nothing needs a
restart.

    vicoa provider ls [--json]                  every provider + install state
    vicoa provider catalog [--json]             what `add` knows by name
    vicoa provider add <catalog-id>             one-click add from the catalog
    vicoa provider add <id> --command "goose acp" --label Goose
                                                any ACP server by hand
    vicoa provider check <id> [--cwd DIR]       spawn it, run the handshake,
                                                report models/modes or why not
    vicoa provider enable|disable <id>
    vicoa provider rm <id>

``check`` is the answer to "I added it — does it work?": it runs the exact
``initialize`` → ``session/new`` a session would and says which step failed.
"""

from __future__ import annotations

import json as _json
import shlex
import sys


def _emit(payload: dict, args) -> int:
    if getattr(args, "json", False):
        print(_json.dumps(payload, indent=2))
    return 1 if "error" in payload else 0


def _fail(payload: dict, args) -> bool:
    if "error" in payload:
        if getattr(args, "json", False):
            print(_json.dumps(payload, indent=2))
        else:
            print(f"error: {payload['error']}", file=sys.stderr)
        return True
    return False


def _cmd_ls(args) -> int:
    from vicoa.rpc import provider_ops

    payload = provider_ops.provider_list()
    if getattr(args, "json", False):
        return _emit(payload, args)
    rows = payload["providers"]
    width = max((len(r["id"]) for r in rows), default=2)
    for r in rows:
        if not r["enabled"]:
            state = "disabled"
        elif r["installed"]:
            state = "ready"
        else:
            state = "missing"
        source = "" if r["source"] == "builtin" else "  (config)"
        print(f"{r['id']:<{width}}  {state:<8}  {shlex.join(r['command'])}{source}")
    print(
        "\nready = binary found; missing = add it, then `vicoa provider check <id>`;\n"
        "`vicoa provider catalog` lists agents you can add by name."
    )
    return 0


def _cmd_catalog(args) -> int:
    from protocol.acp_catalog import ACP_CATALOG
    from vicoa.rpc import provider_ops

    if getattr(args, "json", False):
        print(_json.dumps(ACP_CATALOG, indent=2))
        return 0
    present = {r["id"] for r in provider_ops.provider_list()["providers"]}
    width = max(len(e["id"]) for e in ACP_CATALOG)
    for e in ACP_CATALOG:
        mark = "*" if e["id"] in present else " "
        print(f"{mark} {e['id']:<{width}}  {e['label']:<18} {shlex.join(e['command'])}")
    print("\n* = already in your config.  `vicoa provider add <id>` to add one.")
    return 0


def _cmd_add(args) -> int:
    from protocol.acp_catalog import catalog_entry
    from vicoa.rpc import provider_ops

    if args.launch_command:
        entry = {
            "id": args.id,
            "label": args.label or args.id,
            "command": shlex.split(args.launch_command),
        }
        if args.env:
            entry["env"] = dict(kv.split("=", 1) for kv in args.env if "=" in kv)
        if args.install_hint:
            entry["install_hint"] = args.install_hint
    else:
        found = catalog_entry(args.id)
        if found is None:
            print(
                f"error: '{args.id}' is not in the catalog. Run `vicoa provider catalog`,\n"
                f"or add any ACP server by hand: vicoa provider add {args.id} "
                f'--command "<binary> <acp args>" --label "<name>"',
                file=sys.stderr,
            )
            return 2
        entry = dict(found)
        if args.label:
            entry["label"] = args.label

    result = provider_ops.provider_add(entry, overwrite=args.overwrite)
    if _fail(result, args):
        return 1
    if getattr(args, "json", False):
        return _emit(result, args)
    print(
        f"Added '{result['id']}' ({result['label']}): {shlex.join(result['command'])}"
    )
    if result["installed"]:
        print(
            f"Binary found at {result['binary']}. Verify it with: vicoa provider check {result['id']}"
        )
    else:
        print(
            f"Binary not found on this machine yet. {result['install_hint']}".rstrip()
        )
        print(f"Once installed, run: vicoa provider check {result['id']}")
    return 0


_MAX_LISTED = 8


def _ids(items: list) -> str:
    """Comma-join ids, folding a long list (Cursor reports ~40 models)."""
    ids = [str(m.get("id")) for m in items if m.get("id")]
    if len(ids) > _MAX_LISTED:
        return (
            ", ".join(ids[:_MAX_LISTED])
            + f", … (+{len(ids) - _MAX_LISTED} more; --json for all)"
        )
    return ", ".join(ids)


def _cmd_check(args) -> int:
    from vicoa.rpc import provider_ops

    result = provider_ops.provider_probe(args.id, cwd=args.cwd, timeout=args.timeout)
    if getattr(args, "json", False):
        print(_json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1
    if "error" in result and "stage" not in result:
        print(f"error: {result['error']}", file=sys.stderr)
        return 2
    print(f"{result['label']} ({result['id']}): {shlex.join(result['command'])}")
    if result.get("ok"):
        agent = result.get("agent") or {}
        who = " ".join(v for v in (agent.get("name"), agent.get("version")) if v)
        print(
            f"  OK — handshake and session/new succeeded in {result['elapsed_ms']} ms"
            + (f" ({who})" if who else "")
        )
        models = result.get("models") or []
        modes = result.get("modes") or []
        print(f"  models: {_ids(models) or '(agent reports none before a prompt)'}")
        print(f"  modes:  {_ids(modes) or '(none)'}")
        return 0
    print(f"  FAILED at {result['stage']}: {result['error']}")
    for line in result.get("stderr") or []:
        print(f"  | {line}")
    return 1


def _cmd_enable(args) -> int:
    from vicoa.rpc import provider_ops

    result = provider_ops.provider_set_enabled(args.id, True)
    return 1 if _fail(result, args) else _emit(result, args)


def _cmd_disable(args) -> int:
    from vicoa.rpc import provider_ops

    result = provider_ops.provider_set_enabled(args.id, False)
    return 1 if _fail(result, args) else _emit(result, args)


def _cmd_rm(args) -> int:
    from vicoa.rpc import provider_ops

    result = provider_ops.provider_remove(args.id)
    if _fail(result, args):
        return 1
    if not getattr(args, "json", False):
        print(f"Removed '{args.id}' from {provider_ops.config_path()}")
    return _emit(result, args)


_HANDLERS = {
    "ls": _cmd_ls,
    "catalog": _cmd_catalog,
    "add": _cmd_add,
    "check": _cmd_check,
    "enable": _cmd_enable,
    "disable": _cmd_disable,
    "rm": _cmd_rm,
}


def run_provider_command(args) -> int:
    """Entry point wired into ``cli.py``'s dispatch for ``vicoa provider``."""
    sub = getattr(args, "provider_command", None)
    handler = _HANDLERS.get(sub) if sub else None
    if handler is None:
        print(
            "usage: vicoa provider {ls,catalog,add,check,enable,disable,rm} ...\n"
            "Run `vicoa provider --help` for details.",
            file=sys.stderr,
        )
        return 2
    return handler(args)


def add_provider_subparser(subparsers) -> None:
    """Register the ``provider`` subcommand tree on ``cli.py``'s subparsers."""
    parser = subparsers.add_parser(
        "provider",
        help="Add, check and manage the ACP coding agents this machine can run",
    )
    sub = parser.add_subparsers(dest="provider_command")

    p_ls = sub.add_parser(
        "ls", help="List providers on this machine with install state"
    )
    p_ls.add_argument("--json", action="store_true", help="Output raw JSON")

    p_catalog = sub.add_parser("catalog", help="List agents `add` knows by name")
    p_catalog.add_argument("--json", action="store_true", help="Output raw JSON")

    p_add = sub.add_parser(
        "add", help="Add a provider from the catalog, or any ACP server"
    )
    p_add.add_argument(
        "id", help="Catalog id, or a new id (lowercase slug) with --command"
    )
    # dest must not be "command": that is the top-level subcommand slot, and
    # argparse would overwrite it with None (sending `vicoa provider add x`
    # down cli.py's default "launch an agent" path).
    p_add.add_argument(
        "--command",
        dest="launch_command",
        help='Launch command, e.g. "goose acp" (marks a custom add)',
    )
    p_add.add_argument(
        "--label", help="Display name (defaults to the catalog's, or the id)"
    )
    p_add.add_argument(
        "--env",
        action="append",
        metavar="KEY=VALUE",
        help="Environment for the agent (repeatable)",
    )
    p_add.add_argument(
        "--install-hint", help="Text to show while the binary is missing"
    )
    p_add.add_argument(
        "--overwrite", action="store_true", help="Replace an existing entry"
    )
    p_add.add_argument("--json", action="store_true", help="Output raw JSON")

    p_check = sub.add_parser(
        "check", help="Spawn a provider and run the session handshake"
    )
    p_check.add_argument("id", help="Provider id")
    p_check.add_argument(
        "--cwd", help="Directory to open the probe session in (default: a scratch dir)"
    )
    p_check.add_argument(
        "--timeout", type=float, help="Seconds to wait for the handshake"
    )
    p_check.add_argument("--json", action="store_true", help="Output raw JSON")

    p_enable = sub.add_parser("enable", help="Show a hidden provider again")
    p_enable.add_argument("id", help="Provider id")
    p_enable.add_argument("--json", action="store_true", help="Output raw JSON")

    p_disable = sub.add_parser(
        "disable", help="Hide a provider without deleting its entry"
    )
    p_disable.add_argument("id", help="Provider id")
    p_disable.add_argument("--json", action="store_true", help="Output raw JSON")

    p_rm = sub.add_parser("rm", help="Delete a provider from your config")
    p_rm.add_argument("id", help="Provider id")
    p_rm.add_argument("--json", action="store_true", help="Output raw JSON")
