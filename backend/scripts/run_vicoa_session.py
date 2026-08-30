#!/usr/bin/env python3
"""Launch a local vicoa session and mirror it through the WebSocket relay."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from vicoa.cli import ensure_api_key  # type: ignore  # pylint: disable=wrong-import-position # noqa: E402
from vicoa.session_sharing import run_agent_with_relay  # type: ignore  # pylint: disable=wrong-import-position # noqa: E402


def parse_args() -> tuple[argparse.Namespace, Iterable[str]]:
    parser = argparse.ArgumentParser(
        description="Run a claude/amp session with vicoa's WebSocket relay",
    )
    parser.add_argument(
        "--agent",
        choices=["claude", "amp"],
        default="claude",
        help="Agent to run (default: claude)",
    )
    parser.add_argument("--api-key", help="Explicit API key to use")
    parser.add_argument(
        "--base-url",
        default="https://agent.vicoa.com",
        help="Base URL for vicoa APIs",
    )
    parser.add_argument(
        "--auth-url",
        default="https://vicoa.com",
        help="Auth URL used if a re-login is needed",
    )
    parser.add_argument("--name", help="Friendly session name")
    parser.add_argument(
        "--permission-mode",
        choices=["acceptEdits", "auto", "bypassPermissions", "default", "plan"],
        help="Permission mode passed through to Claude (auto = Sonnet 4.6+ / Opus 4.7+ only)",
    )
    parser.add_argument(
        "--dangerously-skip-permissions",
        action="store_true",
        help="Bypass Claude permission prompts (use with caution)",
    )
    parser.add_argument(
        "--idle-delay",
        type=float,
        default=3.5,
        help="Seconds before considering Claude idle (default: 3.5)",
    )
    parser.add_argument(
        "--relay-host",
        default="127.0.0.1",
        help="Relay host to connect to (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--relay-port",
        type=int,
        default=8787,
        help="Relay WebSocket port (default: 8787)",
    )
    parser.add_argument(
        "--no-relay",
        action="store_true",
        help="Disable relay streaming and run locally only",
    )

    return parser.parse_known_args()


def main() -> None:
    args, passthrough = parse_args()

    if args.no_relay:
        os.environ["VICOA_RELAY_DISABLED"] = "1"
    if args.relay_host:
        os.environ["VICOA_RELAY_HOST"] = args.relay_host
    if args.relay_port:
        os.environ["VICOA_RELAY_WS_PORT"] = str(args.relay_port)

    api_key = ensure_api_key(args)

    exit_code = run_agent_with_relay(args.agent, args, passthrough, api_key)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
