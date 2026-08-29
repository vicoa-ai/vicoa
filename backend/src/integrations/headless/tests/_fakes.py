"""In-memory fake for `vicoa.sdk.async_client.AsyncVicoaClient`.

Only the surface the runner actually uses is implemented. Add to this when
the runner grows new calls — keep the fake honest by mirroring real return
shapes from ``vicoa.sdk.models``.

Filename starts with ``_`` so pytest does not try to collect it as a test
module.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Sequence, Union

from vicoa.sdk.exceptions import TimeoutError as VicoaTimeoutError
from vicoa.sdk.models import (
    CreateMessageResponse,
    EndSessionResponse,
    Message,
    PendingMessagesResponse,
    RegisterAgentInstanceResponse,
)


def _looks_like_permission_prompt(content: str) -> bool:
    """Heuristic: a permission prompt body always contains the OPTIONS block
    rendered by ``permission.render_permission_prompt``.

    Cheaper and clearer than peeking into ``message_metadata`` because the
    permission prompt has none — its protocol is purely textual.
    """
    return "[OPTIONS]" in (content or "")


SendMessageHandler = Callable[
    [Dict[str, Any]], Union[str, List[str], BaseException, None]
]
"""Per-call hook the test passes in to decide what queued_user_messages look like.

The callable receives the kwargs the runner passed to ``send_message``. It can
return:

