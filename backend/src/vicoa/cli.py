"""Vicoa Main Entry Point

This is the main entry point for the vicoa command that supports:
- Default (no subcommand): Claude chat integration
- mcp: MCP stdio server
"""

import argparse
import sys
import subprocess
import json
import os
import platform
import shutil
from pathlib import Path
import webbrowser
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
import secrets
import requests
import time
import threading
from typing import Optional
from .machine_daemon import (
    DaemonStartResult,
    ensure_background_daemon_running,
    find_running_daemon_pid,
    migrate_legacy_flat_state,
    run_daemon,
    stop_background_daemon,
)
from .machine_state import read_machine_id
from . import credentials_state
from .constants import DEFAULT_API_URL, DEFAULT_AUTH_URL
from .file_sync import sync_project_files
from .utils import get_project_path
from .commands.automation import add_automation_subparser, run_automation_command
from .commands.plugin import add_plugin_subparser, run_plugin_command
from .commands.instance import run_session_command
from .commands.ls import cmd_ls as _cmd_ls
from .commands.stop import cmd_stop
from .commands.task import TASK_PRIORITIES, TASK_STATUSES, run_task_command


AGENT_CHOICES = ["claude", "amp", "codex", "opencode"]

# Agents served by the generic ACP module (integrations/headless/generic_acp).
# Headless/daemon mode only — there is no TUI wrapper for these.
GENERIC_ACP_AGENT_CHOICES = ["cursor", "gemini", "copilot", "kimi", "hermes"]
# Native-RPC Pi family (integrations/headless/pi_family/). Not ACP — one
# wrapper, two agents, selected with `--agent`.
PI_FAMILY_AGENT_CHOICES = ["omp", "pi"]

AGENT_CHOICES.extend(GENERIC_ACP_AGENT_CHOICES)
AGENT_CHOICES.extend(PI_FAMILY_AGENT_CHOICES)


def sync_project_files_async(api_key: str, base_url: str, project_path: str) -> None:
    """Run project file sync in background so startup is not blocked."""

    thread = threading.Thread(
        target=sync_project_files,
        args=(api_key, base_url, project_path),
        daemon=True,
        name="vicoa-file-sync",
    )
    thread.start()


def run_python_module(module_path, args_list, env_vars=None):
    """Run a Python module either as subprocess (normal) or direct import (frozen).

    Args:
        module_path: Full module path (e.g., "integrations.cli_wrappers.claude_code")
        args_list: List of command-line arguments to pass
        env_vars: Optional dict of environment variables to set
    """
    if getattr(sys, "frozen", False):
        # Frozen mode: import and run directly
        import importlib

        # Resolve main() by trying the module itself first, then its __main__
        # submodule (for packages whose entry point lives in __main__.py).
        # Capture the import error from the primary candidate so we can surface
        # real failures (e.g. a missing dependency in the bundle) instead of
        # masking them as "no main() function".
        main_func = None
        primary_error: Optional[BaseException] = None

        try:
            mod = importlib.import_module(module_path)
            main_func = getattr(mod, "main", None)
        except ImportError as exc:
            primary_error = exc

        if main_func is None and primary_error is None:
            try:
                submod = importlib.import_module(f"{module_path}.__main__")
                main_func = getattr(submod, "main", None)
            except ImportError:
                # Module imported fine but has no __main__ submodule; we'll
                # fall through to the AttributeError below.
                pass

        if main_func is None:
            if primary_error is not None:
                raise ImportError(
                    f"Failed to import {module_path} in frozen build: {primary_error}"
                ) from primary_error
            raise AttributeError(f"Module {module_path} has no main() function")

        # args_list[0] is the program name (sys.argv[0]); rest are real args
        original_argv = sys.argv
        original_env = {}
        sys.argv = args_list

        if env_vars:
            for key, value in env_vars.items():
                original_env[key] = os.environ.get(key)
                os.environ[key] = value

        try:
            exit_code = main_func()
            if exit_code and exit_code != 0:
                sys.exit(exit_code)
        finally:
            sys.argv = original_argv
            for key, orig_value in original_env.items():
                if orig_value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = orig_value
    else:
        # Normal Python: spawn subprocess.
        # args_list[0] is the program-name slot (sys.argv[0] equivalent) used in
        # frozen mode; skip it here because the subprocess already has a real argv[0].
        real_args = args_list[1:] if args_list else []
        cmd = [sys.executable, "-m", module_path] + real_args
        result = subprocess.run(cmd, env=env_vars)
        if result.returncode != 0:
            sys.exit(result.returncode)


def get_current_version():
    """Get the current installed version of vicoa"""
    try:
        from vicoa import __version__

        return __version__
    except Exception:
        return "unknown"


def _parse_version(version: str) -> tuple[int, ...]:
    """Parse the numeric release portion of a version into a comparable tuple.

    Handles plain semver (``1.5.4``) and trims any pre-release/build suffix
    (``1.5.4-darwin-arm64`` -> ``(1, 5, 4)``). Returns an empty tuple when the
    string has no leading numeric components so callers can detect failure.
    """
    release = version.strip().lstrip("v").split("-", 1)[0].split("+", 1)[0]
    parts: list[int] = []
    for piece in release.split("."):
        if not piece.isdigit():
            break
        parts.append(int(piece))
    return tuple(parts)


def check_for_updates():
    """Check the npm registry for a newer version of vicoa.

    Vicoa is distributed via the ``@vicoa/cli`` npm package, so we compare
    against the npm ``latest`` dist-tag rather than PyPI.

    Banner output goes to stderr so it never pollutes structured stdout
    (e.g. ``vicoa ls --json | jq …`` was breaking on the leading banner).
    """
    try:
        # The scoped package's slash must be percent-encoded for the
        # single-version registry endpoint.
        response = requests.get(
            "https://registry.npmjs.org/@vicoa%2Fcli/latest", timeout=2
        )
        latest_version = response.json()["version"]
        current_version = get_current_version()

        latest_parsed = _parse_version(latest_version)
        current_parsed = _parse_version(current_version)

        # Only nudge when the registry version is strictly newer — never on a
        # downgrade or an unparseable/dev version.
        if (
            current_version != "unknown"
            and latest_parsed
            and current_parsed
            and latest_parsed > current_parsed
        ):
            print(
                f"\n✨ New version available: {current_version} → {latest_version}",
                file=sys.stderr,
            )
            print("   Run: npm install -g @vicoa/cli@latest", file=sys.stderr)
            print("   Keep vicoa up-to-date for the best experience\n", file=sys.stderr)
    except Exception:
        pass


def get_credentials_path():
    """Get the path to the credentials file"""
    config_dir = Path.home() / ".vicoa"
    return config_dir / "credentials.json"


def get_user_config_path():
    """Get the path to the user config file (for non-secret settings)."""
    config_dir = Path.home() / ".vicoa"
    return config_dir / "config.json"


def load_user_config() -> dict:
    """Load user config from ~/.vicoa/config.json if present."""
    path = get_user_config_path()
    if not path.exists():
        return {}
    try:
        with open(path, "r") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
            return {}
    except Exception:
        return {}


def save_user_config(new_data: dict):
    """Persist user config to ~/.vicoa/config.json, merging with existing."""
    path = get_user_config_path()
    path.parent.mkdir(mode=0o700, exist_ok=True)
    existing = load_user_config()
    existing.update(new_data)
    with open(path, "w") as f:
        json.dump(existing, f, indent=2)
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass


def load_stored_api_key(base_url: str | None = None):
    """Load the stored API key for ``base_url`` (the deployment/profile).

    Delegates to :mod:`vicoa.credentials_state`, which keeps one key per
    normalized base URL and transparently migrates the legacy single-key file.
    A ``None`` base_url resolves the default deployment's entry.
    """
    return credentials_state.load_api_key(base_url)


def save_api_key(api_key, base_url: str | None = None):
    """Save the API key as the credential for ``base_url``.

    Keyed by the agent-server base URL the daemon authenticates against (not the
    auth URL where the key is minted), so a self-host login never clobbers the
    cloud token.
    """
    credentials_state.save_api_key(base_url, api_key)


class AuthHTTPServer(HTTPServer):
    """Custom HTTP server with attributes for authentication"""

    api_key: Optional[str]
    state: Optional[str]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.api_key = None
        self.state = None


class AuthCallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler for the OAuth callback"""

    def log_message(self, format, *args):
        # Suppress default logging
        pass

    def do_GET(self):
        # Parse query parameters
        if "?" in self.path:
            query_string = self.path.split("?", 1)[1]
            params = urllib.parse.parse_qs(query_string)

            # Verify state parameter
            server: AuthHTTPServer = self.server  # type: ignore
            if "state" in params and params["state"][0] == server.state:
                if "api_key" in params:
                    api_key = params["api_key"][0]
                    # Store the API key in the server instance
                    server.api_key = api_key
                    print("\n✓ Vicoa CLI connected!")

                    # Send success response with nice styling
                    self.send_response(200)
                    self.send_header("Content-type", "text/html")
                    self.end_headers()
                    success_page = b"""
                    <html>
                    <head>
                        <title>Vicoa CLI - Connected</title>
                        <meta http-equiv="refresh" content="1;url=__VICOA_DASHBOARD_URL__">
                        <style>
                            body {
                                margin: 0;
                                padding: 0;
                                min-height: 100vh;
                                background: linear-gradient(135deg, #1a1618 0%, #2a1f3d 100%);
                                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                                display: flex;
                                align-items: center;
                                justify-content: center;
                                color: #fef3c7;
                            }
                            .card {
                                background: rgba(26, 22, 24, 0.8);
                                border: 1px solid rgba(245, 158, 11, 0.2);
                                border-radius: 12px;
                                padding: 48px;
                                text-align: center;
                                box-shadow: 0 20px 40px rgba(0, 0, 0, 0.3),
                                           0 0 60px rgba(245, 158, 11, 0.1);
                                max-width: 400px;
                                animation: fadeIn 0.5s ease-out;
                            }
                            @keyframes fadeIn {
                                from { opacity: 0; transform: translateY(20px); }
                                to { opacity: 1; transform: translateY(0); }
                            }
                            .icon {
                                width: 64px;
                                height: 64px;
                                margin: 0 auto 24px;
                                background: rgba(134, 239, 172, 0.2);
                                border-radius: 50%;
                                display: flex;
                                align-items: center;
                                justify-content: center;
                                animation: scaleIn 0.5s ease-out 0.2s both;
                            }
                            @keyframes scaleIn {
                                from { transform: scale(0); }
                                to { transform: scale(1); }
                            }
                            .checkmark {
                                width: 32px;
                                height: 32px;
                                stroke: #86efac;
                                stroke-width: 3;
                                fill: none;
                                stroke-dasharray: 100;
                                stroke-dashoffset: 100;
                                animation: draw 0.5s ease-out 0.5s forwards;
                            }
                            @keyframes draw {
                                to { stroke-dashoffset: 0; }
                            }
                            h1 {
                                margin: 0 0 16px;
                                font-size: 24px;
                                font-weight: 600;
                                color: #86efac;
                            }
                            p {
                                margin: 0;
                                opacity: 0.8;
                                line-height: 1.5;
                            }
                            .close-hint {
                                margin-top: 24px;
                                font-size: 14px;
                                opacity: 0.6;
                            }
                        </style>
                    </head>
                    <body>
                        <div class="card">
                            <div class="icon">
                                <svg class="checkmark" viewBox="0 0 24 24">
                                    <path d="M20 6L9 17l-5-5" />
                                </svg>
                            </div>
                            <h1>Vicoa CLI Connected</h1>
                            <p>You can now securely remote control your coding agents from your phone.</p>
                            <p class="close-hint">Opening your dashboard in a moment...</p>
                            <p style="margin-top: 20px; font-size: 12px;">
                                If you are not redirected automatically,
                                <a href="__VICOA_DASHBOARD_URL__" style="color: #86efac;">click here</a>.
                            </p>
                        </div>
                        <script>
                            setTimeout(() => {
                                window.location.href = '__VICOA_DASHBOARD_URL__';
                            }, 500);
                        </script>
                    </body>
                    </html>
                    """
                    # Self-hosted installs set VICOA_AUTH_URL, so the
                    # post-login redirect follows their own dashboard.
                    self.wfile.write(
                        success_page.replace(
                            b"__VICOA_DASHBOARD_URL__",
                            f"{DEFAULT_AUTH_URL}/dashboard".encode(),
                        )
                    )
                    # Give the browser time to receive the response
                    self.wfile.flush()
                    return
            else:
                # Invalid or missing state parameter
                self.send_response(403)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write(b"""
                <html>
                <head><title>Vicoa CLI - Authentication Failed</title></head>
                <body style="font-family: sans-serif; text-align: center; padding: 50px;">
                    <h1>Authentication Failed</h1>
                    <p>Invalid authentication state. Please try again.</p>
                </body>
                </html>
                """)
                return

        # Send error response
        self.send_response(400)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(b"""
        <html>
        <head><title>Vicoa CLI - Authentication Failed</title></head>
        <body style="font-family: sans-serif; text-align: center; padding: 50px;">
            <h1>Authentication Failed</h1>
            <p>No API key was received. Please try again.</p>
        </body>
        </html>
        """)


# Real graphical browsers we're willing to auto-launch on Linux/BSD, roughly by
# popularity. We deliberately do NOT include xdg-open / x-www-browser / gio /
# gnome-open here: on a headless server those delegate to a console browser
# (w3m/links/lynx) that blocks on the TTY — the exact failure we're avoiding.
_LINUX_GUI_BROWSERS = (
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
    "firefox",
    "firefox-esr",
    "brave-browser",
    "microsoft-edge",
    "microsoft-edge-stable",
    "opera",
    "vivaldi",
    "vivaldi-stable",
)


def _find_linux_gui_browser() -> str | None:
    """Return the path to a real graphical browser, or None on a headless box.

    Only used on Linux/BSD. We never fall back to the stdlib ``webbrowser``
    module here: on a server it happily launches a terminal browser
    (w3m/links/lynx) that grabs the TTY. We require both a display server and a
    known GUI-browser binary; anything short of that means "headless server,
    just print the URL". Note ``DISPLAY`` alone is not enough — SSH X11
    forwarding and stale tmux environments set it on machines with no browser,
    so the binary probe is the real gate.
    """
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return None
    for name in _LINUX_GUI_BROWSERS:
        path = shutil.which(name)
        if path:
            return path
    return None


def _open_auth_url(url: str) -> None:
    """Best-effort open the sign-in URL, never hijacking the terminal.

    On macOS/Windows the OS opener always routes to the desktop GUI, so we let
    the stdlib handle it. On Linux/BSD we launch a real GUI browser ourselves,
    fully detached (new session, stdio to /dev/null) so that even a misfire can
    never block this TTY. If no GUI browser is found we do nothing and rely on
    the printed URL + paste-key fallback the caller already displays.
    """
    system = platform.system()
    if system in ("Darwin", "Windows"):
        try:
            webbrowser.open(url)
        except Exception:
            pass
        return

    browser = _find_linux_gui_browser()
    if not browser:
        return
    try:
        subprocess.Popen(
            [browser, url],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception:
        pass


def authenticate_via_browser(auth_url="https://vicoa.ai"):
    """Connect Vicoa CLI via browser and return the API key"""

    # Generate a secure random state parameter
    state = secrets.token_urlsafe(32)

    # Start local server to receive the callback
    server = AuthHTTPServer(("127.0.0.1", 0), AuthCallbackHandler)
    server.state = state
    server.api_key = None
    port = server.server_port

    # Construct the auth URL
    auth_base = auth_url.rstrip("/")
    auth_url = f"{auth_base}/cli-auth?port={port}&state={urllib.parse.quote(state)}"

    print("\nOWelcome to Vicoa")
    print("Browser didn't open? Use the url below to sign in:")
    print(f"\n  {auth_url}\n")

    # Run server in a thread
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.daemon = True
    server_thread.start()

    # Open a browser only when a real GUI browser is present, and launch it
    # detached so it can never hijack this TTY. On a headless server this is a
    # no-op and we rely on the printed URL + paste-key fallback above — never a
    # terminal browser (w3m/links/lynx).
    _open_auth_url(auth_url)

    print("After signing in to Vicoa:")
    print("  • Click the 'Connect' button in your browser, or")
    print("  • Generate an API key, copy it, and paste it below")

    print(
        "\nPaste API key here (or wait for browser connection): ",
        end="",
        flush=True,
    )

    import select as _select

    api_key = None
    start_time = time.time()
    timeout = 300

    while time.time() - start_time < timeout:
        # Check if browser authenticated
        if server.api_key:
            print("\n✓ Vicoa CLI connected!")
            api_key = server.api_key
            break

        # Poll stdin without blocking — works in frozen binaries unlike subprocess(sys.executable)
        try:
            readable, _, _ = _select.select([sys.stdin], [], [], 0.1)
            if readable:
                line = sys.stdin.readline().strip()
                if line:
                    print("✓ Token received!")
                    api_key = line
                    break
        except (OSError, ValueError):
            time.sleep(0.1)

    if not api_key:
        print("\n✗ Authentication timed out")

    # If we got the API key, wait a bit for the browser to process
    if api_key and server.api_key:
        time.sleep(1.5)  # Give browser time to receive response and start redirect

    # Shutdown server in a separate thread to avoid deadlock
    def shutdown_server():
        server.shutdown()

    shutdown_thread = threading.Thread(target=shutdown_server)
    shutdown_thread.start()
    shutdown_thread.join(timeout=1)  # Wait max 1 second for shutdown

    server.server_close()

    if api_key:
        return api_key
    else:
        raise Exception("Authentication failed - no API key received")


def ensure_api_key(args):
    """Ensure API key is available, authenticate if needed"""
    # Check if API key is provided via argument
    if hasattr(args, "api_key") and args.api_key:
        return args.api_key

    # Check if API key is in environment variable
    env_api_key = os.environ.get("VICOA_API_KEY")
    if env_api_key:
        return env_api_key

    # Try to load from storage, keyed by the deployment this invocation targets
    # so a self-host key and the cloud key can coexist.
    base_url = getattr(args, "base_url", None) or DEFAULT_API_URL
    api_key = load_stored_api_key(base_url)
    if api_key:
        return api_key

    # Authenticate via browser
    print("Starting Vicoa CLI connection...")
    # Fall back to DEFAULT_AUTH_URL (which honours VICOA_AUTH_URL) rather than a
    # hardcoded vicoa.ai, so a self-hosted CLI reached from a subcommand that
    # never declared --auth-url still opens the right dashboard for login.
    auth_url = getattr(args, "auth_url", None) or DEFAULT_AUTH_URL
    try:
        api_key = authenticate_via_browser(auth_url)
        save_api_key(api_key, base_url)
        print("Vicoa CLI connected. API key saved.")
        return api_key
    except Exception as e:
        raise Exception(f"Authentication failed: {str(e)}")


def cmd_headless(args, unknown_args):
    """Handle the 'headless' subcommand"""
    api_key = ensure_api_key(args)

    # Sync slash commands to backend
    agent_type = getattr(args, "agent", "claude").lower()
    base_url = getattr(args, "base_url", DEFAULT_API_URL)
    sync_user_commands(api_key, base_url, agent_type)

    # Sync project files to backend
    import os

    project_path = os.getcwd()
    sync_project_files_async(api_key, base_url, project_path)

    # Import and run the selected headless module
    import importlib

    module_name = "integrations.headless.claude_code"
    argv_prog = "headless_claude"
    agent_type = getattr(args, "agent", "claude").lower()
    if agent_type == "codex":
        # Native `codex app-server` is the only supported codex backend; the
        # legacy codex-acp adapter is retired. This is the single route every
        # caller reaches codex through — the frozen daemon bundle (which can
        # only invoke exposed subcommands, i.e. `vicoa headless --agent codex`)
        # and dev runs (`python -m vicoa.cli headless`) both land here.
        module_name = "integrations.headless.codex_native"
        argv_prog = "headless_codex_native"
    elif agent_type == "opencode":
        module_name = "integrations.headless.opencode_acp"
        argv_prog = "headless_opencode_acp"
    elif agent_type in GENERIC_ACP_AGENT_CHOICES:
        module_name = "integrations.headless.generic_acp"
        argv_prog = f"headless_{agent_type}"
    elif agent_type in PI_FAMILY_AGENT_CHOICES:
        # Native RPC wrapper shared by pi and omp; `--agent` picks the row in
        # PI_FAMILY_AGENTS. Same single-route posture as codex: the frozen
        # daemon bundle can only invoke exposed subcommands, so both it and a
        # dev `python -m vicoa.cli headless` land here.
        module_name = "integrations.headless.pi_native"
        argv_prog = f"headless_{agent_type}"

    module = importlib.import_module(module_name)
    headless_main = getattr(module, "main")

    # Prepare sys.argv for the headless runner
    original_argv = sys.argv
    new_argv = [argv_prog, "--api-key", api_key]

    if hasattr(args, "base_url") and args.base_url:
        new_argv.extend(["--base-url", args.base_url])

    if hasattr(args, "name") and args.name:
        new_argv.extend(["--name", args.name])

    if hasattr(args, "session_id") and args.session_id:
        new_argv.extend(["--session-id", args.session_id])

    if agent_type == "claude":
        # Claude headless-specific flags
        if hasattr(args, "prompt") and args.prompt:
            new_argv.extend(["--prompt", args.prompt])

        if hasattr(args, "permission_mode") and args.permission_mode:
            new_argv.extend(["--permission-mode", args.permission_mode])

        if hasattr(args, "allowed_tools") and args.allowed_tools:
            new_argv.extend(["--allowed-tools", args.allowed_tools])

        if hasattr(args, "disallowed_tools") and args.disallowed_tools:
            new_argv.extend(["--disallowed-tools", args.disallowed_tools])

        if hasattr(args, "cwd") and args.cwd:
            new_argv.extend(["--cwd", args.cwd])

        if hasattr(args, "enable_thinking") and args.enable_thinking:
            new_argv.append("--enable-thinking")

        if hasattr(args, "debug") and args.debug:
            new_argv.append("--debug")
    else:
        # Native codex + ACP wrappers use project path.
        project_path = getattr(args, "cwd", None) or os.getcwd()
        new_argv.extend(["--project-path", project_path])
        if hasattr(args, "prompt") and args.prompt:
            new_argv.extend(["--prompt", args.prompt])
        if agent_type == "codex":
            # --model / --reasoning-effort / --auth-method are not headless
            # subcommand flags, so they arrive in unknown_args and are
            # appended below. permission_mode IS a known headless flag, so
            # forward it explicitly to codex_native.
            if getattr(args, "permission_mode", None):
                new_argv.extend(["--permission-mode", args.permission_mode])
        if agent_type in GENERIC_ACP_AGENT_CHOICES:
            new_argv.extend(["--agent", agent_type])
            if getattr(args, "permission_mode", None):
                new_argv.extend(["--permission-mode", args.permission_mode])
        if agent_type in PI_FAMILY_AGENT_CHOICES:
            new_argv.extend(["--agent", agent_type])
            if getattr(args, "permission_mode", None):
                new_argv.extend(["--permission-mode", args.permission_mode])
            # --model / --thinking-effort are not `headless` subcommand flags,
            # so they arrive in unknown_args and are appended below.

    # Pass through unknown args to the selected headless runner.
    if unknown_args:
        new_argv.extend(unknown_args)

    try:
        sys.argv = new_argv
        headless_main()
    finally:
        sys.argv = original_argv


def _enable_windows_vt() -> None:
    """Turn on ANSI escape processing for the Windows console; no-op elsewhere.

    Modern terminals (Windows Terminal, PowerShell 7) enable this already, but
    legacy conhost does not, so the cursor-movement escapes below would print
    literally. Best-effort: any failure just leaves the console as-is.
    """
    if os.name != "nt":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        STD_OUTPUT_HANDLE = -11
        ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        handle = kernel32.GetStdHandle(STD_OUTPUT_HANDLE)
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(
                handle, mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING
            )
    except Exception:
        pass


def _arrow_yes_no(question: str) -> bool:
    """Arrow-key Yes/No prompt. Returns True for Yes, False for No/cancel."""
    RESET = "\x1b[0m"
    BOLD = "\x1b[1m"
    DIM = "\x1b[2m"
    CYAN = "\x1b[36m"

    options = ["Yes", "No"]

    def _render(selected: int) -> None:
        sys.stdout.write(f"{question}\r\n")
        for i, opt in enumerate(options):
            if i == selected:
                sys.stdout.write(f"{CYAN}{BOLD}> {opt}{RESET}\r\n")
            else:
                sys.stdout.write(f"  {DIM}{opt}{RESET}\r\n")
        sys.stdout.flush()

    def _clear(lines: int) -> None:
        for _ in range(lines):
            sys.stdout.write("\x1b[1A\x1b[2K")
        sys.stdout.flush()

    if not sys.stdin.isatty():
        return False

    selected = 0
    total_lines = 1 + len(options)  # question + options

    # Windows has no termios/tty (they are POSIX-only, and the frozen build
    # ships without them, so importing crashes the process). Read keys through
    # msvcrt instead. This branch must come before any termios import.
    if os.name == "nt":
        import msvcrt

        _enable_windows_vt()
        _render(selected)
        while True:
            ch = msvcrt.getwch()
            # Arrow keys arrive as a two-char sequence: a \x00 or \xe0 prefix
            # then H (up) / P (down). Either arrow just toggles the two options.
            if ch in ("\x00", "\xe0"):
                ch2 = msvcrt.getwch()
                if ch2 in ("H", "P"):
                    selected = 1 - selected
            elif ch in ("\r", "\n"):
                _clear(total_lines)
                return selected == 0
            elif ch == "\x03":  # Ctrl-C
                _clear(total_lines)
                return False
            _clear(total_lines)
            _render(selected)

    import tty
    import termios

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        _render(selected)
        while True:
            ch = sys.stdin.read(1)
            if ch == "\x1b":
                ch2 = sys.stdin.read(1)
                if ch2 == "[":
                    ch3 = sys.stdin.read(1)
                    if ch3 in ("A", "B"):
                        selected = 1 - selected
            elif ch in ("\r", "\n"):
                _clear(total_lines)
                return selected == 0
            elif ch in ("\x03", "\x04"):
                _clear(total_lines)
                return False
            _clear(total_lines)
            _render(selected)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _resolve_local_listener_settings(args):
    """Validate the desktop local-listener flags; None when not requested.

    The nonce arrives via VICOA_LOCAL_NONCE (never argv — process lists leak),
    and the allowed renderer origin via VICOA_LOCAL_ORIGIN.
    """
    local_listener = getattr(args, "local_listener", False)
    local_only = getattr(args, "local_only", False)
    if local_only and not local_listener:
        print("Error: --local-only requires --local-listener.")
        sys.exit(2)
    if not local_listener:
        return None

    local_port = getattr(args, "local_port", None)
    if not local_port:
        print("Error: --local-listener requires --local-port <port>.")
        sys.exit(2)
    nonce = os.environ.get("VICOA_LOCAL_NONCE", "").strip()
    if not nonce:
        print(
            "Error: --local-listener requires the VICOA_LOCAL_NONCE "
            "environment variable (refusing to start an unauthenticated "
            "local listener)."
        )
        sys.exit(2)

    from vicoa.local_server.runner import LocalListenerSettings

    return LocalListenerSettings(
        port=int(local_port),
        nonce=nonce,
        allowed_origin=os.environ.get("VICOA_LOCAL_ORIGIN", "http://localhost:3000"),
        local_only=local_only,
    )


def cmd_machine_daemon(args):
    """Run the machine daemon to handle remote spawn requests."""
    local_settings = _resolve_local_listener_settings(args)

    if local_settings is not None and local_settings.local_only:
        # Local (logged-out) mode is DISABLED: the desktop app is
        # login-required, and no user session data may be created or stored
        # in ~/.vicoa/local_store.db. The previous dispatch is kept below,
        # commented out, until local mode is removed for good.
        print(
            "Error: --local-only (logged-out local mode) is disabled — "
            "sign in and run the daemon with credentials."
        )
        sys.exit(2)
        # Logged-out desktop mode: no credentials, no browser auth, no
        # machine registration / heartbeat / cloud WS / spawn polling — the
        # local server carries everything. The per-base-url daemon state
        # machinery is skipped too: the base URL is this launch's loopback
        # port, so there is no cloud daemon identity to collide with.
        # from vicoa.local_server.runner import run_local_only_daemon
        #
        # try:
        #     run_local_only_daemon(
        #         settings=local_settings,
        #         cli_version=get_current_version(),
        #     )
        # except KeyboardInterrupt:
        #     print("\n[INFO] Daemon stopped by user")
        # return

    base_url = getattr(args, "base_url", DEFAULT_API_URL) or DEFAULT_API_URL
    # Upgrade-path safety: if the state file is still the legacy flat shape,
    # migrate it under the right URL bucket BEFORE the collision lookup, so
    # a user upgrading while their old daemon is running (or who just stopped
    # it before upgrading) sees us as the same machine on the backend.
    migrate_legacy_flat_state(base_url)
    existing_pid = find_running_daemon_pid(base_url)
    if existing_pid is not None and existing_pid != os.getpid():
        if getattr(args, "takeover", False):
            # Non-interactive replacement (desktop shell spawn): never prompt.
            # Same stop mechanics as the interactive path below —
            # stop_background_daemon does SIGTERM, waits, falls back to
            # SIGKILL, and clears the persisted PID (machine_id survives so
            # we re-register as the same machine).
            print(
                f"[daemon] takeover: stopping existing daemon "
                f"(pid {existing_pid}) for {base_url}"
            )
            stopped, message = stop_background_daemon(base_url=base_url)
            if not stopped:
                print(f"Failed to stop existing daemon: {message}")
                sys.exit(1)
            print(
                f"[daemon] takeover: stopped daemon pid {existing_pid}; "
                "starting replacement"
            )
        else:
            confirmed = _arrow_yes_no(
                f"A Vicoa daemon is already running for {base_url}. "
                "Stop it and start a new one?"
            )
            if not confirmed:
                print(
                    f"Run 'vicoa stop daemon --base-url {base_url}' "
                    "to stop it manually."
                )
                return
            stopped, message = stop_background_daemon(base_url=base_url)
            if not stopped:
                print(f"Failed to stop existing daemon: {message}")
                sys.exit(1)
            print("Existing daemon stopped.")

    api_key = ensure_api_key(args)

    poll_interval = getattr(args, "poll_interval", 5) or 5
    heartbeat_interval = getattr(args, "heartbeat_interval", 30) or 30

    try:
        if local_settings is not None:
            # Credentialed daemon plus the desktop local listener (RPC/pty
            # served on 127.0.0.1; chat still flows through the cloud).
            from vicoa.local_server.runner import run_daemon_with_local_listener

            run_daemon_with_local_listener(
                api_key=api_key,
                base_url=args.base_url,
                settings=local_settings,
                poll_interval=poll_interval,
                heartbeat_interval=heartbeat_interval,
                cli_version=get_current_version(),
            )
        else:
            run_daemon(
                api_key=api_key,
                base_url=args.base_url,
                poll_interval=poll_interval,
                heartbeat_interval=heartbeat_interval,
                cli_version=get_current_version(),
            )
    except KeyboardInterrupt:
        print("\n[INFO] Daemon stopped by user")


def cmd_ls(args) -> None:
    base_url = getattr(args, "base_url", None) or DEFAULT_API_URL
    api_key = load_stored_api_key(base_url) or os.environ.get("VICOA_API_KEY")
    _cmd_ls(args, api_key=api_key)


def _daemon_launch_directory(args) -> str:
    explicit_project_path = getattr(args, "project_path", None)
    explicit_cwd = getattr(args, "cwd", None)
    launch_directory = explicit_project_path or explicit_cwd or os.getcwd()
    return os.path.abspath(os.path.expanduser(launch_directory))


def maybe_start_machine_daemon(args, api_key: str) -> None:
    """Start the machine daemon in the background unless disabled or already running."""
    if getattr(args, "no_daemon", False):
        return

    base_url = getattr(args, "base_url", DEFAULT_API_URL)
    launch_directory = _daemon_launch_directory(args)

    result: DaemonStartResult | None = None
    try:
        result = ensure_background_daemon_running(
            api_key=api_key,
            base_url=base_url,
            cwd=launch_directory,
        )
    except Exception:
        # Daemon autostart should never block interactive CLI usage.
        pass

    if result is DaemonStartResult.AUTH_INVALID:
        # The credential is dead (revoked key / deleted account) and re-auth
        # hasn't happened. Exit before launching the agent — otherwise the
        # wrapper would register an agent instance, FK-violate on
        # `user_agents_user_id_fkey`, get 401 from PR #45's handler, and tear
        # the link down anyway. Skipping that round-trip keeps the backend
        # logs clean and avoids a half-started agent the user didn't ask for.
        print("Vicoa is disconnected (credential expired), run vicoa --auth")
        sys.exit(1)


def update_machine_recent_directories(args, api_key: str) -> None:
    """Register the current CLI directory so it appears in machine recent directories."""
    base_url = getattr(args, "base_url", DEFAULT_API_URL) or DEFAULT_API_URL
    launch_directory = _daemon_launch_directory(args)
    display_directory = get_project_path(launch_directory)

    try:
        machine_id = read_machine_id(base_url)
        if machine_id is None:
            # No daemon has registered for this base_url yet — nothing to link.
            return

        from vicoa.sdk.client import VicoaClient

        with VicoaClient(api_key=api_key, base_url=base_url) as client:
            client.update_machine_recent_directory(
                machine_id,
                display_directory,
                cli_version=get_current_version(),
                python_version=platform.python_version(),
            )
    except Exception:
        # Recent-directory updates should not block CLI startup.
        pass


def update_machine_recent_directories_async(args, api_key: str) -> None:
    """Run recent-directory update in background so command startup is not blocked."""

    thread = threading.Thread(
        target=update_machine_recent_directories,
        args=(args, api_key),
        daemon=True,
        name="vicoa-recent-directories-sync",
    )
    thread.start()


def _macos_major_version() -> Optional[int]:
    """Return the macOS major version (e.g. 14) or None if not on macOS / unparseable."""
    if platform.system() != "Darwin":
        return None
    try:
        return int(platform.mac_ver()[0].split(".")[0])
    except (ValueError, IndexError):
        return None


def _windows_unsupported_message() -> str:
    return (
        "This is not supported on Windows yet.\n"
        "\n"
        "You can still use Vicoa by running the background daemon:\n"
        "\n"
        "    vicoa daemon\n"
        "\n"
        "The daemon connects this machine to your Vicoa account.\n"
        "You can start new coding sessions from Vicoa mobile app or the web dashboard (https://vicoa.ai)\n"
    )


def _old_macos_codex_unsupported_message(mac_version: str) -> str:
    return (
        f"'vicoa codex' isn't supported on macOS {mac_version} yet.\n"
        "\n"
        "Try one of these instead on this machine:\n"
        "    vicoa            # Claude Code\n"
        "    vicoa opencode   # OpenCode\n"
        "\n"
        "Or run the daemon and launch Codex remotely from the web or mobile app:\n"
        "\n"
        "    vicoa daemon\n"
        "\n"
        "The daemon connects this machine to your Vicoa account."
    )


def _check_agent_platform_support(agent: str) -> Optional[str]:
    """Return a user-facing message if `agent` can't run on this platform, else None.

    Rules:
    - Windows: no interactive agent is supported; user should run `vicoa daemon`.
    - macOS < 14 (Sonoma): only `vicoa codex` is blocked (the bundled Codex binary
      requires macOS 14+). Claude and OpenCode still work.
    - macOS 14+ / Linux: everything supported.
    """
    if platform.system() == "Windows":
        return _windows_unsupported_message()

    major = _macos_major_version()
    if major is not None and 0 < major < 14 and agent == "codex":
        return _old_macos_codex_unsupported_message(platform.mac_ver()[0])

    return None


def run_agent_default(args, unknown_args):
    """Run the agent locally without the relay."""
    agent = getattr(args, "agent", "claude").lower()

    unsupported_msg = _check_agent_platform_support(agent)
    if unsupported_msg is not None:
        print()
        print(unsupported_msg)
        print()
        sys.exit(0)

    api_key = ensure_api_key(args)
    update_machine_recent_directories_async(args, api_key)
    maybe_start_machine_daemon(args, api_key)

    # Sync slash commands to backend
    base_url = getattr(args, "base_url", DEFAULT_API_URL)
    sync_user_commands(api_key, base_url, agent)

    # Sync project files to backend
    import os

    project_path = os.getcwd()
    sync_project_files_async(api_key, base_url, project_path)

    # Handle --resume flag: update agent instance status and set as agent_instance_id
    resume_session_id = getattr(args, "resume", None)
    if resume_session_id:
        try:
            from vicoa.sdk.client import VicoaClient

            base_url = getattr(args, "base_url", DEFAULT_API_URL)
            client = VicoaClient(api_key=api_key, base_url=base_url)
            # Update status to ACTIVE when resuming
            client.update_agent_instance_status(resume_session_id, "ACTIVE")
            # Set as agent_instance_id so it's used for the session
            args.agent_instance_id = resume_session_id

            # Add --resume flag to unknown_args so it's passed to the agent CLI
            unknown_args = list(unknown_args) if unknown_args else []
            unknown_args.extend(["--resume", resume_session_id])
        except Exception as e:
            print(f"Warning: Failed to update session status: {e}")

    env = os.environ.copy()
    env["VICOA_API_KEY"] = api_key

    # Reuse base_url from earlier to avoid redundant getattr
    if base_url:
        env["VICOA_API_URL"] = base_url
        env["VICOA_BASE_URL"] = base_url

    agent_instance_id = getattr(args, "agent_instance_id", None)
    if agent_instance_id:
        env["VICOA_AGENT_INSTANCE_ID"] = agent_instance_id

    if getattr(args, "name", None):
        env["VICOA_AGENT_DISPLAY_NAME"] = args.name

    if agent in GENERIC_ACP_AGENT_CHOICES or agent in PI_FAMILY_AGENT_CHOICES:
        # These agents integrate via a headless wrapper only (ACP for the
        # generic set, native RPC for pi/omp); there is no vicoa TUI wrapper
        # for them.
        print(
            f"Terminal (TUI) mode isn't available for '{agent}'. "
            f"Start a session from the Vicoa app or web dashboard, or run:\n"
            f"  vicoa headless --agent {agent}",
            file=sys.stderr,
        )
        sys.exit(1)

    if agent == "codex":
        from vicoa.agents.codex import run_codex

        exit_code = run_codex(args, unknown_args, api_key)
        if exit_code is None:
            exit_code = 0
        if exit_code != 0:
            sys.exit(exit_code)
        return

    if agent == "opencode":
        from vicoa.agents.opencode import run_opencode

        exit_code = run_opencode(args, unknown_args, api_key)
        if exit_code is None:
            exit_code = 0
        if exit_code != 0:
            sys.exit(exit_code)
        return

    # Determine which agent module to run
    if agent == "claude":
        module = "integrations.cli_wrappers.claude_code"
    elif agent == "amp":
        module = "integrations.cli_wrappers.amp.amp"
    else:
        print(f"Error: Unknown agent '{agent}'", file=sys.stderr)
        sys.exit(1)

    # Run the agent module (handles both frozen and normal mode)
    args_list = [agent] + (list(unknown_args) if unknown_args else [])
    run_python_module(module, args_list, env)


def cmd_mcp(args):
    """Handle the 'mcp' subcommand"""
    # Build arguments for the MCP server
    args_list = ["mcp_server"]

    if args.api_key:
        args_list.extend(["--api-key", args.api_key])
    if args.base_url:
        args_list.extend(["--base-url", args.base_url])
    if args.permission_tool:
        args_list.append("--permission-tool")
    if args.git_diff:
        args_list.append("--git-diff")
    if args.agent_instance_id:
        args_list.extend(["--agent-instance-id", args.agent_instance_id])
    if args.disable_tools:
        args_list.append("--disable-tools")

    try:
        run_python_module("servers.mcp.stdio_server", args_list)
    except KeyboardInterrupt:
        print("\n[INFO] MCP server stopped by user")
        sys.exit(0)


def add_runner_arguments(parser: argparse.ArgumentParser) -> None:
    """Arguments shared by both default and terminal subcommands."""

    parser.add_argument(
        "--api-key", help="API key for authentication (uses stored key if not provided)"
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_API_URL,
        help="Base URL of the Vicoa API server",
    )
    parser.add_argument(
        "--auth-url",
        default=DEFAULT_AUTH_URL,
        help="Base URL of the Vicoa frontend for authentication",
    )
    parser.add_argument(
        "--agent",
        choices=AGENT_CHOICES,
        default="claude",
        help="Which AI agent to use (default: claude code)",
    )
    parser.add_argument(
        "--name",
        default=None,
        help=(
            "Name of the agent instance when registering the session "
            "(defaults to the underlying agent name)"
        ),
    )
    parser.add_argument(
        "--agent-instance-id",
        type=str,
        help="Pre-existing agent instance ID to use for this session",
    )
    parser.add_argument(
        "--task",
        metavar="TASK_ID",
        default=None,
        help=(
            "Link this session to a task (full UUID from `vicoa task ls`). To "
            "link or unlink an existing session, use `vicoa session --task`."
        ),
    )
    parser.add_argument(
        "--resume",
        type=str,
        metavar="SESSION_ID",
        help="Resume a previous session by session ID (updates status to ACTIVE)",
    )
    parser.add_argument(
        "--no-daemon",
        action="store_true",
        help="Do not auto-start the background Vicoa daemon for this run",
    )


def add_global_arguments(parser: argparse.ArgumentParser) -> None:
    """Add global arguments that work across all subcommands."""

    parser.add_argument(
        "--auth",
        action="store_true",
        help="Authenticate or re-authenticate with Vicoa",
    )
    parser.add_argument(
        "--reauth",
        action="store_true",
        help="Force re-authentication even if API key exists",
    )
    parser.add_argument(
        "--version", action="store_true", help="Show version information"
    )
    parser.add_argument(
        "--set-default",
        nargs="?",
        const="__USE_AGENT__",
        help=(
            "Set default agent for future runs. Use without a value to use the current --agent, "
            "or pass an agent name (claude|amp|codex)."
        ),
    )
    add_runner_arguments(parser)


def sync_user_commands(api_key: str, base_url: str, agent_type: str = "claude"):
    """Sync the user's slash commands and skills to the backend.

    Claude scans ~/.claude + ./.claude (commands and skills); Codex scans
    ~/.codex/prompts plus the ~/.agents/skills, ~/.codex/skills, and
    ./.agents/skills skill dirs. Agents without a local source scan empty
    and skip the upload.

    Args:
        api_key: Vicoa API key
        base_url: Vicoa API base URL
        agent_type: Agent type ('claude', 'codex', or 'opencode')
    """
    try:
        from integrations.cli_wrappers.claude_code.command_sync import (
            scan_agent_commands,
        )
        from vicoa.sdk.client import VicoaClient

        # Scan for commands
        commands = scan_agent_commands(agent_type)

        if not commands:
            # No commands to sync
            return

        # Sync to backend
        client = VicoaClient(api_key=api_key, base_url=base_url)
        client.sync_commands(agent_type=agent_type, commands=commands)
    except Exception:
        # Silently fail - don't block agent startup if command sync fails
        pass


# File syncing is now handled by vicoa.file_sync module
# (scan_project_files and sync_project_files have been moved there)


def main():
    """Main entry point with subcommand support"""
    # Create main parser
    parser = argparse.ArgumentParser(
        description="Vicoa - AI Agent Dashboard and Tools",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start Claude chat (default)
  vicoa
  vicoa --api-key YOUR_API_KEY

  # Start Codex chat
  vicoa codex
  vicoa codex --api-key YOUR_API_KEY

  # Start OpenCode chat
  vicoa opencode
  vicoa opencode --api-key YOUR_API_KEY

  # Start Amp chat
  vicoa --agent=amp
  vicoa --agent=amp --api-key YOUR_API_KEY

  # Resume a previous session
  vicoa --resume SESSION_ID
  vicoa codex --resume SESSION_ID

  # Start headless Claude (controlled via web dashboard)
  vicoa headless
  vicoa headless --prompt "Help me debug this codebase"
  vicoa headless --permission-mode acceptEdits --allowed-tools Read,Write,Bash

  # Run MCP stdio server
  vicoa mcp
  vicoa mcp --git-diff

  # Stop the local background connection
  vicoa stop
  vicoa disconnect

  # Authenticate
  vicoa --auth

  # Show version
  vicoa --version

  # Set default agent for future runs
  vicoa --set-default codex
  # or equivalently
  vicoa --agent codex --set-default
        """,
    )

    # Add global arguments
    add_global_arguments(parser)

    # Create subparsers
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # 'mcp' subcommand
    mcp_parser = subparsers.add_parser("mcp", help="Run MCP stdio server")
    mcp_parser.add_argument(
        "--permission-tool",
        action="store_true",
        help="Enable Claude Code permission prompt tool",
    )
    mcp_parser.add_argument(
        "--git-diff",
        action="store_true",
        help="Enable git diff capture for log_step and ask_question",
    )
    mcp_parser.add_argument(
        "--agent-instance-id",
        type=str,
        help="Pre-existing agent instance ID to use for this session",
    )
    mcp_parser.add_argument(
        "--api-key",
        type=str,
        help="API key to use for the MCP server",
    )
    mcp_parser.add_argument(
        "--disable-tools",
        action="store_true",
        help="Disable all tools except the permission tool",
    )

    # 'headless' subcommand
    headless_parser = subparsers.add_parser(
        "headless",
        help="Run agent in headless mode (controlled via web dashboard)",
    )
    # Add the same global arguments to headless subcommand
    headless_parser.add_argument(
        "--api-key", help="API key for authentication (uses stored key if not provided)"
    )
    headless_parser.add_argument(
        "--base-url",
        default=DEFAULT_API_URL,
        help="Base URL of the Vicoa API server",
    )
    headless_parser.add_argument(
        "--auth-url",
        default=DEFAULT_AUTH_URL,
        help="Base URL of the Vicoa frontend for authentication",
    )
    headless_parser.add_argument(
        "--agent",
        choices=AGENT_CHOICES,
        default="claude",
        help="Which AI agent to use (default: claude code)",
    )
    headless_parser.add_argument(
        "--prompt",
        default=None,
        help="Optional initial prompt to POST as the first user message. "
        "When omitted, the session starts blank and waits for user input.",
    )
    headless_parser.add_argument(
        "--permission-mode",
        # No static choices: valid modes are per-agent (Claude SDK modes,
        # ACP session modes for cursor/gemini/copilot/kimi). The daemon
        # validates against the catalog before spawning; the wrapper
        # validates live against the agent's advertised modes.
        help="Permission mode for the selected agent (e.g. Claude: default/"
        "acceptEdits/plan/bypassPermissions/auto; ACP agents: their mode ids)",
    )
    headless_parser.add_argument(
        "--allowed-tools",
        type=str,
        help="Comma-separated list of allowed tools (e.g., 'Read,Write,Bash')",
    )
    headless_parser.add_argument(
        "--disallowed-tools",
        type=str,
        help="Comma-separated list of disallowed tools",
    )
    headless_parser.add_argument(
        "--cwd",
        type=str,
        help="Working directory for headless Claude (defaults to current directory)",
    )
    headless_parser.add_argument(
        "--enable-thinking",
        action="store_true",
        help="Enable thinking mode (sets MAX_THINKING_TOKENS=1024)",
    )
    headless_parser.add_argument(
        "--session-id",
        type=str,
        help="Session ID for the headless agent instance",
    )
    headless_parser.add_argument(
        "--debug",
        action="store_true",
        help=(
            "Enable DEBUG logging in the headless session log "
            "(also honors VICOA_DEBUG=1 env var)."
        ),
    )

    # 'daemon' subcommand
    daemon_parser = subparsers.add_parser(
        "daemon",
        help="Run a background daemon that listens for remote session requests",
    )
    daemon_parser.add_argument(
        "--api-key", help="API key for authentication (uses stored key if not provided)"
    )
    daemon_parser.add_argument(
        "--base-url",
        default=DEFAULT_API_URL,
        help="Base URL of the Vicoa API server",
    )
    daemon_parser.add_argument(
        "--auth-url",
        default=DEFAULT_AUTH_URL,
        help="Base URL of the Vicoa frontend for authentication",
    )
    daemon_parser.add_argument(
        "--poll-interval",
        type=int,
        default=5,
        help="Seconds between polling the server for new session requests (default: 5)",
    )
    daemon_parser.add_argument(
        "--heartbeat-interval",
        type=int,
        default=30,
        help="Seconds between daemon heartbeat updates (default: 30)",
    )
    daemon_parser.add_argument(
        "--takeover",
        action="store_true",
        help=(
            "If a daemon is already running for the same base URL, stop it "
            "non-interactively and start this one in its place (used by the "
            "desktop shell, which cannot answer prompts)"
        ),
    )
    daemon_parser.add_argument(
        "--local-listener",
        action="store_true",
        help=(
            "Serve the desktop app's local WebSocket/REST endpoint on "
            "127.0.0.1 (requires --local-port and the VICOA_LOCAL_NONCE "
            "environment variable; renderer origin via VICOA_LOCAL_ORIGIN)"
        ),
    )
    daemon_parser.add_argument(
        "--local-port",
        type=int,
        default=None,
        help="Loopback port for --local-listener (chosen by the desktop shell)",
    )
    daemon_parser.add_argument(
        "--local-only",
        action="store_true",
        help=(
            "Start without credentials: skip cloud registration/heartbeat/"
            "WebSocket entirely and serve sessions from the local store "
            "(desktop logged-out mode; requires --local-listener)"
        ),
    )

    # 'ls' subcommand — read-only enumeration of active sessions
    ls_parser = subparsers.add_parser(
        "ls",
        help="List active vicoa agent instances on this machine",
    )
    ls_parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON instead of the table",
    )

    # 'stop' subcommand — daemon / sessions / all, all with confirmation
    stop_parser = subparsers.add_parser(
        "stop",
        help="Stop daemon, sessions, or both (prompts for confirmation)",
    )
    stop_parser.add_argument(
        "target",
        nargs="?",
        default="daemon",
        help=(
            "What to stop: 'daemon' (default), 'sessions', 'all', "
            "or a session ID / 8-char prefix from `vicoa ls`."
        ),
    )
    stop_parser.add_argument(
        "--agent",
        choices=AGENT_CHOICES,
        help="When target=sessions/all, only stop sessions of this agent type",
    )
    stop_parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Skip the confirmation prompt",
    )
    stop_parser.add_argument(
        "--base-url",
        default=DEFAULT_API_URL,
        help=(
            "Only stop the daemon for this base URL. "
            "Without it, `stop daemon` stops every running daemon."
        ),
    )

    # 'disconnect' alias — daemon-only stop, kept for backwards compat
    subparsers.add_parser(
        "disconnect",
        help="Alias for `vicoa stop daemon`",
    )

    # 'task' subcommand — manage the user's task backlog. Primary consumer is a
    # running agent (`vicoa task create ...`), so every leaf accepts --json.
    task_parser = subparsers.add_parser(
        "task",
        help="List, read, create, update, or delete tasks",
    )
    task_sub = task_parser.add_subparsers(dest="task_command")

    # Auth/output flags shared by every task subcommand (argparse parent so they
    # work after the leaf verb, e.g. `vicoa task list --json`).
    task_common = argparse.ArgumentParser(add_help=False)
    task_common.add_argument(
        "--api-key",
        help="API key (defaults to VICOA_API_KEY or the stored credential)",
    )
    task_common.add_argument(
        "--base-url",
        default=DEFAULT_API_URL,
        help="Base URL of the Vicoa API server",
    )
    task_common.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON instead of a table",
    )

    task_ls = task_sub.add_parser("ls", parents=[task_common], help="List tasks")
    task_ls.add_argument(
        "--project", metavar="PROJECT_ID", help="Only tasks in this project"
    )
    task_ls.add_argument(
        "--status", choices=TASK_STATUSES, help="Only tasks with this status"
    )
    task_ls.add_argument(
        "--priority", choices=TASK_PRIORITIES, help="Only tasks with this priority"
    )

    task_get = task_sub.add_parser(
        "get", parents=[task_common], help="Show one task's full details"
    )
    task_get.add_argument("task_id", help="Task id (full UUID)")

    task_create = task_sub.add_parser(
        "create", parents=[task_common], help="Create a task"
    )
    task_create.add_argument("title", help="Task title")
    task_create.add_argument("--description", help="Longer description")
    task_create.add_argument(
        "--project",
        metavar="PROJECT_ID",
        help="Project id to file under (omit to use your Inbox)",
    )
    task_create.add_argument(
        "--status", choices=TASK_STATUSES, help="Initial status (default: backlog)"
    )
    task_create.add_argument(
        "--priority", choices=TASK_PRIORITIES, help="Priority (default: none)"
    )
    task_create.add_argument(
        "--parent", metavar="TASK_ID", help="Parent task id (creates a subtask)"
    )
    task_create.add_argument(
        "--start", metavar="ISO8601", help="Start date, e.g. 2026-08-01"
    )
    task_create.add_argument(
        "--due", metavar="ISO8601", help="Due date, e.g. 2026-08-01T17:00:00Z"
    )

    task_update = task_sub.add_parser(
        "update",
        parents=[task_common],
        help="Update a task (only the flags you pass change)",
    )
    task_update.add_argument("task_id", help="Task id (full UUID)")
    task_update.add_argument("--title", help="New title")
    task_update.add_argument("--description", help="New description")
    task_update.add_argument(
        "--project", metavar="PROJECT_ID", help="Move to this project"
    )
    task_update.add_argument("--status", choices=TASK_STATUSES, help="New status")
    task_update.add_argument("--priority", choices=TASK_PRIORITIES, help="New priority")
    task_update.add_argument("--parent", metavar="TASK_ID", help="New parent task id")
    task_update.add_argument("--start", metavar="ISO8601", help="New start date")
    task_update.add_argument("--due", metavar="ISO8601", help="New due date")

    task_delete = task_sub.add_parser(
        "delete", parents=[task_common], help="Delete a task"
    )
    task_delete.add_argument("task_id", help="Task id (full UUID)")
    task_delete.add_argument(
        "-y", "--yes", action="store_true", help="Skip the confirmation prompt"
    )

    # 'automation' subcommand — registered from its command module so cli.py
    # stays lean (parser + handlers + builders all live in
    # commands/automation.py).
    add_automation_subparser(subparsers)

    # 'plugin' subcommand — manage machine-local plugins (themes, sidebar,
    # composer). Registered from its command module (commands/plugin.py); these
    # operate on ~/.vicoa/plugins directly, not over the network.
    add_plugin_subparser(subparsers)

    # 'session' subcommand — inspect the user's agent sessions from the backend.
    # Distinct from `vicoa ls` (local processes only): this spans every machine
    # and finished sessions, and can print a session's message transcript.
    session_parser = subparsers.add_parser(
        "session",
        help="List and inspect your agent sessions (across machines, with transcripts)",
    )
    session_sub = session_parser.add_subparsers(dest="session_command")

    # Auth/output flags shared by every session subcommand (argparse parent so
    # they work after the leaf verb, e.g. `vicoa session ls --json`).
    session_common = argparse.ArgumentParser(add_help=False)
    session_common.add_argument(
        "--api-key",
        help="API key (defaults to VICOA_API_KEY or the stored credential)",
    )
    session_common.add_argument(
        "--base-url",
        default=DEFAULT_API_URL,
        help="Base URL of the Vicoa API server",
    )
    session_common.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON instead of a table",
    )

    # Agents that can be spawned map to catalog ids (excludes 'amp', which the
    # spawn endpoint's catalog doesn't cover). Generic ACP agents are included.
    spawn_agent_choices = [
        "claude",
        "codex",
        "opencode",
        *GENERIC_ACP_AGENT_CHOICES,
        *PI_FAMILY_AGENT_CHOICES,
    ]
    session_start = session_sub.add_parser(
        "start",
        parents=[session_common],
        help="Start a new session on a machine (like the desktop 'New Session')",
    )
    session_start.add_argument(
        "--machine",
        metavar="ID|NAME",
        help="Target machine: id, or a display-name/hostname substring "
        "(`--list-machines` to see them). Defaults to this host's daemon.",
    )
    session_start.add_argument(
        "--dir",
        metavar="PATH",
        help="Directory on the target machine to start the session in",
    )
    session_start.add_argument(
        "--allow-offline",
        action="store_true",
        dest="allow_offline",
        help="Queue the request even if the target daemon looks offline "
        "(it runs when the daemon next reconnects)",
    )
    session_start.add_argument(
        "--agent",
        choices=spawn_agent_choices,
        default=None,
        help="Agent to run (default: claude); also filters --list-models",
    )
    session_start.add_argument(
        "--model",
        help="Model slug (`--list-models` to see options per agent)",
    )
    session_start.add_argument(
        "--effort",
        help="Reasoning effort — claude thinking_effort / codex reasoning_effort",
    )
    session_start.add_argument(
        "--permission-mode",
        dest="permission_mode",
        help="Permission mode (claude/codex/ACP agents)",
    )
    session_start.add_argument(
        "--opencode-mode",
        dest="opencode_mode",
        help="OpenCode agent mode (build|plan)",
    )
    session_start.add_argument(
        "--prompt",
        help="Optional first user message; omit to start the session blank",
    )
    session_start.add_argument("--name", help="Name for the new session")
    session_start.add_argument(
        "--task",
        metavar="TASK_ID",
        help="Link the new session to this task (full UUID from `vicoa task ls`)",
    )
    session_start.add_argument(
        "--wait",
        action="store_true",
        help="Poll until the session leaves STARTING (needs the daemon online)",
    )
    session_start.add_argument(
        "--wait-timeout",
        dest="wait_timeout",
        type=float,
        default=60.0,
        metavar="SECS",
        help="Seconds to wait with --wait (default 60)",
    )
    session_start.add_argument(
        "--list-machines",
        action="store_true",
        dest="list_machines",
        help="List your registered machines and exit",
    )
    session_start.add_argument(
        "--list-models",
        action="store_true",
        dest="list_models",
        help="List agents/models/efforts/modes (optionally filtered by --agent) and exit",
    )

    session_ls = session_sub.add_parser(
        "ls", parents=[session_common], help="List your agent sessions"
    )
    session_ls.add_argument(
        "--active",
        action="store_true",
        help="Only sessions that are still running",
    )
    session_ls.add_argument(
        "--rate-limited",
        action="store_true",
        dest="rate_limited",
        help="Only sessions currently blocked by a rate limit (adds a RESET column)",
    )
    session_ls.add_argument(
        "--limit",
        type=int,
        default=50,
        metavar="N",
        help="Max sessions to list (1-100, default 50)",
    )

    session_get = session_sub.add_parser(
        "get",
        parents=[session_common],
        help="Show a session's details and message transcript",
    )
    session_get.add_argument(
        "session_id",
        help="Session id or 8-char prefix (from `vicoa ls` / `vicoa session ls`)",
    )
    session_get.add_argument(
        "--limit",
        type=int,
        default=50,
        metavar="N",
        help="Number of most-recent messages to show (default 50; ignored with --all)",
    )
    session_get.add_argument(
        "--all",
        action="store_true",
        dest="all_messages",
        help="Show the full transcript instead of the most-recent --limit",
    )
    # Transcript verbosity — all opt-in; the default view is a clean chat log
    # (tool names shown, but no timestamps, emails, control messages, or tool
    # payloads). Tool-use lines themselves always appear.
    session_get.add_argument(
        "--timestamps",
        action="store_true",
        help="Show a timestamp on each message",
    )
    session_get.add_argument(
        "--emails",
        action="store_true",
        help="Show the sender's email on user messages",
    )
    session_get.add_argument(
        "--control",
        action="store_true",
        dest="show_control",
        help="Include in-band control messages (hidden by default)",
    )
    session_get.add_argument(
        "--tool-content",
        action="store_true",
        dest="tool_content",
        help="Include tool-use payloads/diffs (hidden by default; names always show)",
    )
    session_get.add_argument(
        "--full",
        action="store_true",
        help="Show everything: timestamps, emails, control messages, tool payloads",
    )
    session_get.add_argument(
        "--role",
        choices=["user", "agent"],
        help=(
            "Show only messages from this sender (default: both). "
            "--limit counts all senders before this filter, so pair with --all"
        ),
    )

    session_update = session_sub.add_parser(
        "update",
        parents=[session_common],
        help="Set a session's title and/or link it to a task",
    )
    session_update.add_argument(
        "session_id",
        help="Session id or 8-char prefix (from `vicoa session ls`)",
    )
    session_update.add_argument(
        "--title", help="New session title (renames the session)"
    )
    session_update.add_argument(
        "--task",
        metavar="TASK_ID",
        help="Link the session to this task (full UUID from `vicoa task ls`)",
    )
    session_update.add_argument(
        "--unlink-task",
        action="store_true",
        help="Clear the session's task link",
    )

    session_message = session_sub.add_parser(
        "message",
        parents=[session_common],
        help="Send a message into a session (delivered to the running agent)",
    )
    session_message.add_argument(
        "session_id",
        help="Session id or 8-char prefix (from `vicoa session ls`)",
    )
    session_message.add_argument(
        "text",
        help="Message text to send to the agent",
    )

    session_continue = session_sub.add_parser(
        "continue",
        parents=[session_common],
        help="Send 'continue' to a session (e.g. after a rate-limit window resets)",
    )
    session_continue.add_argument(
        "session_id",
        help="Session id or 8-char prefix (from `vicoa session ls`)",
    )

    # 'claude' subcommand
    claude_parser = subparsers.add_parser(
        "claude",
        help="Run Claude Code agent",
    )
    add_runner_arguments(claude_parser)

    # 'codex' subcommand
    codex_parser = subparsers.add_parser(
        "codex",
        help="Run Codex agent",
    )
    add_runner_arguments(codex_parser)

    # 'opencode' subcommand
    opencode_parser = subparsers.add_parser(
        "opencode",
        help="Run OpenCode agent",
    )
    add_runner_arguments(opencode_parser)
    opencode_parser.add_argument(
        "--model",
        help="Model override (e.g., 'anthropic/claude-sonnet-4')",
    )
    opencode_parser.add_argument(
        "--project-path",
        help="Project directory path (defaults to current directory)",
    )
    opencode_parser.add_argument(
        "--upgrade",
        action="store_true",
        help="Clear the cached Vicoa plugin so OpenCode re-fetches the latest version on next run",
    )

    # Parse arguments
    args, unknown_args = parser.parse_known_args()

    # Handle setting default agent before any further processing
    if getattr(args, "set_default", None) is not None:
        desired: str
        used_paired_form = args.set_default == "__USE_AGENT__"
        if used_paired_form:
            desired = getattr(args, "agent", "claude").lower()
        else:
            desired = str(args.set_default).lower()
        if desired not in AGENT_CHOICES:
            print(
                f"Invalid agent '{desired}'. Valid options: {', '.join(AGENT_CHOICES)}"
            )
            sys.exit(2)
        save_user_config({"default_agent": desired})
        print(f"✓ Default agent set to '{desired}'.")
        # Paired form (--agent X --set-default) continues to launch the agent
        # Standalone form (--set-default X) exits immediately
        if not used_paired_form:
            sys.exit(0)

    # Handle version flag
    if args.version:
        print(f"vicoa version {get_current_version()}")
        sys.exit(0)

    # Handle auth flag
    if args.auth or args.reauth:
        try:
            if args.reauth:
                print("Reconnecting Vicoa CLI...")
            else:
                print("Starting Vicoa CLI connection...")
            api_key = authenticate_via_browser(args.auth_url)
            save_api_key(api_key, getattr(args, "base_url", None) or DEFAULT_API_URL)
            print("Vicoa CLI connected. API key saved.")
            sys.exit(0)
        except Exception as e:
            print(f"Authentication failed: {str(e)}")
            sys.exit(1)

    # If user did not explicitly specify --agent, honor stored default
    provided_agent_flag = any(
        a == "--agent" or a.startswith("--agent=") for a in sys.argv[1:]
    )
    if not provided_agent_flag:
        cfg = load_user_config()
        default_agent = cfg.get("default_agent")
        if isinstance(default_agent, str) and default_agent in AGENT_CHOICES:
            args.agent = default_agent

    if args.command == "claude":
        args.agent = "claude"

    if args.command == "codex":
        args.agent = "codex"

    if args.command == "opencode":
        args.agent = "opencode"

    # Check for updates
    check_for_updates()

    # Handle subcommands
    if args.command == "mcp":
        cmd_mcp(args)
    elif args.command == "headless":
        cmd_headless(args, unknown_args)
    elif args.command == "daemon":
        cmd_machine_daemon(args)
    elif args.command == "ls":
        cmd_ls(args)
    elif args.command == "stop":
        cmd_stop(args)
    elif args.command == "disconnect":
        # Daemon-only alias for backwards compat with the pre-subcommand
        # `vicoa stop` / `vicoa disconnect` behavior.
        args.target = "daemon"
        args.agent = None
        args.yes = False
        cmd_stop(args)
    elif args.command == "task":
        sys.exit(run_task_command(args))
    elif args.command == "automation":
        sys.exit(run_automation_command(args))
    elif args.command == "session":
        sys.exit(run_session_command(args))
    elif args.command == "plugin":
        sys.exit(run_plugin_command(args))
    elif args.command in {"claude", "codex", "opencode"}:
        run_agent_default(args, unknown_args)
    else:
        # On Windows, the interactive agent is unsupported; run daemon instead.
        if platform.system() == "Windows":
            cmd_machine_daemon(args)
            return
        # Default behavior: run agent locally without relay
        run_agent_default(args, unknown_args)


if __name__ == "__main__":
    main()
