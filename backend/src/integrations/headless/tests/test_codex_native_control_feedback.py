"""After a mid-session model / effort / permission_mode change driven by
the mobile gear pill, the codex_native runner must:

1. POST an agent-side feedback message ("Model changed to X", etc.) so the
   chat surface confirms the change visually — analogous to Claude
   headless's `_send_feedback_message` (claude_code.py:965).
2. Flip the agent_instance status to ``AWAITING_INPUT`` so the mobile pill
   stops showing the stale "Active" badge while the session sits idle —
   analogous to `_mark_awaiting_input_after_settings_change`
   (claude_code.py:939).

Repro from `plans/inprogress/mid-session-mode-switching.md` test checklist
(Codex headless section): "No messages send back from headless to echo and
confirm the changes are confirmed. Also, after send back the message, the
status should be set to awaiting input."

Order matters: the feedback message must be POSTed BEFORE the status flip,
because the message broadcast itself transiently bumps the row's status to
"Active" (the runner is "doing something") — flipping back to
AWAITING_INPUT afterwards leaves the row in the right terminal state.
"""

from __future__ import annotations

import json
from typing import Optional

import pytest

from _fakes import FakeAsyncVicoaClient
from integrations.headless.codex_native import CodexNativeRunner


pytestmark = pytest.mark.asyncio


class _FakeSession:
    """Stand-in for CodexAppServerSession. The runner mutates the three
    attribute fields on every gear-pill change; we record the writes so the
    tests can assert the runner actually applied them."""

    def __init__(
        self,
        *,
        model: Optional[str] = "gpt-5.4",
        effort: Optional[str] = "medium",
        permission_mode: Optional[str] = "default",
    ) -> None:
        self.model = model
        self.effort = effort
        self.permission_mode = permission_mode

    async def interrupt(self) -> None:  # not used in these tests
        return None

    async def deliver_user_message(self, _text: str) -> None:  # not used
        return None

    async def maybe_route_auq_reply(self, _text: str) -> bool:
        return False


def _build_runner(
    *,
    vicoa_client: FakeAsyncVicoaClient,
    session: _FakeSession,
    session_id: str = "codex-instance",
) -> CodexNativeRunner:
    """Half-initialised runner. Mirrors conftest._build_runner; bypassed
    __init__ so we don't open log files or signal handlers."""
    runner = CodexNativeRunner.__new__(CodexNativeRunner)
    runner.vicoa_client = vicoa_client
    runner.session_id = session_id
    runner.session = session  # type: ignore[assignment]
    runner.agent_name = "Codex"
    return runner


def _control(setting: str, value: str) -> str:
    return json.dumps({"type": "control", "setting": setting, "value": value})


# ---------------------------------------------------------------------------
# model
# ---------------------------------------------------------------------------


async def test_model_change_sends_feedback_message() -> None:
    fake = FakeAsyncVicoaClient()
    session = _FakeSession(model="gpt-5.4")
    runner = _build_runner(vicoa_client=fake, session=session)

    await runner._route(_control("model", "gpt-5.5"))

    assert session.model == "gpt-5.5"
    assert any("gpt-5.5" in (m.get("content") or "") for m in fake.sent_messages), (
        f"expected a feedback message mentioning the new model; got {fake.sent_messages!r}"
    )
    feedback = next(
        m for m in fake.sent_messages if "gpt-5.5" in (m.get("content") or "")
    )
    assert feedback["agent_instance_id"] == "codex-instance"
    assert feedback["requires_user_input"] is False


async def test_model_change_flips_status_to_awaiting_input() -> None:
    fake = FakeAsyncVicoaClient()
    session = _FakeSession(model="gpt-5.4")
    runner = _build_runner(vicoa_client=fake, session=session)

    await runner._route(_control("model", "gpt-5.5"))

    assert fake.status_calls, "expected update_agent_instance_status call"
    assert fake.status_calls[-1]["status"] == "AWAITING_INPUT"
    assert fake.status_calls[-1]["agent_instance_id"] == "codex-instance"


async def test_model_change_feedback_precedes_status_flip() -> None:
    """The feedback POST itself transiently kicks the row to ACTIVE on the
    server (it's an agent-emitted message). Status flip must come AFTER so
    the row settles on AWAITING_INPUT."""
    fake = FakeAsyncVicoaClient()
    session = _FakeSession(model="gpt-5.4")
    runner = _build_runner(vicoa_client=fake, session=session)

    order: list[str] = []
    original_send = fake.send_message
    original_status = fake.update_agent_instance_status

    async def _record_send(*args, **kwargs):
        order.append("send_message")
        return await original_send(*args, **kwargs)

    async def _record_status(*args, **kwargs):
        order.append("status")
        return await original_status(*args, **kwargs)

    fake.send_message = _record_send  # type: ignore[method-assign]
    fake.update_agent_instance_status = _record_status  # type: ignore[method-assign]

    await runner._route(_control("model", "gpt-5.5"))

    assert order == ["send_message", "status"], (
        f"feedback message must be sent before flipping status; saw order={order}"
    )


