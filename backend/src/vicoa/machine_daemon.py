"""Background daemon that keeps a Vicoa CLI machine online for remote sessions."""

from __future__ import annotations

import base64
import enum
import logging
import os
import platform
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock, Thread
from typing import Any, Callable, Optional
from uuid import uuid4

import requests
from requests import Response

from vicoa.spawn_ws_client import SpawnRequestWsClient
from vicoa.terminal.coalescer import TerminalOutputCoalescer
from vicoa.terminal.rpc import PTY_ORDERED_METHODS, PTY_RPC_METHODS, handle_pty_rpc
from vicoa.terminal.service import TerminalService
from requests.exceptions import RequestException, Timeout

from protocol.agent_catalog import (
    PERMISSION_MODES,
    REASONING_EFFORTS,
    THINKING_EFFORTS,
)
from integrations.headless.generic_acp import GENERIC_ACP_AGENTS
from vicoa.utils import derive_ws_url, get_project_path
from vicoa.machine_identity import (
    IdentityAction,
    api_key_fingerprint,
    decide_identity_action,
)
from vicoa.machine_fingerprint import compute_stable_machine_id, hardware_id_hash
from vicoa.sdk.exceptions import AuthenticationError
from vicoa.machine_state import (
    STATE_PATH,
    clear_daemon_pid,
    list_daemon_entries,
    normalize_base_url,
    read_daemon_entry,
    read_state_file,
    save_state_file,
    update_daemon_entry,
    write_daemon_entry,
)

logger = logging.getLogger(__name__)

DEFAULT_POLL_INTERVAL_SECONDS = 5
DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 30
REQUEST_TIMEOUT_SECONDS = 15

# Opaque CLI keys expire in ~90 days; the server only extends one with <7 days
# left. Checking every ~3 days lands ~2 renewal attempts inside that window well
# before expiry, so a machine whose daemon is alive never has to re-login. The
# daemon calls unconditionally — the server-side threshold makes it a no-op
# until it's actually due (and a no-op forever for grandfathered no-exp keys).
RENEW_ENDPOINT = "/api/v1/auth/api-keys/current/renew"
RENEW_CHECK_INTERVAL_SECONDS = 3 * 24 * 3600


@dataclass
class MachineRegistration:
    machine_id: str
    display_name: Optional[str]
    hostname: Optional[str]
    platform: Optional[str]


def _find_cli_in_common_locations(name: str) -> str | None:
    """Locate an npm-installed CLI even when the daemon's PATH is minimal.

    Thin wrapper kept for callers in this module; the real search lives
    in ``vicoa.utils.find_npm_cli`` (shared with the claude_code and
    codex_acp resolvers so they stay in lockstep).
    """
    from vicoa.utils import find_npm_cli

    return find_npm_cli(name)


def _pid_exists(pid: int) -> bool:
    if pid <= 0:
        return False

    if os.name == "nt":
        try:
            handle = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True,
                check=False,
                text=True,
            )
        except Exception:
            return False
        return str(pid) in handle.stdout

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True

    return True


def _command_looks_like_vicoa_daemon(command: str) -> bool:
    normalized = " ".join(command.lower().split())
    # python -m vicoa.cli daemon ...
    if "vicoa.cli daemon" in normalized:
        return True
    # /path/to/vicoa daemon ... (frozen binary or entry-point script invoked directly)
    # ps shows: /path/to/python /path/to/vicoa daemon ...
    # Exclude processes where Node.js is the interpreter (first token). The npm
    # wrapper launches as `node <script>`, while the frozen binary and Python
    # entry-point are invoked directly — their argv[0] is never `node`.
    parts = normalized.split()
    if not parts:
        return False
    interpreter = parts[0]
    is_node_interpreter = interpreter == "node" or interpreter.endswith("/node")
    has_daemon = "daemon" in parts
    has_vicoa = any("vicoa" in p for p in parts)
    if has_daemon and has_vicoa and not is_node_interpreter:
        return True
    return False


def _read_process_command(pid: int) -> str | None:
    if pid <= 0:
        return None

    if sys.platform.startswith("linux"):
        cmdline_path = Path("/proc") / str(pid) / "cmdline"
        try:
            raw = cmdline_path.read_bytes()
        except Exception:
            raw = b""
        if raw:
            parts = [part.decode("utf-8", errors="ignore") for part in raw.split(b"\0")]
            return " ".join(part for part in parts if part)

    if os.name == "posix":
        try:
            result = subprocess.run(
                ["ps", "-p", str(pid), "-o", "command="],
                capture_output=True,
                check=False,
                text=True,
            )
        except Exception:
            return None
        command = result.stdout.strip()
        return command or None

    return None


def _extract_base_url_from_command(command: str) -> str | None:
    """Pull the ``--base-url`` value out of a daemon's command line, if any.

    ``build_daemon_command`` always emits the flag, so every daemon spawned by
    this version is tagged. Returns ``None`` for legacy daemons whose argv
    omitted the flag — the caller maps those to the default URL.
    """
    parts = command.split()
    for idx, part in enumerate(parts):
        if part == "--base-url" and idx + 1 < len(parts):
            return parts[idx + 1]
        if part.startswith("--base-url="):
            return part.split("=", 1)[1]
    return None


def _scan_process_list_for_daemons() -> dict[str, int]:
    """Return ``{normalized_base_url: pid}`` for every running vicoa daemon.

    Used as a fallback when the state file is stale or missing — e.g. the user
    cleared ``~/.vicoa/`` while a daemon was running. Daemons whose command
    line omits ``--base-url`` are bucketed under the default URL.
    """
    if os.name != "posix":
        return {}

    try:
        result = subprocess.run(
            ["ps", "ax", "-o", "pid=,command="],
            capture_output=True,
            check=False,
            text=True,
        )
    except Exception:
        return {}

    discovered: dict[str, int] = {}
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        pid_text, _, command = stripped.partition(" ")
        if not pid_text.isdigit():
            continue
        pid = int(pid_text)
        if pid == os.getpid():
            continue
        if not _command_looks_like_vicoa_daemon(command):
            continue
        raw_url = _extract_base_url_from_command(command)
        key = normalize_base_url(raw_url)
        # First match wins — there should never be two daemons for the same
        # URL, but if there are, the older PID is the live one we care about.
        discovered.setdefault(key, pid)
    return discovered


def migrate_legacy_flat_state(
    fallback_base_url: str, state_path: Path = STATE_PATH
) -> None:
    """One-shot upgrade migration for pre-multi-daemon state files.

    Old CLI versions persisted a single flat
    ``{daemon_pid, machine_id, display_name}`` at the top level — the
    ``machine_id`` belonged to whichever backend the most-recent daemon last
    registered against, not necessarily the default URL. The naive in-memory
    migration in ``_get_daemons_section`` always buckets that machine_id under
    the default URL, which orphans the user's existing backend machine row
    when the upgraded daemon is run against a custom ``--base-url``
    (the file-listing RPC then resolves to a stale, offline machine).

    This helper does the on-disk migration with two signals:

    1. If the legacy ``daemon_pid`` is still alive, read its argv and bucket
       under the ``--base-url`` it was actually launched with. This is the
       authoritative signal — the running daemon's URL is the URL its
       machine_id belongs to.
    2. Otherwise (legacy daemon already stopped before the upgrade) fall back
       to ``fallback_base_url``. Callers pass the URL the user is *currently*
       working with (e.g. ``args.base_url`` for ``vicoa daemon``), so users
       who consistently target the same URL keep their machine identity.

    Safe to call repeatedly — once the state file has a ``daemons`` key
    (i.e. has been touched by the new CLI) this is a no-op.
    """
    state = read_state_file(state_path)
    if "daemons" in state:
        return  # already in new shape; nothing to do

    legacy_pid = state.get(_PID_KEY := "daemon_pid")
    legacy_machine_id = state.get(_MID_KEY := "machine_id")
    legacy_display = state.get(_DN_KEY := "display_name")
    if not any([legacy_pid, legacy_machine_id, legacy_display]):
        # Nothing worth preserving — leave the file alone so the next
        # ``update_daemon_entry`` call writes a clean new-shape file.
        return

    target_url = fallback_base_url
    if isinstance(legacy_pid, int) and legacy_pid > 0 and _pid_exists(legacy_pid):
        command = _read_process_command(legacy_pid)
        if command and _command_looks_like_vicoa_daemon(command):
            extracted = _extract_base_url_from_command(command)
            if extracted:
                target_url = extracted

    entry: dict[str, Any] = {}
    if isinstance(legacy_pid, int) and legacy_pid > 0:
        entry[_PID_KEY] = legacy_pid
    if isinstance(legacy_machine_id, str) and legacy_machine_id:
        entry[_MID_KEY] = legacy_machine_id
    if isinstance(legacy_display, str) and legacy_display:
        entry[_DN_KEY] = legacy_display

    save_state_file({"daemons": {normalize_base_url(target_url): entry}}, state_path)


def find_running_daemon_pid(base_url: str, state_path: Path = STATE_PATH) -> int | None:
    """Return the live PID of the daemon for ``base_url``, or ``None``.

    Looks at the persisted state first, then falls back to scanning the
    process list and self-heals state when it finds an unrecorded match.
    """
    entry = read_daemon_entry(base_url, state_path)
    daemon_pid = entry.get("daemon_pid")
    if isinstance(daemon_pid, int) and _pid_exists(daemon_pid):
        command = _read_process_command(daemon_pid)
        if command is None or _command_looks_like_vicoa_daemon(command):
            return daemon_pid

    discovered = _scan_process_list_for_daemons()
    pid = discovered.get(normalize_base_url(base_url))
    if pid is not None:
        try:
            update_daemon_entry(base_url, {"daemon_pid": pid}, state_path)
        except Exception:
            pass
        return pid

    return None


def list_running_daemons(
    state_path: Path = STATE_PATH,
) -> list[tuple[str, int]]:
    """Return ``[(normalized_base_url, pid)]`` for every live vicoa daemon.

    Merges the persisted state with a process-list scan so a daemon that the
    state file doesn't know about (or vice-versa) still surfaces.
    """
    result: dict[str, int] = {}
    for url, entry in list_daemon_entries(state_path).items():
        pid = entry.get("daemon_pid")
        if not isinstance(pid, int) or pid <= 0:
            continue
        if not _pid_exists(pid):
            continue
        command = _read_process_command(pid)
        if command is not None and not _command_looks_like_vicoa_daemon(command):
            continue
        result[url] = pid

    for url, pid in _scan_process_list_for_daemons().items():
        # Don't overwrite an entry the state file already validated.
        result.setdefault(url, pid)

    return sorted(result.items())


def _reset_state_on_identity_change(
    api_key: str, base_url: str, state_path: Path
) -> None:
    """Execute the verdict from ``decide_identity_action``: stop the running
    daemon and clear ``base_url``'s entry on RESET, stamp the fingerprint on
    STAMP_FINGERPRINT, no-op on NONE.

    The policy (read state, compute action, optional ownership ping) lives
    in ``vicoa.machine_identity`` so it stays testable without patching
    subprocess kills; this function is the side-effect half.
    """
    action = decide_identity_action(api_key, base_url, state_path)
    if action is IdentityAction.RESET:
        stop_background_daemon(base_url=base_url, state_path=state_path)
        write_daemon_entry(base_url, {}, state_path)
    elif action is IdentityAction.STAMP_FINGERPRINT:
        update_daemon_entry(
            base_url,
            {"api_key_fingerprint": api_key_fingerprint(api_key)},
            state_path,
        )


