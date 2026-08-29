"""OpenCode agent integration for Vicoa CLI.

This module provides the CLI entry point for running OpenCode with Vicoa integration.
It installs the opencode-vicoa plugin if needed and launches OpenCode with the
appropriate environment variables.
"""

import json
import os
import shutil
import signal
import subprocess
import sys
import uuid
from pathlib import Path
from typing import List, Optional

from vicoa.constants import DEFAULT_API_URL
from vicoa.sdk.client import VicoaClient


def _terminal_status_for_exit_code(exit_code: int) -> str:
    if exit_code == 0:
        return "COMPLETED"
    if exit_code < 0:
        return "KILLED"
    return "FAILED"


PLUGIN_NAME = "@vicoa/opencode"
OPENCODE_CONFIG_PATH = Path.home() / ".config" / "opencode" / "config.json"
OPENCODE_CACHE_PLUGIN_PATH = (
    Path.home() / ".cache" / "opencode" / "node_modules" / PLUGIN_NAME
)


def run_opencode(args, unknown_args: List[str], api_key: str) -> int:
    """Run OpenCode with Vicoa plugin integration.

    This function:
    1. Checks if OpenCode is installed
    2. Ensures opencode-vicoa plugin is installed
    3. Sets up environment variables
    4. Launches OpenCode (plugin loads automatically)

    Args:
        args: Parsed command-line arguments
        unknown_args: Additional arguments to pass through
        api_key: Vicoa API key

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    # Check if OpenCode is installed
    opencode_path = shutil.which("opencode")
    if not opencode_path:
        print("Error: OpenCode not installed", file=sys.stderr)
        print("Install OpenCode from: https://opencode.ai/", file=sys.stderr)
        return 1

    # Handle --upgrade-plugin: upgrade and exit immediately
    if getattr(args, "upgrade", False):
        upgrade_plugin()
        return 0

    # Extract args
    project_path = getattr(args, "project_path", None) or os.getcwd()
    model = getattr(args, "model", None)
    name = getattr(args, "name", None) or "OpenCode"
    agent_instance_id = getattr(args, "agent_instance_id", None)
    base_url = getattr(args, "base_url", None)
    resume = getattr(args, "resume", None)
    # headless = getattr(args, "headless", False)

    # Use resume as agent_instance_id if provided
    if resume:
        agent_instance_id = resume
    elif not agent_instance_id:
        agent_instance_id = str(uuid.uuid4())

    # # If headless mode, use ACP wrapper
    # if headless:
    #     return _run_opencode_headless(
    #         api_key=api_key,
    #         base_url=base_url,
    #         project_path=project_path,
    #         agent_instance_id=agent_instance_id,
    #         name=name,
    #         is_resuming=bool(resume),
    #         model=model,
    #     )

    # Register plugin in OpenCode config and pre-install into cache so OpenCode
    # doesn't show a black screen while installing on first launch.
    if not _ensure_plugin_registered():
        print(
            "Warning: Failed to register Vicoa plugin, continuing anyway...",
            file=sys.stderr,
        )
    _ensure_plugin_installed()

    # Set up environment variables
    env = os.environ.copy()
    env["VICOA_API_KEY"] = api_key

    if base_url:
        env["VICOA_API_URL"] = base_url
        env["VICOA_BASE_URL"] = base_url

    env["VICOA_AGENT_INSTANCE_ID"] = agent_instance_id
    env["VICOA_AGENT_NAME"] = name

    if model:
        env["OPENCODE_MODEL"] = model

    # Build OpenCode command
    command = ["opencode"]

    # Add any additional args
    if unknown_args:
        command.extend(unknown_args)

    # Hold an open fd on ~/.vicoa/opencode_wrapper/<agent_instance_id>.log
    # so ``vicoa ls`` can map this launcher's PID to its session UUID.
    # ``agent_processes._enrich_tui_agents_posix`` scans ``lsof`` for files
    # matching ``~/.vicoa/<type>_wrapper/<uuid>.log``; the opencode plugin
    # runs inside the opencode child process, so without our own fd here
    # the enrichment finds nothing and ``vicoa ls`` falls back to
    # ``pid:NNNN``. Nothing else writes to this file — it exists purely as
    # a presence marker the kernel exposes via lsof.
    session_log_file = None
    try:
        log_dir = Path.home() / ".vicoa" / "opencode_wrapper"
        log_dir.mkdir(parents=True, exist_ok=True)
        session_log_file = open(log_dir / f"{agent_instance_id}.log", "a")
    except Exception:
        pass

    # Forward SIGTERM/SIGHUP to the opencode child as SIGINT so a
    # ``vicoa stop`` triggers the binary's normal Ctrl+C exit path AND
    # lets the ``finally`` block below run end_session. Python's default
    # SIGTERM disposition terminates the launcher immediately, the plugin
    # inside opencode never gets to call end_session, and the session row
    # stays ACTIVE.
    proc: Optional[subprocess.Popen] = None

    def _forward_term_to_opencode(sig: int, _: object) -> None:
        if proc is None or proc.poll() is not None:
            return
        try:
            proc.send_signal(signal.SIGINT)
            print(
                f"[INFO] Received signal {sig}; forwarding SIGINT to opencode",
                file=sys.stderr,
            )
        except Exception:
            pass

    old_term_handler = signal.signal(signal.SIGTERM, _forward_term_to_opencode)
    old_hup_handler = signal.signal(signal.SIGHUP, _forward_term_to_opencode)

    exit_code = 0
    try:
        proc = subprocess.Popen(command, env=env, cwd=project_path)
        try:
            exit_code = proc.wait()
        except KeyboardInterrupt:
            print("\nInterrupted by user")
            exit_code = 130
            try:
                exit_code = proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    proc.terminate()
                    proc.wait(timeout=3)
                except (Exception, subprocess.TimeoutExpired):
                    try:
                        proc.kill()
                    except Exception:
                        pass
    except Exception as e:
        print(f"Error launching OpenCode: {e}", file=sys.stderr)
        exit_code = 1
    finally:
        try:
            signal.signal(signal.SIGTERM, old_term_handler)
            signal.signal(signal.SIGHUP, old_hup_handler)
        except Exception:
            pass

        # Backstop: end_session so the session row transitions out of
        # ACTIVE even if the plugin couldn't (opencode dying abruptly,
        # plugin shutdown hook racing the subprocess exit, etc.). Cheap
        # double-finalize is safe — server-side end_session is idempotent
        # for already-terminal rows.
        try:
            with VicoaClient(
                api_key=api_key,
                base_url=base_url or DEFAULT_API_URL,
            ) as backstop_client:
                final_status = _terminal_status_for_exit_code(exit_code)
                if final_status == "COMPLETED":
                    backstop_client.end_session(agent_instance_id)
                else:
                    backstop_client.update_agent_instance_status(
                        agent_instance_id, final_status
                    )
        except Exception as e:
            print(
                f"[WARN] Failed to finalize OpenCode session: {e}",
                file=sys.stderr,
            )

        if session_log_file is not None:
            try:
                session_log_file.close()
            except Exception:
                pass

    return exit_code


def _load_opencode_config() -> dict:
    """Load ~/.opencode/config.json, returning an empty dict if it doesn't exist."""
    if not OPENCODE_CONFIG_PATH.exists():
        return {}
    try:
        with open(OPENCODE_CONFIG_PATH, "r") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save_opencode_config(config: dict) -> None:
    """Write config back to ~/.opencode/config.json, creating the directory if needed."""
    OPENCODE_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OPENCODE_CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)


