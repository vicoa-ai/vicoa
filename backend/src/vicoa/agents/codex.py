import os
import platform
import signal
import subprocess
import sys
import uuid
import threading
import time
from pathlib import Path
from typing import Optional

from integrations.codex_helpers.initial_session_config import (
    build_initial_session_config_codex,
)
from vicoa.constants import DEFAULT_API_URL
from vicoa.sdk.client import VicoaClient
from vicoa.utils import get_project_path


def _terminal_status_for_exit_code(exit_code: int) -> str:
    if exit_code == 0:
        return "COMPLETED"
    if exit_code < 0:
        return "KILLED"
    return "FAILED"


def _platform_tag() -> tuple[str, str, str]:
    system = platform.system()
    machine = platform.machine().lower()

    if system == "Darwin":
        arch = "arm64" if machine in ("arm64", "aarch64") else "x64"
        ext = ""
        tag = f"darwin-{arch}"
    elif system == "Linux":
        arch = "x64" if machine in ("x86_64", "amd64") else machine
        ext = ""
        tag = f"linux-{arch}"
    elif system == "Windows":
        arch = "x64" if machine in ("amd64", "x86_64") else machine
        ext = ".exe"
        tag = f"win-{arch}"
    else:
        # Fallback for unknown
        arch = machine or "unknown"
        ext = ""
        tag = f"{system.lower()}-{arch}"
    return tag, ext, system


def _packaged_binary_path() -> Path:
    """Return packaged binary path inside the wheel, if present."""
    tag, ext, _ = _platform_tag()
    base = Path(__file__).resolve().parent.parent / "_bin" / "codex" / tag
    return base / f"codex{ext}"


def _env_binary_path() -> Optional[Path]:
    """Return a path from VICOA_CODEX_PATH if set.

    Accepts either a direct file path to the binary or a directory, in which case
    we append the platform-specific binary name (codex[.exe]).
    """
    p = os.environ.get("VICOA_CODEX_PATH")
    if not p:
        return None
    p = os.path.expanduser(p)
    path = Path(p)
    if path.is_dir():
        _, ext, _ = _platform_tag()
        return path / f"codex{ext}"
    return path


def _resolve_codex_binary() -> Path:
    # 1) explicit override via env var
    env_p = _env_binary_path()
    if env_p and env_p.exists():
        return env_p

    # 2) packaged in the wheel
    packaged = _packaged_binary_path()
    if packaged.exists():
        return packaged

    raise FileNotFoundError(
        "Codex binary not found.\n"
        "Set VICOA_CODEX_PATH to specify the binary path.\n"
        f"Otherwise, expected a packaged binary in the wheel at: {_packaged_binary_path()}\n\n"
        "To build in local vicoa repo:\n"
        "  cd src/integrations/cli_wrappers/codex/codex-rs && cargo build --release -p codex-cli\n"
        "The built binary will be at:\n"
        "  src/integrations/cli_wrappers/codex/codex-rs/target/release/codex\n"
        "Then set VICOA_CODEX_PATH to either the binary file or its directory."
    )


