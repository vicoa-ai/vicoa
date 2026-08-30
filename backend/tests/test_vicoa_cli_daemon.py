from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path
import signal
from typing import Any

from vicoa import cli
from vicoa import machine_daemon


def test_ensure_background_daemon_running_skips_when_existing(monkeypatch, tmp_path):
    state_path = tmp_path / "daemon_state.json"
    launched = False

    def fake_popen(*args, **kwargs):
        nonlocal launched
        launched = True
        raise AssertionError("daemon should not start when already running")

    monkeypatch.setattr(
        machine_daemon, "find_running_daemon_pid", lambda *_args, **_kw: 321
    )
    monkeypatch.setattr(machine_daemon.subprocess, "Popen", fake_popen)

    started = machine_daemon.ensure_background_daemon_running(
        api_key="test-key",
        base_url="https://api.vicoa.ai",
        cwd="/tmp/project",
        state_path=state_path,
    )

    assert started is machine_daemon.DaemonStartResult.ALREADY_RUNNING
    assert launched is False


def test_ensure_background_daemon_running_launches_and_persists_pid(
    monkeypatch, tmp_path
):
    state_path = tmp_path / "daemon_state.json"
    captured: dict[str, Any] = {}

    class DummyProcess:
        pid = 456

    def fake_popen(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return DummyProcess()

    monkeypatch.setattr(
        machine_daemon, "find_running_daemon_pid", lambda *_args, **_kw: None
    )
    monkeypatch.setattr(machine_daemon.subprocess, "Popen", fake_popen)

    started = machine_daemon.ensure_background_daemon_running(
        api_key="test-key",
        base_url="https://api.vicoa.ai",
        cwd="/tmp/project",
        state_path=state_path,
    )

    assert started is machine_daemon.DaemonStartResult.SPAWNED
    assert captured["command"] == [
        machine_daemon.sys.executable,
        "-m",
        "vicoa.cli",
        "daemon",
        "--api-key",
        "test-key",
        "--base-url",
        "https://api.vicoa.ai",
    ]
    kwargs = captured["kwargs"]
    assert kwargs["cwd"] == "/tmp/project"
    assert kwargs["stdout"] is machine_daemon.subprocess.DEVNULL
    assert kwargs["stderr"] is machine_daemon.subprocess.DEVNULL
    assert kwargs["stdin"] is machine_daemon.subprocess.DEVNULL

    saved_state = json.loads(state_path.read_text())
    # Multi-daemon shape: PID is stored under the per-base-url entry, not at
    # the top level.
    assert saved_state["daemons"]["https://api.vicoa.ai"]["daemon_pid"] == 456


def test_ensure_background_daemon_running_returns_auth_invalid_when_flagged(
    monkeypatch, tmp_path
):
    """When the last daemon flagged the credential dead (``auth_invalid_at``)
    and the current key still matches the stored fingerprint, don't respawn a
    doomed daemon — return AUTH_INVALID so the caller can print the
    disconnected message once. Re-auth (new key) wipes the entry, so this only
    fires for the same dead key."""
    from vicoa.machine_identity import api_key_fingerprint
    from vicoa.machine_state import write_daemon_entry

    state_path = tmp_path / "daemon_state.json"
    base_url = "https://api.vicoa.ai"
    api_key = "test-key"

    write_daemon_entry(
        base_url,
        {
            "machine_id": "mac-1",
            "api_key_fingerprint": api_key_fingerprint(api_key),
            "auth_invalid_at": "2026-06-14T00:00:00+00:00",
            "daemon_pid": None,
        },
        state_path,
    )

    def fake_popen(*args, **kwargs):
        raise AssertionError("must not spawn a daemon for a known-dead credential")

    monkeypatch.setattr(
        machine_daemon, "find_running_daemon_pid", lambda *_a, **_k: None
    )
    monkeypatch.setattr(machine_daemon.subprocess, "Popen", fake_popen)

    result = machine_daemon.ensure_background_daemon_running(
        api_key=api_key,
        base_url=base_url,
        cwd="/tmp/project",
        state_path=state_path,
    )

    assert result is machine_daemon.DaemonStartResult.AUTH_INVALID


def test_build_daemon_command():
    assert machine_daemon.build_daemon_command(
        api_key="test-key",
        base_url="https://api.vicoa.ai",
    ) == [
        machine_daemon.sys.executable,
        "-m",
        "vicoa.cli",
        "daemon",
        "--api-key",
        "test-key",
        "--base-url",
        "https://api.vicoa.ai",
    ]


def test_maybe_start_machine_daemon_uses_project_path(monkeypatch):
    captured: dict[str, object] = {}

    def fake_ensure_background_daemon_running(**kwargs):
        captured.update(kwargs)
        return True

    monkeypatch.setattr(
        cli,
        "ensure_background_daemon_running",
        fake_ensure_background_daemon_running,
    )

    args = Namespace(
        no_daemon=False,
        base_url="https://api.vicoa.ai",
        project_path="~/workspace/demo",
        cwd=None,
    )

    cli.maybe_start_machine_daemon(args, "test-key")

    assert captured == {
        "api_key": "test-key",
        "base_url": "https://api.vicoa.ai",
        "cwd": str(Path("~/workspace/demo").expanduser().resolve()),
    }


def test_maybe_start_machine_daemon_prints_disconnected_on_auth_invalid(
    monkeypatch, capsys
):
    """When the daemon refuses to spawn because the credential is flagged dead,
    the foreground launch must tell the user how to recover AND exit so the
    agent doesn't start a half-link session that would FK-violate on its first
    REST write. Originally this test asserted "agent still launches"; behavior
    changed 2026-06-18 after reproducing the 500-storm-on-agent-instance the
    half-link path produced."""
    import pytest

    monkeypatch.setattr(
        cli,
        "ensure_background_daemon_running",
        lambda **_kw: machine_daemon.DaemonStartResult.AUTH_INVALID,
    )

    args = Namespace(
        no_daemon=False,
        base_url="https://api.vicoa.ai",
        project_path=None,
        cwd=None,
    )

    with pytest.raises(SystemExit) as excinfo:
        cli.maybe_start_machine_daemon(args, "test-key")

    assert excinfo.value.code == 1
    out = capsys.readouterr().out
    assert "vicoa --auth" in out
    assert "disconnected" in out.lower()


def test_maybe_start_machine_daemon_silent_on_normal_spawn(monkeypatch, capsys):
    """A normal spawn prints no disconnected message."""
    monkeypatch.setattr(
        cli,
        "ensure_background_daemon_running",
        lambda **_kw: machine_daemon.DaemonStartResult.SPAWNED,
    )

    args = Namespace(
        no_daemon=False,
        base_url="https://api.vicoa.ai",
        project_path=None,
        cwd=None,
    )

    cli.maybe_start_machine_daemon(args, "test-key")

    assert "disconnected" not in capsys.readouterr().out.lower()


def test_maybe_start_machine_daemon_respects_no_daemon(monkeypatch):
    called = False

    def fake_ensure_background_daemon_running(**kwargs):
        nonlocal called
        called = True
        return True

    monkeypatch.setattr(
        cli,
        "ensure_background_daemon_running",
        fake_ensure_background_daemon_running,
    )

    args = Namespace(
        no_daemon=True,
        base_url="https://api.vicoa.ai",
        project_path=None,
        cwd=None,
    )

    cli.maybe_start_machine_daemon(args, "test-key")

    assert called is False


def test_update_machine_recent_directories_uses_launch_directory(monkeypatch, tmp_path):
    captured: dict[str, object] = {}

    class FakeClient:
        def __init__(self, *, api_key: str, base_url: str):
            captured["api_key"] = api_key
            captured["base_url"] = base_url

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def update_machine_recent_directory(
            self,
            machine_id: str,
            cwd: str,
            *,
            cli_version: str | None = None,
            python_version: str | None = None,
        ) -> None:
            captured["machine_id"] = machine_id
            captured["cwd"] = cwd
            captured["cli_version"] = cli_version
            captured["python_version"] = python_version

    # State-file lookup is exercised by tests in test_machine_state.py.
    # Here we just stub the resolved machine_id so this test focuses on the
    # cli function's call shape into VicoaClient.
    monkeypatch.setattr(cli, "read_machine_id", lambda _base_url: "machine-123")
    monkeypatch.setattr(cli, "get_current_version", lambda: "1.2.3")
    monkeypatch.setattr("vicoa.sdk.client.VicoaClient", FakeClient)

    args = Namespace(
        base_url="https://api.vicoa.ai",
        project_path=None,
        cwd="~/workspace/demo",
    )

    cli.update_machine_recent_directories(args, "test-key")

    assert captured == {
        "api_key": "test-key",
        "base_url": "https://api.vicoa.ai",
        "machine_id": "machine-123",
        "cwd": "~/workspace/demo",
        "cli_version": "1.2.3",
        "python_version": cli.platform.python_version(),
    }


def test_update_machine_recent_directories_skips_without_machine_id(monkeypatch):
    called = False

    class FakeClient:
        def __init__(self, *args, **kwargs):
            nonlocal called
            called = True

    monkeypatch.setattr(cli, "read_machine_id", lambda _base_url: None)
    monkeypatch.setattr("vicoa.sdk.client.VicoaClient", FakeClient)

    args = Namespace(
        base_url="https://api.vicoa.ai",
        project_path=None,
        cwd="~/workspace/demo",
    )

    cli.update_machine_recent_directories(args, "test-key")

    assert called is False


def test_update_machine_recent_directories_async_starts_background_thread(
    monkeypatch,
):
    captured: dict[str, object] = {}

    class FakeThread:
        def __init__(self, *, target, args, daemon, name):
            captured["target"] = target
            captured["args"] = args
            captured["daemon"] = daemon
            captured["name"] = name

        def start(self) -> None:
            captured["started"] = True

    monkeypatch.setattr(cli.threading, "Thread", FakeThread)

    args = Namespace(
        base_url="https://api.vicoa.ai",
        project_path=None,
        cwd="~/workspace/demo",
    )

    cli.update_machine_recent_directories_async(args, "test-key")

    assert captured == {
        "target": cli.update_machine_recent_directories,
        "args": (args, "test-key"),
        "daemon": True,
        "name": "vicoa-recent-directories-sync",
        "started": True,
    }


def test_stop_background_daemon_when_not_running(tmp_path):
    stopped, message = machine_daemon.stop_background_daemon(
        base_url="https://api.vicoa.ai",
        state_path=tmp_path / "daemon_state.json",
    )

    assert stopped is False
    assert message == "No active Vicoa connection."


def test_stop_background_daemon_clears_saved_pid(monkeypatch, tmp_path):
    state_path = tmp_path / "daemon_state.json"
    # Multi-daemon shape: PID lives under the per-base-url entry alongside
    # the registration's machine_id, which must survive across stop/start so
    # the daemon re-registers as the same machine.
    state_path.write_text(
        json.dumps(
            {
                "daemons": {
                    "https://api.vicoa.ai": {
                        "daemon_pid": 456,
                        "machine_id": "mac-123",
                    },
                }
            }
        )
    )

    calls: list[tuple[int, int]] = []
    pid_state = {"alive": True}

    monkeypatch.setattr(
        machine_daemon, "find_running_daemon_pid", lambda *_args, **_kw: 456
    )
    monkeypatch.setattr(
        machine_daemon,
        "_read_process_command",
        lambda pid: "python -m vicoa.cli daemon",
    )

    def fake_kill(pid: int, sig: int) -> None:
        calls.append((pid, sig))
        pid_state["alive"] = False

    monkeypatch.setattr(machine_daemon.os, "kill", fake_kill)
    monkeypatch.setattr(machine_daemon, "_pid_exists", lambda pid: pid_state["alive"])

    stopped, message = machine_daemon.stop_background_daemon(
        base_url="https://api.vicoa.ai",
        state_path=state_path,
    )

    assert stopped is True
    assert message == "Stopped Vicoa connection."
    assert calls == [(456, signal.SIGTERM)]
    saved_state = json.loads(state_path.read_text())
    # Entry survives because machine_id is preserved — only daemon_pid is
    # cleared, so the next `vicoa daemon` re-registers as the same machine.
    entry = saved_state["daemons"]["https://api.vicoa.ai"]
    assert "daemon_pid" not in entry
    assert entry["machine_id"] == "mac-123"


# --- backward-compat tests for users upgrading from the single-daemon CLI ----
#
# Pre-multi-daemon installs persist a flat state file:
#   {"daemon_pid": 12345, "machine_id": "mac-abc", "display_name": "Mac"}
# The new code must still find the running daemon, stop it cleanly, and
# preserve `machine_id` so the next `vicoa daemon` re-registers as the same
# machine on the backend — otherwise the mobile app's "Online" pill would
# detach from the upgraded daemon's heartbeats.

LEGACY_STATE = {
    "daemon_pid": 12345,
    "machine_id": "mac-legacy",
    "display_name": "Nick's Mac",
}


def test_legacy_state_find_running_daemon_pid(monkeypatch, tmp_path):
    """A pre-upgrade state file still resolves the running daemon for the
    default base_url, without needing a manual migration step."""
    state_path = tmp_path / "daemon_state.json"
    state_path.write_text(json.dumps(LEGACY_STATE))

    monkeypatch.setattr(machine_daemon, "_pid_exists", lambda pid: pid == 12345)
    monkeypatch.setattr(
        machine_daemon,
        "_read_process_command",
        lambda pid: "python -m vicoa.cli daemon",
    )

    pid = machine_daemon.find_running_daemon_pid(
        "https://agents.vicoa.ai", state_path=state_path
    )
    assert pid == 12345


def test_legacy_state_stop_preserves_machine_id(monkeypatch, tmp_path):
    """End-to-end upgrade path: stopping a daemon that has only the legacy
    flat state on disk leaves the new shape behind with machine_id intact."""
    state_path = tmp_path / "daemon_state.json"
    state_path.write_text(json.dumps(LEGACY_STATE))

    pid_state = {"alive": True}
    calls: list[tuple[int, int]] = []

    monkeypatch.setattr(machine_daemon, "_pid_exists", lambda pid: pid_state["alive"])
    monkeypatch.setattr(
        machine_daemon,
        "_read_process_command",
        lambda pid: "python -m vicoa.cli daemon",
    )

    def fake_kill(pid: int, sig: int) -> None:
        calls.append((pid, sig))
        pid_state["alive"] = False

    monkeypatch.setattr(machine_daemon.os, "kill", fake_kill)

    stopped, _ = machine_daemon.stop_background_daemon(
        base_url="https://agents.vicoa.ai", state_path=state_path
    )

    assert stopped is True
    assert calls == [(12345, signal.SIGTERM)]

    # On-disk shape is now the new format, legacy top-level keys are gone,
    # and the machine registration (machine_id + display_name) survives so
    # the next daemon launch reconnects as the same backend machine row.
    saved = json.loads(state_path.read_text())
    assert "daemon_pid" not in saved
    assert "machine_id" not in saved
    assert "display_name" not in saved
    default_entry = saved["daemons"]["https://agents.vicoa.ai"]
    assert "daemon_pid" not in default_entry
    assert default_entry["machine_id"] == "mac-legacy"
    assert default_entry["display_name"] == "Nick's Mac"


def test_legacy_state_read_machine_id_for_sdk(tmp_path):
    """The SDK reads machine_id without knowing the user upgraded — it
    must still resolve from a pre-upgrade flat state file when the client
    is talking to the default API URL."""
    from vicoa.machine_state import read_machine_id

    state_path = tmp_path / "daemon_state.json"
    state_path.write_text(json.dumps(LEGACY_STATE))

    # SDK call shape (sync + async clients): pass self.base_url.
    assert (
        read_machine_id("https://agents.vicoa.ai", state_path=state_path)
        == "mac-legacy"
    )


# --- migrate_legacy_flat_state: pre-multi-daemon upgrade migration ----------
#
# Pre-multi-daemon installs persisted a single flat {daemon_pid, machine_id,
# display_name} at the top level. The naive in-memory fallback in
# _get_daemons_section always buckets that machine_id under the default URL —
# which orphans the user's existing backend machine row when their last
# daemon was actually running against a custom --base-url. The smart on-disk
# migration here uses the legacy daemon's argv (when alive) to pick the right
# URL bucket, falling back to whatever URL the caller is currently using.


def test_migrate_legacy_flat_state_uses_live_pid_argv(monkeypatch, tmp_path):
    """Live legacy PID + extractable --base-url → that URL wins.

    The reporter's actual scenario: a user upgrades while their localhost
    daemon is still running. Migration must read the live PID's argv and
    bucket under http://localhost:8080 instead of the default URL.
    """
    state_path = tmp_path / "daemon_state.json"
    state_path.write_text(
        json.dumps(
            {
                "daemon_pid": 19612,
                "machine_id": "mac-localhost",
                "display_name": "Mac",
            }
        )
    )

    monkeypatch.setattr(machine_daemon, "_pid_exists", lambda pid: pid == 19612)
    monkeypatch.setattr(
        machine_daemon,
        "_read_process_command",
        # Real argv shape: argv[0] (interpreter), then the daemon entry, then
        # --api-key, then --base-url. The extractor only cares that
        # --base-url <value> appears somewhere.
        lambda pid: (
            "python -m vicoa.cli daemon --api-key SECRET "
            "--base-url http://localhost:8080"
        ),
    )

    # Caller passes a *different* fallback URL (the default) — proves the
    # live-PID signal genuinely overrides the fallback rather than just
    # agreeing with it by coincidence.
    machine_daemon.migrate_legacy_flat_state(
        "https://agents.vicoa.ai", state_path=state_path
    )

    saved = json.loads(state_path.read_text())
    assert "daemon_pid" not in saved, "legacy top-level keys must be stripped"
    assert "machine_id" not in saved
    assert "https://agents.vicoa.ai" not in saved["daemons"], (
        "legacy machine_id must NOT land under the fallback URL when the "
        "live PID's argv says otherwise"
    )
    entry = saved["daemons"]["http://localhost:8080"]
    assert entry == {
        "daemon_pid": 19612,
        "machine_id": "mac-localhost",
        "display_name": "Mac",
    }


def test_migrate_legacy_flat_state_falls_back_when_pid_dead(monkeypatch, tmp_path):
    """Legacy daemon already stopped before upgrade → bucket under whatever
    URL the caller (CLI command or the current daemon) is running against.

    This is the safest guess we can make without argv to inspect: most users
    consistently target the same URL, so the URL they're currently working
    with is almost always the URL their machine_id belongs to.
    """
    state_path = tmp_path / "daemon_state.json"
    state_path.write_text(json.dumps({"daemon_pid": 99999, "machine_id": "mac-prev"}))

    monkeypatch.setattr(machine_daemon, "_pid_exists", lambda pid: False)

    machine_daemon.migrate_legacy_flat_state(
        "http://localhost:8080", state_path=state_path
    )

    saved = json.loads(state_path.read_text())
    assert saved == {
        "daemons": {
            "http://localhost:8080": {
                "daemon_pid": 99999,
                "machine_id": "mac-prev",
            }
        }
    }


def test_migrate_legacy_flat_state_ignores_pid_reused_by_other_process(
    monkeypatch, tmp_path
):
    """The legacy PID happens to be alive but isn't a vicoa daemon anymore
    (the OS recycled it). Fall back to the caller's URL — don't trust an
    argv that won't be a vicoa daemon's."""
    state_path = tmp_path / "daemon_state.json"
    state_path.write_text(json.dumps({"daemon_pid": 4242, "machine_id": "mac-reused"}))

    monkeypatch.setattr(machine_daemon, "_pid_exists", lambda pid: True)
    # An unrelated process picked up the recycled PID — its command line
    # has no resemblance to a vicoa daemon.
    monkeypatch.setattr(
        machine_daemon, "_read_process_command", lambda pid: "/usr/bin/sshd -D"
    )

    machine_daemon.migrate_legacy_flat_state(
        "http://localhost:8080", state_path=state_path
    )

    saved = json.loads(state_path.read_text())
    assert "http://localhost:8080" in saved["daemons"]
    assert saved["daemons"]["http://localhost:8080"]["machine_id"] == "mac-reused"


def test_migrate_legacy_flat_state_is_idempotent(tmp_path):
    """Already in new shape → exact no-op. Adding the migration call at
    multiple entry points (cmd_machine_daemon, ensure_background_daemon_running,
    register_machine) must be free."""
    state_path = tmp_path / "daemon_state.json"
    original = {
        "daemons": {
            "http://localhost:8080": {
                "daemon_pid": 11111,
                "machine_id": "mac-already-migrated",
            }
        }
    }
    state_path.write_text(json.dumps(original))
    mtime_before = state_path.stat().st_mtime_ns

    machine_daemon.migrate_legacy_flat_state(
        "https://agents.vicoa.ai", state_path=state_path
    )

    # Idempotency check is sharper than "value equality": the file must not
    # have been rewritten at all, otherwise three call sites would each
    # spam an fsync.
    assert state_path.stat().st_mtime_ns == mtime_before
    assert json.loads(state_path.read_text()) == original


def test_migrate_legacy_flat_state_missing_file_is_noop(tmp_path):
    """No state file at all (fresh install) → no-op. Don't create an empty
    file just to look busy — the first real write will create it."""
    state_path = tmp_path / "daemon_state.json"

    machine_daemon.migrate_legacy_flat_state(
        "https://agents.vicoa.ai", state_path=state_path
    )

    assert not state_path.exists()


def test_migrate_legacy_flat_state_empty_legacy_state_is_noop(tmp_path):
    """A flat state with no legacy fields worth preserving is left alone —
    the next ``update_daemon_entry`` call will write a clean new-shape
    file when it has something to actually persist."""
    state_path = tmp_path / "daemon_state.json"
    state_path.write_text(json.dumps({"unrelated_key": "value"}))
    mtime_before = state_path.stat().st_mtime_ns

    machine_daemon.migrate_legacy_flat_state(
        "https://agents.vicoa.ai", state_path=state_path
    )

    assert state_path.stat().st_mtime_ns == mtime_before


def test_migrate_legacy_flat_state_live_pid_without_base_url_flag(
    monkeypatch, tmp_path
):
    """Live legacy PID is a vicoa daemon but its argv has no --base-url
    (theoretically possible if launched manually) → use the caller's
    fallback URL."""
    state_path = tmp_path / "daemon_state.json"
    state_path.write_text(
        json.dumps({"daemon_pid": 5555, "machine_id": "mac-flagless"})
    )

    monkeypatch.setattr(machine_daemon, "_pid_exists", lambda pid: True)
    monkeypatch.setattr(
        machine_daemon,
        "_read_process_command",
        lambda pid: "python -m vicoa.cli daemon --api-key SECRET",
    )

    machine_daemon.migrate_legacy_flat_state(
        "https://agents.vicoa.ai", state_path=state_path
    )

    saved = json.loads(state_path.read_text())
    assert saved["daemons"]["https://agents.vicoa.ai"]["machine_id"] == "mac-flagless"


def test_migrate_legacy_flat_state_base_url_equals_form(monkeypatch, tmp_path):
    """argv uses ``--base-url=URL`` rather than ``--base-url URL`` — both
    forms are valid argparse input. Extractor must handle both."""
    state_path = tmp_path / "daemon_state.json"
    state_path.write_text(json.dumps({"daemon_pid": 7777, "machine_id": "mac-equals"}))

    monkeypatch.setattr(machine_daemon, "_pid_exists", lambda pid: True)
    monkeypatch.setattr(
        machine_daemon,
        "_read_process_command",
        lambda pid: "python -m vicoa.cli daemon --base-url=http://localhost:8080",
    )

    machine_daemon.migrate_legacy_flat_state(
        "https://agents.vicoa.ai", state_path=state_path
    )

    saved = json.loads(state_path.read_text())
    assert "http://localhost:8080" in saved["daemons"]


# --- vicoa daemon --takeover: non-interactive replacement ---------------------
#
# The desktop (Electron) shell restarts the daemon in cloud mode after login.
# That spawn is non-interactive — if the user already runs `vicoa daemon` in a
# terminal for the same base URL, the normal collision path would block on the
# arrow-key prompt forever. `--takeover` stops the existing daemon through the
# exact same stop mechanics the interactive path uses (stop_background_daemon:
# SIGTERM -> wait -> SIGKILL fallback -> PID cleared, machine_id preserved)
# and then proceeds with normal startup. Without the flag, behavior is
# unchanged.

BASE_URL = "https://api.vicoa.ai"


def _daemon_args(**overrides) -> Namespace:
    base: dict[str, Any] = dict(
        base_url=BASE_URL,
        takeover=False,
        local_listener=False,
        local_only=False,
        local_port=None,
        poll_interval=5,
        heartbeat_interval=30,
        api_key="test-key",
    )
    base.update(overrides)
    return Namespace(**base)


def _patch_daemon_environment(monkeypatch, *, existing_pid: int | None) -> None:
    """Common cmd_machine_daemon surroundings, isolated from the real
    ~/.vicoa state file and any real credential lookup."""
    monkeypatch.setattr(cli, "migrate_legacy_flat_state", lambda _url: None)
    monkeypatch.setattr(cli, "find_running_daemon_pid", lambda _url: existing_pid)
    monkeypatch.setattr(cli, "ensure_api_key", lambda _args: "test-key")
    monkeypatch.setattr(cli, "get_current_version", lambda: "1.2.3")


def test_daemon_takeover_stops_existing_without_prompting(monkeypatch, capsys):
    """--takeover with a live same-base-url daemon: stop it via the shared
    stop path, never render the interactive prompt, then start normally."""
    order: list[str] = []
    captured: dict[str, Any] = {}
    _patch_daemon_environment(monkeypatch, existing_pid=4242)

    def _no_prompt(*_a, **_k):
        raise AssertionError("--takeover must never prompt")

    monkeypatch.setattr(cli, "_arrow_yes_no", _no_prompt)

    def fake_stop(*, base_url):
        order.append("stop")
        captured["stopped_base_url"] = base_url
        return True, "Stopped Vicoa connection."

    monkeypatch.setattr(cli, "stop_background_daemon", fake_stop)

    def fake_run_daemon(**kwargs):
        order.append("run")
        captured["run_daemon"] = kwargs

    monkeypatch.setattr(cli, "run_daemon", fake_run_daemon)

    cli.cmd_machine_daemon(_daemon_args(takeover=True))

    # Stop first, then normal startup — same order as the interactive path.
    assert order == ["stop", "run"]
    assert captured["stopped_base_url"] == BASE_URL
    assert captured["run_daemon"]["api_key"] == "test-key"
    assert captured["run_daemon"]["base_url"] == BASE_URL
    out = capsys.readouterr().out
    # The log must say what was stopped (pid + base URL) for the shell logs.
    assert "4242" in out
    assert "takeover" in out.lower()
    assert BASE_URL in out


def test_daemon_takeover_skips_stop_when_none_running(monkeypatch):
    """No collision -> --takeover is a no-op: no stop call, normal startup."""
    started: dict[str, Any] = {}
    _patch_daemon_environment(monkeypatch, existing_pid=None)

    def _no_stop(**_kw):
        raise AssertionError("nothing to take over; stop must not be called")

    monkeypatch.setattr(cli, "stop_background_daemon", _no_stop)
    monkeypatch.setattr(cli, "run_daemon", lambda **kwargs: started.update(kwargs))

    cli.cmd_machine_daemon(_daemon_args(takeover=True))

    assert started["api_key"] == "test-key"


def test_daemon_takeover_exits_when_stop_fails(monkeypatch, capsys):
    """If the existing daemon can't be stopped, exit 1 instead of racing it
    (two daemons for one base URL would fight over the state entry)."""
    import pytest

    _patch_daemon_environment(monkeypatch, existing_pid=4242)
    monkeypatch.setattr(
        cli,
        "stop_background_daemon",
        lambda **_kw: (False, "Failed to stop Vicoa connection."),
    )

    def _no_run(**_kw):
        raise AssertionError("must not start while the old daemon is alive")

    monkeypatch.setattr(cli, "run_daemon", _no_run)

    with pytest.raises(SystemExit) as excinfo:
        cli.cmd_machine_daemon(_daemon_args(takeover=True))

    assert excinfo.value.code == 1
    assert "Failed to stop existing daemon" in capsys.readouterr().out


def test_daemon_takeover_composes_with_local_listener(monkeypatch):
    """The desktop always passes --local-listener in cloud mode; --takeover
    must stop the collider and then boot the daemon+local-listener runner."""
    import vicoa.local_server.runner as local_runner

    order: list[str] = []
    captured: dict[str, Any] = {}
    _patch_daemon_environment(monkeypatch, existing_pid=777)
    monkeypatch.setenv("VICOA_LOCAL_NONCE", "aa" * 16)
    monkeypatch.delenv("VICOA_LOCAL_ORIGIN", raising=False)

    def _no_prompt(*_a, **_k):
        raise AssertionError("--takeover must never prompt")

    monkeypatch.setattr(cli, "_arrow_yes_no", _no_prompt)
    monkeypatch.setattr(
        cli,
        "stop_background_daemon",
        lambda **kw: (order.append("stop"), (True, "Stopped Vicoa connection."))[1],
    )

    def fake_run_with_listener(**kwargs):
        order.append("run")
        captured.update(kwargs)

    # cmd_machine_daemon imports this lazily from the module, so patching the
    # module attribute intercepts the call.
    monkeypatch.setattr(
        local_runner, "run_daemon_with_local_listener", fake_run_with_listener
    )

    cli.cmd_machine_daemon(
        _daemon_args(takeover=True, local_listener=True, local_port=45991)
    )

    assert order == ["stop", "run"]
    assert captured["api_key"] == "test-key"
    assert captured["base_url"] == BASE_URL
    settings = captured["settings"]
    assert settings.port == 45991
    assert settings.local_only is False
    assert settings.nonce == "aa" * 16


def test_daemon_without_takeover_still_prompts(monkeypatch, capsys):
    """No flag -> behavior unchanged: the interactive prompt decides, and a
    declined prompt leaves the existing daemon alone."""
    prompted: dict[str, Any] = {}
    _patch_daemon_environment(monkeypatch, existing_pid=4242)

    def fake_prompt(question: str) -> bool:
        prompted["question"] = question
        return False

    monkeypatch.setattr(cli, "_arrow_yes_no", fake_prompt)

    def _no_stop(**_kw):
        raise AssertionError("declined prompt must not stop the daemon")

    monkeypatch.setattr(cli, "stop_background_daemon", _no_stop)

    def _no_run(**_kw):
        raise AssertionError("declined prompt must not start a new daemon")

    monkeypatch.setattr(cli, "run_daemon", _no_run)

    cli.cmd_machine_daemon(_daemon_args())

    assert BASE_URL in prompted["question"]
    assert "vicoa stop daemon" in capsys.readouterr().out
