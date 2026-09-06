"""One Pi-family conversation, driven over the RPC transport.

Owns the turn lifecycle, the event routing, and every push to vicoa-server.
The runner above it owns the WebSocket, the message queue and the process.

The turn model is the part worth reading carefully, because the obvious
reading of the event names is wrong:

* ``turn_*`` brackets **one model round trip**. A single tool-using prompt
  produces ``agent_start`` -> (``turn_start`` … ``turn_end``) x2 ->
  ``agent_end``. Settling on ``turn_end`` would end the turn the moment the
  model paused to call a tool.
* ``agent_*`` brackets the prompt — but even ``agent_end`` is "one low-level
  run finished", and may be followed by a retry, a compaction, or a queued
  continuation. omp marks the real one with ``isTerminal``; pi emits a separate
  ``agent_settled``. Both are handled, and a grace timer covers a build that
  emits neither.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Dict, List, Optional

from integrations.headless import auq
from integrations.headless.permission import PermissionReplyRegistry
from integrations.headless.pi_family import commands as commands_mod
from integrations.headless.pi_family import ui_requests
from integrations.headless.pi_family.event_mapper import EventMapper
from integrations.headless.pi_family.host_tools import HostToolRouter
from integrations.headless.pi_family.protocol import ReadyGate, perform_handshake
from integrations.headless.pi_family.rpc_types import (
    as_dict,
    as_list,
    as_str,
    context_from_session_stats,
    model_entries,
    qualified_model_id,
    split_model_id,
)
from integrations.headless.pi_family.spec import PiFamilySpec
from integrations.headless.pi_family.subagents import (
    DEFAULT_SUBSCRIPTION_LEVEL,
    SubagentTracker,
)
from integrations.headless.pi_family.transport import (
    PiRpcError,
    PiTransport,
    PiTransportClosed,
)
from integrations.headless.session_lifecycle import (
    WRAPPER_STOP_STATUSES as _WRAPPER_STOP_STATUSES,
)
from integrations.headless.usage import UsageState
from vicoa.attachments import (
    AttachmentRef,
    attachment_note,
    attachments_dir,
    is_image_mime,
    save_attachment,
    unavailable_note,
)


logger = logging.getLogger(__name__)


_STATUS_ACTIVE = "ACTIVE"
_STATUS_AWAITING_INPUT = "AWAITING_INPUT"

#: 24 hours, matching the Claude and Codex AUQ timeouts — long enough that a
#: user can step away, short enough that abandoned sessions don't leak futures.
_AUQ_TIMEOUT_SECONDS = 24 * 60 * 60

#: Fallback settle window after a non-terminal ``agent_end`` on an agent that
#: promises a dedicated settle event. Only fires when that event never arrives
#: (a version drift, or a dropped frame); the real path is the event itself.
_SETTLE_GRACE_SECONDS = 8.0

#: Per-call request bounds. These bound *control* RPCs, never the model's
#: thinking — the prompt ack returns as soon as the turn is accepted, and the
#: turn itself streams afterwards.
_PROMPT_ACK_TIMEOUT = 60.0
_CONTROL_TIMEOUT = 20.0
#: ``compact`` and ``handoff`` run an LLM call of their own, so they get no
#: bound at all — a 30s cap would fail them routinely.
_LLM_COMMAND_TIMEOUT: Optional[float] = None

#: Silence watchdog: if the agent sends nothing at all for this long while a
#: turn is open, settle the row and unpark the turn. The transport reader stays
#: open, so later output simply re-activates the session. Ported from the
#: Claude/Codex watchdogs.
_STATUS_SETTLE_IDLE_SECONDS = 600.0
_STATUS_WATCHDOG_INTERVAL = 30.0


class PiRuntimeSession:
    """Drives one ``pi``/``omp`` conversation for one Vicoa agent instance."""

    def __init__(
        self,
        *,
        vicoa_client: Any,
        instance_id: str,
        cwd: str,
        transport: PiTransport,
        spec: PiFamilySpec,
        ready_gate: ReadyGate,
        agent_type: str,
        model: Optional[str] = None,
        thinking_effort: Optional[str] = None,
        permission_mode: Optional[str] = None,
        stderr_tail: Optional[Any] = None,
        machine_id: Optional[str] = None,
    ) -> None:
        self.vicoa_client = vicoa_client
        self.instance_id = instance_id
        self.cwd = cwd
        self.transport = transport
        self.spec = spec
        self.agent_type = agent_type
        self.model = model
        self.thinking_effort = thinking_effort
        self.permission_mode = permission_mode
        self.machine_id = machine_id
        self._ready_gate = ready_gate
        self._stderr_tail = stderr_tail

        self.status = "starting"
        #: Set by the runner when the session is closed from another client, so
        #: a racing in-flight turn can't re-open the row via ``_set_status``.
        self.stopping = False
        self._closed = False

        #: The agent's own session id, read back from ``get_state`` and
        #: persisted so a later launch can resume with ``--session <id>``.
        #: It cannot be supplied up front: the flag resolves, never creates.
        self.agent_session_id: Optional[str] = None

        self._mapper = EventMapper(
            agent_type=agent_type, thinking_source=spec.catalog_id
        )
        self._subagents = SubagentTracker()
        self._permission_registry = PermissionReplyRegistry()
        self._auq_registry = auq.AskUserQuestionRegistry()
        self._usage = UsageState()
        self._usage_last_core: Optional[dict] = None

        #: Resolves when the current prompt has fully settled.
        self._turn_done: Optional["asyncio.Future[None]"] = None
        self._turn_active = False
        self._settle_task: Optional["asyncio.Task[None]"] = None
        self._watchdog_task: Optional["asyncio.Task[None]"] = None
        self._close_task: Optional["asyncio.Task[None]"] = None
        #: Background tasks for dialogs, which must not block the read loop.
        self._dialog_tasks: set["asyncio.Task[None]"] = set()

        self.available_models: List[Dict[str, str]] = []
        #: The model the agent reports it is actually running, as the same
        #: ``provider/id`` key the picker uses. Read from ``get_state`` rather
        #: than assumed from ``self.model``: the spawn-time value is only a
        #: *preference*, and it is empty for the common case where the user
        #: left the picker on "Default" — which is exactly when the gear used
        #: to fall back to naming the first model in the list, or nothing.
        self.current_model: Optional[str] = None
        self.host_tools: Optional[HostToolRouter] = None
        #: Command index last synced, so an unchanged push is a no-op.
        self._last_commands: Optional[Dict[str, Dict[str, str]]] = None

        self.transport.on_event = self._handle_event
        self.transport.on_close = self._on_transport_closed

    # ------------------------------------------------------------------
    # Bring-up
    # ------------------------------------------------------------------

    async def start(self, *, host_tools: Optional[HostToolRouter] = None) -> None:
        """Handshake, capture the session id, and apply spawn-time settings."""
        await self.transport.start()
        if self._watchdog_task is None:
            self._watchdog_task = asyncio.create_task(self._run_status_watchdog())
        await perform_handshake(
            self.transport, self.spec, self._ready_gate, stderr_tail=self._stderr_tail
        )

        if self.spec.supports_host_tools and host_tools is not None:
            self.host_tools = host_tools
            await host_tools.register(self._request)

        if self.spec.supports_subagents:
            await self._try_request(
                "set_subagent_subscription", {"level": DEFAULT_SUBSCRIPTION_LEVEL}
            )

        await self._refresh_state()
        await self._report_models()
        await self._pull_commands()
        await self._set_status(_STATUS_AWAITING_INPUT)

    async def _refresh_state(self) -> None:
        """Read ``get_state`` for the session id and the live current model.

        Best-effort: losing the id costs a future resume, never the session
        starting now.
        """
        state = await self._try_request("get_state")
        if state is None:
            return
        session_id = as_str(state.get("sessionId"))
        if session_id and session_id != self.agent_session_id:
            self.agent_session_id = session_id
            await self._persist_session_id()
        current = qualified_model_id(state.get("model"))
        if current:
            self.current_model = current

    async def _report_models(self) -> None:
        """PATCH the machine's real model list onto ``session_config``.

        Both agents proxy many providers whose available models are per-machine
        configuration, so — exactly as for OpenCode — the live list is the
        authoritative one and the static catalog is only a starter set.
        """
        data = await self._try_request("get_available_models")
        if data is None:
            return
        models = model_entries(data.get("models"))
        if not models:
            return
        self.available_models = models
        delta: Dict[str, Any] = {"available_models": models}
        # Prefer what the agent says it is running over what we asked for at
        # spawn: the two differ whenever the user left the picker on "Default"
        # (no --model passed at all) or the agent resolved a fuzzy pattern.
        current = self.current_model or self.model
        if current:
            delta["current_model"] = current
        await self._patch_session_config(delta)

    async def _report_current_model(self) -> None:
        """Re-read and publish the live model after the agent changed it.

        omp emits ``model_changed`` when a slash command or an extension
        switches models behind our back; without this the gear keeps naming
        the previous one.
        """
        previous = self.current_model
        await self._refresh_state()
        if self.current_model and self.current_model != previous:
            self.model = self.current_model
            await self._patch_session_config(
                {
                    "agent": self.spec.catalog_id,
                    "model": self.current_model,
                    "current_model": self.current_model,
                }
            )

    async def _pull_commands(self) -> None:
        data = await self._try_request(self.spec.commands_rpc)
        if data is None:
            return
        await self._sync_commands(data.get("commands"))

    async def _sync_commands(self, commands: Any) -> None:
        index = commands_mod.build_command_index(commands)
        if not index or index == self._last_commands:
            return
        self._last_commands = index
        try:
            await self.vicoa_client.sync_commands(
                agent_type=self.spec.catalog_id, commands=index
            )
            logger.info("pi_family: synced %d slash commands", len(index))
        except Exception:
            logger.debug("pi_family: command sync failed", exc_info=True)

    # ------------------------------------------------------------------
    # Turns
    # ------------------------------------------------------------------

    async def deliver_user_message(
        self, text: str, attachments: "tuple[AttachmentRef, ...]" = ()
    ) -> None:
        """Run one turn, or resolve a pending permission prompt.

        Turn serialization and burst coalescing live one layer up in the
        runner, so this stays a one-turn primitive its caller awaits.
        """
        if text and self._permission_registry.has_pending():
            if self._permission_registry.resolve_text(text):
                return
        await self.prompt(text, attachments)

    async def prompt(
        self, text: str, attachments: "tuple[AttachmentRef, ...]" = ()
    ) -> None:
        body, images = await self._build_prompt_payload(text, attachments)
        if not body and not images:
            return

        # Register the completion future and flip status BEFORE awaiting the
        # ack: the reader can race ahead and process the whole turn before this
        # coroutine resumes, and setting status here keeps the transition
        # monotonic.
        loop = asyncio.get_running_loop()
        done: "asyncio.Future[None]" = loop.create_future()
        self._turn_done = done
        self._turn_active = True
        self._cancel_settle()
        await self._set_status(_STATUS_ACTIVE)

        params: Dict[str, Any] = {"message": body}
        if images:
            params["images"] = images
        try:
            await self.transport.request("prompt", params, timeout=_PROMPT_ACK_TIMEOUT)
        except PiTransportClosed:
            # The agent is gone. ``_on_transport_closed`` already surfaced the
            # reason and settles the row; unwind quietly.
            logger.warning("pi_family: prompt aborted — transport closed")
            self._finish_turn()
            return
        except Exception as exc:
            logger.warning("pi_family: prompt failed: %s", exc)
            # Surface BEFORE settling: an agent-message POST re-opens the row
            # as ACTIVE, so a settle-then-post order leaves a stale spinner.
            await self._post(f"⚠️ **Prompt failed**\n\n{exc}")
            self._finish_turn()
            await self._set_status(_STATUS_AWAITING_INPUT)
            return

        try:
            await done
        finally:
            self._turn_active = False
            self._turn_done = None

    def steer(self, text: str) -> bool:
        """Redirect the running turn without waiting for it to end.

        Returns False when no turn is running, so the caller can fall back to a
        normal prompt. ``steer`` is fire-and-forget by protocol.
        """
        if not self._turn_active or not text.strip():
            return False
        self.transport.send("steer", {"message": text})
        return True

    def follow_up(self, text: str) -> bool:
        """Queue a message to run after the current turn finishes."""
        if not self._turn_active or not text.strip():
            return False
        self.transport.send("follow_up", {"message": text})
        return True

    async def interrupt(self) -> None:
        """Best-effort stop of the running turn.

        Cancels pending human-in-the-loop futures first — their handlers then
        answer the agent with a cancel instead of waiting on a user who has
        already pressed Stop — and then aborts. A Stop with no turn running
        still settles the row, because the dashboard may be showing a stale
        ACTIVE that only this path can clear.
        """
        self._permission_registry.cancel_all()
        self._auq_registry.cancel_all()
        if not self._turn_active:
            await self._set_status(_STATUS_AWAITING_INPUT)
            return
        try:
            await self.transport.request("abort", timeout=_CONTROL_TIMEOUT)
        except Exception as exc:
            logger.warning("pi_family: abort failed: %s", exc)
            self._finish_turn()
            await self._set_status(_STATUS_AWAITING_INPUT)

    async def _build_prompt_payload(
        self, text: str, attachments: "tuple[AttachmentRef, ...]"
    ) -> tuple[str, List[Dict[str, Any]]]:
        """Text + native image blocks for a ``prompt`` frame.

        Images ride natively as ``ImageContent`` (base64 + mimeType). Other
        files are saved next to the session and referenced by path in a text
        note the agent opens with its own file tools; a failed download
        degrades to a note so the agent knows something was meant to be there.
        """
        if not attachments:
            return text, []
        images: List[Dict[str, Any]] = []
        notes: List[str] = []
        for ref in attachments:
            try:
                data, mime_type = await self.vicoa_client.download_attachment(ref.id)
                local = save_attachment(
                    attachments_dir(self.instance_id), ref, data, mime_type
                )
                if is_image_mime(mime_type):
                    import base64

                    images.append(
                        {
                            "type": "image",
                            "data": base64.b64encode(data).decode("ascii"),
                            "mimeType": mime_type,
                        }
                    )
                else:
                    notes.append(attachment_note(local))
            except Exception:
                logger.exception("pi_family: failed to download attachment %s", ref.id)
                notes.append(unavailable_note(ref))
        body = "\n".join(part for part in [text, *notes] if part)
        return body, images

    # ------------------------------------------------------------------
    # Event routing
    # ------------------------------------------------------------------

    async def _handle_event(self, frame: Dict[str, Any]) -> None:
        frame_type = as_str(frame.get("type"))

        # The ready frame is consumed by the handshake gate, never rendered.
        if self._ready_gate.offer(frame):
            return

        if frame_type == "extension_ui_request":
            self._spawn_dialog(frame)
            return
        if frame_type == "host_tool_call":
            if self.host_tools is not None:
                self.host_tools.handle_call(frame)
            return
        if frame_type == "host_tool_cancel":
            if self.host_tools is not None:
                self.host_tools.handle_cancel(frame)
            return
        if frame_type == "available_commands_update":
            await self._sync_commands(frame.get("commands"))
            return
        if frame_type == "model_changed":
            await self._report_current_model()
            return
        if frame_type in {"subagent_lifecycle", "subagent_progress"}:
            await self._handle_subagent(frame_type, frame.get("payload"))
            return
        if frame_type == "subagent_event":
            # Only reachable at the ``events`` subscription level, which we do
            # not use (110 frames for one trivial subagent). Dropped rather
            # than rendered so an operator who raises the level manually can't
            # flood the chat.
            return

        await self._handle_lifecycle(frame_type, frame)

        for emission in self._mapper.handle(frame):
            await self._post(emission.content, emission.metadata)

    async def _handle_lifecycle(self, frame_type: str, frame: Dict[str, Any]) -> None:
        if frame_type in {"agent_start", "turn_start", "message_start"}:
            # Work is (still) happening: cancel any settle the previous
            # ``agent_end`` armed, and make sure the row reads active.
            self._cancel_settle()
            if self._turn_active and self.status != _STATUS_ACTIVE:
                await self._set_status(_STATUS_ACTIVE)
            return

        if frame_type == self.spec.settle_event:
            await self._settle_turn()
            return

        if frame_type == "agent_end":
            if frame.get("willRetry") is True or frame.get("isTerminal") is False:
                # A retry or an async continuation will resume this run.
                return
            if self.spec.settle_event is None:
                await self._settle_turn()
            else:
                self._arm_settle(_SETTLE_GRACE_SECONDS)
            return

    async def _handle_subagent(self, frame_type: str, payload: Any) -> None:
        if frame_type == "subagent_lifecycle":
            rendered = self._subagents.handle_lifecycle(payload)
        else:
            rendered = self._subagents.handle_progress(payload)
        if rendered is None:
            return
        content, metadata = rendered
        await self._post(content, metadata)

    # ------------------------------------------------------------------
    # Turn settling
    # ------------------------------------------------------------------

    def _arm_settle(self, delay: float) -> None:
        """Settle after ``delay`` unless more work arrives first."""
        self._cancel_settle()

        async def _later() -> None:
            try:
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                return
            logger.info(
                "pi_family: no %s within %.0fs of agent_end; settling",
                self.spec.settle_event,
                delay,
            )
            await self._settle_turn()

        self._settle_task = asyncio.create_task(_later())

    def _cancel_settle(self) -> None:
        task = self._settle_task
        self._settle_task = None
        if task is not None and not task.done():
            task.cancel()

    async def _settle_turn(self) -> None:
        self._cancel_settle()
        self._mapper.reset_message()
        await self._set_status(_STATUS_AWAITING_INPUT)
        await self._flush_usage()
        self._finish_turn()

    def _finish_turn(self) -> None:
        """Unpark ``prompt``'s awaiter. Safe to call more than once."""
        future = self._turn_done
        if future is not None and not future.done():
            future.set_result(None)

    async def _run_status_watchdog(self) -> None:
        """Settle a turn whose agent went silent.

        Never stops the transport reader — a turn that resumes after the settle
        simply re-activates the session through its normal event path.
        """
        while not self._closed:
            try:
                await asyncio.sleep(_STATUS_WATCHDOG_INTERVAL)
            except asyncio.CancelledError:
                return
            if self._closed or self.stopping or not self._turn_active:
                continue
            if (
                self._permission_registry.has_pending()
                or self._auq_registry.has_pending()
            ):
                # The agent is quiet because it is waiting on a human. That is
                # not a stall.
                continue
            idle = asyncio.get_running_loop().time() - self.transport.last_activity
            if idle < _STATUS_SETTLE_IDLE_SECONDS:
                continue
            logger.warning(
                "pi_family: no output for %.0fs with a turn open; settling", idle
            )
            await self._settle_turn()

    def _on_transport_closed(self, reason: str) -> None:
        """The child died on its own. Unpark the turn and surface why."""
        if self._closed:
            return
        self._finish_turn()
        self._close_task = asyncio.create_task(self._handle_unexpected_close(reason))

    async def _handle_unexpected_close(self, reason: str) -> None:
        logger.warning("pi_family: transport closed unexpectedly: %s", reason)
        await self._post(f"⚠️ **{self.agent_type} exited unexpectedly**\n\n{reason}")
        await self._set_status(_STATUS_AWAITING_INPUT)

    # ------------------------------------------------------------------
    # Dialogs
    # ------------------------------------------------------------------

    def _spawn_dialog(self, frame: Dict[str, Any]) -> None:
        """Handle an ``extension_ui_request`` without blocking the read loop.

        A dialog can park on a human for hours; doing that inline would stop
        every subsequent frame, including the agent's own progress.
        """
        kind = ui_requests.classify(frame)
        if kind == "ignore":
            logger.debug(
                "pi_family: ignoring extension_ui_request method=%s",
                frame.get("method"),
            )
            return
        if kind == "cancel":
            # The agent withdrew a dialog. Cancel the matching pending future;
            # its handler then replies with ``cancelled``.
            self._permission_registry.cancel_all()
            self._auq_registry.cancel_all()
            return
        task = asyncio.create_task(self._run_dialog(kind, frame))
        self._dialog_tasks.add(task)
        task.add_done_callback(self._dialog_tasks.discard)

    async def _run_dialog(self, kind: str, frame: Dict[str, Any]) -> None:
        try:
            if kind == "notice":
                text = ui_requests.render_notice(frame)
                if text:
                    await self._post(text)
                # Notices are informational; the agent does not wait on them.
                return
            if kind == "permission":
                await self._run_permission_dialog(frame)
                return
            await self._run_question_dialog(frame)
        except asyncio.CancelledError:
            self._respond(frame, {"cancelled": True})
            raise
        except Exception:
            logger.exception("pi_family: dialog handler failed; cancelling")
            self._respond(frame, {"cancelled": True})

    async def _run_permission_dialog(self, frame: Dict[str, Any]) -> None:
        request_id = as_str(frame.get("id")) or uuid.uuid4().hex
        future = self._permission_registry.create(request_id)
        body = ui_requests.render_permission_prompt(frame)
        try:
            await self.vicoa_client.send_message(
                content=body,
                agent_type=self.agent_type,
                agent_instance_id=self.instance_id,
                requires_user_input=True,
                poll_for_reply=False,
            )
            reply = await future
        except asyncio.CancelledError:
            self._respond(frame, {"cancelled": True})
            return
        except Exception:
            logger.exception("pi_family: failed to post permission prompt")
            self._respond(frame, {"cancelled": True})
            return
        label = ui_requests.match_option(reply, as_list(frame.get("options")))
        if label is None:
            self._respond(frame, {"cancelled": True})
            return
        self._respond(frame, {"value": label})

    async def _run_question_dialog(self, frame: Dict[str, Any]) -> None:
        questions, is_text_mode = ui_requests.build_question(frame)
        request_id = uuid.uuid4().hex
        future = self._auq_registry.create(request_id)
        metadata = auq.build_metadata(
            questions=questions,
            prompt=auq.ASK_USER_QUESTION_PROMPT_LABEL,
            tool_use_id=as_str(frame.get("id")) or None,
            request_id=request_id,
        )
        try:
            try:
                response = await self.vicoa_client.send_message(
                    content=auq.ASK_USER_QUESTION_PROMPT_LABEL,
                    agent_type=self.agent_type,
                    agent_instance_id=self.instance_id,
                    requires_user_input=True,
                    poll_for_reply=False,
                    message_metadata=metadata,
                )
            except Exception:
                logger.exception("pi_family: failed to POST question; cancelling")
                self._respond(frame, {"cancelled": True})
                return
            self._auq_registry.bind_message_id(
                request_id, getattr(response, "message_id", None)
            )
            try:
                decoded = await asyncio.wait_for(future, timeout=_AUQ_TIMEOUT_SECONDS)
            except asyncio.TimeoutError:
                logger.warning("pi_family: question %s timed out", request_id)
                self._respond(frame, {"cancelled": True, "timedOut": True})
                return
            except asyncio.CancelledError:
                self._respond(frame, {"cancelled": True})
                return
        finally:
            self._auq_registry.cancel(request_id)
        self._respond(
            frame,
            ui_requests.answer_to_response(frame, decoded, is_text_mode=is_text_mode),
        )

    def _respond(self, frame: Dict[str, Any], payload: Dict[str, Any]) -> None:
        body = dict(payload)
        body.setdefault("id", as_str(frame.get("id")))
        self.transport.send("extension_ui_response", body)

    def try_resolve_pending_reply(self, text: str) -> bool:
        """Consume ``text`` as a permission reply if one is pending.

        The runner calls this before enqueuing on the turn queue: a permission
        reply must resolve inline, since the turn awaiting it is exactly what
        would drain that queue.
        """
        if text and self._permission_registry.has_pending():
            return self._permission_registry.resolve_text(text)
        return False

    async def maybe_route_auq_reply(self, content: str) -> bool:
        decoded = auq.decode_reply(content)
        if decoded is None:
            return False
        self._auq_registry.resolve(decoded)
        return True

    # ------------------------------------------------------------------
    # Mid-session settings
    # ------------------------------------------------------------------

    async def set_model(self, model_id: str) -> bool:
        """Switch models mid-session. Returns False when the agent refused."""
        provider, bare_id = split_model_id(model_id)
        if provider is None:
            provider = self._provider_for(bare_id)
        try:
            await self.transport.request(
                "set_model",
                {"provider": provider or "", "modelId": bare_id},
                timeout=_CONTROL_TIMEOUT,
            )
        except Exception as exc:
            logger.warning("pi_family: set_model %s failed: %s", model_id, exc)
            return False
        self.model = model_id
        self.current_model = model_id
        await self._patch_session_config(
            {
                "agent": self.spec.catalog_id,
                "model": model_id,
                "current_model": model_id,
            }
        )
        return True

    def _provider_for(self, model_id: str) -> Optional[str]:
        """Find a bare model id's provider in the live list.

        The catalog stores ``provider/id``, but a user (or an older stored
        selection) may hand us a bare id; ``set_model`` needs both halves.
        """
        for entry in self.available_models:
            entry_id = entry.get("id", "")
            provider, bare = split_model_id(entry_id)
            if bare == model_id:
                return provider
        return None

    async def set_thinking_level(self, level: str) -> bool:
        if level not in self.spec.thinking_levels:
            logger.info(
                "pi_family: dropping thinking level %r (unsupported by %s)",
                level,
                self.spec.catalog_id,
            )
            return False
        try:
            await self.transport.request(
                "set_thinking_level", {"level": level}, timeout=_CONTROL_TIMEOUT
            )
        except Exception as exc:
            logger.warning("pi_family: set_thinking_level failed: %s", exc)
            return False
        self.thinking_effort = level
        await self._patch_session_config(
            {"agent": self.spec.catalog_id, "thinking_effort": level}
        )
        return True

    async def compact(self, instructions: Optional[str] = None) -> bool:
        if not self.spec.supports_compaction:
            return False
        params = {"customInstructions": instructions} if instructions else None
        try:
            await self.transport.request(
                "compact", params, timeout=_LLM_COMMAND_TIMEOUT
            )
        except Exception as exc:
            logger.warning("pi_family: compact failed: %s", exc)
            await self._post(f"⚠️ Compaction failed: {exc}")
            return False
        await self._flush_usage(force=True)
        return True

    async def set_auto_compaction(self, enabled: bool) -> bool:
        return (
            await self._try_request("set_auto_compaction", {"enabled": enabled})
        ) is not None

    async def handoff(self, instructions: Optional[str] = None) -> Optional[str]:
        """Write a handoff document. Returns the saved path when there is one."""
        if not self.spec.supports_handoff:
            return None
        params = {"customInstructions": instructions} if instructions else None
        try:
            data = await self.transport.request(
                "handoff", params, timeout=_LLM_COMMAND_TIMEOUT
            )
        except Exception as exc:
            logger.warning("pi_family: handoff failed: %s", exc)
            await self._post(f"⚠️ Handoff failed: {exc}")
            return None
        return as_str(as_dict(data).get("savedPath")) or None

    # ------------------------------------------------------------------
    # Vicoa-side pushes
    # ------------------------------------------------------------------

    async def _post(self, content: str, metadata: Optional[dict] = None) -> None:
        if not content:
            return
        try:
            await self.vicoa_client.send_message(
                content=content,
                agent_type=self.agent_type,
                agent_instance_id=self.instance_id,
                message_metadata=metadata,
            )
        except Exception:
            logger.exception("pi_family: send_message failed (%d chars)", len(content))

    async def _set_status(self, new_status: str) -> None:
        self.status = new_status
        if self.stopping and new_status.upper() not in _WRAPPER_STOP_STATUSES:
            return
        try:
            await self.vicoa_client.update_agent_instance_status(
                self.instance_id, new_status
            )
        except Exception:
            # Advisory: the next transition re-syncs.
            logger.warning("pi_family: failed to push status=%s", new_status)

    async def _patch_session_config(self, delta: dict) -> None:
        try:
            await self.vicoa_client.patch_agent_instance(
                self.instance_id, session_config=delta
            )
        except Exception:
            logger.debug("pi_family: PATCH session_config failed", exc_info=True)

    async def _persist_session_id(self) -> None:
        """Record the agent's session id so a later launch can resume it."""
        try:
            await self.vicoa_client.patch_agent_instance(
                self.instance_id,
                instance_metadata={"pi_session_id": self.agent_session_id},
            )
        except Exception:
            logger.debug("pi_family: failed to persist session id", exc_info=True)

    async def _flush_usage(self, *, force: bool = False) -> None:
        """Pull ``get_session_stats`` and stamp it onto ``instance_metadata``."""
        stats = await self._try_request("get_session_stats")
        if stats is None:
            return
        self._usage.set_context(context_from_session_stats(stats))
        core = self._usage.core()
        if core is None or (core == self._usage_last_core and not force):
            return
        blob = self._usage.blob()
        if blob is None:
            return
        try:
            await self.vicoa_client.patch_agent_instance(
                self.instance_id, instance_metadata={"usage": blob}
            )
            self._usage_last_core = core
        except Exception:
            logger.debug("pi_family: failed to flush usage", exc_info=True)

    # ------------------------------------------------------------------
    # Request helpers
    # ------------------------------------------------------------------

    async def _request(
        self, command: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        return await self.transport.request(command, params, timeout=_CONTROL_TIMEOUT)

    async def _try_request(
        self, command: str, params: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Send an optional command, returning ``None`` on any failure.

        Used for everything a build might not implement. Both agents answer an
        unrecognised command with ``Unknown command: …``, and the surfaces this
        feeds (models, stats, commands) all degrade gracefully to their static
        fallbacks.
        """
        try:
            return await self._request(command, params)
        except PiRpcError as exc:
            if exc.is_unknown_command:
                logger.debug("pi_family: %s unsupported by this build", command)
            else:
                logger.info("pi_family: %s failed: %s", command, exc)
            return None
        except Exception as exc:
            logger.info("pi_family: %s failed: %s", command, exc)
            return None

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    async def aclose(self) -> None:
        self._closed = True
        self._cancel_settle()
        for task in (self._watchdog_task, self._close_task):
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
        self._watchdog_task = None
        for task in list(self._dialog_tasks):
            if not task.done():
                task.cancel()
        self._permission_registry.cancel_all()
        self._auq_registry.cancel_all()
        if self.host_tools is not None:
            await self.host_tools.aclose()
        self._finish_turn()
        await self.transport.aclose()


__all__ = ["PiRuntimeSession"]