def run_codex(args, unknown_args, api_key: str) -> int:
    """Launch the Codex CLI binary and keep the agent session alive via heartbeat.

    Mirrors the Claude wrapper behavior by sending periodic heartbeats to the
    dashboard while the Codex subprocess is running.
    """
    try:
        bin_path = _resolve_codex_binary()
    except FileNotFoundError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)
    env = os.environ.copy()

    # Wire Vicoa env for the Rust client
    env["VICOA_API_KEY"] = api_key
    base_url = getattr(args, "base_url", None) or DEFAULT_API_URL
    if base_url:
        env["VICOA_API_URL"] = base_url

    # Get or create session ID
    session_id = getattr(args, "agent_instance_id", None) or env.get("VICOA_SESSION_ID")
    if not session_id:
        session_id = str(uuid.uuid4())
    env["VICOA_SESSION_ID"] = session_id

    # Register the agent instance with project_path and home_dir
    client: Optional[VicoaClient] = None
    try:
        client = VicoaClient(api_key=api_key, base_url=base_url)
        project_path = get_project_path(getattr(args, "cwd", None))

        # Seed session_config from CODEX_* env vars set by the daemon so the
        # mobile chat-header pill has values before the Rust bridge PATCHes
        # from the first TurnContext. Returns None when nothing is known —
        # the SDK omits the field and the server preserves any pre-staged
        # row value. See plans/inprogress/mid-session-mode-switching.md.
        initial_session_config = build_initial_session_config_codex()
        registration = client.register_agent_instance(
            agent_type="codex",
            transport="ws",
            agent_instance_id=session_id,
            name=getattr(args, "name", None),
            project=project_path,
            home_dir=str(Path.home()),
            session_config=initial_session_config,
        )
        session_id = registration.agent_instance_id
        env["VICOA_SESSION_ID"] = session_id
        # Note: The Codex binary will send its own session start message when it launches
    except Exception as e:
        print(f"[WARN] Failed to register agent instance: {e}")
        # Continue anyway - the Rust client might handle registration

    # Hold an open fd on ~/.vicoa/codex_wrapper/<session_id>.log so
    # ``vicoa ls`` can map this launcher's PID to its session UUID.
    # ``agent_processes._enrich_tui_agents_posix`` scans ``lsof`` output for
    # files matching ``~/.vicoa/<type>_wrapper/<uuid>.log`` and reads the
    # UUID from the filename — but the Rust codex binary that actually
    # writes that log is a *child* of this process, so without our own fd
    # the enrichment finds nothing and ``vicoa ls`` falls back to
    # ``pid:NNNN``. Append mode is concurrency-safe with the Rust writer
    # (POSIX atomic O_APPEND) and we never write from Python; the handle
    # is purely a presence marker that the kernel exposes to lsof.
    session_log_file = None
    try:
        log_dir = Path.home() / ".vicoa" / "codex_wrapper"
        log_dir.mkdir(parents=True, exist_ok=True)
        session_log_file = open(log_dir / f"{session_id}.log", "a")
    except Exception:
        pass

    # Ensure executable bit if running from packaged file on Unix
    if bin_path.is_file() and os.name != "nt":
        mode = os.stat(bin_path).st_mode
        if (mode & 0o111) == 0:
            try:
                os.chmod(bin_path, mode | 0o111)
            except PermissionError:
                print(
                    f"[ERROR] Codex binary is not executable and chmod failed (permission denied).\n"
                    f"Fix with: sudo chmod +x {bin_path}",
                    file=sys.stderr,
                )
                sys.exit(1)

    # Add the binary's directory to LD_LIBRARY_PATH so auditwheel-bundled
    # shared libs (e.g. libcap-<hash>.so) placed alongside the binary are found.
    if os.name != "nt":
        lib_dir = str(bin_path.parent)
        existing = env.get("LD_LIBRARY_PATH", "")
        env["LD_LIBRARY_PATH"] = f"{lib_dir}:{existing}" if existing else lib_dir

    cmd = [str(bin_path)]
    if unknown_args:
        cmd.extend(unknown_args)

    # Start a background heartbeat loop similar to the Claude wrapper.
    # This may 404 until the Codex process creates the instance; that's fine.
    stop_event = threading.Event()

    def _heartbeat_loop(
        api_key: str,
        base_url: Optional[str],
        agent_instance_id: str,
        interval: float = 30.0,
    ) -> None:
        try:
            client = VicoaClient(
                api_key=api_key,
                base_url=(base_url or DEFAULT_API_URL),
            )
            session = client.session
            url = (base_url or DEFAULT_API_URL).rstrip(
                "/"
            ) + f"/api/v1/agents/instances/{agent_instance_id}/heartbeat"

            import random

            time.sleep(random.uniform(0, 2.0))
            while not stop_event.is_set():
                try:
                    resp = session.post(url, timeout=10)
                    _ = resp.status_code  # ignore; 404 expected until instance exists
                except Exception:
                    pass

                # Sleep with jitter; ensure a minimum reasonable delay
                delay = interval + random.uniform(-2.0, 2.0)
                if delay < 5:
                    delay = 5
                end_time = time.time() + delay
                while time.time() < end_time and not stop_event.is_set():
                    time.sleep(0.1)
        except Exception:
            # Never let heartbeat failures crash the launcher
            pass

    hb_thread = threading.Thread(
        target=_heartbeat_loop,
        args=(api_key, base_url, session_id),
        daemon=True,
    )
    hb_thread.start()

    # Forward SIGTERM/SIGHUP to the codex child as SIGINT so a ``vicoa stop``
    # triggers the binary's normal Ctrl+C exit path (clean terminal restore,
    # resume hint) AND lets the ``finally`` block below run end_session.
    # Without these handlers Python's default SIGTERM disposition terminates
    # the launcher immediately — finally never runs, the session row stays
    # ACTIVE, and the codex child is orphaned to be reaped by init.
    proc: Optional[subprocess.Popen] = None

    def _forward_term_to_codex(sig: int, _: object) -> None:
        if proc is None or proc.poll() is not None:
            return
        try:
            proc.send_signal(signal.SIGINT)
            print(
                f"[INFO] Received signal {sig}; forwarding SIGINT to codex",
                file=sys.stderr,
            )
        except Exception:
            pass

    old_term_handler = signal.signal(signal.SIGTERM, _forward_term_to_codex)
    old_hup_handler = signal.signal(signal.SIGHUP, _forward_term_to_codex)

    exit_code = 0
    try:
        proc = subprocess.Popen(cmd, env=env)
        try:
            exit_code = proc.wait()
        except KeyboardInterrupt:
            # Terminal driver already SIGINTed the child via the foreground
            # process group; just bound the wait so a stuck child can't hang
            # our cleanup.
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
    finally:
        # Restore prior handlers so any signal arriving during cleanup
        # routes to whatever the caller installed (usually default).
        try:
            signal.signal(signal.SIGTERM, old_term_handler)
            signal.signal(signal.SIGHUP, old_hup_handler)
        except Exception:
            pass
        # Signal heartbeat thread to exit and join briefly
        stop_event.set()
        try:
            hb_thread.join(timeout=2.0)
        except Exception:
            pass

        # Release the lsof-marker fd so a quick restart in the same session
        # doesn't briefly show two open handles.
        if session_log_file is not None:
            try:
                session_log_file.close()
            except Exception:
                pass

        if client and session_id:
            final_status = _terminal_status_for_exit_code(exit_code)
            try:
                if final_status == "COMPLETED":
                    client.end_session(session_id)
                else:
                    client.update_agent_instance_status(session_id, final_status)
            except Exception as e:
                print(
                    f"[WARN] Failed to finalize Codex session with status {final_status}: {e}",
                    file=sys.stderr,
                )
            finally:
                try:
                    client.close()
                except Exception:
                    pass

    return exit_code
