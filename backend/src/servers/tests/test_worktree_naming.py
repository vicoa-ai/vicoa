"""The server half of naming a new worktree from its spawn's prompt.

`start_worktree_naming` runs on every relayed `spawn-session`: it must touch
only spawns the daemon would otherwise name at random, mark them so the daemon
waits, and always answer that daemon — with the names, or with an empty frame
when naming failed, so the daemon stops waiting at once.
"""

import asyncio
from typing import cast

import pytest

from servers import worktree_naming
from shared.llms.session_names import SessionNames
from shared.websocket.connection_manager import Connection
from shared.websocket.rpc import RpcRouter


def _spawn(**overrides) -> dict:
    params: dict = {
        "directory": "~/projects/app",
        "agent": "claude",
        "worktree": {"new": True},
        "metadata": {"prompt": "Fix the Safari logout bug"},
    }
    params.update(overrides)
    return params


@pytest.fixture
def router(monkeypatch: pytest.MonkeyPatch) -> RpcRouter:
    fresh = RpcRouter()
    monkeypatch.setattr(worktree_naming, "rpc_router", fresh)
    monkeypatch.setattr(worktree_naming, "session_naming_configured", lambda: True)
    return fresh


class _FakeDaemon:
    """Stands in for the daemon's connection: records what is pushed to it."""

    def __init__(self) -> None:
        self.sent: list[dict] = []

    def enqueue(self, frame: dict) -> None:
        self.sent.append(frame)


def _daemon(router: RpcRouter) -> tuple[_FakeDaemon, list[dict]]:
    daemon = _FakeDaemon()
    router.register("u1", "m1", "spawn-session", cast(Connection, daemon))
    return daemon, daemon.sent


async def _drain() -> None:
    await asyncio.gather(*list(worktree_naming._tasks))


async def test_names_a_new_worktree_and_pushes_them_to_the_daemon(
    router: RpcRouter, monkeypatch: pytest.MonkeyPatch
):
    _, sent = _daemon(router)
    seen: list[str] = []

    def fake_generate(prompt: str) -> SessionNames:
        seen.append(prompt)
        return SessionNames(title="Fix Safari logout", branch="fix-safari-logout")

    monkeypatch.setattr(worktree_naming, "generate_session_names", fake_generate)
    params = _spawn()

    worktree_naming.start_worktree_naming("u1", "m1", params)
    await _drain()

    token = params["worktree"]["auto_name"]
    assert isinstance(token, str) and token
    assert seen == ["Fix the Safari logout bug"]
    assert sent == [
        {
            "type": "worktree-name",
            "token": token,
            "branch": "fix-safari-logout",
            "title": "Fix Safari logout",
        }
    ]


async def test_a_failed_naming_still_releases_the_daemon(
    router: RpcRouter, monkeypatch: pytest.MonkeyPatch
):
    _, sent = _daemon(router)

    def boom(prompt: str) -> SessionNames:
        raise RuntimeError("provider down")

    monkeypatch.setattr(worktree_naming, "generate_session_names", boom)
    params = _spawn()

    worktree_naming.start_worktree_naming("u1", "m1", params)
    await _drain()

    assert sent == [{"type": "worktree-name", "token": params["worktree"]["auto_name"]}]


@pytest.mark.parametrize(
    "params",
    [
        _spawn(worktree=None),
        _spawn(worktree={"new": False}),
        _spawn(worktree={"new": True, "name": "my-pick"}),
        _spawn(resume={"agent_instance_id": "i1"}),
        _spawn(metadata={"prompt": "   "}),
        _spawn(metadata=None),
    ],
)
async def test_leaves_every_other_spawn_alone(
    router: RpcRouter, monkeypatch: pytest.MonkeyPatch, params: dict
):
    _, sent = _daemon(router)
    monkeypatch.setattr(
        worktree_naming,
        "generate_session_names",
        lambda prompt: pytest.fail("named a spawn it should have left alone"),
    )
    before = repr(params)

    worktree_naming.start_worktree_naming("u1", "m1", params)
    await _drain()

    assert repr(params) == before
    assert sent == []


async def test_no_provider_means_no_wait(
    router: RpcRouter, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(worktree_naming, "session_naming_configured", lambda: False)
    params = _spawn()

    worktree_naming.start_worktree_naming("u1", "m1", params)

    assert "auto_name" not in params["worktree"]


async def test_an_initial_prompt_counts_too(
    router: RpcRouter, monkeypatch: pytest.MonkeyPatch
):
    _daemon(router)
    monkeypatch.setattr(
        worktree_naming,
        "generate_session_names",
        lambda prompt: SessionNames(title=None, branch="x-y"),
    )
    params = _spawn(metadata={"initial_prompt": "Do the thing"})

    worktree_naming.start_worktree_naming("u1", "m1", params)
    await _drain()

    assert "auto_name" in params["worktree"]
