"""Claude wrapper heartbeat: a 404 on its own instance is terminal.

The wrapper heartbeats ``POST /api/v1/agents/instances/{id}/heartbeat`` every
30s. When the row is gone (e.g. the owning user was deleted while Claude is
running), the endpoint returns 404 — *not* 401, so PR #45's wrapper-side
``_drop_vicoa_link`` doesn't fire. Without a special case the loop logs a
WARN every 30s forever (the 2026-06-17 noise the user observed).

Fix: a 404 on the wrapper's *own* instance is unambiguous — there is nothing
left to heartbeat against. The loop exits cleanly with a one-line INFO,
Claude itself keeps running (the human is at the terminal).

See plans/bugs/p0-agent-jwt-no-db-validation.md.
"""

from __future__ import annotations

import types

import pytest

from integrations.cli_wrappers.claude_code.claude_wrapper_v2_0 import ClaudeWrapper


class _FakeResp:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        self.text = ""


def _bare_wrapper() -> ClaudeWrapper:
    """Construct a wrapper without running ``__init__`` so we can drive
    ``_heartbeat_loop`` in isolation. Mirrors the pattern PR #45 uses for the
    wrapper unit tests."""
    w = ClaudeWrapper.__new__(ClaudeWrapper)
    w.log = lambda *_a, **_k: None  # type: ignore[method-assign]
    w.running = True
    w.base_url = "https://agents.example"
    w.agent_instance_id = "inst-1"
    w.heartbeat_interval = 30.0
    return w


def test_heartbeat_exits_silently_on_404(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A 404 on the wrapper's own instance heartbeat ends the loop with an
    INFO line, not a WARN — and the loop doesn't re-poll."""
    w = _bare_wrapper()
    logged: list[str] = []
    w.log = lambda msg: logged.append(msg)  # type: ignore[method-assign]
    posts = {"n": 0}

    def _post(*_a, **_k):
        posts["n"] += 1
        if posts["n"] >= 2:
            raise KeyboardInterrupt  # safety: a non-stopping loop ends here
        return _FakeResp(404)

    w.vicoa_client_sync = types.SimpleNamespace(
        session=types.SimpleNamespace(post=_post)
    )
    monkeypatch.setattr(
        "integrations.cli_wrappers.claude_code.claude_wrapper_v2_0.time.sleep",
        lambda *_a, **_k: None,
    )

    w._heartbeat_loop()  # must return after the first 404

    assert posts["n"] == 1  # did not keep pinging
    assert any("no longer exists" in m for m in logged)
    assert not any("[WARN]" in m for m in logged)


def test_heartbeat_keeps_pinging_on_transient_5xx(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 5xx is a transient backend error — the heartbeat must NOT exit (only
    404 is treated as terminal). Loop keeps going until ``running`` flips."""
    w = _bare_wrapper()
    posts = {"n": 0}

    def _post(*_a, **_k):
        posts["n"] += 1
        if posts["n"] >= 3:
            w.running = False  # clean exit after a couple of retries
        return _FakeResp(503)

    w.vicoa_client_sync = types.SimpleNamespace(
        session=types.SimpleNamespace(post=_post)
    )
    monkeypatch.setattr(
        "integrations.cli_wrappers.claude_code.claude_wrapper_v2_0.time.sleep",
        lambda *_a, **_k: None,
    )

    w._heartbeat_loop()

    assert posts["n"] >= 2  # kept pinging through the 5xx
