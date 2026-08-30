"""Interactive amp wrapper: a mid-session Vicoa 401 drops the link, keeps Amp.

Amp already handles a 401 at startup (no agent running yet -> exit). Mid-session
the rule flips: a human is at the terminal, so a dead credential must drop the
remote link and tell the user once, without killing the running Amp process.

Rule (plans/todos/cli-401-fatal-auth-handling.md): human present -> drop link,
keep agent.
"""

from __future__ import annotations

from integrations.cli_wrappers.amp.amp import AmpWrapper
from vicoa.sdk.exceptions import AuthenticationError


def _bare_wrapper() -> AmpWrapper:
    w = AmpWrapper.__new__(AmpWrapper)
    w.log = lambda *a, **k: None  # type: ignore[method-assign]
    w.running = True
    w.child_pid = 5151
    w._vicoa_link_dropped = False  # set by __init__, which __new__ skips
    return w


def test_drop_vicoa_link_is_idempotent_and_keeps_agent(capsys) -> None:
    w = _bare_wrapper()

    w._drop_vicoa_link()
    w._drop_vicoa_link()

    out = capsys.readouterr().out
    assert out.count("vicoa --auth") == 1
    assert w.running is True
    assert w.child_pid == 5151


async def test_request_user_input_drops_link_on_authentication_error() -> None:
    """The user-input long-poll hits the SDK async client, which raises
    AuthenticationError on a 401. The broad ``except Exception`` must not
    swallow it — drop the link instead of re-polling the dead endpoint."""
    w = _bare_wrapper()
    w.requested_input_messages = set()

    class _AsyncClient:
        async def request_user_input(self, **k):
            raise AuthenticationError("401")

    w.vicoa_client_async = _AsyncClient()

    dropped = {"n": 0}
    w._drop_vicoa_link = lambda: dropped.__setitem__("n", dropped["n"] + 1)  # type: ignore[method-assign]

    await w.request_user_input("msg-1")

    assert dropped["n"] == 1