# ---------------------------------------------------------------------------
# effort
# ---------------------------------------------------------------------------


async def test_effort_change_sends_feedback_message() -> None:
    fake = FakeAsyncVicoaClient()
    session = _FakeSession(effort="medium")
    runner = _build_runner(vicoa_client=fake, session=session)

    await runner._route(_control("effort", "high"))

    assert session.effort == "high"
    assert any("high" in (m.get("content") or "") for m in fake.sent_messages), (
        f"expected feedback mentioning new effort; got {fake.sent_messages!r}"
    )


async def test_effort_change_flips_status_to_awaiting_input() -> None:
    fake = FakeAsyncVicoaClient()
    session = _FakeSession(effort="medium")
    runner = _build_runner(vicoa_client=fake, session=session)

    await runner._route(_control("effort", "high"))

    assert fake.status_calls, "expected update_agent_instance_status call"
    assert fake.status_calls[-1]["status"] == "AWAITING_INPUT"


# ---------------------------------------------------------------------------
# permission_mode
# ---------------------------------------------------------------------------


async def test_permission_mode_change_uses_catalog_label_full_access() -> None:
    """The feedback message must use the human-readable catalog label
    ("Full Access") not the wire slug ("bypassPermissions") — the slug is
    a developer-facing identifier that leaks implementation detail into
    the user's chat. Labels come from shared/agent_catalog.py's codex
    `permission_modes` entries."""
    fake = FakeAsyncVicoaClient()
    session = _FakeSession(permission_mode="default")
    runner = _build_runner(vicoa_client=fake, session=session)

    await runner._route(_control("permission_mode", "bypassPermissions"))

    assert session.permission_mode == "bypassPermissions"
    feedback = next(
        (
            m
            for m in fake.sent_messages
            if "Permission mode" in (m.get("content") or "")
        ),
        None,
    )
    assert feedback is not None, (
        f"expected a permission-mode feedback; got {fake.sent_messages!r}"
    )
    assert feedback["content"] == "Permission mode changed to Full Access"
    # The raw slug must not leak into user-facing text.
    assert "bypassPermissions" not in feedback["content"]


async def test_permission_mode_change_uses_catalog_label_default() -> None:
    """Same label-not-slug rule for the `default` → "Default" mapping."""
    fake = FakeAsyncVicoaClient()
    session = _FakeSession(permission_mode="bypassPermissions")
    runner = _build_runner(vicoa_client=fake, session=session)

    await runner._route(_control("permission_mode", "default"))

    feedback = next(
        m for m in fake.sent_messages if "Permission mode" in (m.get("content") or "")
    )
    assert feedback["content"] == "Permission mode changed to Default"


async def test_permission_mode_change_flips_status_to_awaiting_input() -> None:
    fake = FakeAsyncVicoaClient()
    session = _FakeSession(permission_mode="default")
    runner = _build_runner(vicoa_client=fake, session=session)

    await runner._route(_control("permission_mode", "bypassPermissions"))

    assert fake.status_calls, "expected update_agent_instance_status call"
    assert fake.status_calls[-1]["status"] == "AWAITING_INPUT"


# ---------------------------------------------------------------------------
# interrupt
# ---------------------------------------------------------------------------


class _RecordingSession(_FakeSession):
    """Session double that logs when ``interrupt()`` was called relative to
    the runner's vicoa POSTs."""

    def __init__(self, order: list[str]) -> None:
        super().__init__()
        self._order = order
        self.interrupts = 0

    async def interrupt(self) -> None:
        self.interrupts += 1
        self._order.append("session.interrupt")


async def test_interrupt_sends_feedback_message() -> None:
    """Stop was silent on codex — claude and the ACP agents both narrate it."""
    fake = FakeAsyncVicoaClient()
    order: list[str] = []
    session = _RecordingSession(order)
    runner = _build_runner(vicoa_client=fake, session=session)

    await runner._route(json.dumps({"type": "control", "setting": "interrupt"}))

    assert session.interrupts == 1
    assert len(fake.sent_messages) == 1
    assert "Interrupted" in fake.sent_messages[0]["content"]
    assert fake.sent_messages[0]["requires_user_input"] is False


async def test_interrupt_feedback_precedes_the_stop() -> None:
    """The notice must be POSTed BEFORE the interrupt.

    Every agent-message POST re-opens the row as ACTIVE server-side, so a
    notice sent afterwards would undo the AWAITING_INPUT that ``turn/completed``
    (or ``interrupt()`` itself) writes — the same ordering bug that left the
    claude runner stuck on "active" after a Stop.
    """
    fake = FakeAsyncVicoaClient()
    order: list[str] = []
    session = _RecordingSession(order)
    runner = _build_runner(vicoa_client=fake, session=session)

    original_send = fake.send_message

    async def _record_send(*args, **kwargs):
        order.append("send_message")
        return await original_send(*args, **kwargs)

    fake.send_message = _record_send  # type: ignore[assignment]

    await runner._route(json.dumps({"type": "control", "setting": "interrupt"}))

    assert order == ["send_message", "session.interrupt"]
