"""Interactive claude wrapper: a Vicoa 401 drops the link but keeps Claude.

For an interactive session a human is at the terminal, so a dead remote
credential must NOT destroy in-progress local work. The wrapper stops the link
threads (heartbeat / long-poll respin), tells the user once how to recover, and
leaves Claude running.

Rule (plans/todos/cli-401-fatal-auth-handling.md): human present -> drop link,
keep agent.
"""

from __future__ import annotations

import types

from integrations.cli_wrappers.claude_code.claude_wrapper_v2_0 import ClaudeWrapper


class _FakeResp:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        self.text = ""


def _bare_wrapper() -> ClaudeWrapper:
    w = ClaudeWrapper.__new__(ClaudeWrapper)
    w.log = lambda *a, **k: None  # type: ignore[method-assign]
    w.running = True
    w.child_pid = 4242
    w._vicoa_link_dropped = False  # set by __init__, which __new__ skips
    return w


def test_drop_vicoa_link_is_idempotent_and_keeps_agent(capsys) -> None:
    """Dropping the link prints the recovery hint once, never kills Claude
    (child_pid / running untouched), and is safe to call repeatedly (every
    subsequent 401 just no-ops)."""
    w = _bare_wrapper()

    w._drop_vicoa_link()
    w._drop_vicoa_link()
    w._drop_vicoa_link()

    out = capsys.readouterr().out
    assert out.count("vicoa --auth") == 1  # printed exactly once
    assert w.running is True  # Claude keeps running
    assert w.child_pid == 4242  # local process not killed


def test_heartbeat_drops_link_on_401_and_stops(monkeypatch) -> None:
    """A 401 heartbeat is fatal-auth: stop the heartbeat thread and drop the
    link, instead of logging a warning and pinging forever. Other 4xx/5xx stay
    transient. A sleep stub keeps the test fast / bounded."""
    w = _bare_wrapper()
    w.agent_instance_id = "inst-1"
    w.base_url = "https://agents.example"
    w.heartbeat_interval = 30.0

    posts = {"n": 0}

    def _post(*a, **k):
        posts["n"] += 1
        if posts["n"] >= 2:
            raise KeyboardInterrupt  # safety: a non-stopping loop ends here
        return _FakeResp(401)

    w.vicoa_client_sync = types.SimpleNamespace(
        session=types.SimpleNamespace(post=_post)
    )

    dropped = {"n": 0}
    w._drop_vicoa_link = lambda: dropped.__setitem__("n", dropped["n"] + 1)  # type: ignore[method-assign]

    monkeypatch.setattr(
        "integrations.cli_wrappers.claude_code.claude_wrapper_v2_0.time.sleep",
        lambda *_a, **_k: None,
    )

    w._heartbeat_loop()  # must return (not loop) once the 401 drops the link

    assert dropped["n"] == 1
    assert posts["n"] == 1  # stopped after the first 401, did not keep pinging


async def test_long_poll_drops_link_on_authentication_error() -> None:
    """The user-input long-poll runs on the SDK async client, which raises
    AuthenticationError on a 401. Its broad ``except Exception`` must not
    swallow that — it must drop the link (which stops the respin)."""
    w = _bare_wrapper()
    w.requested_input_messages = {"msg-1"}
    w.message_processor = types.SimpleNamespace(pending_input_message_id="msg-1")

    class _AsyncClient:
        async def _ensure_session(self):
            return None

        async def request_user_input(self, **k):
            from vicoa.sdk.exceptions import AuthenticationError

            raise AuthenticationError("401")

    w.vicoa_client_async = _AsyncClient()

    dropped = {"n": 0}
    w._drop_vicoa_link = lambda: dropped.__setitem__("n", dropped["n"] + 1)  # type: ignore[method-assign]

    await w.request_user_input_async("msg-1")

    assert dropped["n"] == 1
