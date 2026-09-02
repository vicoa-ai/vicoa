"""Native ``codex app-server`` session.

Drives a single Codex conversation for one ``agent_instance`` over the
JSON-RPC NDJSON transport. Scope of this slice (tracer bullet):

- bring-up: ``initialize`` -> ``initialized`` -> ``thread/start``
- one turn: ``turn/start`` -> ``item/completed(agentMessage)`` -> ``turn/completed``
- write one vicoa ``messages`` row per non-intercepted item

Out of scope here (subsequent slices, all numbered in
``plans/todos/native-codex-app-server.md``): permission flow, plan mode,
slash commands, thread resume, cancel/interrupt, more item variants,
token-usage snapshots, ``skills/changed`` invalidation, subprocess spawn,
crash-loop detector.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Dict, List, Optional

from integrations.headless import auq
from integrations.headless import usage as usage_mod
from integrations.headless.usage import UsageState
from integrations.headless.codex.item_renderer import render_item
from integrations.headless.codex.permission import (
    DECISION_CANCEL,
    parse_decision,
    render_command_permission_prompt,
    render_file_change_permission_prompt,
)
from integrations.headless.codex.transport import (
    CodexTransport,
    CodexTransportClosed,
)
from integrations.headless.permission import PermissionReplyRegistry
from integrations.headless.thinking import build_thinking_metadata
from integrations.headless.session_lifecycle import (
    WRAPPER_STOP_STATUSES as _WRAPPER_STOP_STATUSES,
)
from vicoa.attachments import (
    AttachmentRef,
    attachment_note,
    attachments_dir,
    is_image_mime,
    save_attachment,
    unavailable_note,
)


# 24 hours — matches the claude_code AUQ timeout
# (claude_code.py:80::ASK_USER_QUESTION_TIMEOUT_SECONDS). Long enough that a
# user can step away and come back; short enough that genuinely abandoned
# sessions don't leak futures forever.
_AUQ_TIMEOUT_SECONDS = 24 * 60 * 60

# Per-call request bounds forwarded to ``transport.send_request``. Codex work
# is legitimately long, so these bound the *handshake*, not the agent's
# thinking: ``turn/start`` only returns once codex accepts the turn (the turn
# itself streams afterwards); ``model/list`` and ``turn/interrupt`` are quick
# control RPCs. A stall in any of them used to hang the caller forever.
_TURN_START_TIMEOUT = 90.0
_MODEL_LIST_TIMEOUT = 10.0
_INTERRUPT_TIMEOUT = 10.0

# Silence watchdog (``_run_status_watchdog``): if codex sends *nothing at all*
# for this long while a turn is open — no deltas, no completion — settle the
# status row to AWAITING_INPUT and unwedge the parked turn. Ported from
# claude_code's watchdog (``_STATUS_SETTLE_IDLE_SECONDS`` / interval); the
# transport reader never stops, so any later output re-activates the session.
_STATUS_SETTLE_IDLE_SECONDS = 600.0
_STATUS_WATCHDOG_INTERVAL = 30.0

# How long ``interrupt`` waits for an in-flight ``turn/start`` to identify its
# turn before deciding what to interrupt. A Stop pressed in the gap between
# turn/start-sent and its response used to just settle status and miss the turn
# actually starting. Short so Stop still feels responsive.
_INTERRUPT_IDENTIFY_TIMEOUT = 5.0


logger = logging.getLogger(__name__)

_CLIENT_INFO = {"name": "vicoa", "title": "Vicoa", "version": "0.1"}


# Canonical vicoa-server agent_instance status strings (mirrors the values
# used by ``acp_base.py:_set_agent_status`` and the dashboard's status chips).
_STATUS_ACTIVE = "ACTIVE"
_STATUS_AWAITING_INPUT = "AWAITING_INPUT"


# Vicoa permission_mode -> codex per-turn overrides. The shape of these
# overrides is verified against codex 0.144.5's app-server schema (dumped via
# `codex app-server generate-json-schema`): approvalPolicy=AskForApproval,
# sandboxPolicy discriminated on `type`, collaborationMode={mode, settings}.
# Earlier 0.131.0/0.135.0 notes predate that schema-dump check.
#
# | vicoa permission_mode | approvalPolicy | sandboxPolicy.type   | collabMode |
# |-----------------------|----------------|----------------------|------------|
# | default               | (inherit)      | (inherit)            | default    |
# | bypassPermissions     | never          | dangerFullAccess     | default    |
PERMISSION_MODE_DEFAULT = "default"
PERMISSION_MODE_BYPASS = "bypassPermissions"


def _codex_question_to_vicoa(question: Dict[str, Any]) -> Dict[str, Any]:
    """Translate one Codex ``RequestUserInputQuestion`` to the shape vicoa-app
    / vicoa-web's picker parses (``auq.build_metadata`` normalises further).

    Key remapping:
    * ``header`` / ``question`` / ``options`` -> same names
    * ``isOther`` / ``isSecret`` -> dropped (vicoa picker has no equivalent).
      v1: when ``isOther`` is true and the user wants free text, they'd need
      a text-mode question. Codex doesn't currently emit text-mode questions
      via this RPC (it always has options); revisit if that changes.
    * No codex multi-select flag — defaults to single-select.
    """
    return {
        "question": question.get("question") or "",
        "header": question.get("header"),
        "options": question.get("options") or [],
        "multi_select": False,
    }


def _build_codex_answers(
    questions: List[Dict[str, Any]], decoded: Dict[str, Any]
) -> Dict[str, Dict[str, List[str]]]:
    """Map the dashboard's per-question reply onto Codex's
    ``{question.id: {answers: [labels]}}`` response shape.

    Iterates ``questions`` and ``decoded["answers"]`` in lockstep (the
    dashboard returns answers in question order). For each:
    * ``mode == "option"``: look up the selected option's label by index
      (single-select) or join indices (multi-select fallback).
    * ``mode == "text"``: pass the typed string straight through.

    Missing / empty answers are omitted; codex treats an absent question id
    the same as ``{answers: []}``.
    """
    answer_blocks = decoded.get("answers") or []
    out: Dict[str, Dict[str, List[str]]] = {}
    for i, question in enumerate(questions):
        qid = question.get("id")
        if not isinstance(qid, str) or not qid:
            continue
        if i >= len(answer_blocks):
            continue
        answer = answer_blocks[i]
        if not isinstance(answer, dict):
            continue
        labels: List[str] = []
        mode = answer.get("mode")
        if mode == "text":
            text = answer.get("text")
            if isinstance(text, str) and text.strip():
                labels.append(text.strip())
        elif mode == "option":
            options = question.get("options") or []
            indexes: List[int] = []
            if "option_indexes" in answer:
                raw_indexes = answer.get("option_indexes") or []
                indexes = [idx for idx in raw_indexes if isinstance(idx, int)]
            elif "option_index" in answer:
                idx = answer.get("option_index")
                if isinstance(idx, int):
                    indexes = [idx]
            for idx in indexes:
                if 0 <= idx < len(options) and isinstance(options[idx], dict):
                    label = options[idx].get("label")
                    if isinstance(label, str) and label:
                        labels.append(label)
        if labels:
            out[qid] = {"answers": labels}
    return out


class CodexAppServerSession:
    def __init__(
        self,
        *,
        vicoa_client: Any,
        instance_id: str,
        cwd: str,
        transport: CodexTransport,
        thread_id: Optional[str] = None,
        agent_type: str = "codex",
        model: Optional[str] = None,
        effort: Optional[str] = None,
        permission_mode: Optional[str] = None,
    ) -> None:
        self.vicoa_client = vicoa_client
        self.instance_id = instance_id
        self.cwd = cwd
        self.transport = transport
        self.thread_id = thread_id
        self.agent_type = agent_type
        # Per-turn overrides forwarded to ``turn/start``. Codex's default
        # model (``gpt-5-codex``) is NOT supported on ChatGPT auth, so
        # callers SHOULD pass an explicit model when the user is on
        # chatgpt — otherwise the first turn fails with HTTP 400.
        self.model = model
        self.effort = effort
        # vicoa-side permission_mode ("default" / "bypassPermissions").
        # `default` inherits the user's codex config; `bypassPermissions`
        # overrides approvalPolicy + sandboxPolicy. See PERMISSION_MODE_*
        # constants for the canonical mapping.
        self.permission_mode = permission_mode

        # Live model discovery (codex ``model/list``). Populated by
        # :py:meth:`discover_and_report_models` after bring-up; stays empty when
        # the installed codex predates ``model/list`` or the call fails, in
        # which case the static agent-catalog list is the picker fallback.
        self.available_models: List[Dict[str, str]] = []
        self.discovered_default_model: Optional[str] = None

        self.status = "starting"
        # Set by the runner when the session is closed from another client, so
        # a racing in-flight turn can't re-open the row via _set_status.
        self.stopping = False
        self.active_turn_id: Optional[str] = None
        # One in-flight turn at a time in v1. The future resolves when the
        # matching ``turn/completed`` notification arrives.
        self._turn_completed: Optional["asyncio.Future[None]"] = None
        # True between sending ``turn/start`` and it resolving (or failing).
        # ``interrupt`` consults this so a Stop that lands before the turn id
        # arrives waits for identification instead of mis-firing.
        self._turn_start_pending = False
        # Set once ``active_turn_id`` is known (or the turn/start attempt ends).
        # ``interrupt`` waits on it to target the turn that is actually starting.
        self._turn_identified: asyncio.Event = asyncio.Event()
        # Set on aclose so the status watchdog loop exits.
        self._closed = False
        self._watchdog_task: Optional["asyncio.Task[None]"] = None
        # Holds the fire-and-forget task spawned by ``_on_transport_closed`` so
        # it isn't garbage-collected mid-flight (asyncio keeps only a weak ref).
        self._close_task: Optional["asyncio.Task[None]"] = None

        # Live context-window + rate-limit usage stamped onto
        # instance_metadata.usage. Context is captured from tokenUsage
        # notifications during the turn and flushed at turn/completed; rate
        # limits flush immediately. ``_usage_last_core`` dedupes PATCHes.
        self._usage = UsageState()
        self._usage_last_core: Optional[dict] = None

        # Permission registry reuses the existing FIFO machinery from the
        # claude_code path so the WS routing semantics stay aligned across
        # agent types. Codex's ``acceptForSession`` is protocol-native; we
        # don't need vicoa-side caching.
        self._permission_registry = PermissionReplyRegistry()
        self._next_permission_id = 1

        # AskUserQuestion registry — same shape as claude's, keyed by a
        # vicoa-side ``request_id`` we mint per ``item/tool/requestUserInput``
        # call. The dashboard echoes ``request_id`` back inside the control
        # reply so the right pending future resolves.
        self._auq_registry = auq.AskUserQuestionRegistry()

        # Wire transport callbacks back into this session.
        self.transport.on_notification = self._handle_notification
        # Fires only on unexpected codex death (read-loop EOF/error). Unblocks a
        # turn parked on ``await completed`` — which isn't a transport request,
        # so the transport's fail-pending can't reach it — without waiting for
        # the 600s silence watchdog.
        self.transport.on_close = self._on_transport_closed
        self.transport.register_request_handler(
            "item/commandExecution/requestApproval",
            self._handle_command_approval,
        )
        self.transport.register_request_handler(
            "item/fileChange/requestApproval",
            self._handle_file_change_approval,
        )
        # AUQ (``item/tool/requestUserInput``): structured questions. v1
        # stub auto-cancels so codex doesn't block waiting on a human.
        # Reusing ``auq.AskUserQuestionRegistry`` for real wire-up is a
        # follow-up slice.
        self.transport.register_request_handler(
            "item/tool/requestUserInput",
            self._handle_user_input_request,
        )
        # ``item/permissions/requestApproval`` (extra fs / network grants).
        # Plan \xa76 v1 stub: auto-reply empty grant, scope=turn. Surfacing a
        # real UI for this is deferred.
        self.transport.register_request_handler(
            "item/permissions/requestApproval",
            self._handle_permissions_request,
        )

    async def start(self) -> None:
        await self.transport.start()
        # Start the silence watchdog now; it no-ops until a turn is open, so
        # running it across bring-up costs nothing and covers every return path.
        if self._watchdog_task is None:
            self._watchdog_task = asyncio.create_task(self._run_status_watchdog())
        await self.transport.send_request(
            "initialize",
            {"clientInfo": _CLIENT_INFO, "capabilities": {"experimentalApi": True}},
        )
        self.transport.notify("initialized", {})

        if self.thread_id is not None:
            try:
                result = await self.transport.send_request(
                    "thread/resume",
                    {"threadId": self.thread_id, "cwd": self.cwd},
                )
                self.thread_id = result.get("thread", {}).get("id", self.thread_id)
                # Resuming can hand back a different id; persist so the *next*
                # resume targets the thread codex actually continued.
                await self._persist_thread_id()
                await self._set_status(_STATUS_AWAITING_INPUT)
                return
            except Exception as exc:
                # Codex CLI upgrade with thread-file schema change, deletion
                # by user, or not_found / invalid_argument from codex itself.
                # Falling through to thread/start is silent and correct; log
                # at WARN so daemon operators can see the cadence.
                logger.warning(
                    "codex thread/resume failed for thread_id=%s; falling back "
                    "to thread/start: %s",
                    self.thread_id,
                    exc,
                )
                self.thread_id = None

        result = await self.transport.send_request("thread/start", {"cwd": self.cwd})
        self.thread_id = result["thread"]["id"]
        await self._persist_thread_id()
        await self._set_status(_STATUS_AWAITING_INPUT)

    async def discover_and_report_models(self) -> None:
        """Query codex ``model/list`` and PATCH the machine's real models onto
        session_config for the mid-session gear.

        Mirrors the ACP agents' live-model reporting
        (``acp_base._report_live_session_state``) but sourced from codex's
        ``model/list`` RPC, which returns the account/version-filtered set (with
        the true default) rather than the static catalog's version-agnostic
        guess. ``model/list`` is global to the app-server, so this is
        thread-independent and safe to run once after bring-up.

        Best-effort: an older codex without ``model/list``, an unresponsive
        server, or an auth error leaves ``available_models`` empty and the
        static agent-catalog list remains the picker fallback — the same
        graceful degradation paseo uses (``safeParse`` -> ``[]``).
        """
        models: List[Dict[str, str]] = []
        default_id: Optional[str] = None
        cursor: Optional[str] = None
        try:
            for _ in range(20):  # bounded pagination guard
                params: Dict[str, Any] = {"includeHidden": False}
                if cursor:
                    params["cursor"] = cursor
                result = await self.transport.send_request(
                    "model/list", params, timeout=_MODEL_LIST_TIMEOUT
                )
                for m in result.get("data") or []:
                    mid = m.get("id")
                    if not mid:
                        continue
                    models.append(
                        {"id": str(mid), "label": str(m.get("displayName") or mid)}
                    )
                    if m.get("isDefault") and default_id is None:
                        default_id = str(mid)
                cursor = result.get("nextCursor")
                if not cursor:
                    break
        except Exception as exc:
            logger.info(
                "codex session: model/list unavailable (%s); using static catalog",
                exc,
            )
            return

        self.available_models = models
        self.discovered_default_model = default_id
        if not models:
            return
        # current_model: the user's explicit spawn pick if any, else codex's
        # own default. The gear reads current_model (falling back to model).
        current = self.model or default_id
        delta: Dict[str, Any] = {"available_models": models}
        if current:
            delta["current_model"] = current
        try:
            await self.vicoa_client.patch_agent_instance(
                self.instance_id, session_config=delta
            )
            logger.info(
                "codex session: reported %d live models (default=%s, current=%s)",
                len(models),
                default_id,
                current,
            )
        except Exception:
            logger.warning(
                "codex session: failed to PATCH available_models (non-fatal)",
                exc_info=True,
            )

    async def on_user_message(
        self, text: str, attachments: "tuple[AttachmentRef, ...]" = ()
    ) -> None:
        if self.thread_id is None:
            raise RuntimeError("session not started")
        # Register the completion future and flip status BEFORE awaiting
        # turn/start. The transport's reader can race ahead and process
        # turn/completed before this coroutine resumes from send_request;
        # setting status here keeps the transition monotonic
        # (awaiting_input -> active -> awaiting_input).
        completed: "asyncio.Future[None]" = asyncio.get_running_loop().create_future()
        self._turn_completed = completed
        # Mark a turn/start in flight and clear the identification gate so an
        # interrupt racing this send waits for the turn id rather than missing
        # the turn about to start.
        self._turn_start_pending = True
        self._turn_identified.clear()
        await self._set_status(_STATUS_ACTIVE)
        logger.info(
            "codex session: starting turn (thread=%s, model=%s, user_text=%r)",
            self.thread_id,
            self.model,
            text[:80],
        )
        input_items = (
            await self._build_input_items(text, attachments)
            if attachments
            else [{"type": "text", "text": text}]
        )
        params: Dict[str, Any] = {
            "threadId": self.thread_id,
            "input": input_items,
        }
        if self.model:
            params["model"] = self.model
        if self.effort:
            params["effort"] = self.effort
        params.update(self._permission_mode_overrides())
        try:
            try:
                result = await self.transport.send_request(
                    "turn/start", params, timeout=_TURN_START_TIMEOUT
                )
            except asyncio.CancelledError:
                raise
            except CodexTransportClosed:
                # codex is gone. ``_on_transport_closed`` already reported the
                # death (with stderr) and settles the row; just unwind quietly
                # and make sure the row isn't left ACTIVE for this attempt.
                logger.warning("codex session: turn/start aborted — transport closed")
                await self._set_status(_STATUS_AWAITING_INPUT)
                return
            except Exception as exc:
                # turn/start stalled past its bound or codex rejected the turn
                # (e.g. model not allowed on this auth tier). Neither drives a
                # turn/completed, so without settling here the row stays ACTIVE
                # forever and the message is silently lost. Surface the reason
                # BEFORE settling — an agent-message POST re-opens the row as
                # ACTIVE, so the order matters (mirrors _handle_turn_completed).
                logger.warning("codex session: turn/start failed: %s", exc)
                await self._send_error_to_vicoa(
                    {"message": str(exc)}, prefix="Codex turn failed to start"
                )
                await self._set_status(_STATUS_AWAITING_INPUT)
                return
            # Real shape (codex 0.144.5 TurnStartResponse): {turn: {id,
            # status, ...}}. Plan said turnId at the top level — wrong;
            # corrected after observing live wire trace.
            turn = result.get("turn") or {}
            self.active_turn_id = turn.get("id")
            logger.info("codex session: turn started (turnId=%s)", self.active_turn_id)
            # Turn identified: release any interrupt waiting on the id.
            self._turn_start_pending = False
            self._turn_identified.set()
            await completed
            logger.info("codex session: turn complete (turnId=%s)", self.active_turn_id)
        finally:
            # Unblock any interrupt waiter even when turn/start raised (timeout,
            # transport closed) — it will see active_turn_id is None and settle.
            self._turn_start_pending = False
            self._turn_identified.set()
            self._turn_completed = None
            self.active_turn_id = None

    async def _run_status_watchdog(self) -> None:
        """Settle the status row when codex goes silent mid-turn.

        Codex normally drives ``ACTIVE -> AWAITING_INPUT`` from
        ``turn/completed``. If it drops that notification (app-server hiccup,
        lost frame) the turn coroutine parks on ``await completed`` forever and
        the row stays ``ACTIVE`` — only a user interrupt recovers it. This loop
        watches the transport's last-inbound-frame time and, after a long gap
        with a turn still open and no human reply pending, settles the row and
        unwedges the parked turn.

        Like claude_code's watchdog this NEVER stops the transport reader — a
        turn that resumes after the settle simply re-opens and re-marks the
        session ACTIVE via its normal notification path.
        """
        while not self._closed:
            try:
                await asyncio.sleep(_STATUS_WATCHDOG_INTERVAL)
            except asyncio.CancelledError:
                return
            if self._closed or self.stopping:
                continue
            # Nothing to settle unless a turn is actually in flight.
            turn_open = self.active_turn_id is not None or (
                self._turn_completed is not None and not self._turn_completed.done()
            )
            if not turn_open:
                continue
            # A pending human reply is a legitimate reason for codex to be quiet.
            if (
                self._permission_registry.has_pending()
                or self._auq_registry.has_pending()
            ):
                continue
            idle = asyncio.get_running_loop().time() - self.transport.last_activity
            if idle < _STATUS_SETTLE_IDLE_SECONDS:
                continue
            logger.warning(
                "codex session: no app-server output for %.0fs with a turn open; "
                "settling status to AWAITING_INPUT (transport reader stays open, "
                "later output re-activates the session)",
                idle,
            )
            await self._settle_stalled_turn()

    def _on_transport_closed(self, reason: str) -> None:
        """Transport read-loop reported codex died unexpectedly.

        Sync callback invoked on the event loop from the reader task. Unblock a
        turn parked on ``await completed`` (resolving the future lets
        ``on_user_message`` unwind and clear ``active_turn_id``), then schedule
        the async status settle + error surface. No-op once we're closing —
        aclose never triggers this path, but a shutdown racing a real death
        might.
        """
        if self._closed:
            return
        fut = self._turn_completed
        if fut is not None and not fut.done():
            fut.set_result(None)
        self._close_task = asyncio.create_task(
            self._handle_unexpected_transport_close(reason)
        )

    async def _handle_unexpected_transport_close(self, reason: str) -> None:
        logger.warning("codex session: transport closed unexpectedly: %s", reason)
        # Surface BEFORE settling: an agent-message POST re-opens the row as
        # ACTIVE (requires_user_input defaults False), so a settle-then-post
        # order would leave the stale spinner. The reason carries codex's
        # stderr tail when the spawn layer captured one.
        await self._send_error_to_vicoa(
            {"message": reason}, prefix="Codex exited unexpectedly"
        )
        await self._set_status(_STATUS_AWAITING_INPUT)

    async def _settle_stalled_turn(self) -> None:
        """Resolve a wedged turn: flip status, flush usage, unpark the awaiter.

        Resolving ``_turn_completed`` lets the parked ``on_user_message``
        coroutine unwind (clearing ``active_turn_id`` in its finally) so the
        session accepts the next message. A ``turn/completed`` that arrives
        afterwards is harmless — the future is already done and gets cleared.
        """
        await self._set_status(_STATUS_AWAITING_INPUT)
        await self._flush_usage()
        fut = self._turn_completed
        if fut is not None and not fut.done():
            fut.set_result(None)

    async def aclose(self) -> None:
        self._closed = True
        if self._watchdog_task is not None and not self._watchdog_task.done():
            self._watchdog_task.cancel()
            try:
                await self._watchdog_task
            except (asyncio.CancelledError, Exception):
                pass
            self._watchdog_task = None
        self._permission_registry.cancel_all()
        self._auq_registry.cancel_all()
        await self.transport.aclose()

    async def interrupt(self) -> None:
        """Cooperatively cancel the in-flight turn (plan \xa712 Layers 1+2).

        Order:
          1. Cancel pending permission/AUQ futures so their handlers reply
             with ``decision: cancel`` instead of waiting on the user.
          2. Send ``turn/interrupt`` to codex.

        Layer 3 (SIGTERM/SIGKILL escalation when codex doesn't honor the
        interrupt) lives in ``CodexSubprocess.aclose`` at the daemon layer.

        When there is no turn to interrupt we still settle the row on
        AWAITING_INPUT. Codex normally drives that transition from
        ``turn/completed``, but a Stop pressed with no active turn — the row
        showing a stale ACTIVE, or the click landing in the window between
        ``turn/start`` being sent and its response arriving — used to return
        silently, leaving the dashboard stuck on "active" with no way to
        clear it.
        """
        # Cancel any pending permission prompts first: their handlers are
        # awaiting registry futures; cancelling unblocks them and they
        # respond with decision=cancel. Same for AUQ — pending questions
        # resolve with empty answers (codex's cancel signal).
        self._permission_registry.cancel_all()
        self._auq_registry.cancel_all()

        # If a turn/start is mid-flight, its id hasn't landed yet. Wait briefly
        # for identification so we interrupt the turn that's actually starting
        # instead of no-op'ing on ``active_turn_id is None``. Bounded so a
        # Stop with genuinely no turn (or a wedged handshake) still settles.
        if self.active_turn_id is None and self._turn_start_pending:
            try:
                await asyncio.wait_for(
                    self._turn_identified.wait(), timeout=_INTERRUPT_IDENTIFY_TIMEOUT
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "codex interrupt: turn/start did not identify within %.0fs; "
                    "settling status",
                    _INTERRUPT_IDENTIFY_TIMEOUT,
                )

        if self.active_turn_id is None or self.thread_id is None:
            await self._set_status(_STATUS_AWAITING_INPUT)
            return
        try:
            await self.transport.send_request(
                "turn/interrupt",
                {"threadId": self.thread_id, "turnId": self.active_turn_id},
                timeout=_INTERRUPT_TIMEOUT,
            )
        except Exception as exc:
            # Codex may already be tearing down or have closed the transport.
            # Don't raise — the caller's job is "make a best-effort stop".
            logger.warning("codex turn/interrupt failed: %s", exc)
            # No turn/completed is coming if the request never landed, so
            # settle the status here instead of leaving the row on ACTIVE.
            await self._set_status(_STATUS_AWAITING_INPUT)

    def try_resolve_pending_reply(self, text: str) -> bool:
        """Resolve a pending permission prompt with ``text`` if one is open.

        Returns True when the text was consumed as a permission reply. The
        runner calls this in ``_route`` BEFORE enqueuing a message onto the
        serialized turn queue — a permission reply must resolve inline, since
        the turn awaiting it is exactly what would drain the queue, so queuing
        the reply behind that turn would deadlock.
        """
        if text and self._permission_registry.has_pending():
            return self._permission_registry.resolve_text(text)
        return False

    async def deliver_user_message(
        self, text: str, attachments: "tuple[AttachmentRef, ...]" = ()
    ) -> None:
        """Run one turn for a user message (or resolve a pending permission).

        Order: a pending permission reply resolves inline first (FIFO); AUQ and
        the new-message-during-pending-permission auto-cancel both land in later
        slices. Turn serialization and burst-coalescing live one layer up in
        ``CodexNativeRunner`` (single consumer over ``_turn_queue``), so this
        method stays a one-turn primitive that its callers await to completion.
        """
        if text and self._permission_registry.has_pending():
            if self._permission_registry.resolve_text(text):
                return
        await self.on_user_message(text, attachments)

    async def _build_input_items(
        self, text: str, attachments: "tuple[AttachmentRef, ...]"
    ) -> List[Dict[str, Any]]:
        """Build ``turn/start`` input items, downloading attachments to files.

        Every attachment is parked under ``~/.vicoa/attachments/<instance>``.
        Images are passed natively as ``localImage`` items (camelCase tag,
        app-server-protocol v2 ``UserInput``); other files are referenced by
        path in a text note that Codex opens with its own file tools. Failed
        downloads degrade to a text note so the agent knows something was meant
        to be attached.
        """
        image_items: List[Dict[str, Any]] = []
        notes: List[str] = []
        for ref in attachments:
            try:
                data, mime_type = await self.vicoa_client.download_attachment(ref.id)
                local = save_attachment(
                    attachments_dir(self.instance_id), ref, data, mime_type
                )
                if is_image_mime(mime_type):
                    image_items.append({"type": "localImage", "path": str(local.path)})
                else:
                    notes.append(attachment_note(local))
            except Exception:
                logger.exception(
                    "codex session: failed to download attachment %s", ref.id
                )
                notes.append(unavailable_note(ref))

        full_text = "\n".join(part for part in [text, *notes] if part)
        items: List[Dict[str, Any]] = []
        if full_text:
            items.append({"type": "text", "text": full_text})
        items.extend(image_items)
        return items

    async def _handle_command_approval(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return await self._run_permission_prompt(
            render_command_permission_prompt(params)
        )

    async def _handle_file_change_approval(
        self, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        return await self._run_permission_prompt(
            render_file_change_permission_prompt(params)
        )

    async def _run_permission_prompt(self, body: str) -> Dict[str, Any]:
        request_id = f"perm-{self._next_permission_id}"
        self._next_permission_id += 1
        fut = self._permission_registry.create(request_id)
        try:
            await self.vicoa_client.send_message(
                content=body,
                agent_type=self.agent_type,
                agent_instance_id=self.instance_id,
                requires_user_input=True,
                poll_for_reply=False,
            )
            reply = await fut
        except asyncio.CancelledError:
            # Session shutdown, transport close, or interrupt cancelled the
            # registry future. Tell codex to cancel this tool call.
            return {"decision": DECISION_CANCEL}
        return {"decision": parse_decision(reply)}

    async def _handle_user_input_request(
        self, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Surface ``item/tool/requestUserInput`` (Codex AskUserQuestion) to
        the dashboard's structured picker.

        Codex request shape (per ``codex-rs/protocol/src/request_user_input.rs``):
        ``{threadId, turnId, itemId, questions: [{id, header, question,
        isOther, isSecret, options?: [{label, description}]}]}``

        Codex response shape:
        ``{answers: {<question.id>: {answers: [<label>...]}}}`` -- a map
        keyed by the per-question ``id`` whose value is a list of selected
        labels (or free-text strings when the question is text-mode).
        Empty map signals cancel.

        Routing: the user's reply arrives as a vicoa control message which
        ``CodexNativeRunner._route`` -> ``maybe_route_auq_reply`` decodes and
        feeds into ``_auq_registry``. We await that future here and shape
        the decoded answers back into codex's keyed-by-question.id format.
        """
        questions = params.get("questions") or []
        if not isinstance(questions, list) or not questions:
            # No questions to ask; reply with empty answers (cancel).
            return {"answers": {}}

        request_id = uuid.uuid4().hex
        future = self._auq_registry.create(request_id)
        metadata = auq.build_metadata(
            questions=[_codex_question_to_vicoa(q) for q in questions],
            prompt=auq.ASK_USER_QUESTION_PROMPT_LABEL,
            tool_use_id=params.get("itemId"),
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
                logger.exception("codex AUQ: failed to POST prompt; cancelling request")
                return {"answers": {}}
            message_id = getattr(response, "message_id", None)
            self._auq_registry.bind_message_id(request_id, message_id)
            try:
                decoded = await asyncio.wait_for(future, timeout=_AUQ_TIMEOUT_SECONDS)
            except asyncio.TimeoutError:
                logger.warning(
                    "codex AUQ %s timed out after %ds; cancelling",
                    request_id,
                    _AUQ_TIMEOUT_SECONDS,
                )
                return {"answers": {}}
            except asyncio.CancelledError:
                # Session shutdown or interrupt cancelled the future. Tell
                # codex this AUQ was cancelled.
                return {"answers": {}}
        finally:
            self._auq_registry.cancel(request_id)

        if decoded.get("cancelled"):
            return {"answers": {}}
        return {"answers": _build_codex_answers(questions, decoded)}

    async def maybe_route_auq_reply(self, content: str) -> bool:
        """Try to resolve an in-flight AUQ from a dashboard control reply.

        Returns True if the message was a recognised AUQ reply (regardless
        of whether a future was waiting for it). Callers should NOT also
        route the same content to ``deliver_user_message`` — that would
        cause an AUQ reply to also start a new turn.
        """
        decoded = auq.decode_reply(content)
        if decoded is None:
            return False
        self._auq_registry.resolve(decoded)
        return True

    async def _handle_permissions_request(
        self, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """v1 stub for ``item/permissions/requestApproval``.

        Codex asks for additional fs/network grants mid-session. We reply
        with an empty grant scoped to the current turn — equivalent to
        "don't broaden anything, but don't cancel either". Surfacing the
        requested entries to the user lands in a follow-up slice.
        """
        logger.info(
            "codex emitted item/permissions/requestApproval; auto-stubbing empty "
            "grant (v1 stub). params=%r",
            params,
        )
        return {"permissions": {}, "scope": "turn"}

    async def _handle_notification(self, method: str, params: Dict[str, Any]) -> None:
        if method == "item/completed":
            await self._handle_item(params.get("item") or {})
            return
        if method == "turn/completed":
            await self._handle_turn_completed(params)
            return
        if method == "thread/tokenUsage/updated":
            # Per-conversation context window. Fires several times per turn;
            # store the latest and flush once at turn/completed to avoid
            # spamming broadcasts.
            self._usage.set_context(usage_mod.codex_context(params.get("tokenUsage")))
            return
        if method == "account/rateLimits/updated":
            # Session/weekly quota snapshot (full, unlike Claude's per-window
            # events). Flush immediately so a limit warning isn't delayed to
            # the end of the turn.
            if self._usage.set_limits(usage_mod.codex_limits(params.get("rateLimits"))):
                await self._flush_usage()
            return
        if method == "error":
            await self._handle_error_notification(params)
            return
        # Unhandled notifications are logged at DEBUG. Notifications like
        # ``item/agentMessage/delta`` and ``hook/started`` fire dozens of
        # times per turn — at INFO they drown out the actually-useful
        # lines. With --debug, they're still available.
        logger.debug("codex session: ignoring notification method=%s", method)

    async def _handle_turn_completed(self, params: Dict[str, Any]) -> None:
        # Real shape: {threadId, turn: {id, status, error, ...}}. Plan said
        # {threadId, turnId} — wrong; this corrects after live trace.
        turn = params.get("turn") or {}
        status = turn.get("status")
        error = turn.get("error")
        if status == "failed" and error:
            # Surface the failure to the chat. The model's apology won't
            # arrive because the request was rejected upstream (e.g. model
            # not allowed on the user's auth tier) — without this, the user
            # types a message and nothing happens, ever.
            await self._send_error_to_vicoa(error, prefix="Codex turn failed")
        await self._set_status(_STATUS_AWAITING_INPUT)
        # Flush the context window captured from tokenUsage notifications
        # during this turn (rate limits flush eagerly on their own event).
        await self._flush_usage()
        fut = self._turn_completed
        if fut is not None and not fut.done():
            fut.set_result(None)

    async def _persist_thread_id(self) -> None:
        """Record codex's thread id so the session can be resumed later.

        ``thread/resume`` needs the id codex assigned, which lives only in this
        process's memory — when the wrapper exits it is lost and the
        conversation becomes unresumable even though the protocol supports it.

        ``instance_metadata`` is shallow-merged server-side, so this preserves
        sibling keys (notably ``usage``). Best-effort: failing to record the id
        costs a future resume, it must never break the session bringing up now.
        """
        if not (self.vicoa_client and self.instance_id and self.thread_id):
            return
        try:
            await self.vicoa_client.patch_agent_instance(
                self.instance_id,
                instance_metadata={"codex_thread_id": self.thread_id},
            )
        except Exception:
            logger.debug("codex session: failed to persist thread id", exc_info=True)

    async def _flush_usage(self) -> None:
        """PATCH the merged usage blob onto instance_metadata.usage.

        Best-effort: dedupes no-op flushes and swallows errors so a usage
        stamp can never break a turn.
        """
        if not (self.vicoa_client and self.instance_id):
            return
        core = self._usage.core()
        if core is None or core == self._usage_last_core:
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
            logger.debug("codex session: failed to flush usage blob", exc_info=True)

    def _permission_mode_overrides(self) -> Dict[str, Any]:
        """Return the turn/start params that realise the vicoa permission_mode.

        Returns an empty dict for ``default`` / unset — codex inherits from
        ``~/.codex/config.toml`` and any thread-level defaults.

        Wire shape verified against codex 0.144.5:
        * ``approvalPolicy``: ``AskForApproval`` string enum
        * ``sandboxPolicy``: object with discriminant ``type`` (camelCase
          variant name); ``readOnly`` / ``workspaceWrite`` / ``dangerFullAccess``
        * ``collaborationMode``: ``{mode: "plan"|"default", settings: {...}}``
          (per ``codex-rs/app-server/tests/suite/v2/plan_item.rs`` fixture).
        """
        mode = self.permission_mode
        if mode == PERMISSION_MODE_BYPASS:
            return {
                "approvalPolicy": "never",
                "sandboxPolicy": {"type": "dangerFullAccess"},
                "collaborationMode": {
                    "mode": "default",
                    "settings": self._collab_settings(),
                },
            }
        # default / None / unknown: no overrides; codex uses its own config.
        return {}

    def _collab_settings(self) -> Dict[str, Any]:
        """Settings sub-object on CollaborationMode.

        ``model`` is required by the Rust ``Settings`` struct — fall back to
        an empty string when we don't have an override, mirroring how the
        codex TUI sends the user's selected preset name when no explicit
        model is set. ``reasoning_effort`` and ``developer_instructions``
        are optional.
        """
        settings: Dict[str, Any] = {"model": self.model or ""}
        if self.effort:
            settings["reasoning_effort"] = self.effort
        return settings

    async def _set_status(self, new_status: str) -> None:
        """Update local status and best-effort POST to vicoa-server.

        Vicoa-server stores ``instance.status`` as the chat surface label
        (ACTIVE while a turn runs, AWAITING_INPUT once it returns). Without
        this push the dashboard stays stuck on whatever status the row had
        when ``register_agent_instance`` created it — so the user sees
        "ACTIVE" forever after a successful turn.
        """
        self.status = new_status
        # If the session was closed from another client, a racing in-flight
        # turn could re-open the row we were told to shut down. Suppress
        # non-terminal writes once stopping.
        if self.stopping and new_status.upper() not in _WRAPPER_STOP_STATUSES:
            return
        try:
            await self.vicoa_client.update_agent_instance_status(
                self.instance_id, new_status
            )
        except Exception:
            # Status updates are advisory. Don't crash the session if the
            # network blips or vicoa-server returns 5xx — the next status
            # transition will re-sync.
            logger.warning(
                "codex session: failed to push status=%s to vicoa", new_status
            )

    async def _handle_error_notification(self, params: Dict[str, Any]) -> None:
        # codex emits the raw error mid-turn before turn/completed; if it
        # will retry we don't want to spam the chat, so check willRetry.
        if params.get("willRetry"):
            logger.info(
                "codex session: error notification (will retry): %s",
                params.get("error"),
            )
            return
        await self._send_error_to_vicoa(params.get("error") or {}, prefix="Codex error")

    async def _send_error_to_vicoa(self, error: Dict[str, Any], *, prefix: str) -> None:
        message = error.get("message") if isinstance(error, dict) else None
        if not message:
            message = str(error)
        # codex sometimes wraps a JSON string inside .message (the upstream
        # OpenAI 400 body). Try to unwrap it for readability.
        try:
            import json as _json

            decoded = _json.loads(message)
            inner = (
                decoded.get("error", {}).get("message")
                if isinstance(decoded, dict)
                else None
            )
            if inner:
                message = inner
        except (ValueError, TypeError):
            pass
        body = f"⚠️ **{prefix}**\n\n{message}"
        logger.warning("codex session: surfacing error to vicoa: %s", message)
        try:
            await self.vicoa_client.send_message(
                content=body,
                agent_type=self.agent_type,
                agent_instance_id=self.instance_id,
            )
        except Exception:
            logger.exception(
                "codex session: failed to surface error to vicoa: %s", message
            )

    async def _handle_item(self, item: Dict[str, Any]) -> None:
        item_type = item.get("type")
        content = render_item(item)
        if content is None:
            logger.info(
                "codex session: item %s rendered to nothing (dropped). keys=%s",
                item_type,
                sorted(item.keys()),
            )
            return
        logger.info(
            "codex session: writing item %s to vicoa (%d chars)",
            item_type,
            len(content),
        )
        # Reasoning items become a collapsed "thinking" card (metadata-tagged)
        # instead of an inline reasoning bubble; the rendered text still rides
        # in ``content`` so pre-card clients degrade to inline text.
        message_metadata = (
            build_thinking_metadata("codex") if item_type == "reasoning" else None
        )
        try:
            await self.vicoa_client.send_message(
                content=content,
                agent_type=self.agent_type,
                agent_instance_id=self.instance_id,
                message_metadata=message_metadata,
            )
        except Exception:
            logger.exception(
                "codex session: vicoa send_message failed for item %s", item_type
            )
