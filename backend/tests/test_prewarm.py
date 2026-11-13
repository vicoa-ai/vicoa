"""Prewarmed sessions: the daemon's standby pool and how spawn-session adopts.

A `prewarm-session` launches the session a spawn would launch, with
``--standby`` and a stdin pipe; a matching `spawn-session` writes the prompt
down that pipe instead of starting cold. See vicoa/prewarm.py.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from vicoa import machine_daemon, prewarm
from vicoa.machine_daemon import MachineDaemon
from vicoa.prewarm import PrewarmPool, Standby


class _FakeStdin:
    def __init__(self) -> None:
        self.written = b""
        self.closed = False

    def write(self, data: bytes) -> int:
        if self.closed:
            raise ValueError("write to closed file")
        self.written += data
        return len(data)

    def flush(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True


class _FakeProcess:
    def __init__(self, pid: int = 4321) -> None:
        self.pid = pid
        self.stdin = _FakeStdin()
        self.exit_code: int | None = None

    def poll(self) -> int | None:
        return self.exit_code

    def wait(self, timeout: float | None = None) -> int:
        if self.exit_code is None:
            self.exit_code = 0  # it read end of file and left
        return self.exit_code

    def terminate(self) -> None:
        self.exit_code = -15

    def kill(self) -> None:
        self.exit_code = -9


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _launcher(processes: list[_FakeProcess]):
    def launch() -> tuple[str, Any]:
        process = _FakeProcess(pid=100 + len(processes))
        processes.append(process)
        return f"sid-{len(processes)}", process

    return launch


# ----- the pool -----


def test_a_standby_is_taken_once() -> None:
    pool = PrewarmPool()
    launched: list[_FakeProcess] = []
    pool.add("k", _launcher(launched))
    entry = pool.take("k")
    assert entry is not None and entry.session_id == "sid-1"
    assert pool.take("k") is None


def test_the_oldest_standby_is_evicted_past_capacity() -> None:
    discarded: list[tuple[str, str]] = []
    pool = PrewarmPool(
        capacity=2, on_discard=lambda e, why: discarded.append((e.session_id, why))
    )
    launched: list[_FakeProcess] = []
    for key in ("a", "b", "c"):
        pool.add(key, _launcher(launched))
    assert len(pool) == 2
    assert discarded == [("sid-1", "evicted")]
    assert launched[0].stdin.closed  # end of file: it exits unregistered


def test_a_re_request_keeps_the_standby_past_its_original_expiry() -> None:
    clock = _Clock()
    pool = PrewarmPool(ttl_seconds=180, clock=clock)
    launched: list[_FakeProcess] = []
    pool.add("k", _launcher(launched))
    clock.now += 170
    assert pool.refresh("k") is not None
    clock.now += 170  # 340s after launch, 170s after the refresh
    assert pool.take("k") is not None


def test_an_expired_or_dead_standby_is_dropped() -> None:
    clock = _Clock()
    discarded: list[str] = []
    pool = PrewarmPool(
        ttl_seconds=180, clock=clock, on_discard=lambda e, why: discarded.append(why)
    )
    launched: list[_FakeProcess] = []
    pool.add("old", _launcher(launched))
    pool.add("dead", _launcher(launched))
    launched[1].exit_code = 1
    clock.now += 181
    assert pool.take("old") is None
    assert pool.take("dead") is None
    assert sorted(discarded) == ["exited", "expired"]


def test_close_discards_everything() -> None:
    pool = PrewarmPool()
    launched: list[_FakeProcess] = []
    pool.add("a", _launcher(launched))
    pool.add("b", _launcher(launched))
    pool.close()
    assert len(pool) == 0
    assert all(p.stdin.closed for p in launched)


def test_send_go_writes_one_line_and_lets_go_of_the_pipe() -> None:
    process = _FakeProcess()
    assert prewarm.send_go(process, "fix the build") is True  # type: ignore[arg-type]
    assert json.loads(process.stdin.written) == {"prompt": "fix the build"}
    assert process.stdin.closed


def test_send_go_to_a_dead_standby_fails() -> None:
    process = _FakeProcess()
    process.exit_code = 1
    assert prewarm.send_go(process, "x") is False  # type: ignore[arg-type]


def test_the_key_masks_the_session_id_only() -> None:
    a = prewarm.standby_key(
        ["vicoa", "--session-id", "id-1", "--model", "m"], "id-1", "/p"
    )
    b = prewarm.standby_key(
        ["vicoa", "--session-id", "id-2", "--model", "m"], "id-2", "/p"
    )
    c = prewarm.standby_key(
        ["vicoa", "--session-id", "id-3", "--model", "n"], "id-3", "/p"
    )
    assert a == b != c
    assert prewarm.standby_key(["x"], "id", "/p") != prewarm.standby_key(
        ["x"], "id", "/q"
    )


def test_vm_stat_counts_reclaimable_pages() -> None:
    out = (
        "Mach Virtual Memory Statistics: (page size of 16384 bytes)\n"
        "Pages free:                               10.\n"
        "Pages active:                            500.\n"
        "Pages inactive:                           20.\n"
        "Pages speculative:                         5.\n"
        "Pages purgeable:                           1.\n"
    )
    assert prewarm.parse_vm_stat(out) == 36 * 16384
    assert prewarm.parse_vm_stat("garbage") is None


@pytest.mark.parametrize("value", ["0", "false", "off", "no"])
def test_the_env_switch_turns_prewarm_off(monkeypatch, value: str) -> None:
    monkeypatch.setenv(prewarm.PREWARM_ENV, value)
    assert prewarm.prewarm_disabled() is True


# ----- the daemon -----


@pytest.fixture(autouse=True)
def _home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    return tmp_path


@pytest.fixture
def daemon(monkeypatch: pytest.MonkeyPatch) -> MachineDaemon:
    monkeypatch.delenv(prewarm.PREWARM_ENV, raising=False)
    daemon = MachineDaemon(api_key="test-key", base_url="http://localhost:0")
    monkeypatch.setattr(daemon, "send_heartbeat", lambda: None)
    monkeypatch.setattr(daemon, "_check_agent_installation", lambda agent: None)
    monkeypatch.setattr(daemon, "_monitor_session_process", lambda **kw: None)
    monkeypatch.setattr(
        daemon, "_wait_for_registration", lambda session_id, process, **kw: None
    )
    monkeypatch.setattr(machine_daemon, "available_memory_bytes", lambda: 8 * 1024**3)
    return daemon


@pytest.fixture
def launches(daemon: MachineDaemon, monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    calls: list[dict[str, Any]] = []

    def fake_launch(command, *, cwd, env, session_id, stdin_pipe=False):
        process = _FakeProcess(pid=1000 + len(calls))
        calls.append(
            {
                "command": command,
                "cwd": cwd,
                "session_id": session_id,
                "stdin_pipe": stdin_pipe,
                "env_id": env.get("VICOA_AGENT_INSTANCE_ID"),
                "process": process,
            }
        )
        return process

    monkeypatch.setattr(daemon, "_launch_session_process", fake_launch)
    return calls


def _params(tmp_path: Path, **metadata: Any) -> dict[str, Any]:
    return {
        "directory": str(tmp_path),
        "agent": "claude",
        "metadata": {
            "model": "claude-haiku-5-5",
            "permission_mode": "default",
            **metadata,
        },
    }


def test_prewarm_launches_a_standby_with_a_stdin_pipe(
    daemon, launches, tmp_path
) -> None:
    result = daemon.prewarm_session_rpc({"params": _params(tmp_path, prompt="ignored")})
    assert result == {"status": "started"}
    [call] = launches
    assert call["stdin_pipe"] is True
    assert call["command"][-1] == "--standby"
    assert "--prompt" not in call["command"]
    assert call["env_id"] == call["session_id"]


def test_the_same_prewarm_twice_keeps_one_standby(daemon, launches, tmp_path) -> None:
    daemon.prewarm_session_rpc({"params": _params(tmp_path)})
    assert daemon.prewarm_session_rpc({"params": _params(tmp_path)}) == {
        "status": "warm"
    }
    assert len(launches) == 1


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"agent": "codex"}, "agent"),
        ({"worktree": {"new": True}}, "worktree"),
        ({"resume": {"agent_instance_id": "x"}}, "resume"),
        ({"directory": "/nonexistent/vicoa-prewarm-test"}, "directory"),
    ],
)
def test_prewarm_skips_what_it_cannot_warm(
    daemon, launches, tmp_path, change: dict, reason: str
) -> None:
    params = {**_params(tmp_path), **change}
    assert daemon.prewarm_session_rpc({"params": params}) == {"skipped": reason}
    assert launches == []


def test_prewarm_skips_when_turned_off_low_on_memory_or_logged_out(
    daemon, launches, tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv(prewarm.PREWARM_ENV, "0")
    assert daemon.prewarm_session_rpc({"params": _params(tmp_path)}) == {
        "skipped": "disabled"
    }
    monkeypatch.delenv(prewarm.PREWARM_ENV)

    monkeypatch.setattr(machine_daemon, "available_memory_bytes", lambda: 512 * 1024**2)
    assert daemon.prewarm_session_rpc({"params": _params(tmp_path)}) == {
        "skipped": "memory"
    }

    daemon._fatal_auth.set()
    assert daemon.prewarm_session_rpc({"params": _params(tmp_path)}) == {
        "skipped": "auth"
    }
    assert launches == []


def test_spawn_adopts_the_matching_standby(daemon, launches, tmp_path) -> None:
    daemon.prewarm_session_rpc({"params": _params(tmp_path)})
    [standby] = launches

    result = daemon.spawn_session_rpc(
        {"params": _params(tmp_path, prompt="fix the build")}
    )

    assert len(launches) == 1  # no cold launch
    assert result["agent_instance_id"] == standby["session_id"]
    assert result["prewarmed"] is True
    assert json.loads(standby["process"].stdin.written) == {"prompt": "fix the build"}
    assert len(daemon._prewarm) == 0


def test_a_spawn_with_other_settings_starts_cold_and_leaves_the_standby(
    daemon, launches, tmp_path
) -> None:
    daemon.prewarm_session_rpc({"params": _params(tmp_path)})
    result = daemon.spawn_session_rpc(
        {"params": {**_params(tmp_path, prompt="x"), "metadata": {"model": "other"}}}
    )
    assert len(launches) == 2
    assert "prewarmed" not in result
    assert launches[1]["stdin_pipe"] is False
    assert len(daemon._prewarm) == 1  # may belong to another composer


def test_a_standby_that_died_is_replaced_by_a_cold_start(
    daemon, launches, tmp_path
) -> None:
    daemon.prewarm_session_rpc({"params": _params(tmp_path)})
    launches[0]["process"].exit_code = 1
    result = daemon.spawn_session_rpc({"params": _params(tmp_path, prompt="x")})
    assert len(launches) == 2
    assert result["agent_instance_id"] == launches[1]["session_id"]
    assert "prewarmed" not in result


def test_a_resume_never_adopts(daemon, launches, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(daemon, "_session_process_is_running", lambda sid: False)
    daemon.prewarm_session_rpc({"params": _params(tmp_path)})
    params = {
        **_params(tmp_path, prompt="x"),
        "resume": {"agent_instance_id": "old-id"},
    }
    result = daemon.spawn_session_rpc({"params": params})
    assert result["agent_instance_id"] == "old-id"
    assert len(daemon._prewarm) == 1


def test_a_discarded_standby_leaves_no_stderr_file(daemon, tmp_path) -> None:
    path = daemon._session_stderr_path("sid-x")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("")
    daemon._forget_standby(
        Standby(key="k", session_id="sid-x", process=_FakeProcess(), expires_at=0),  # type: ignore[arg-type]
        "expired",
    )
    assert not path.exists()


def test_the_daemon_advertises_prewarm(daemon) -> None:
    assert "prewarm-session" in daemon._supported_rpc_methods()