* ``str``        — single queued reply
* ``list[str]``  — multiple queued replies
* ``None``       — no queued reply (used when the runner does not require input)
* ``Exception``  — raised from inside ``send_message`` (e.g. ``VicoaTimeoutError``)
"""


AuqReplyValue = Union[str, List[str], BaseException]
"""Reply (or replies) the fake delivers via the SSE control path once an
``ask_user_question`` POST lands. See ``FakeAsyncVicoaClient.__init__``."""

AuqReplyHandler = Callable[[Dict[str, Any]], AuqReplyValue]

PermissionReplyValue = Union[str, BaseException]
"""Reply the fake delivers via the SSE listener once a permission-prompt
POST lands. The fake calls ``runner._maybe_route_permission_reply(reply)``
which resolves the registry FIFO future."""

PermissionReplyHandler = Callable[[Dict[str, Any]], PermissionReplyValue]


class FakeAsyncVicoaClient:
    """Drop-in replacement for ``AsyncVicoaClient`` used by the runner.

    Three ways to feed replies back to the runner:

    * ``send_message_handler`` — legacy polling path. Whatever the handler
      returns lands in ``CreateMessageResponse.queued_user_messages``. Only
      used by tests that simulate the old polling protocol (e.g. SDK back-
      compat tests).
    * ``auq_reply`` — Future-based AUQ path. When ``send_message`` is called
      with ``ask_user_question`` metadata, the fake schedules a deferred
      call to ``runner._handle_control_command(reply)``.
    * ``permission_reply`` — Future-based permission path. When
      ``send_message`` is called for a permission prompt (detected by the
      ``[OPTIONS]`` block in the content), the fake schedules a deferred
      call to ``runner._maybe_route_permission_reply(reply)``.

    ``runner`` is set by ``conftest._build_runner`` via a back-ref.
    """

    def __init__(
        self,
        *,
        send_message_handler: Optional[SendMessageHandler] = None,
        auq_reply: Optional[Union[AuqReplyValue, AuqReplyHandler]] = None,
        permission_reply: Optional[
            Union[PermissionReplyValue, PermissionReplyHandler]
        ] = None,
        pending_messages: Optional[List[str]] = None,
        registration: Optional[RegisterAgentInstanceResponse] = None,
        stream_events: Optional[List[Dict[str, str]]] = None,
        block_after_stream_events: bool = True,
    ) -> None:
        self._send_message_handler = send_message_handler
        self._auq_reply = auq_reply
        self._permission_reply = permission_reply
        self._pending_messages = pending_messages or []
        self._registration = registration
        self._stream_events = list(stream_events or [])
        self._block_after_stream_events = block_after_stream_events

        # Set by conftest after construction so deferred AUQ-reply deliveries
        # can call ``runner._handle_control_command(reply)``.
        self.runner: Any = None

        # Call recorders — tests assert against these.
        self.sent_messages: List[Dict[str, Any]] = []
        self.sent_user_messages: List[Dict[str, Any]] = []
        self.register_calls: List[Dict[str, Any]] = []
        self.patch_calls: List[Dict[str, Any]] = []
        self.end_session_calls: List[str] = []
        self.mark_requires_input_calls: List[str] = []
        self.mark_consumed_calls: List[str] = []
        self.status_calls: List[Dict[str, Any]] = []
        # Single ordered log across recorders, so tests can assert *sequencing*
        # between calls that land in different lists. Ordering is load-bearing
        # for the interrupt path: an agent-message POST re-opens the row as
        # ACTIVE server-side, so it has to precede the AWAITING_INPUT write.
        # Entries: ``"send_message"`` / ``"status:AWAITING_INPUT"``.
        self.call_log: List[str] = []
        self.closed: bool = False
        self.message_id_seq: int = 0
        # Background tasks the fake spawned to deliver AUQ replies. Tests
        # ``await`` them via ``drain_pending_deliveries()``.
        self._pending_deliveries: List["asyncio.Task[None]"] = []

    # ------------------------------------------------------------------
    # Surface used by HeadlessClaudeRunner.initialize()
    # ------------------------------------------------------------------
    async def register_agent_instance(
        self,
        *,
        agent_type: str,
        transport: str = "ws",
        agent_instance_id: Optional[Union[str, uuid.UUID]] = None,
        name: Optional[str] = None,
        project: Optional[str] = None,
        home_dir: Optional[str] = None,
        session_config: Optional[Dict[str, Any]] = None,
    ) -> RegisterAgentInstanceResponse:
        self.register_calls.append(
            {
                "agent_type": agent_type,
                "transport": transport,
                "agent_instance_id": str(agent_instance_id)
                if agent_instance_id
                else None,
                "name": name,
                "project": project,
                "home_dir": home_dir,
                "session_config": session_config,
            }
        )
        if self._registration is not None:
            return self._registration
        return RegisterAgentInstanceResponse(
            agent_instance_id=str(agent_instance_id or uuid.uuid4()),
            agent_type_id=None,
            agent_type_name=agent_type,
            status="active",
            name=name,
            instance_metadata=None,
            project=project,
        )

    async def patch_agent_instance(
        self,
        agent_instance_id: Union[str, uuid.UUID],
        *,
        name: Optional[str] = None,
        session_config: Optional[Dict[str, Any]] = None,
        instance_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        self.patch_calls.append(
            {
                "agent_instance_id": str(agent_instance_id),
                "name": name,
                "session_config": session_config,
                "instance_metadata": instance_metadata,
            }
        )
        return {}

    async def update_agent_instance_status(
        self,
        agent_instance_id: Union[str, uuid.UUID],
        status: str,
    ) -> None:
        self.status_calls.append(
            {
                "agent_instance_id": str(agent_instance_id),
                "status": status,
            }
        )
        self.call_log.append(f"status:{status}")

    # ------------------------------------------------------------------
    # Surface used by the can_use_tool handlers
    # ------------------------------------------------------------------
    async def send_message(
        self,
        content: str,
        agent_type: Optional[str] = None,
        agent_instance_id: Optional[Union[str, uuid.UUID]] = None,
        requires_user_input: bool = False,
        timeout_minutes: int = 1440,
        poll_interval: float = 10.0,
        send_push: Optional[bool] = None,
        send_email: Optional[bool] = None,
        send_sms: Optional[bool] = None,
        git_diff: Optional[str] = None,
        message_metadata: Optional[Dict[str, Any]] = None,
        poll_for_reply: Optional[bool] = None,
    ) -> CreateMessageResponse:
        call = {
            "content": content,
            "agent_type": agent_type,
            "agent_instance_id": str(agent_instance_id) if agent_instance_id else None,
            "requires_user_input": requires_user_input,
            "timeout_minutes": timeout_minutes,
            "poll_interval": poll_interval,
            "send_push": send_push,
            "send_email": send_email,
            "send_sms": send_sms,
            "git_diff": git_diff,
            "message_metadata": message_metadata,
            "poll_for_reply": poll_for_reply,
        }
        self.sent_messages.append(call)
        self.call_log.append("send_message")
        self.message_id_seq += 1
        message_id = f"msg-{self.message_id_seq}"

        queued: List[str] = []
        if self._send_message_handler is not None:
            outcome = self._send_message_handler(call)
            if isinstance(outcome, BaseException):
                raise outcome
            if isinstance(outcome, str):
                queued = [outcome]
            elif isinstance(outcome, list):
                queued = list(outcome)

        # AUQ Future-based path: when the runner POSTs an AskUserQuestion
        # prompt, schedule the configured reply(s) to be delivered back via
        # the SSE control path (``runner._handle_control_command``). This
        # mirrors how the dashboard echoes the user's pick to the runner.
        if (
            self._auq_reply is not None
            and isinstance(message_metadata, dict)
            and "ask_user_question" in message_metadata
        ):
            reply_outcome = (
                self._auq_reply(call) if callable(self._auq_reply) else self._auq_reply
            )
            if isinstance(reply_outcome, BaseException):
                raise reply_outcome
            replies: Sequence[str]
            if isinstance(reply_outcome, str):
                replies = [reply_outcome]
            elif isinstance(reply_outcome, list):
                replies = list(reply_outcome)
            else:
                replies = []
            if replies and self.runner is not None:
                self._pending_deliveries.append(
                    asyncio.create_task(self._deliver_auq_replies(list(replies)))
                )

        # Permission Future-based path: detect the permission prompt by its
        # ``[OPTIONS]`` block, then deliver the configured reply through the
        # SSE listener fast-path (``_maybe_route_permission_reply``).
        if self._permission_reply is not None and _looks_like_permission_prompt(
            content
        ):
            permission_outcome = (
                self._permission_reply(call)
                if callable(self._permission_reply)
                else self._permission_reply
            )
            if isinstance(permission_outcome, BaseException):
                raise permission_outcome
            if isinstance(permission_outcome, str) and self.runner is not None:
                self._pending_deliveries.append(
                    asyncio.create_task(
                        self._deliver_permission_reply(permission_outcome)
                    )
                )

        return CreateMessageResponse(
            success=True,
            agent_instance_id=str(agent_instance_id or "fake-instance"),
            message_id=message_id,
            queued_user_messages=queued,
        )

    async def _deliver_auq_replies(self, replies: List[str]) -> None:
        """Hand replies to the runner one at a time via the SSE control path."""
        # Yield once so the caller of ``send_message`` returns first and
        # ``_handle_ask_user_question`` is parked on the registry future
        # before we try to resolve it.
        await asyncio.sleep(0)
        if self.runner is None:
            return
        for reply in replies:
            await self.runner._handle_control_command(reply)

    async def _deliver_permission_reply(self, reply: str) -> None:
        """Hand a permission reply to the runner via the SSE listener fast path."""
        await asyncio.sleep(0)
        if self.runner is None:
            return
        # Mirror the SSE listener's routing order: try AUQ first (no-op for
        # plain permission text), then permission. Falls back to the
        # user-message queue if no future is pending, which is the legacy
        # behaviour tests sometimes assert against.
        if await self.runner._maybe_route_ask_user_question_reply(reply):
            return
        if await self.runner._maybe_route_permission_reply(reply):
            return
        await self.runner._user_message_queue.put(reply)

    async def drain_pending_deliveries(self) -> None:
        """Await all in-flight AUQ-reply delivery tasks; safe to call repeatedly."""
        if not self._pending_deliveries:
            return
        pending = self._pending_deliveries
        self._pending_deliveries = []
        await asyncio.gather(*pending, return_exceptions=True)

    async def get_pending_messages_raw(
        self,
        agent_instance_id: Union[str, uuid.UUID],
    ) -> tuple[List[Dict[str, Any]], str]:
        """Return raw pending message dicts + status (metadata preserved).

        Tests set ``self.pending_raw`` to a list of raw ``MessageResponse``
        dicts to simulate the persisted tail the reconcile REST recovery reads
        (``HeadlessClaudeRunner._recover_pending_reply_via_rest``). Cleared
        after the first hand-out so a second call returns nothing, mirroring the
        server advancing ``last_read_message_id`` past the delivered rows.
        """
        self.get_pending_raw_calls = getattr(self, "get_pending_raw_calls", 0) + 1
        pending: List[Dict[str, Any]] = list(getattr(self, "pending_raw", []) or [])
        self.pending_raw = []
        return pending, getattr(self, "pending_raw_status", "ok")

    async def send_user_message(
        self,
        agent_instance_id: Union[str, uuid.UUID],
        content: str,
        mark_as_read: bool = True,
    ) -> Dict[str, Any]:
        self.sent_user_messages.append(
            {
                "agent_instance_id": str(agent_instance_id),
                "content": content,
                "mark_as_read": mark_as_read,
            }
        )
        return {"success": True, "message_id": f"user-{len(self.sent_user_messages)}"}

    async def get_pending_messages(
        self,
        agent_instance_id: Union[str, uuid.UUID],
        last_read_message_id: Optional[str] = None,
    ) -> PendingMessagesResponse:
        msgs = [
            Message(
                id=f"pending-{i}",
                content=content,
                sender_type="user",
                created_at="1970-01-01T00:00:00Z",
                requires_user_input=False,
            )
            for i, content in enumerate(self._pending_messages, start=1)
        ]
        # Clear after handing them out so a second call returns nothing.
        self._pending_messages = []
        return PendingMessagesResponse(
            agent_instance_id=str(agent_instance_id),
            messages=msgs,
            status="ok",
        )

    async def stream_user_messages(
        self,
        agent_instance_id: Union[str, uuid.UUID],
    ) -> AsyncIterator[Dict[str, str]]:
        for event in self._stream_events:
            yield event
        if self._block_after_stream_events:
            # Park forever; the runner will cancel us on shutdown.
            await asyncio.Event().wait()

    async def mark_message_requires_input(
        self, message_id: Union[str, uuid.UUID]
    ) -> List[Dict[str, Any]]:
        self.mark_requires_input_calls.append(str(message_id))
        return []

    async def mark_message_consumed(self, message_id: Union[str, uuid.UUID]) -> None:
        self.mark_consumed_calls.append(str(message_id))

    async def download_attachment(self, attachment_id: str) -> tuple[bytes, str]:
        """Serve from ``self.attachments`` ({id: (bytes, mime)}); raise otherwise."""
        store: Dict[str, tuple[bytes, str]] = getattr(self, "attachments", {})
        if attachment_id not in store:
            raise RuntimeError(f"attachment {attachment_id} not found")
        return store[attachment_id]

    async def end_session(
        self, agent_instance_id: Union[str, uuid.UUID]
    ) -> EndSessionResponse:
        self.end_session_calls.append(str(agent_instance_id))
        return EndSessionResponse(
            success=True,
            agent_instance_id=str(agent_instance_id),
            final_status="completed",
        )

    async def close(self) -> None:
        self.closed = True


__all__ = [
    "AuqReplyHandler",
    "AuqReplyValue",
    "FakeAsyncVicoaClient",
    "SendMessageHandler",
    "VicoaTimeoutError",
]