class DaemonStartResult(enum.Enum):
    """Outcome of ``ensure_background_daemon_running``.

    Replaces the old bool so the foreground caller can distinguish a
    deliberately-not-spawned dead credential (``AUTH_INVALID``) from a normal
    spawn/skip and print the disconnected message once.
    """

    SPAWNED = "spawned"
    ALREADY_RUNNING = "already_running"
    AUTH_INVALID = "auth_invalid"


def ensure_background_daemon_running(
    *,
    api_key: str,
    base_url: str,
    cwd: str | None = None,
    state_path: Path = STATE_PATH,
) -> DaemonStartResult:
    """Spawn a daemon for ``base_url`` if one isn't already running for it."""
    # If the state file is still in the pre-multi-daemon flat shape, migrate
    # it under the URL the caller is asking us to run against (or whichever
    # URL the live legacy PID was actually using, when discoverable). Doing
    # this BEFORE the lookup means the existing machine_id is recovered into
    # the right bucket, so the backend re-registers as the same machine.
    migrate_legacy_flat_state(base_url, state_path)
    # User-switch defense: if the persisted machine identity was registered
    # under a different API key, stop the old daemon and clear the entry so
    # the spawn below re-registers under the new identity. Same-user reauth
    # (same key) is a no-op; legacy state without a fingerprint takes a one
    # -time backend ownership ping.
    _reset_state_on_identity_change(api_key, base_url, state_path)

    # A previous daemon flagged this credential dead (401) and nulled its PID.
    # If the current key still matches the stored fingerprint, re-spawning
    # would just produce another doomed daemon — so refuse and let the caller
    # surface the disconnected message. `_reset_state_on_identity_change`
    # already wiped the entry on a key change, so a match here means the SAME
    # dead key; re-auth mints a new key, wipes the entry, and clears this.
    entry = read_daemon_entry(base_url, state_path)
    if entry.get("auth_invalid_at") and entry.get(
        "api_key_fingerprint"
    ) == api_key_fingerprint(api_key):
        return DaemonStartResult.AUTH_INVALID

    running_pid = find_running_daemon_pid(base_url, state_path)
    if running_pid is not None:
        return DaemonStartResult.ALREADY_RUNNING

    command = build_daemon_command(api_key=api_key, base_url=base_url)

    popen_kwargs: dict[str, Any] = {
        "cwd": cwd or os.getcwd(),
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = (
            subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        )
    else:
        popen_kwargs["start_new_session"] = True

    process = subprocess.Popen(command, **popen_kwargs)
    update_daemon_entry(base_url, {"daemon_pid": process.pid}, state_path)
    return DaemonStartResult.SPAWNED


def build_daemon_command(*, api_key: str, base_url: str) -> list[str]:
    if getattr(sys, "frozen", False):
        # Running as a PyInstaller binary — invoke the binary directly
        return [sys.executable, "daemon", "--api-key", api_key, "--base-url", base_url]
    return [
        sys.executable,
        "-m",
        "vicoa.cli",
        "daemon",
        "--api-key",
        api_key,
        "--base-url",
        base_url,
    ]


def stop_background_daemon(
    *,
    base_url: str,
    state_path: Path = STATE_PATH,
    timeout_seconds: float = 5.0,
) -> tuple[bool, str]:
    """Terminate the daemon for ``base_url``. Clears its PID on success."""
    daemon_pid = find_running_daemon_pid(base_url, state_path)
    if daemon_pid is None:
        return False, "No active Vicoa connection."

    command = _read_process_command(daemon_pid)
    if command is not None and not _command_looks_like_vicoa_daemon(command):
        return False, "No active Vicoa connection."

    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(daemon_pid), "/T"],
                capture_output=True,
                check=False,
                text=True,
            )
        else:
            os.kill(daemon_pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    except Exception as exc:
        return False, f"Failed to stop Vicoa connection: {exc}"

    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if not _pid_exists(daemon_pid):
            clear_daemon_pid(base_url, state_path)
            return True, "Stopped Vicoa connection."
        time.sleep(0.1)

    if os.name != "nt":
        try:
            os.kill(daemon_pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except Exception as exc:
            return False, f"Failed to stop Vicoa connection: {exc}"

        deadline = time.time() + 2.0
        while time.time() < deadline:
            if not _pid_exists(daemon_pid):
                clear_daemon_pid(base_url, state_path)
                return True, "Stopped Vicoa connection."
            time.sleep(0.1)

    return False, "Failed to stop Vicoa connection."


class MachineDaemon:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        poll_interval: int = DEFAULT_POLL_INTERVAL_SECONDS,
        heartbeat_interval: int = DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
        cli_version: str | None = None,
        ws_url: str | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.poll_interval = max(1, poll_interval)
        self.heartbeat_interval = max(5, heartbeat_interval)
        self.cli_version = cli_version
        # When set, spawn requests arrive over the WebSocket /ws endpoint;
        # otherwise the daemon falls back to the legacy SSE stream.
        self.ws_url = ws_url
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
        )
        # Tag every REST request with the daemon version so the server can
        # compute the Wave B SSE-retirement gate (websocket-migration §4 item 6).
        if cli_version:
            self.session.headers["X-CLI-Version"] = cli_version
        self.machine_id: Optional[str] = None
        # Assigned by the desktop runner (local_server.runner) so the local
        # /healthz endpoint can report cloud auth state to the tray. Called
        # with "connected" after a successful registration and "auth_failed"
        # on fatal auth; None (the default) everywhere else.
        self.on_cloud_status: Callable[[str], None] | None = None
        self._last_heartbeat_sent: float = 0.0
        # Set by any REST 401 (see ``_raise_for_auth``). The cross-thread
        # signal that the credential is dead: a background heartbeat thread
        # sets it, the main loop watches it to stop the stream and exit.
        self._fatal_auth = Event()
        # Set by ``request_stop()`` — the desktop local-listener runner's
        # shutdown path. A plain ``vicoa daemon`` never requests a stop (its
        # lifetime is the process's), so both stay inert outside the desktop.
        self._stop_requested = Event()
        # Wakes the background key-renewal loop out of its long sleep so it exits
        # promptly on shutdown or a dead credential.
        self._stop_renewal = Event()
        self._ws_client: Optional[SpawnRequestWsClient] = None
        # Terminals opened on THIS machine from another device (the remote
        # `pty-*` path). Built lazily on first use — a daemon that never serves
        # a remote terminal never spawns the coalescer thread. Distinct from the
        # desktop local_server's TerminalService (that one drives this machine's
        # OWN UI over 127.0.0.1); the two never share a pty.
        self._terminal_service: Optional[TerminalService] = None
        self._pty_coalescer: Optional[TerminalOutputCoalescer] = None
        self._terminal_lock = Lock()
        self._active_request_ids: set[str] = set()
        self._active_request_ids_lock = Lock()
        self._spawn_executor = ThreadPoolExecutor(
            max_workers=4, thread_name_prefix="spawn"
        )

    # ------------------------------------------------------------------
    # Persistence helpers — each daemon owns its own per-base-url entry.
    # ------------------------------------------------------------------
    def _load_entry(self) -> dict[str, Any]:
        return read_daemon_entry(self.base_url)

    def _persist_entry(self, updates: dict[str, Any]) -> None:
        try:
            update_daemon_entry(self.base_url, updates)
        except Exception as exc:
            print(f"[daemon] failed to persist state: {exc}")

    def _notify_cloud_status(self, status: str) -> None:
        """Report a cloud-auth transition to the local server, when attached.

        Best-effort by design: the callback only feeds the desktop tray's
        /healthz view, so a broken callback must never take the daemon down.
        """
        callback = self.on_cloud_status
        if callback is None:
            return
        try:
            callback(status)
        except Exception:
            logger.exception("cloud-status callback failed (status=%s)", status)

    @property
    def fatal_auth(self) -> bool:
        """Read-only: has a 401 marked this daemon's credential dead?

        The desktop local-listener runner reads this after ``run()`` returns
        to tell fatal auth apart from any other exit; nothing here mutates
        fatal-auth state.
        """
        return self._fatal_auth.is_set()

    def request_stop(self) -> None:
        """Ask a ``run()`` blocking on another thread to wind down.

        Desktop local-listener shutdown only: stops the spawn WS client so
        ``_ws_listen_for_spawn_requests`` returns and ``run()`` exits through
        its normal cleanup. The plain ``vicoa daemon`` path never calls this.
        Covers the WS listen path only — the local-listener daemon always has
        ``ws_url`` set, so it never sits in the legacy SSE loop.
        """
        self._stop_requested.set()
        self._stop_renewal.set()
        client = self._ws_client
        if client is not None:
            client.stop()

    # ------------------------------------------------------------------
    # REST helpers
    # ------------------------------------------------------------------
    def _raise_for_auth(self, response: Response) -> None:
        """Convert an agent-server 401 into a fatal-auth signal.

        A 401 means the daemon's credential is genuinely dead (revoked key or
        deleted user) — nothing between the daemon and origin emits a spurious
        401 (Fly's proxy 5xx's on infra problems). Raising ``AuthenticationError``
        — which is NOT a ``RequestException`` — lets it escape the broad
        ``except RequestException`` in the heartbeat/poll loops instead of being
        swallowed and retried forever.
        """
        if response.status_code == 401:
            self._fatal_auth.set()
            raise AuthenticationError("agent server rejected credentials (401)")

    def _handle_fatal_auth(self) -> None:
        """Persist the dead-credential verdict so the daemon can exit cleanly.

        The merging persist keeps ``machine_id``/``display_name``/
        ``api_key_fingerprint`` while nulling ``daemon_pid`` (a foreground
        ``vicoa <agent>`` must not treat us as the live owner) and stamping
        ``auth_invalid_at`` so the next foreground launch with the SAME key
        prints the disconnected message instead of respawning a doomed daemon.
        ``register_machine`` clears the stamp on the next successful re-auth.
        """
        self._persist_entry(
            {
                "auth_invalid_at": datetime.now(timezone.utc).isoformat(),
                "daemon_pid": None,
            }
        )
        self._notify_cloud_status("auth_failed")
        logger.info("[daemon] credential rejected (401); link disconnected, exiting")

    def _post(self, path: str, payload: dict[str, Any] | None = None) -> Response:
        url = f"{self.base_url}{path}"
        response = self.session.post(url, json=payload, timeout=REQUEST_TIMEOUT_SECONDS)
        self._raise_for_auth(response)
        return response

    # ------------------------------------------------------------------
    # Credential renewal — keeps an opaque CLI key from lapsing while the
    # daemon is alive (server extends its expiry in place; the token is
    # unchanged, so machine identity is never reset).
    # ------------------------------------------------------------------
    def _renewal_loop(self) -> None:
        # Renew once at startup so a key that lapsed toward expiry during a long
        # offline gap is pushed forward immediately, then on a slow heartbeat.
        self._try_renew()
        while not self._stop_renewal.wait(RENEW_CHECK_INTERVAL_SECONDS):
            self._try_renew()

    def _try_renew(self) -> None:
        try:
            self._post(RENEW_ENDPOINT).raise_for_status()
        except AuthenticationError:
            # The credential is already dead — the heartbeat/main loop owns the
            # fatal-auth exit. Stop looping so we don't hammer a 401.
            self._stop_renewal.set()
        except RequestException as exc:
            # Transient (network, 5xx, or a Postgres hiccup surfacing as 500):
            # the key is unchanged, so just try again next cycle.
            logger.debug("[daemon] key renewal deferred: %s", exc)

    def _patch(self, path: str, payload: dict[str, Any]) -> Response:
        url = f"{self.base_url}{path}"
        response = self.session.patch(
            url, json=payload, timeout=REQUEST_TIMEOUT_SECONDS
        )
        self._raise_for_auth(response)
        return response

    def _put(self, path: str, payload: dict[str, Any]) -> Response:
        url = f"{self.base_url}{path}"
        response = self.session.put(url, json=payload, timeout=REQUEST_TIMEOUT_SECONDS)
        self._raise_for_auth(response)
        return response

    # ------------------------------------------------------------------
    # Registration & heartbeat
    # ------------------------------------------------------------------
    def _detect_available_agents(self) -> dict[str, bool]:
        """Which agent CLIs are installed on this machine (D2).

        `_check_agent_installation` returns None when the CLI is found, so a
        None result maps to True. Detection runs once here at registration —
        cheap, and it avoids spawning `--version` subprocesses on the heartbeat
        loop (D3).
        """
        return {
            agent: self._check_agent_installation(agent) is None
            for agent in ("claude", "codex", "opencode", *GENERIC_ACP_AGENTS)
        }

    def _capabilities(self) -> list[str]:
        """Feature flags the app reads from machine metadata to feature-detect.

        `worktree` tells the app this daemon understands the `spawn-session`
        `worktree` param and the `git-worktree-*` RPCs, so it can show the
        worktree option. An old daemon omits it and the app stays hidden.

        `agent-scan` tells the app the `scan-agents` RPC is routable here,
        so the desktop agent scan can offer a Rescan button. An old daemon
        omits it and the button stays hidden rather than failing `no_handler`.

        `file-index` tells the client the `scan-files` RPC is routable here,
        so `@`-mentions can read the live project index off this machine
        instead of the CLI-synced copy in the DB. Feature-detecting on this
        rather than catching `no_handler` matters: the server's RPC router
        waits out a 3s grace window before returning `no_handler`, and paying
        that on every `@` against an old daemon is worse than not trying.

        `command-index` tells the client the `scan-commands` RPC is routable
        here, so the `/` menu can read the machine's live slash command and
        skill set instead of the CLI-synced copy in the DB. Same rationale as
        `file-index` for gating on the flag rather than catching `no_handler`.

        `terminal` tells the client the `pty-*` RPCs are routable here, so it
        can offer the terminal tab for THIS machine from another device. An old
        daemon omits it and the button stays hidden rather than failing
        `no_handler` on `pty-spawn`.

        `file-write` tells the client the `write-file`/`stat-file` RPCs are
        routable here, so the Files panel can show the Edit affordance. An old
        daemon omits it and the panel stays read-only rather than offering an
        Edit button that would fail `no_handler` on save.

        `git-base` tells the client the `git-show-file` RPC is routable here, so
        the Changes tab can offer the editable side-by-side/inline diff (it
        needs the HEAD baseline to diff the working file against). An old daemon
        omits it and the diff view falls back to the read-only inline diff.

        `git-write` tells the client the `git-stage`/`git-unstage`/`git-commit`
        RPCs are routable here, so the Changes tab can offer staging controls
        and the commit box. An old daemon omits it and the tab stays read-only
        rather than failing `no_handler` on the first stage click.
        """
        return [
            "worktree",
            "agent-scan",
            "file-index",
            "command-index",
            "terminal",
            "file-write",
            "git-base",
            "git-write",
            "skill-manage",
        ]

    def register_machine(self) -> MachineRegistration:
        # First-run-after-upgrade: if the state file is still in the legacy
        # flat shape, migrate it to the new per-URL shape now — bucketing
        # under our own base_url when the legacy PID is gone, or under the
        # legacy PID's argv-declared URL when it's still alive. This is what
        # preserves the existing machine_id so the backend re-registers as
        # the same machine instead of provisioning a fresh row.
        migrate_legacy_flat_state(self.base_url)

        entry = self._load_entry()
        # Stamp our PID immediately so a concurrent `vicoa daemon` invocation
        # sees us as the live owner before the register round-trip completes.
        self._persist_entry({"daemon_pid": os.getpid()})
        # Prefer the cached id; when the cache is empty (fresh install, or the
        # state file / machine row was deleted) fall back to an id derived
        # deterministically from this host's hardware GUID + API key, so the
        # same machine re-registers as the same row instead of a fresh random
        # uuid4. compute_stable_machine_id returns None when no stable hardware
        # id is readable, and register then mints the legacy uuid4.
        machine_id = entry.get("machine_id") or compute_stable_machine_id(self.api_key)

        payload: dict[str, Any] = {
            "machine_id": machine_id,
            # Server-side dedup anchor: the backend maps (user_id, hardware_id)
            # to a stable machine row, so re-auth / key rotation (which changes
            # machine_id, since it folds in the key) still resolves to the same
            # machine. None on hosts with no readable hardware id — the backend
            # then falls back to the client-supplied machine_id.
            "hardware_id": hardware_id_hash(),
            "hostname": platform.node()[:255],
            "platform": platform.platform()[:255],
            "home_dir": str(Path.home()),
            "display_name": entry.get("display_name"),
            "metadata": {
                "cli_version": self.cli_version,
                "python_version": platform.python_version(),
                "cwd": get_project_path(),
                "available_agents": self._detect_available_agents(),
                "capabilities": self._capabilities(),
            },
        }

        response = self._post("/api/v1/machines/register", payload)
        response.raise_for_status()
        data = response.json()

        self.machine_id = data["machine_id"]
        self._persist_entry(
            {
                "machine_id": self.machine_id,
                "display_name": data.get("display_name"),
                # Stamp the key fingerprint at registration so a later CLI
                # invocation under a different API key can detect the identity
                # mismatch with one local SHA256 instead of a backend round
                # trip. See `vicoa.machine_identity.decide_identity_action`.
                "api_key_fingerprint": api_key_fingerprint(self.api_key),
                # A successful registration is the only heal path for a prior
                # fatal-auth: clear the stamp so the daemon resumes normally.
                "auth_invalid_at": None,
            }
        )

        print(
            f"[daemon] machine registered as {self.machine_id} (hostname={data.get('hostname')})"
        )
        self._notify_cloud_status("connected")

        return MachineRegistration(
            machine_id=data["machine_id"],
            display_name=data.get("display_name"),
            hostname=data.get("hostname"),
            platform=data.get("platform"),
        )

    def send_heartbeat(self) -> None:
        if not self.machine_id:
            return

        payload = {
            "metadata": {
                "last_pid": os.getpid(),
            }
        }
        try:
            response = self._post(
                f"/api/v1/machines/{self.machine_id}/heartbeat", payload
            )
            response.raise_for_status()
            self._last_heartbeat_sent = time.time()
        except RequestException as exc:
            logger.debug(f"Heartbeat failed (will retry): {exc}")

    # ------------------------------------------------------------------
    # Spawn handling
    # ------------------------------------------------------------------
    def poll_for_requests(self) -> Optional[dict[str, Any]]:
        if not self.machine_id:
            return None
        try:
            response = self._post(
                f"/api/v1/machines/{self.machine_id}/spawn-requests/next",
                payload={},
            )
        except Timeout:
            logger.debug("Poll request timed out (will retry)")
            return None
        except RequestException as exc:
            logger.debug(f"Failed to poll for requests (will retry): {exc}")
            return None

        if response.status_code == 204:
            return None

        if response.status_code != 200:
            print(
                f"[daemon] unexpected response polling spawn requests: {response.status_code}"
            )
            return None

        try:
            return response.json()
        except ValueError:
            print("[daemon] failed to decode spawn request payload")
            return None

    def report_request_status(
        self,
        request_id: str,
        status: str,
        *,
        agent_instance_id: str | None = None,
        message: str | None = None,
        retry_on_missing_agent: bool = False,
        retry_timeout: float = 30.0,
    ) -> bool:
        if not self.machine_id:
            return False
        if not request_id:
            # RPC-spawned sessions (Phase 5) have no spawn-request row to
            # report against — the monitor still runs for crash-fallback.
            return False

        payload = {
            "status": status,
            "agent_instance_id": agent_instance_id,
            "message": message,
        }

        deadline = time.time() + retry_timeout if retry_on_missing_agent else None

        while True:
            try:
                response = self._patch(
                    f"/api/v1/machines/{self.machine_id}/spawn-requests/{request_id}",
                    payload,
                )
            except RequestException as exc:
                print(f"[daemon] failed to report request status: {exc}")
                return False

            if response.status_code == 200:
                return True

            if retry_on_missing_agent and response.status_code == 400:
                detail: str | None = None
                try:
                    body = response.json()
                    detail = body.get("detail") if isinstance(body, dict) else None
                except ValueError:
                    detail = None

                if detail and "agent_instance_id not found" in detail:
                    if deadline is not None and time.time() < deadline:
                        time.sleep(0.5)
                        continue
                    print(
                        "[daemon] agent instance not yet available to update spawn request"
                    )
                    return False

            print(
                f"[daemon] unexpected response when reporting status: {response.status_code}"
            )
            try:
                print(f"[daemon] response body: {response.text}")
            except Exception:
                pass
            return False

    def _update_instance_status(self, agent_instance_id: str, status: str) -> None:
        """Best-effort terminal-status update for a headless session's instance.

        Called from ``_monitor_session_process`` only when a daemon-spawned
        child exits with a NON-ZERO code — i.e. it was SIGKILLed, crashed,
        or got SIGTERM without a handler and never ran its own cleanup. A
        clean exit (code 0) means the process already set its own status
        during graceful shutdown, so we deliberately don't call this there
        — writing again would just race the process's own update.
        """
        if not agent_instance_id:
            return
        try:
            response = self._put(
                f"/api/v1/agent-instances/{agent_instance_id}/status",
                {"status": status},
            )
        except RequestException as exc:
            print(f"[daemon] failed to update instance status: {exc}")
            return
        if response.status_code == 200:
            print(f"[daemon] instance {agent_instance_id} status set to {status}")
        else:
            print(
                f"[daemon] unexpected response updating instance status: "
                f"{response.status_code}"
            )

    # ------------------------------------------------------------------
    # Session launching
    # ------------------------------------------------------------------
    #: Per-agent flag carrying the agent's *own* conversation handle, as
    #: distinct from the Vicoa instance id. Claude needs none: Vicoa pins its
    #: session id to the instance id at first launch, so `--resume <instance>`
    #: already names the transcript.
    _AGENT_SESSION_FLAG: dict[str, str] = {
        "codex": "--codex-thread-id",
        "opencode": "--acp-session-id",
    }

    def _session_process_is_running(self, instance_id: str) -> bool:
        """Whether an agent process is already serving this instance.

        Read from ``ps`` rather than from daemon-local bookkeeping on purpose:
        sessions are spawned with ``start_new_session=True`` so they outlive a
        daemon restart, which means in-memory state would miss exactly the
        long-lived processes a resume is most likely to collide with.

        Best effort — on failure we report "not running" and allow the spawn.
        A missed duplicate is recoverable; blocking every resume because the
        scan broke is not.
        """
        try:
            from vicoa.agent_processes import list_running_agents

            return any(
                (agent.session_id or "") == instance_id
                for agent in list_running_agents()
            )
        except Exception:
            logger.debug("running-agent scan failed", exc_info=True)
            return False

    def _resume_args(
        self,
        *,
        agent: str,
        session_id: str | None,
        agent_session_id: str | None,
    ) -> list[str]:
        """Flags that turn a spawn into a resume.

        Two independent things, deliberately kept separate:

        * ``--resume <instance id>`` reattaches the existing Vicoa row. Every
          wrapper needs it, because registering an id that already exists
          returns 409 for anything but a pre-allocated STARTING row.
        * the per-agent handle restores the *conversation*. It is absent when
          the previous run never recorded one, or when the agent can't reload
          — in which case the session comes back with no memory rather than
          not at all.
        """
        if not session_id:
            return []
        args = ["--resume", session_id]
        if agent_session_id:
            flag = self._AGENT_SESSION_FLAG.get(
                agent, "--acp-session-id" if agent in GENERIC_ACP_AGENTS else ""
            )
            if flag:
                args.extend([flag, agent_session_id])
        return args

    def _build_headless_command(
        self,
        *,
        directory: str,
        agent: str,
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        is_resuming: bool = False,
        agent_session_id: str | None = None,
    ) -> list[str]:
        cmd = self._build_headless_command_base(
            directory=directory,
            agent=agent,
            session_id=session_id,
            metadata=metadata,
        )
        if is_resuming:
            cmd.extend(
                self._resume_args(
                    agent=agent,
                    session_id=session_id,
                    agent_session_id=agent_session_id,
                )
            )
        return cmd

    def _build_headless_command_base(
        self,
        *,
        directory: str,
        agent: str,
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> list[str]:
        normalized_agent = agent

        if getattr(sys, "frozen", False):
            cmd = [
                sys.executable,
                "headless",
                "--api-key",
                self.api_key,
                "--base-url",
                self.base_url,
                "--cwd",
                directory,
                "--agent",
                normalized_agent,
                "--session-id",
                session_id or "",
            ]
            if normalized_agent == "codex":
                auth_method = self._extract_codex_auth_method(metadata)
                if auth_method:
                    cmd.extend(["--auth-method", auth_method])
                model = self._extract_codex_model(metadata)
                if model:
                    cmd.extend(["--model", model])
                reasoning_effort = self._extract_reasoning_effort(metadata)
                if reasoning_effort is not None:
                    cmd.extend(["--reasoning-effort", reasoning_effort])
                permission_mode = self._extract_permission_mode(metadata, agent="codex")
                if permission_mode:
                    cmd.extend(["--permission-mode", permission_mode])
                prompt = self._extract_prompt(metadata)
                if prompt:
                    cmd.extend(["--prompt", prompt])
            elif normalized_agent == "opencode":
                agent_mode = self._extract_opencode_mode(metadata)
                if agent_mode:
                    cmd.extend(["--agent-mode", agent_mode])
                model = self._extract_opencode_model(metadata)
                if model:
                    cmd.extend(["--model", model])
                prompt = self._extract_prompt(metadata)
                if prompt:
                    cmd.extend(["--prompt", prompt])
            elif normalized_agent in GENERIC_ACP_AGENTS:
                model = self._extract_generic_model(metadata)
                if model:
                    cmd.extend(["--model", model])
                permission_mode = self._extract_permission_mode(
                    metadata, agent=normalized_agent
                )
                if permission_mode:
                    cmd.extend(["--permission-mode", permission_mode])
                prompt = self._extract_prompt(metadata)
                if prompt:
                    cmd.extend(["--prompt", prompt])
            else:
                permission_mode = self._extract_permission_mode(
                    metadata, agent="claude"
                )
                cmd.extend(["--permission-mode", permission_mode or "default"])
                prompt = self._extract_prompt(metadata)
                if prompt:
                    cmd.extend(["--prompt", prompt])
                allowed_tools = self._extract_tool_list(metadata, "allowed_tools")
                if allowed_tools:
                    cmd.extend(["--allowed-tools", allowed_tools])
                disallowed_tools = self._extract_tool_list(metadata, "disallowed_tools")
                if disallowed_tools:
                    cmd.extend(["--disallowed-tools", disallowed_tools])
                model = self._extract_claude_model(metadata)
                if model:
                    cmd.extend(["--model", model])
                thinking_effort = self._extract_thinking_effort(metadata)
                if thinking_effort is not None:
                    cmd.extend(["--thinking-effort", thinking_effort])
                if self._extract_enable_thinking(metadata):
                    cmd.append("--enable-thinking")
            return cmd

        if normalized_agent == "codex":
            # Native codex app-server is the only supported codex backend.
            # Route through the `headless` subcommand — identical to the frozen
            # bundle above and to every other agent — so codex has a single
            # spawn path with no frozen/source divergence. cli.py maps
            # `--agent codex` to integrations.headless.codex_native. The legacy
            # ACP adapter modules (``integrations.headless.codex_acp``,
            # ``vicoa.agents.codex_acp``) remain on disk only for the helper
            # imports codex_native reuses; they are no longer spawned.
            cmd = [
                sys.executable,
                "-m",
                "vicoa.cli",
                "headless",
                "--api-key",
                self.api_key,
                "--base-url",
                self.base_url,
                "--cwd",
                directory,
                "--agent",
                "codex",
            ]
            if session_id:
                cmd.extend(["--session-id", session_id])
            auth_method = self._extract_codex_auth_method(metadata)
            if auth_method:
                cmd.extend(["--auth-method", auth_method])
            model = self._extract_codex_model(metadata)
            if model:
                cmd.extend(["--model", model])
            reasoning_effort = self._extract_reasoning_effort(metadata)
            if reasoning_effort is not None:
                cmd.extend(["--reasoning-effort", reasoning_effort])
            permission_mode = self._extract_permission_mode(metadata, agent="codex")
            if permission_mode:
                cmd.extend(["--permission-mode", permission_mode])
            prompt = self._extract_prompt(metadata)
            if prompt:
                cmd.extend(["--prompt", prompt])
            return cmd

        if normalized_agent == "opencode":
            cmd = [
                sys.executable,
                "-m",
                "integrations.headless.opencode_acp",
                "--api-key",
                self.api_key,
                "--base-url",
                self.base_url,
                "--project-path",
                directory,
                "--name",
                "OpenCode",
            ]
            if session_id:
                cmd.extend(["--session-id", session_id])
            agent_mode = self._extract_opencode_mode(metadata)
            if agent_mode:
                cmd.extend(["--agent-mode", agent_mode])
            model = self._extract_opencode_model(metadata)
            if model:
                cmd.extend(["--model", model])
            prompt = self._extract_prompt(metadata)
            if prompt:
                cmd.extend(["--prompt", prompt])
            return cmd

        if normalized_agent in GENERIC_ACP_AGENTS:
            spec = GENERIC_ACP_AGENTS[normalized_agent]
            cmd = [
                sys.executable,
                "-m",
                "integrations.headless.generic_acp",
                "--agent",
                normalized_agent,
                "--api-key",
                self.api_key,
                "--base-url",
                self.base_url,
                "--project-path",
                directory,
                "--name",
                spec.display_name,
            ]
            if session_id:
                cmd.extend(["--session-id", session_id])
            model = self._extract_generic_model(metadata)
            if model:
                cmd.extend(["--model", model])
            permission_mode = self._extract_permission_mode(
                metadata, agent=normalized_agent
            )
            if permission_mode:
                cmd.extend(["--permission-mode", permission_mode])
            prompt = self._extract_prompt(metadata)
            if prompt:
                cmd.extend(["--prompt", prompt])
            return cmd

        cmd = [
            sys.executable,
            "-m",
            "vicoa.cli",
            "headless",
            "--api-key",
            self.api_key,
            "--base-url",
            self.base_url,
            "--cwd",
            directory,
            "--name",
            self._agent_display_name(normalized_agent),
            "--agent",
            normalized_agent,
        ]
        if session_id:
            cmd.extend(["--session-id", session_id])
        permission_mode = self._extract_permission_mode(metadata, agent="claude")
        if permission_mode:
            cmd.extend(["--permission-mode", permission_mode])
        else:
            cmd.extend(["--permission-mode", "default"])
        prompt = self._extract_prompt(metadata)
        if prompt:
            cmd.extend(["--prompt", prompt])
        allowed_tools = self._extract_tool_list(metadata, "allowed_tools")
        if allowed_tools:
            cmd.extend(["--allowed-tools", allowed_tools])
        disallowed_tools = self._extract_tool_list(metadata, "disallowed_tools")
        if disallowed_tools:
            cmd.extend(["--disallowed-tools", disallowed_tools])
        model = self._extract_claude_model(metadata)
        if model:
            cmd.extend(["--model", model])
        thinking_effort = self._extract_thinking_effort(metadata)
        if thinking_effort is not None:
            cmd.extend(["--thinking-effort", thinking_effort])
        if self._extract_enable_thinking(metadata):
            cmd.append("--enable-thinking")
        return cmd

    def _normalize_agent(self, agent: str | None) -> str:
        if not agent:
            return "claude"

        normalized = str(agent).strip().lower()
        alias_map = {
            "claude": "claude",
            "claude code": "claude",
            "codex": "codex",
            "opencode": "opencode",
            **{agent_id: agent_id for agent_id in GENERIC_ACP_AGENTS},
        }

        resolved = alias_map.get(normalized)
        if resolved is None:
            known = ", ".join(["claude", "codex", "opencode", *GENERIC_ACP_AGENTS])
            raise ValueError(f"agent must be one of: {known}")
        return resolved

    def _check_agent_installation(self, agent: str) -> str | None:
        """Return an error message when the requested agent is unavailable."""
        if agent == "claude":
            try:
                from integrations.cli_wrappers.claude_code.utils.cli_finder import (
                    find_claude_cli,
                )

                find_claude_cli()
                return None
            except FileNotFoundError:
                return "Claude Code CLI ('claude') is not installed or not on PATH."

        if agent == "opencode":
            if _find_cli_in_common_locations("opencode"):
                return None
            return "OpenCode CLI ('opencode') is not installed or not on PATH."

        if agent == "codex":
            # Native ``codex app-server`` is the only supported backend.
            # The codex-acp adapter modules remain on disk for rollback but
            # aren't part of the install precheck anymore.
            if _find_cli_in_common_locations("codex"):
                return None
            return (
                "Codex CLI ('codex') is not installed or not on PATH. "
                "Install from https://developers.openai.com/codex/cli."
            )

        spec = GENERIC_ACP_AGENTS.get(agent)
        if spec is not None:
            from integrations.headless.generic_acp import resolve_agent_binary

            # PATH/npm locations (find_npm_cli) plus the spec's extra_dirs
            # (e.g. kimi-code's ~/.kimi-code/bin, which isn't on PATH).
            if resolve_agent_binary(spec, which=_find_cli_in_common_locations):
                return None
            tried = "', '".join(spec.binaries)
            return (
                f"{spec.display_name} CLI ('{tried}') is not installed or not "
                f"on PATH. {spec.install_hint}"
            )

        return f"Unsupported agent '{agent}' requested"

    def _agent_display_name(self, agent: str) -> str:
        if agent == "codex":
            return "Codex"
        if agent == "opencode":
            return "OpenCode"
        spec = GENERIC_ACP_AGENTS.get(agent)
        if spec is not None:
            return spec.display_name
        return "Claude Code"

    def _extract_tool_list(
        self, metadata: dict[str, Any] | None, key: str
    ) -> str | None:
        if not metadata:
            return None
        value = metadata.get(key)
        if not value:
            return None
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            cleaned = [str(item).strip() for item in value if str(item).strip()]
            if cleaned:
                return ",".join(cleaned)
        return None

    def _extract_prompt(self, metadata: dict[str, Any] | None) -> str | None:
        if not metadata:
            return None
        prompt = metadata.get("prompt") or metadata.get("initial_prompt")
        if isinstance(prompt, str) and prompt.strip():
            return prompt
        return None

    def _extract_generic_model(self, metadata: dict[str, Any] | None) -> str | None:
        """Model id passthrough for the generic ACP agents.

        Catalog model lists for these agents are UI hints; the wrapper
        applies the value best-effort via the agent's ACP model config
        option, so no daemon-side enum validation is needed."""
        if not metadata:
            return None
        value = metadata.get("model")
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None

    def _extract_permission_mode(
        self, metadata: dict[str, Any] | None, *, agent: str
    ) -> str | None:
        """Return a canonical `permission_mode` for the given agent.

        Returns None when the field is absent or empty (caller picks a default).
        Raises ValueError when the value is present-but-not-in-the-per-agent
        enum — spawn-session catches this and surfaces it as an RPC error so
        the daemon never ships through a mode it can't translate.
        """
        if not metadata:
            return None
        value = metadata.get("permission_mode")
        if not isinstance(value, str):
            return None
        normalized = value.strip()
        if not normalized:
            return None

        allowed = PERMISSION_MODES.get(agent)
        if allowed is None:
            # Agents without a permission_mode knob (e.g. opencode) silently
            # ignore the field; this lets a forward-compat client send a
            # shared persistence shape without per-agent branching.
            return None

        if normalized in allowed:
            return normalized

        # Back-compat aliases — pre-v2 clients sent these forms. Drop once
        # both web and mobile ship the v2 selection key (§3.5).
        if agent == "claude":
            alias_map = {
                "accept_edits": "acceptEdits",
                "accept-edits": "acceptEdits",
                "accept": "acceptEdits",
                "bypass": "bypassPermissions",
                "plan mode": "plan",
            }
            aliased = alias_map.get(normalized.lower())
            if aliased is not None and aliased in allowed:
                return aliased

        if agent == "codex":
            # Catalog 2026-06-05-2 → -3 dropped `plan` from codex. Old
            # in-memory clients keep sending it until they refresh the
            # catalog; silently fall back to `default` so spawn doesn't
            # fail mid-rollout. Drop once min_client_version covers it.
            if normalized == "plan":
                return "default"

        raise ValueError(f"Invalid permission_mode {normalized!r} for agent {agent!r}")

    def _extract_thinking_effort(self, metadata: dict[str, Any] | None) -> str | None:
        """Return a Claude `thinking_effort` value or None when absent."""
        if not metadata:
            return None
        value = metadata.get("thinking_effort")
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError(f"Invalid thinking_effort {value!r}: must be a string")
        normalized = value.strip()
        if not normalized:
            return None
        if normalized not in THINKING_EFFORTS:
            raise ValueError(f"Invalid thinking_effort {normalized!r}")
        return normalized

    def _extract_reasoning_effort(self, metadata: dict[str, Any] | None) -> str | None:
        """Return a Codex `reasoning_effort` value or None when absent."""
        if not metadata:
            return None
        value = metadata.get("reasoning_effort")
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError(f"Invalid reasoning_effort {value!r}: must be a string")
        normalized = value.strip()
        if not normalized:
            return None
        if normalized not in REASONING_EFFORTS:
            raise ValueError(f"Invalid reasoning_effort {normalized!r}")
        return normalized

    def _extract_opencode_mode(self, metadata: dict[str, Any] | None) -> str | None:
        if not metadata:
            return None

        value = metadata.get("agent_mode") or metadata.get("opencode_agent_mode")
        if not isinstance(value, str):
            return None

        normalized = value.strip().lower()
        if normalized in {"build", "plan"}:
            return normalized
        return None

    def _extract_claude_model(self, metadata: dict[str, Any] | None) -> str | None:
        """Return a Claude model id from metadata; empty / non-string → None.

        Catalog membership is intentionally NOT enforced — the agent CLI is
        the source of truth (plan §3.9), so a backend deploy can add
        `claude-opus-4-9` to the catalog and clients pick it without every
        user's daemon needing to redeploy.
        """
        if not metadata:
            return None
        value = metadata.get("model")
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None

    def _extract_codex_model(self, metadata: dict[str, Any] | None) -> str | None:
        """Return a codex model id from metadata. Same non-validating shape
        as Claude; the codex CLI is the source of truth."""
        if not metadata:
            return None
        value = metadata.get("model")
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None

    def _extract_opencode_model(self, metadata: dict[str, Any] | None) -> str | None:
        if not metadata:
            return None

        value = metadata.get("model") or metadata.get("opencode_model")
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None

    def _extract_codex_acp_command(self, metadata: dict[str, Any] | None) -> str | None:
        if not metadata:
            return None
        value = metadata.get("codex_acp_command") or metadata.get("codexAcpCommand")
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None

    def _extract_codex_auth_method(self, metadata: dict[str, Any] | None) -> str | None:
        if not metadata:
            return None
        value = metadata.get("auth_method") or metadata.get("codex_auth_method")
        if not isinstance(value, str):
            return None
        normalized = value.strip().lower()
        if normalized in {"chatgpt", "codex-api-key", "openai-api-key"}:
            return normalized
        return None

    def _validate_session_metadata(
        self, agent: str, metadata: dict[str, Any] | None
    ) -> None:
        """Eagerly run per-agent structural validation.

        Called before any filesystem / install / Popen work so the daemon
        returns a clean `{"error": ...}` synchronously on bad metadata
        (plans/new-session-model-selection.md §3.9).
        """
        self._extract_permission_mode(metadata, agent=agent)
        if agent == "claude":
            self._extract_thinking_effort(metadata)
        elif agent == "codex":
            self._extract_reasoning_effort(metadata)

    def _extract_enable_thinking(self, metadata: dict[str, Any] | None) -> bool:
        if not metadata:
            return True
        value = metadata.get("enable_thinking")
        if value is None:
            return True
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() not in {"false", "0", "no", "off"}
        return bool(value)

    def _session_stderr_path(self, session_id: str) -> Path:
        """On-disk stderr log for a spawned headless session."""
        return Path.home() / ".vicoa" / "session_stderr" / f"{session_id}.log"

    def _open_session_stderr(self, session_id: str):
        """Open a per-session file for the spawned child's stderr.

        Replaces ``stderr=DEVNULL`` so a headless runner that dies during
        startup (rejected model, missing dependency, auth failure) leaves its
        traceback on disk instead of vanishing — the single biggest reason a
        codex spawn shows up as ``instance_never_registered`` with no clue why.
        A plain file (not the daemon's inherited pipes) preserves the desktop
        survival property: the child holds its own dup'd fd and outlives a
        daemon/app exit. Falls back to DEVNULL if the path can't be opened, so
        diagnostics can never block a spawn. Mirrors Paseo's codex app-server
        transport, which buffers child stderr and folds it into the failure it
        surfaces.
        """
        try:
            path = self._session_stderr_path(session_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            return open(path, "wb")
        except Exception as exc:  # noqa: BLE001 - diagnostics must never block spawn
            logger.debug("could not open stderr log for %s: %s", session_id, exc)
            return subprocess.DEVNULL

    def _read_session_stderr_tail(self, session_id: str, max_bytes: int = 4000) -> str:
        """Last few KB of a session's captured stderr, for crash diagnostics."""
        try:
            path = self._session_stderr_path(session_id)
            if not path.exists():
                return ""
            data = path.read_bytes()[-max_bytes:]
            return data.decode("utf-8", errors="replace").strip()
        except Exception:  # noqa: BLE001 - best-effort read
            return ""

    def _monitor_session_process(
        self,
        *,
        request_id: str,
        session_id: str,
        process: subprocess.Popen[bytes],
    ) -> None:
        """Monitor a running headless process and report its completion status."""
        try:
            return_code: int | None = None
            try:
                return_code = process.wait()
            except Exception as exc:
                self.report_request_status(
                    request_id,
                    "error",
                    agent_instance_id=session_id,
                    message=str(exc),
                )
                return
            if return_code == 0:
                self.report_request_status(
                    request_id,
                    "success",
                    agent_instance_id=session_id,
                    message="Session completed successfully",
                )
            else:
                stderr_tail = self._read_session_stderr_tail(session_id)
                message = f"Headless session exited with code {return_code}"
                if stderr_tail:
                    # The child's dying words — a startup crash (rejected model,
                    # missing dep, auth failure) that DEVNULL used to swallow.
                    # Log the full tail for post-mortem; append only its last
                    # line to the reported status so the message stays short.
                    logger.warning(
                        "[daemon] session %s exited with code %s; stderr tail:\n%s",
                        session_id,
                        return_code,
                        stderr_tail,
                    )
                    message = f"{message}: {stderr_tail.splitlines()[-1][:300]}"
                self.report_request_status(
                    request_id,
                    "error",
                    agent_instance_id=session_id,
                    message=message,
                )
                # Non-zero exit = SIGKILL / crash / SIGTERM-without-handler:
                # the process never ran its own cleanup, so the agent
                # instance is still stuck in a live status. Set a terminal
                # one as the fallback. Negative codes are signal deaths
                # (-15 SIGTERM, -9 SIGKILL) → KILLED; positive codes are
                # error exits → FAILED. Exit code 0 is intentionally NOT
                # handled here — a clean exit means the process already
                # set its own status during graceful shutdown.
                fallback_status = (
                    "KILLED"
                    if return_code is not None and return_code < 0
                    else "FAILED"
                )
                self._update_instance_status(session_id, fallback_status)
        finally:
            self._active_request_ids.discard(request_id)

    # ------------------------------------------------------------------
    # Remote terminal (pty-* over the cloud relay)
    # ------------------------------------------------------------------
    def _ensure_terminal_service(self) -> TerminalService:
        """Build the terminal service + output coalescer on first remote pty use."""
        with self._terminal_lock:
            if self._terminal_service is None:
                coalescer = TerminalOutputCoalescer(
                    on_output=self._emit_pty_output,
                    on_exit=self._emit_pty_exit,
                )
                service = TerminalService()
                # Reader threads → coalescer → upstream push. Coalescing folds a
                # burst into few frames so the relay's 256-frame outbox can't be
                # blown by a chatty terminal.
                service.bind(on_output=coalescer.handle, on_exit=coalescer.mark_exit)
                self._pty_coalescer = coalescer
                self._terminal_service = service
            return self._terminal_service

    def _emit_pty_output(self, pty_id: str, data: bytes) -> None:
        client = self._ws_client
        if client is not None:
            client.push_frame(
                {
                    "type": "pty-output",
                    "pty_id": pty_id,
                    "data": base64.b64encode(data).decode("ascii"),
                }
            )

    def _emit_pty_exit(self, pty_id: str, exit_code: int | None) -> None:
        client = self._ws_client
        if client is not None:
            client.push_frame(
                {"type": "pty-exit", "pty_id": pty_id, "exit_code": exit_code}
            )

    def _shutdown_terminals(self) -> None:
        """Kill any remote-terminal ptys and stop the coalescer (daemon wind-down)."""
        service = self._terminal_service
        coalescer = self._pty_coalescer
        if service is not None:
            try:
                service.shutdown()
            except Exception:
                logger.exception("terminal service shutdown failed")
        if coalescer is not None:
            try:
                coalescer.shutdown()
            except Exception:
                logger.exception("pty coalescer shutdown failed")

    def _handle_rpc_request(self, frame: dict[str, Any]) -> dict[str, Any]:
        """Dispatch an `rpc-request` frame to its handler (§2.8, Phase 5)."""
        method = frame.get("method")
        if method in PTY_RPC_METHODS:
            # Terminal opened on this machine from another device. Output is not
            # returned here — it streams back as `pty-output`/`pty-exit` frames
            # via the coalescer + `SpawnRequestWsClient.push_frame`.
            result = handle_pty_rpc(
                self._ensure_terminal_service(),
                str(method),
                frame.get("params") or {},
            )
            return (
                result
                if result is not None
                else {"error": f"unknown RPC method: {method}"}
            )
        if method == "spawn-session":
            return self.spawn_session_rpc(frame)
        if method == "list-files":
            from vicoa.rpc import file_ops

            return file_ops.list_files(**(frame.get("params") or {}))
        if method == "read-file":
            from vicoa.rpc import file_ops

            return file_ops.read_file(**(frame.get("params") or {}))
        if method == "stat-file":
            from vicoa.rpc import file_ops

            return file_ops.stat_file(**(frame.get("params") or {}))
        if method == "write-file":
            from vicoa.rpc import file_ops

            return file_ops.write_file(**(frame.get("params") or {}))
        if method == "scan-files":
            from vicoa.rpc import file_index

            return file_index.scan_files(**(frame.get("params") or {}))
        if method == "scan-commands":
            from vicoa.rpc import command_index

            return command_index.scan_commands(**(frame.get("params") or {}))
        if method == "list-skills":
            from vicoa.rpc import skills_ops

            return skills_ops.list_skills(**(frame.get("params") or {}))
        if method == "get-skill":
            from vicoa.rpc import skills_ops

            return skills_ops.get_skill(**(frame.get("params") or {}))
        if method == "install-skill":
            from vicoa.rpc import skills_ops

            return skills_ops.install_skill(**(frame.get("params") or {}))
        if method == "uninstall-skill":
            from vicoa.rpc import skills_ops

            return skills_ops.uninstall_skill(**(frame.get("params") or {}))
        if method == "git-status":
            from vicoa.rpc import git_ops

            return git_ops.git_status(**(frame.get("params") or {}))
        if method == "git-diff":
            from vicoa.rpc import git_ops

            return git_ops.git_diff(**(frame.get("params") or {}))
        if method == "git-log":
            from vicoa.rpc import git_ops

            return git_ops.git_log(**(frame.get("params") or {}))
        if method == "git-commit-files":
            from vicoa.rpc import git_ops

            return git_ops.git_commit_files(**(frame.get("params") or {}))
        if method == "git-commit-diff":
            from vicoa.rpc import git_ops

            return git_ops.git_commit_diff(**(frame.get("params") or {}))
        if method == "git-show-file":
            from vicoa.rpc import git_ops

            return git_ops.git_show_file(**(frame.get("params") or {}))
        if method == "git-stage":
            from vicoa.rpc import git_ops

            return git_ops.git_stage(**(frame.get("params") or {}))
        if method == "git-unstage":
            from vicoa.rpc import git_ops

            return git_ops.git_unstage(**(frame.get("params") or {}))
        if method == "git-commit":
            from vicoa.rpc import git_ops

            return git_ops.git_commit(**(frame.get("params") or {}))
        if method == "git-worktree-list":
            from vicoa.rpc import worktree_ops

            return worktree_ops.list_worktrees(**(frame.get("params") or {}))
        if method == "git-worktree-remove":
            from vicoa.rpc import worktree_ops

            params = frame.get("params") or {}
            # Teardown runs here (the app-driven removal), not in `remove_worktree`
            # itself, so the launch-failure `_rollback_worktree` — which calls
            # `remove_worktree` directly — never tears down a worktree whose setup
            # never ran. Best-effort + non-fatal: a bad teardown must not block
            # the removal.
            self._run_worktree_teardown_best_effort(params)
            return worktree_ops.remove_worktree(**params)
        if method == "worktree-trust-grant":
            from vicoa.rpc.worktree_trust import grant_repo_trust

            repo_dir = (frame.get("params") or {}).get("directory")
            if not isinstance(repo_dir, str) or not repo_dir.strip():
                return {"error": "worktree-trust-grant requires a directory"}
            grant_repo_trust(repo_dir)
            return {"ok": True}
        if method == "worktree-run-setup":
            return self._run_worktree_setup_background(frame.get("params") or {})
        if method == "scan-agents":
            return self.scan_agents_rpc()
        if method == "fetch-claude-usage":
            from vicoa.rpc import claude_usage

            return claude_usage.fetch_claude_usage(**(frame.get("params") or {}))
        return {"error": f"unknown RPC method: {method}"}

    def _supported_rpc_methods(self) -> list[str]:
        """RPC methods this daemon serves — advertised on connect AND routed in
        `_handle_rpc_request`. Single source so the two never drift apart.
        """
        return [
            "spawn-session",
            "list-files",
            "read-file",
            "stat-file",
            "write-file",
            "scan-files",
            "scan-commands",
            "list-skills",
            "get-skill",
            "install-skill",
            "uninstall-skill",
            "git-status",
            "git-diff",
            "git-log",
            "git-commit-files",
            "git-commit-diff",
            "git-show-file",
            "git-stage",
            "git-unstage",
            "git-commit",
            "git-worktree-list",
            "git-worktree-remove",
            "worktree-trust-grant",
            "worktree-run-setup",
            "scan-agents",
            "fetch-claude-usage",
            *PTY_RPC_METHODS,
        ]

    def scan_agents_rpc(self) -> dict[str, Any]:
        """Re-probe for installed agent CLIs and publish the fresh result.

        Detection otherwise runs exactly once, at registration (D3 — keeping
        `--version` subprocesses off the heartbeat loop), so an agent installed
        after the daemon started stays invisible. This is the only way to
        refresh it without a restart, which matters because a restart would
        kill the machine's live sessions.

        Not cheap: `find_npm_cli` falls back to an `npm config get prefix`
        subprocess per miss. Only ever call this on an explicit user action.

        Returns the fresh map directly so the caller doesn't need a cloud
        round-trip; the push to `machines.machine_metadata` is what lets *other*
        clients (web, mobile) converge.
        """
        agents = self._detect_available_agents()
        self.push_available_agents(agents)
        return {"available_agents": agents}

    def push_available_agents(self, agents: dict[str, bool]) -> None:
        """Refresh `available_agents` in the cloud machine row.

        Re-POSTs register, which is idempotent: the backend anchors on
        (user_id, hardware_id), so this updates the existing row in place —
        same machine_id, no dropped sessions, no WS reconnect — and its
        metadata merge replaces `available_agents` wholesale. It also
        broadcasts a `machine-update`, which is how other clients find out.

        Deliberately NOT `register_machine()`: that sends `cwd`, which the
        backend prepends to `recent_directories`, so reusing it would pollute
        the user's directory picker with the daemon's cwd on every scan.
        Heartbeat is not an option either — its metadata merge silently drops
        writes (missing `flag_modified`; see the plan doc).
        """
        if not self.machine_id:
            # Local-only daemon: no cloud row to refresh. The RPC's return
            # value is still correct.
            return
        try:
            response = self._post(
                "/api/v1/machines/register",
                {
                    "machine_id": self.machine_id,
                    "hardware_id": hardware_id_hash(),
                    "hostname": platform.node()[:255],
                    "platform": platform.platform()[:255],
                    "home_dir": str(Path.home()),
                    "metadata": {
                        "available_agents": agents,
                        "capabilities": self._capabilities(),
                    },
                },
            )
            response.raise_for_status()
        except Exception:
            # The caller already has the fresh map; failing to publish it is
            # not worth failing the scan over.
            logger.warning("failed to publish available_agents", exc_info=True)

    def spawn_session_rpc(self, frame: dict[str, Any]) -> dict[str, Any]:
        """Handle a `spawn-session` RPC: launch a headless agent, return its id.

        Phase 5 (websocket-migration §2.8): no machine_spawn_requests row is
        created — the AgentInstance the agent self-registers is the only record.
        The agent reads VICOA_SPAWN_SOURCE to record its launch source.

        Returns `{"agent_instance_id": ...}` on success, `{"error": ...}` on
        failure; the daemon WS client wraps either in an `rpc-response`.
        """
        params = frame.get("params") or {}
        # Set before the try so the except-path rollback can see it even if an
        # early validation step raises.
        worktree_info: dict[str, Any] | None = None
        try:
            directory = params.get("directory")
            if not isinstance(directory, str) or not directory.strip():
                raise ValueError("Invalid directory supplied")
            normalized_agent = self._normalize_agent(
                str(params.get("agent") or "claude")
            )
            metadata_raw = params.get("metadata")
            metadata = metadata_raw if isinstance(metadata_raw, dict) else None
            # Validate before any filesystem / install side effects so a bad
            # mode produces a clean RPC error, not a half-prepared directory.
            self._validate_session_metadata(normalized_agent, metadata)

            # Resuming reuses the existing instance id instead of minting a new
            # one, so the relaunched agent reattaches to the same row (and, for
            # Claude, to the transcript already filed under that id).
            # `resume.agent_session_id` is the agent's own conversation handle,
            # recorded by the previous run — a separate thing from the instance
            # id, and absent when the agent can't restore its history.
            #
            # Parsed and guarded here, alongside the other validation, so a
            # refused resume leaves no half-prepared worktree or directory
            # behind.
            resume = params.get("resume")
            resume_instance_id: str | None = None
            resume_agent_session_id: str | None = None
            if isinstance(resume, dict):
                raw_instance = resume.get("agent_instance_id")
                if isinstance(raw_instance, str) and raw_instance.strip():
                    resume_instance_id = raw_instance.strip()
                raw_agent_session = resume.get("agent_session_id")
                if isinstance(raw_agent_session, str) and raw_agent_session.strip():
                    resume_agent_session_id = raw_agent_session.strip()
                if resume_instance_id is None:
                    raise ValueError("resume requires agent_instance_id")

                # Archiving a session doesn't kill its agent (the archive
                # signal now stops the wrapper, but a resume can still race it,
                # or hit a --no-daemon session that never got the signal). The
                # agent is still there and usable, so don't spawn a second one
                # — that would attach two wrappers to the same instance and
                # every user message would get answered twice. Instead reopen
                # the row and hand the caller back the running session.
                if self._session_process_is_running(resume_instance_id):
                    logger.info(
                        "resume: session %s already has a running agent; "
                        "reopening instead of spawning a duplicate",
                        resume_instance_id,
                    )
                    self._update_instance_status(resume_instance_id, "AWAITING_INPUT")
                    return {
                        "agent_instance_id": resume_instance_id,
                        "already_running": True,
                    }

            # Optional worktree isolation: `worktree:{new:true}` forks a fresh
            # branch + checkout off the directory's HEAD and runs the agent
            # there instead. The target path is daemon-computed (never
            # app-supplied). A creation failure short-circuits before any
            # launch side effects.
            worktree_param = params.get("worktree")
            if isinstance(worktree_param, dict) and worktree_param.get("new") is True:
                from vicoa.rpc.worktree_ops import create_worktree

                created = create_worktree(directory)
                if "error" in created:
                    return {"error": f"Failed to create worktree: {created['error']}"}
                worktree_info = created
                expanded_directory = created["path"]
            else:
                expanded_directory = os.path.expanduser(directory.strip())
            os.makedirs(expanded_directory, exist_ok=True)

            install_error = self._check_agent_installation(normalized_agent)
            if install_error:
                raise RuntimeError(install_error)

            session_id = resume_instance_id or str(uuid4())

            env = os.environ.copy()
            env.setdefault("VICOA_API_KEY", self.api_key)
            env.setdefault(
                "VICOA_AGENT_TYPE", self._agent_display_name(normalized_agent)
            )
            env["VICOA_AGENT_INSTANCE_ID"] = session_id
            # Recorded as instance_metadata['source'] when the agent registers.
            env["VICOA_SPAWN_SOURCE"] = "app"

            command = self._build_headless_command(
                directory=expanded_directory,
                agent=normalized_agent,
                session_id=session_id,
                metadata=metadata,
                is_resuming=resume_instance_id is not None,
                agent_session_id=resume_agent_session_id,
            )
            self.send_heartbeat()
            # Detach the session's stdio from the daemon's. Without this the
            # child inherits the daemon's stdout/stderr; under the desktop shell
            # those are pipes owned by the Electron process, so quitting the app
            # closes them and the otherwise-detached session dies on its next
            # write (BrokenPipeError). stdin/stdout go to DEVNULL; stderr goes to
            # a per-session FILE (also owned by the OS, not the app's pipes, so
            # the child still outlives a daemon/app exit) so a startup crash is
            # captured instead of lost. The wrapper logs to its own file too.
            stderr_log = self._open_session_stderr(session_id)
            try:
                process = subprocess.Popen(
                    command,
                    cwd=expanded_directory,
                    env=env,
                    start_new_session=True,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=stderr_log,
                )
            finally:
                # The child holds its own dup'd fd now; drop the daemon's copy
                # (the DEVNULL fallback is a bare int with nothing to close).
                if not isinstance(stderr_log, int):
                    stderr_log.close()
        except (ValueError, RuntimeError) as exc:
            self._rollback_worktree(params.get("directory"), worktree_info)
            return {"error": str(exc)}
        except Exception as exc:  # noqa: BLE001 - any spawn failure -> rpc result
            self._rollback_worktree(params.get("directory"), worktree_info)
            return {"error": f"Failed to launch headless session: {exc}"}

        # Monitor with request_id="" — there is no spawn-request row, so the
        # monitor's status reports are no-ops, but the crash-fallback that sets
        # a terminal AgentInstance status still runs.
        Thread(
            target=self._monitor_session_process,
            kwargs={
                "request_id": "",
                "session_id": session_id,
                "process": process,
            },
            daemon=True,
        ).start()
        print(f"[daemon] RPC spawn-session launched {normalized_agent}: {session_id}")
        result: dict[str, Any] = {"agent_instance_id": session_id}
        if worktree_info is not None:
            # Returned only for immediate display; the agent self-registers with
            # project=worktree path, which stays the source of truth.
            result["worktree_path"] = worktree_info["path"]
            result["branch"] = worktree_info["branch"]
            # Setup commands the client runs — visibly — in the new session's
            # terminal (committed `vicoa.json` in the source repo working tree).
            # The daemon owns config discovery; the client only decides where to
            # show it. Best-effort: never fail a launched spawn over setup.
            try:
                from vicoa.rpc.worktree_setup import (
                    read_committed_config_commands,
                    worktree_env_vars,
                )
                from vicoa.rpc.worktree_trust import is_repo_trusted

                source_repo = str(params.get("directory") or "")
                setup_commands = read_committed_config_commands(source_repo, "setup")
                if setup_commands:
                    result["setup_commands"] = setup_commands
                    # The web auto-runs these in the terminal; `setup_trusted`
                    # tells it whether to run silently or ask first (a cloned
                    # repo's vicoa.json is untrusted until the user approves it).
                    result["setup_trusted"] = is_repo_trusted(source_repo)
                    # The terminal shell doesn't inherit the hook env the engine
                    # sets, so hand the client the same VICOA_* vars to export
                    # before it types setup — else `$VICOA_BRANCH_NAME` & co. are
                    # empty there. The daemon is the source of truth for these.
                    result["setup_env"] = worktree_env_vars(
                        worktree_path=str(worktree_info["path"]),
                        source_repo=source_repo,
                        branch_name=str(worktree_info["branch"]),
                    )
            except Exception as exc:  # noqa: BLE001 - setup resolve is best-effort
                print(f"[daemon] worktree setup resolve failed: {exc}")
        return result

    def _run_worktree_setup_background(self, params: dict[str, Any]) -> dict[str, Any]:
        """Run a worktree's setup commands in a background thread (no terminal).

        The fallback for clients that can't open a PTY (Windows today): the web
        can't stream setup into a terminal there, so it asks the daemon to run it
        and the output goes to the daemon log. Trust-gated on the source repo —
        the web grants trust (confirm dialog) before calling this. Returns at once;
        the run is best-effort and never blocks the caller.
        """
        worktree_path = params.get("worktree_path")
        directory = params.get("directory")
        if not isinstance(worktree_path, str) or not worktree_path.strip():
            return {"error": "worktree-run-setup requires a worktree_path"}
        if not isinstance(directory, str) or not directory.strip():
            return {"error": "worktree-run-setup requires a directory"}
        from vicoa.rpc.worktree_trust import is_repo_trusted

        if not is_repo_trusted(directory):
            return {"error": "untrusted"}

        def _run() -> None:
            try:
                from vicoa.rpc.worktree_setup import SetupEvent, run_worktree_setup

                def _log(event: SetupEvent) -> None:
                    if event.type == "output" and event.chunk:
                        print(f"[worktree-setup] {event.chunk}", end="")
                    elif event.type == "command_completed":
                        print(
                            f"[worktree-setup] $ {event.command} "
                            f"-> exit {event.exit_code}"
                        )

                result = run_worktree_setup(worktree_path, directory, on_event=_log)
                if result.results and not result.ok:
                    print(f"[daemon] worktree setup reported failures: {worktree_path}")
            except Exception as exc:  # noqa: BLE001 - background setup is best-effort
                print(f"[daemon] worktree background setup failed: {exc}")

        Thread(target=_run, daemon=True).start()
        return {"ok": True, "started": True}

    def _run_worktree_teardown_best_effort(self, params: dict[str, Any]) -> None:
        """Run a worktree's teardown commands before removal; swallow failures.

        Only the app-driven `git-worktree-remove` reaches here. Output goes to the
        daemon log (teardown is background, not shown in the session terminal like
        setup is). Any error is logged and dropped so the removal always proceeds.
        """
        worktree_path = params.get("worktree_path")
        repo_dir = params.get("cwd")
        if not isinstance(worktree_path, str) or not isinstance(repo_dir, str):
            return
        # Teardown runs unattended, so there is no confirm to show here — it only
        # fires when the repo is already trusted (the user approved setup at least
        # once). An untrusted repo's teardown is skipped, same as its setup.
        from vicoa.rpc.worktree_trust import is_repo_trusted

        if not is_repo_trusted(repo_dir):
            return
        try:
            from vicoa.rpc.worktree_setup import SetupEvent, run_worktree_teardown

            def _log(event: SetupEvent) -> None:
                if event.type == "output" and event.chunk:
                    print(f"[worktree-teardown] {event.chunk}", end="")
                elif event.type == "command_completed":
                    print(
                        f"[worktree-teardown] $ {event.command} "
                        f"-> exit {event.exit_code}"
                    )

            result = run_worktree_teardown(worktree_path, repo_dir, on_event=_log)
            if result.results and not result.ok:
                print(f"[daemon] worktree teardown reported failures: {worktree_path}")
        except Exception as exc:  # noqa: BLE001 - teardown is best-effort
            print(f"[daemon] worktree teardown failed: {exc}")

    def _rollback_worktree(
        self, repo_dir: Any, worktree_info: dict[str, Any] | None
    ) -> None:
        """Remove a worktree created for a spawn that then failed to launch.

        Best-effort: a rollback failure must not mask the original spawn error.
        """
        if not worktree_info or not isinstance(repo_dir, str):
            return
        try:
            from vicoa.rpc.worktree_ops import remove_worktree

            remove_worktree(repo_dir, worktree_info["path"], force=True)
        except Exception as exc:  # noqa: BLE001 - rollback is best-effort
            print(f"[daemon] worktree rollback failed: {exc}")

    def process_request(self, request: dict[str, Any]) -> None:
        request_id_raw = request.get("request_id")
        if not request_id_raw:
            print("[daemon] spawn request missing request_id; skipping")
            return

        request_id = str(request_id_raw)

        with self._active_request_ids_lock:
            if request_id in self._active_request_ids:
                print(
                    f"[daemon] skipping duplicate request {request_id} (already in progress)"
                )
                return
            self._active_request_ids.add(request_id)

        # _handed_off becomes True when the monitor thread takes ownership of the
        # request_id. The finally block releases it on every failure path so the
        # request can be retried; the monitor thread releases it on completion.
        _handed_off = False
        try:
            directory = request.get("directory")
            agent = str(request.get("agent", "claude"))
            try:
                normalized_agent = self._normalize_agent(agent)
            except ValueError as exc:
                self.report_request_status(
                    request_id,
                    "error",
                    message=f"Invalid agent '{agent}': {exc}",
                )
                return
            metadata_raw = request.get("metadata")
            metadata = metadata_raw if isinstance(metadata_raw, dict) else None
            try:
                self._validate_session_metadata(normalized_agent, metadata)
            except ValueError as exc:
                self.report_request_status(
                    request_id,
                    "error",
                    message=str(exc),
                )
                return

            if not isinstance(directory, str) or not directory.strip():
                self.report_request_status(
                    request_id,
                    "error",
                    message="Invalid directory supplied",
                )
                return

            expanded_directory = os.path.expanduser(directory.strip())
            try:
                os.makedirs(expanded_directory, exist_ok=True)
            except Exception as exc:
                self.report_request_status(
                    request_id,
                    "error",
                    message=f"Unable to prepare directory: {exc}",
                )
                return

            agent_install_error = self._check_agent_installation(normalized_agent)
            if agent_install_error:
                self.report_request_status(
                    request_id,
                    "error",
                    message=agent_install_error,
                )
                return

            env = os.environ.copy()
            env.setdefault("VICOA_API_KEY", self.api_key)
            env.setdefault(
                "VICOA_AGENT_TYPE", self._agent_display_name(normalized_agent)
            )

            session_id = str(request.get("agent_instance_id") or uuid4())
            env["VICOA_AGENT_INSTANCE_ID"] = session_id

            command = self._build_headless_command(
                directory=expanded_directory,
                agent=normalized_agent,
                session_id=session_id,
                metadata=metadata,
            )

            print(
                f"[daemon] launching {normalized_agent} session (request={request_id}) at {expanded_directory}"
            )

            # Send immediate heartbeat to show machine is active
            self.send_heartbeat()

            # Detach stdio so the session survives the daemon/app exit —
            # inheriting the daemon's Electron-owned stdout/stderr pipes kills
            # the detached child on quit (BrokenPipeError). stderr goes to a
            # per-session file (OS-owned, so still survives) to capture startup
            # crashes. See the matching note in spawn_session_rpc.
            stderr_log = self._open_session_stderr(session_id)
            try:
                process = subprocess.Popen(
                    command,
                    cwd=expanded_directory,
                    env=env,
                    start_new_session=True,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=stderr_log,
                )
            except Exception as exc:
                self.report_request_status(
                    request_id,
                    "error",
                    message=f"Failed to launch headless session: {exc}",
                )
                return
            finally:
                # The child holds its own dup'd fd now; drop the daemon's copy
                # (the DEVNULL fallback is a bare int with nothing to close).
                if not isinstance(stderr_log, int):
                    stderr_log.close()

            if not self._wait_for_process_ready(process):
                exit_code = process.poll()
                self.report_request_status(
                    request_id,
                    "error",
                    message=(
                        "Headless session failed to start"
                        if exit_code is None
                        else f"Headless process exited with code {exit_code}"
                    ),
                )
                return

            started = self.report_request_status(
                request_id,
                "started",
                agent_instance_id=session_id,
                message="Session started",
                retry_on_missing_agent=True,
                retry_timeout=30.0,
            )

            if not started:
                print(
                    f"[daemon] failed to mark request {request_id} as started; terminating session"
                )
                try:
                    process.terminate()
                    process.wait(timeout=5)
                except Exception:
                    try:
                        process.kill()
                    except Exception:
                        pass
                self.report_request_status(
                    request_id,
                    "error",
                    message="Failed to start headless session",
                )
                return

            # Launch monitor thread so we can continue polling
            session_thread = Thread(
                target=self._monitor_session_process,
                kwargs={
                    "request_id": request_id,
                    "session_id": session_id,
                    "process": process,
                },
                daemon=True,
            )
            session_thread.start()
            print(
                f"[daemon] session {session_id} running in background, continuing to poll for requests"
            )
            _handed_off = True
        finally:
            if not _handed_off:
                self._active_request_ids.discard(request_id)

    def _wait_for_process_ready(
        self,
        process: subprocess.Popen[bytes],
        *,
        timeout: float = 5.0,
        interval: float = 0.1,
    ) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if process.poll() is not None:
                return False
            time.sleep(interval)
        return True

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------
    def run(self) -> None:
        try:
            self.register_machine()
            # Renew the credential in the background now that registration has
            # proven the session works. daemon=True so it never blocks exit;
            # the finally below wakes it out of its long sleep.
            Thread(target=self._renewal_loop, name="key-renewal", daemon=True).start()
            self.send_heartbeat()
            self._catchup_poll()
            self._listen_for_spawn_requests()
        except AuthenticationError:
            # A 401 on a main-thread REST call (startup register/heartbeat, or
            # the SSE GET). Background heartbeat-thread 401s instead set
            # _fatal_auth and stop the stream, surfacing via the check below.
            self._fatal_auth.set()
        except KeyboardInterrupt:
            print("[daemon] shutting down")
            return
        finally:
            self._stop_renewal.set()

        if self._fatal_auth.is_set():
            self._handle_fatal_auth()

    def _listen_for_spawn_requests(self) -> None:
        """Dispatch to the WebSocket listener when configured, else SSE."""
        if self.ws_url:
            self._ws_listen_for_spawn_requests()
        else:
            self._sse_listen_for_spawn_requests()

    def _ws_listen_for_spawn_requests(self) -> None:
        """Receive spawn requests over /ws (websocket-migration §4 Phase 2).

        A `spawn-request` frame is a wake-up only — the request is still
        claimed atomically over REST via `_catchup_poll`, exactly as on SSE.
        The WS client owns its own full-jitter reconnect loop (§2.10), so the
        REST heartbeat just runs alongside it on a background thread.
        """
        stop_heartbeat = Event()

        client = SpawnRequestWsClient(
            ws_url=str(self.ws_url),
            api_key=self.api_key,
            machine_id=str(self.machine_id),
            cli_version=self.cli_version,
            on_spawn_request=self._catchup_poll,
            on_connect=self._catchup_poll,
            on_rpc_request=self._handle_rpc_request,
            rpc_methods=self._supported_rpc_methods(),
            # Skill install/uninstall mutate the on-disk skills dir; route them
            # through the single ordered worker so two writes can't interleave.
            ordered_rpc_methods=sorted(
                PTY_ORDERED_METHODS | {"install-skill", "uninstall-skill"}
            ),
        )
        # Publish the client so ``request_stop()`` (desktop shutdown, another
        # thread) can interrupt the blocking reconnect loop; if the stop
        # request already landed while register/heartbeat/catchup were still
        # running, honour it before entering the loop.
        self._ws_client = client
        if self._stop_requested.is_set():
            client.stop()

        def _heartbeat_loop() -> None:
            while not stop_heartbeat.wait(1):
                if time.time() - self._last_heartbeat_sent >= self.heartbeat_interval:
                    try:
                        self.send_heartbeat()
                    except AuthenticationError:
                        # The WS client owns its own reconnect loop, so a dead
                        # credential never surfaces there — the heartbeat is the
                        # authoritative stopper. _fatal_auth is already set;
                        # stop the client so client.run() returns and run()
                        # flags + exits.
                        client.stop()
                        return

        hb_thread = Thread(target=_heartbeat_loop, daemon=True)
        hb_thread.start()

        try:
            client.run()
        finally:
            self._ws_client = None
            stop_heartbeat.set()
            client.stop()
            # Reap any remote-terminal ptys so a clean shutdown doesn't orphan
            # a user's shell (its running command included, via kill_group).
            self._shutdown_terminals()

    def _sse_listen_for_spawn_requests(self) -> None:
        _BACKOFF = [0, 1, 2, 4, 8, 8, 8]
        attempt = 0
        # Stop reconnecting once a 401 marks the credential dead — the broad
        # ``except`` below would otherwise treat the AuthenticationError as a
        # transient drop and back off forever. ``run()`` then flags + exits.
        while not self._fatal_auth.is_set():
            try:
                self._sse_connect_and_process()
                attempt = 0
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                logger.warning(f"Connection lost: {exc}")
                self._catchup_poll()
                delay = _BACKOFF[min(attempt, len(_BACKOFF) - 1)]
                attempt += 1
                if delay:
                    time.sleep(delay)

    def _sse_connect_and_process(self) -> None:
        import sseclient

        stop_heartbeat = False

        def _heartbeat_loop() -> None:
            while not stop_heartbeat:
                time.sleep(1)
                if stop_heartbeat:
                    break
                now = time.time()
                if now - self._last_heartbeat_sent >= self.heartbeat_interval:
                    self.send_heartbeat()

        hb_thread = Thread(target=_heartbeat_loop, daemon=True)
        hb_thread.start()

        try:
            url = f"{self.base_url}/api/v1/machines/{self.machine_id}/spawn-requests/stream"
            # 35s read timeout: server heartbeat is every 15s, so 2 missed heartbeats
            # raises requests.Timeout — the outer reconnect loop then fires immediately
            # rather than letting the connection silently hang on a dead socket.
            with self.session.get(url, stream=True, timeout=(10, 35)) as response:
                self._raise_for_auth(response)
                response.raise_for_status()
                client = sseclient.SSEClient(response)  # pyright: ignore[reportArgumentType]
                for event in client.events():
                    if event.event == "spawn_request":
                        # Treat SSE as a wake-up signal only. Claim via the
                        # /next poll endpoint so the request is atomically
                        # marked "claimed" in the DB before we process it.
                        # This prevents _catchup_poll from re-delivering the
                        # same request while process_request is still running.
                        # Submit to self._spawn_executor so the SSE consumer
                        # loop is never blocked by process_request's worst-case
                        # 35 s runtime (_wait_for_process_ready + retry loop).
                        claimed = self.poll_for_requests()
                        if claimed is None:
                            print("[daemon] no pending requests found in DB")
                        while claimed:
                            self._spawn_executor.submit(self.process_request, claimed)
                            claimed = self.poll_for_requests()
        finally:
            stop_heartbeat = True

    def _catchup_poll(self) -> None:
        """Claim any requests that arrived while SSE was disconnected."""
        request = self.poll_for_requests()
        if request is None:
            return
        while request:
            print(
                f"[daemon] catchup: found pending request {request.get('request_id')}"
            )
            self._spawn_executor.submit(self.process_request, request)
            request = self.poll_for_requests()


def run_daemon(
    *,
    api_key: str,
    base_url: str,
    poll_interval: int = DEFAULT_POLL_INTERVAL_SECONDS,
    heartbeat_interval: int = DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
    cli_version: str | None = None,
    ws_url: str | None = None,
) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    daemon = MachineDaemon(
        api_key=api_key,
        base_url=base_url,
        poll_interval=poll_interval,
        heartbeat_interval=heartbeat_interval,
        cli_version=cli_version,
        # The `/ws` endpoint shares host:port with the agent-facing REST API
        # (websocket-migration §2.1), so derive it from base_url by default —
        # one URL covers production (agents.vicoa.ai) and local dev
        # (localhost:8080). `VICOA_WS_URL` overrides when host differs.
        ws_url=ws_url or os.getenv("VICOA_WS_URL") or derive_ws_url(base_url),
    )
    daemon.run()