def _ensure_plugin_registered() -> bool:
    """Ensure opencode-vicoa is listed in the OpenCode config plugin array.

    OpenCode automatically installs any plugin listed in config on next run,
    so we only need to write the config entry. Existing plugins are preserved.

    Returns:
        True if the plugin is (now) registered, False on write failure.
    """
    config = _load_opencode_config()

    # Add $schema if not present (for new configs)
    if "$schema" not in config:
        config["$schema"] = "https://opencode.ai/config.json"

    plugins: list = config.get("plugin", [])

    if PLUGIN_NAME in plugins:
        return True

    plugins.append(PLUGIN_NAME)
    config["plugin"] = plugins

    try:
        _save_opencode_config(config)
        print(f"✓ Vicoa plugin registered in {OPENCODE_CONFIG_PATH}")
        print("  OpenCode installs it automatically on first run")
        return True
    except OSError as e:
        print(f"Warning: Failed to write OpenCode config: {e}", file=sys.stderr)
        return False


def _ensure_plugin_installed() -> None:
    """Pre-install the Vicoa plugin into OpenCode's cache before launch.

    OpenCode installs plugins listed in config on startup, which causes a black
    screen while it runs npm. Pre-installing here means OpenCode finds the plugin
    already cached and skips the install, so it opens cleanly.
    """
    if OPENCODE_CACHE_PLUGIN_PATH.exists():
        return

    npm_path = shutil.which("npm")
    if not npm_path:
        return  # No npm available; fall back to OpenCode's own install on startup

    cache_dir = OPENCODE_CACHE_PLUGIN_PATH.parent.parent  # ~/.cache/opencode/
    cache_dir.mkdir(parents=True, exist_ok=True)

    print("Installing Vicoa plugin for OpenCode...", end="", flush=True)
    try:
        result = subprocess.run(
            [npm_path, "install", PLUGIN_NAME],
            cwd=str(cache_dir),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            print(" done")
        else:
            print(" failed (OpenCode will retry on startup)")
    except (subprocess.TimeoutExpired, OSError):
        print(" failed (OpenCode will retry on startup)")


def upgrade_plugin() -> None:
    """Upgrade the opencode-vicoa plugin.

    OpenCode does not auto-update cached plugins, so we clear the cached
    copy.  The plugin entry in config is left intact so that OpenCode
    re-fetches the latest version on the next run.
    """
    if OPENCODE_CACHE_PLUGIN_PATH.exists():
        shutil.rmtree(OPENCODE_CACHE_PLUGIN_PATH)
        print(f"✓ Removed cached plugin from {OPENCODE_CACHE_PLUGIN_PATH}")
    else:
        print("  No cached plugin found — nothing to clear")

    # Make sure the config entry is still present so OpenCode re-installs
    _ensure_plugin_registered()
    print("✓ Plugin will be upgraded on next OpenCode run")
