#!/usr/bin/env python3
"""Headless Codex integration for Vicoa via the native ``codex app-server``.

Daemon entry point. Default codex backend; ``machine_daemon.py`` spawns
this module unconditionally for every ``codex`` agent_type. The legacy
ACP modules (``integrations.headless.codex_acp``,
``vicoa.agents.codex_acp``) remain on disk for rollback / investigation
only.

Lifecycle:
  1. Register the agent_instance with vicoa-server (so the dashboard can
     see it appear).
  2. Spawn ``codex app-server`` via ``codex/spawn.py`` and wire a
     ``CodexAppServerSession`` on top of its stdio.
  3. Stream user messages from vicoa-server; route control commands
     (``interrupt``) to ``session.interrupt()`` and everything else to
     ``session.deliver_user_message()``.
  4. On SIGTERM/SIGINT, cancel cleanly. Always end_session in the finally
     block so the dashboard shows the right final status.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import shutil
import signal
import sys
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from integrations.headless import auq, control_command
from integrations.headless.codex.spawn import (
    CodexSubprocess,
    spawn_codex_app_server,
)
from integrations.headless.codex_app_server import CodexAppServerSession
from integrations.headless.session_lifecycle import instance_update_requests_stop
from integrations.utils.heartbeat import AsyncSessionHeartbeat
from vicoa.agents.codex_acp import read_codex_auth_openai_key
from vicoa.attachments import AttachmentRef, extract_attachment_refs
from vicoa.sdk.async_client import AsyncVicoaClient
from vicoa.sdk.exceptions import AuthenticationError
from vicoa.session_ws_client import SessionMessagesWsClient
from vicoa.utils import derive_ws_url, get_project_path


logger = logging.getLogger(__name__)


# Human-readable labels for the codex `permission_mode` wire slugs the
# gear pill sends. Sourced from the codex entry in
# ``shared/agent_catalog.py`` (`permission_modes`); kept inline because the
# catalog has no label-lookup accessor and the codex set is only two
# values. If a new slug appears in the catalog, add it here so the user
# sees "Permission mode changed to <Label>" instead of the raw slug.
_PERMISSION_MODE_LABELS: Dict[str, str] = {
    "default": "Default",
    "bypassPermissions": "Full Access",
}


def setup_logging(
    session_id: str, *, console_output: bool = True, debug: bool = False
) -> None:
    """Install a per-session log file under ``~/.vicoa/codex_native/<id>.log``.

    Mirrors ``claude_code.setup_logging`` (claude_code.py:142). The file
    handler captures DEBUG always so a session's full wire trace is
    available for post-mortem; the console handler honours --debug.
    """
    root = logging.getLogger()
    # Don't wipe handlers globally — the daemon parent may have installed its
    # own. Only ensure we add our handlers once even on import re-entry.
    if any(
        getattr(h, "_codex_native_session", None) == session_id for h in root.handlers
    ):
        return

    vicoa_dir = Path.home() / ".vicoa"
    log_dir = vicoa_dir / "codex_native"
    log_dir.mkdir(exist_ok=True, parents=True)
    log_file = log_dir / f"{session_id}.log"

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    file_handler._codex_native_session = session_id  # type: ignore[attr-defined]
    root.addHandler(file_handler)

    if console_output:
        # If the parent process already streams to a console, this duplicates
        # — but matches the claude_code shape and keeps `vicoa daemon`'s
        # stdout view useful for live debugging.
        if not any(
            isinstance(h, logging.StreamHandler)
            and not isinstance(h, logging.FileHandler)
            for h in root.handlers
        ):
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.DEBUG if debug else logging.INFO)
            console_handler.setFormatter(formatter)
            root.addHandler(console_handler)

    root.setLevel(logging.DEBUG if debug else logging.INFO)
    logger.info("codex_native: logging to %s", log_file)


class CodexNativeRunner:
    """Owns the WS stream loop + signal handlers + lifecycle around
    ``CodexAppServerSession``.

    Not unit-tested as a whole — exercised end-to-end through real
    vicoa-server + real ``codex app-server``. The orchestrated pieces it
    composes (session, transport, spawn) are unit-tested in
    ``tests/test_codex_app_server.py``, ``test_codex_subprocess.py``, etc.
    """

    def __init__(
        self,
        *,
        vicoa_api_key: str,
        vicoa_base_url: str,
        session_id: str,
        cwd: str,
        agent_name: str,
        initial_prompt: Optional[str],
        thread_id: Optional[str],
        auth_method: str,
        codex_api_key: Optional[str],
        openai_api_key: Optional[str],
        codex_binary_command: Optional[List[str]] = None,
        model: Optional[str] = None,
        effort: Optional[str] = None,
        permission_mode: Optional[str] = None,
        is_resuming: bool = False,
    ) -> None:
        self.api_key = vicoa_api_key
        self.base_url = vicoa_base_url
        self.session_id = session_id
        self.cwd = cwd
        self.project_path = get_project_path(self.cwd)
        self.agent_name = agent_name
        self.initial_prompt = initial_prompt
        self.thread_id = thread_id
        # Reattaching an existing instance row. Registration would 409 on
        # anything that isn't a pre-allocated STARTING row, so resume
        # reopens the instance instead.
        self.is_resuming = is_resuming
        self.auth_method = auth_method
        self.codex_api_key = codex_api_key
        self.openai_api_key = openai_api_key
        self.codex_binary_command = codex_binary_command
        self.model = model
        self.effort = effort
        self.permission_mode = permission_mode

        self.running = True
        self.vicoa_client: Optional[AsyncVicoaClient] = None
        self.codex_subproc: Optional[CodexSubprocess] = None
        self.session: Optional[CodexAppServerSession] = None
        self._main_task: Optional[asyncio.Task[Any]] = None
        # WS client runs in its own thread (sync websocket lib); we bridge
        # its callback into the asyncio loop via run_coroutine_threadsafe.
        self._ws_client: Optional[SessionMessagesWsClient] = None
        self._ws_thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._heartbeat: Optional[AsyncSessionHeartbeat] = None
        # Serialized turn pipeline. ``_route`` enqueues user messages here and a
        # single long-lived consumer (``_consume_user_messages``) runs them one
        # turn at a time, coalescing any burst that piled up while a turn was
        # running into ONE follow-up turn. A single consumer (vs. the old
        # fire-and-forget ``create_task`` per message) removes both the
        # concurrent-turn race on the session's single turn slot and the risk of
        # a dropped task reference stranding a message. Mirrors claude_code's
        # ``run()`` + ``_wait_for_user_input`` loop.
        self._turn_queue: "asyncio.Queue[tuple[str, tuple[AttachmentRef, ...], Optional[str]]]" = asyncio.Queue()
        self._consumer_task: Optional[asyncio.Task[None]] = None
        # Ids of queued user messages the user cancelled before this wrapper
        # picked them up. The cancel arrives as a ``message-update`` WS event
        # after the row was already enqueued on ``_turn_queue``, so it can only
        # be honored at drain time — ``_consume_user_messages`` drops any id in
        # this set. Mirrors claude_code's ``_cancelled_message_ids`` (ACP has the
        # same set). Without it a cancel only updates the DB/UI and codex still
        # runs the message. Every id added here is discarded at the next drain,
        # so it can't grow unbounded (a cancel is only broadcast while the row is
        # still queued, i.e. still waiting in ``_turn_queue``).
        self._cancelled_message_ids: set[str] = set()

    # ------------------------------------------------------------------
    # Setup helpers
    # ------------------------------------------------------------------

    def _install_signal_handlers(self) -> None:
        loop = asyncio.get_running_loop()

        def handle_term() -> None:
            logger.info("codex_native: received termination signal")
            self.running = False
            if self._main_task is not None and not self._main_task.done():
                self._main_task.cancel()

        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, handle_term)
            except NotImplementedError:
                # Windows: signal handlers are not available on the loop.
                pass

    def _build_codex_env(self) -> Dict[str, str]:
        env = dict(os.environ)
        if self.auth_method == "codex-api-key" and self.codex_api_key:
            env["CODEX_API_KEY"] = self.codex_api_key
            env.pop("OPENAI_API_KEY", None)
        elif self.auth_method == "openai-api-key" and self.openai_api_key:
            env["OPENAI_API_KEY"] = self.openai_api_key
            env.pop("CODEX_API_KEY", None)
        else:
            # chatgpt auth: trust user's ~/.codex/auth.json
            env.pop("CODEX_API_KEY", None)
            env.pop("OPENAI_API_KEY", None)
        return env

    # ------------------------------------------------------------------
    # Run loop
    # ------------------------------------------------------------------

    def _build_session_config(self) -> dict:
        """Snapshot of spawn-time config for the chat-header pill. See the
        same method on HeadlessClaudeRunner for the rationale on stripping
        None-valued keys."""
        sc = {
            "agent": "codex",
            "model": self.model,
            "reasoning_effort": self.effort,
            "permission_mode": self.permission_mode,
        }
        return {k: v for k, v in sc.items() if v is not None}

    async def run(self) -> int:
        self._main_task = asyncio.current_task()
        self._loop = asyncio.get_running_loop()
        self._install_signal_handlers()
        try:
            self.vicoa_client = AsyncVicoaClient(
                api_key=self.api_key, base_url=self.base_url
            )
            if self.is_resuming:
                # The row already exists; re-registering it returns 409. Reopen
                # it instead so the UI stops showing the session as stopped
                # while codex comes back up.
                logger.info("codex_native: resuming instance %s", self.session_id)
                try:
                    # AWAITING_INPUT, not ACTIVE: the agent is idle waiting for
                    # the user, and ACTIVE renders a "working" spinner for an
                    # agent that isn't doing anything.
                    await self.vicoa_client.update_agent_instance_status(
                        self.session_id, "AWAITING_INPUT"
                    )
                except Exception:
                    logger.warning(
                        "codex_native: failed to reopen instance on resume",
                        exc_info=True,
                    )
            else:
                # Bound registration to 10s and abort on timeout, mirroring
                # HeadlessClaudeRunner.initialize (claude_code.py). Without the
                # cap the SDK client retries with backoff for up to ~60s (30s
                # per-request timeout × 6 attempts); a registration that only
                # succeeds AFTER the app's ~16s spawn wait window has elapsed
                # leaves an orphan codex session running unregistered — burning
                # the user's usage — while the app already told the user the
                # spawn failed (instance_never_registered). Re-raise so run()'s
                # fatal-error path exits the process instead of registering late.
                try:
                    await asyncio.wait_for(
                        self.vicoa_client.register_agent_instance(
                            agent_type="codex",
                            agent_instance_id=self.session_id,
                            name=self.agent_name,
                            project=self.project_path,
                            home_dir=str(Path.home()),
                            session_config=self._build_session_config(),
                        ),
                        timeout=10.0,
                    )
                except asyncio.TimeoutError:
                    logger.error(
                        "codex_native: agent instance registration timed out "
                        "for session %s — aborting",
                        self.session_id,
                    )
                    raise

            # Keep the session reading as alive while it sits idle awaiting
            # user input — see integrations/utils/heartbeat.py.
            self._heartbeat = AsyncSessionHeartbeat(
                agent_instance_id=self.session_id,
                vicoa_client=self.vicoa_client,
            )
            self._heartbeat.start()

            self.codex_subproc = await spawn_codex_app_server(
                command=self.codex_binary_command,
                cwd=self.cwd,
                env=self._build_codex_env(),
            )
            self.session = CodexAppServerSession(
                vicoa_client=self.vicoa_client,
                instance_id=self.session_id,
                cwd=self.cwd,
                transport=self.codex_subproc.transport,
                thread_id=self.thread_id,
                agent_type="codex",
                model=self.model,
                effort=self.effort,
                permission_mode=self.permission_mode,
            )
            await self.session.start()

            # Discover the machine's real codex models (account/version
            # filtered, with the true default) via `model/list` and PATCH them
            # onto session_config, so the gear shows the actual list instead of
            # static-catalog guesses. Best-effort; never blocks bring-up.
            try:
                await self.session.discover_and_report_models()
            except Exception:
                logger.warning(
                    "codex_native: model discovery failed (non-fatal)",
                    exc_info=True,
                )

            # Start the single turn consumer before the WS subscriber can
            # deliver anything, so no message races ahead of its drain. Held on
            # ``self`` so the loop keeps a strong reference (a bare create_task
            # can be garbage-collected mid-flight).
            self._consumer_task = asyncio.create_task(self._consume_user_messages())

            self._start_ws_client()

            if self.initial_prompt:
                # POST as a user message so the dashboard shows it in the
                # chat. Do NOT call deliver_user_message directly here —
                # vicoa-server broadcasts the POSTed row back to our WS
                # subscription (catch-up or live), which routes through
                # :py:meth:`_on_ws_user_message` -> :py:meth:`_route` ->
                # ``deliver_user_message``. Calling deliver directly would
                # cause two turn/start calls for the same input.
                #
                # Wait for the WS subscriber to finish its catch-up handshake
                # before POSTing, so the broadcast lands on an attached
                # subscription and the prompt is delivered in order. See the
                # codex_native catch-up race investigation 2026-06-06. The
                # wait is an optimisation, not the correctness guarantee —
                # ``mark_as_read=False`` below covers the timeout path.
                if self._ws_client is not None:
                    ready = await asyncio.to_thread(
                        self._ws_client.wait_until_ready, 10.0
                    )
                    if not ready:
                        logger.warning(
                            "codex_native: WS catch-up not ready after 10s; "
                            "POSTing initial prompt anyway"
                        )
                try:
                    # ``mark_as_read=False`` is load-bearing — see the long
                    # comment on the same POST in ``claude_code.initialize``.
                    # The default (True) points the server's
                    # ``last_read_message_id`` at this row, and the catch-up
                    # cursor fallback then excludes the prompt from its own
                    # recovery, hanging the session forever when the
                    # ``ready`` wait above timed out.
                    await self.vicoa_client.send_user_message(
                        agent_instance_id=self.session_id,
                        content=self.initial_prompt,
                        mark_as_read=False,
                    )
                except Exception:
                    logger.exception(
                        "codex_native: failed to POST initial prompt as user message"
                    )

            # Park until the stream loop or signal handler flips `running`
            # off. asyncio.sleep yields cooperatively so the stream task
            # gets scheduled.
            while self.running:
                await asyncio.sleep(1.0)
            return 0
        except (KeyboardInterrupt, asyncio.CancelledError):
            logger.info("codex_native: interrupted, shutting down")
            self.running = False
            return 0
        except Exception:
            logger.exception("codex_native: fatal error")
            return 1
        finally:
            self.running = False
            # Stop the turn consumer so a parked ``deliver_user_message`` (e.g.
            # awaiting turn/completed) doesn't outlive the loop.
            if self._consumer_task is not None and not self._consumer_task.done():
                self._consumer_task.cancel()
                try:
                    await self._consumer_task
                except (asyncio.CancelledError, Exception):
                    pass
            # Stop heartbeating before end_session, so an in-flight beat can't
            # make a finished session look freshly alive.
            if self._heartbeat is not None:
                try:
                    await self._heartbeat.stop()
                except Exception:
                    logger.exception("codex_native: heartbeat stop failed")
            if self._ws_client is not None:
                try:
                    self._ws_client.stop()
                except Exception:
                    logger.exception("codex_native: WS client stop failed")
            if self._ws_thread is not None and self._ws_thread.is_alive():
                # Daemon thread: even if join times out, process exit kills it.
                self._ws_thread.join(timeout=5.0)
            if self.session is not None:
                try:
                    await self.session.aclose()
                except Exception:
                    logger.exception("session aclose failed")
            if self.codex_subproc is not None:
                try:
                    await self.codex_subproc.aclose()
                except Exception:
                    logger.exception("codex subprocess aclose failed")
            if self.vicoa_client is not None:
                try:
                    await self.vicoa_client.end_session(self.session_id)
                except Exception:
                    logger.exception("end_session failed")
                try:
                    await self.vicoa_client.close()
                except Exception:
                    pass

    def _start_ws_client(self) -> None:
        """Spin up the session-scoped /ws subscriber on a background thread.

        Replaces the legacy SSE per-instance stream. ``SessionMessagesWsClient``
        handles hello, ``fetch_messages_request`` catch-up (so we don't need a
        separate ``get_pending_messages`` drain), live ``new-message``
        delivery, and reconnect-with-jitter. We bridge its sync callback into
        the asyncio loop via ``asyncio.run_coroutine_threadsafe``.
        """
        ws_url = os.environ.get("VICOA_WS_URL") or derive_ws_url(self.base_url)
        cli_version = os.environ.get("VICOA_CLI_VERSION")
        self._ws_client = SessionMessagesWsClient(
            ws_url=ws_url,
            api_key=self.api_key,
            instance_id=self.session_id,
            on_user_message=self._on_ws_user_message,
            cli_version=cli_version,
            on_message_update=self._on_ws_message_update,
            on_instance_update=self._on_ws_instance_update,
        )
        self._ws_thread = threading.Thread(
            target=self._ws_thread_target,
            name=f"codex-native-ws-{self.session_id[:8]}",
            daemon=True,
        )
        self._ws_thread.start()
        logger.info("codex_native: WS subscriber connected to %s", ws_url)

    def _ws_thread_target(self) -> None:
        """Thread target that absorbs a fatal-auth AuthenticationError.

        Same rationale as ``InputRequestManager._ws_thread_target`` in the
        claude wrapper — PR #45's `_drop_vicoa_link` covers REST sites but
        not the WS thread's run(). A 4401 close raises AuthenticationError;
        without a wrap the thread dies with a traceback to stderr. Catch it
        here, log a clean one-liner, exit the thread silently.
        """
        client = self._ws_client
        if client is None:
            return
        try:
            client.run()
        except AuthenticationError as exc:
            logger.info("codex_native WS link closed: %s", exc)

    def _on_ws_instance_update(self, body: Dict[str, Any]) -> None:
        """WS-thread callback for instance row changes.

        Stops the runner when the session is archived/closed elsewhere, so the
        agent doesn't keep running in the background after archiving.
        """
        try:
            if not instance_update_requests_stop(body):
                return
            loop = self._loop
            if loop is None or loop.is_closed():
                return
            loop.call_soon_threadsafe(self._stop_from_instance_update)
        except Exception:
            logger.exception("codex_native: instance-update callback raised")

    def _stop_from_instance_update(self) -> None:
        logger.info("codex_native: session closed elsewhere; stopping runner")
        self.running = False
        # Block a racing in-flight turn from re-opening the row via _set_status.
        if self.session is not None:
            self.session.stopping = True
        task = self._main_task
        if task is not None and not task.done():
            task.cancel()

    def _on_ws_message_update(self, body: Dict[str, Any]) -> None:
        """WS-thread callback: remember user-cancelled queued messages.

        The backend stamps ``message_metadata.queue.status = "cancelled"`` and
        broadcasts it when the user removes a still-queued message. We record the
        id so :py:meth:`_consume_user_messages` drops it at drain time instead of
        delivering it as a turn. ``set.add`` is atomic under the GIL, so — unlike
        the routing callbacks — no loop hop is needed. Mirrors
        claude_code._on_ws_message_update.
        """
        try:
            md = body.get("message_metadata") or {}
            status = (md.get("queue") or {}).get("status")
            message_id = body.get("id")
            if status == "cancelled" and message_id:
                self._cancelled_message_ids.add(str(message_id))
                logger.info(
                    "codex_native: user cancelled queued message %s", message_id
                )
        except Exception:
            logger.exception("codex_native: message-update callback raised")

    def _on_ws_user_message(self, body: Dict[str, Any]) -> None:
        """WS-thread callback. Bridge to the asyncio loop and route.

        ``body`` shape matches the ``new-message`` payload: ``{id, content,
        sender_type, created_at, ...}``. We filter to USER-sender messages
        (the broadcast also includes AGENT echoes of our own posts) and
        schedule :py:meth:`_route` on the asyncio loop. Exceptions raised
        here would otherwise crash the WS reader thread silently — catch
        and log.
        """
        try:
            sender = (body.get("sender_type") or "").lower()
            content = body.get("content") or ""
            attachments = tuple(extract_attachment_refs(body.get("message_metadata")))
            logger.info(
                "codex_native: WS new-message sender=%s len=%d attachments=%d",
                sender,
                len(content),
                len(attachments),
            )
            if sender not in {"user", "human"} or (not content and not attachments):
                return
            loop = self._loop
            if loop is None or loop.is_closed():
                return
            message_id = body.get("id")
            asyncio.run_coroutine_threadsafe(
                self._route(
                    content, attachments, str(message_id) if message_id else None
                ),
                loop,
            )
        except Exception:
            logger.exception("codex_native: WS callback raised")

    async def _route(
        self,
        content: str,
        attachments: "tuple[AttachmentRef, ...]" = (),
        message_id: Optional[str] = None,
    ) -> None:
        """Dispatch an inbound user message to the right path on the session.

        Order:
          1. AUQ ack / persist-only messages — silently swallowed (these
             are dashboard echoes of the user's structured AUQ answer).
          2. AUQ structured reply — resolve the AUQ registry; the in-flight
             ``_handle_user_input_request`` handler wakes up and replies to
             codex. Must be checked BEFORE control commands or new turns,
             since AUQ replies are JSON-wrapped control messages and would
             otherwise be misrouted.
          3. Control commands (``interrupt``) — call session.interrupt.
          4. Everything else — ``session.deliver_user_message`` (which
             handles pending permission FIFO + new turns internally).
        """
        assert self.session is not None
        logger.info("codex_native: routing user message (%d chars)", len(content))
        if auq.is_persist_only_message(content):
            logger.info("codex_native: dropping persist-only AUQ ack")
            return
        if await self.session.maybe_route_auq_reply(content):
            logger.info("codex_native: routed AUQ reply to pending question")
            return
        parsed = control_command.parse_control_command(content)
        if parsed is not None:
            setting = parsed.get("setting")
            value = parsed.get("value")
            logger.info(
                "codex_native: control command setting=%s value=%s", setting, value
            )
            if setting == "interrupt":
                # Post the notice BEFORE interrupting. Every agent-message
                # POST runs through create_agent_message, which re-opens the
                # row as ACTIVE whenever requires_user_input is False — so a
                # notice sent afterwards would undo the AWAITING_INPUT that
                # turn/completed (or interrupt() itself) is about to write.
                await self._send_feedback_message(
                    "Interrupted · What should Codex do instead?"
                )
                await self.session.interrupt()
            elif setting == "model" and value:
                # CodexAppServerSession reads .model on every turn/start, so
                # mutating the field makes the next turn use the new model.
                # PATCH session_config so mobile pill confirms immediately.
                # Include `agent: "codex"` so a row that started with NULL
                # session_config gets a complete identity (mobile's
                # SessionConfig.fromJson defaults missing agent to "claude").
                self.session.model = value
                await self._patch_session_config({"agent": "codex", "model": value})
                await self._send_feedback_message(f"Model changed to {value}")
                await self._mark_awaiting_input_after_settings_change("model")
            elif setting == "effort" and value:
                self.session.effort = value
                await self._patch_session_config(
                    {"agent": "codex", "reasoning_effort": value}
                )
                await self._send_feedback_message(f"Effort changed to {value}")
                await self._mark_awaiting_input_after_settings_change("effort")
            elif setting == "permission_mode" and value:
                # Same bundle of approval+sandbox+collab overrides applies
                # on every turn/start via _permission_mode_overrides.
                self.session.permission_mode = value
                await self._patch_session_config(
                    {"agent": "codex", "permission_mode": value}
                )
                label = _PERMISSION_MODE_LABELS.get(value, value)
                await self._send_feedback_message(f"Permission mode changed to {label}")
                await self._mark_awaiting_input_after_settings_change("permission_mode")
            # Unknown settings (thinking, etc.) are claude-specific or
            # legacy. Silently ignore.
            return
        # A permission reply must resolve inline — the turn awaiting it is what
        # drains the queue, so enqueuing it behind that turn would deadlock the
        # single consumer. Clear its queued badge too (it was stamped queued if
        # it landed while the row was ACTIVE).
        if content and self.session.try_resolve_pending_reply(content):
            logger.info("codex_native: resolved pending permission reply inline")
            await self._mark_message_consumed(message_id)
            return
        # Hand the message to the serialized consumer, which runs one turn at a
        # time and coalesces a burst the user sent while a turn was running into
        # a single follow-up turn. put_nowait never blocks (unbounded queue), so
        # the WS reader keeps flowing.
        logger.info("codex_native: enqueuing message for the turn consumer")
        self._turn_queue.put_nowait((content, attachments, message_id))

    @staticmethod
    def _coalesce_turn_batch(
        batch: "list[tuple[str, tuple[AttachmentRef, ...], Optional[str]]]",
    ) -> "tuple[str, tuple[AttachmentRef, ...]]":
        """Merge a burst of queued user messages into one turn's input.

        Non-empty texts join on a blank line so the agent sees them as a single
        prompt; attachments concatenate in arrival order. Message ids are
        handled separately (consumed stamp), so they're dropped here.
        """
        text = "\n\n".join(content for content, _, _ in batch if content)
        attachments: "tuple[AttachmentRef, ...]" = tuple(
            att for _, atts, _ in batch for att in atts
        )
        return text, attachments

    async def _mark_message_consumed(self, message_id: Optional[str]) -> None:
        """Clear a message's ``message_metadata.queue`` badge in the UI.

        The backend stamps every message that arrives while the row is ACTIVE
        as "queued"; nothing else in this wrapper clears it, so without this the
        web/app pins the message in its queued bar forever even after the agent
        has answered it. Best-effort — a failed stamp must never abort the turn.
        """
        if not message_id or self.vicoa_client is None:
            return
        try:
            await self.vicoa_client.mark_message_consumed(message_id)
        except Exception:
            logger.debug("codex_native: mark_message_consumed failed", exc_info=True)

    async def _consume_user_messages(self) -> None:
        """Single consumer: run queued user messages one turn at a time.

        Blocks on the next message, then drains everything else already waiting
        (non-blocking) and coalesces the batch into ONE turn — so a burst the
        user sent while a turn was running runs together, not one turn each.
        The bounded ``wait_for`` lets the loop notice ``running`` flipping off
        during shutdown. Mirrors claude_code's ``_wait_for_user_input`` drain.
        """
        assert self.session is not None
        while self.running:
            try:
                first = await asyncio.wait_for(self._turn_queue.get(), timeout=5.0)
            except asyncio.TimeoutError:
                continue
            batch = [first]
            while True:
                try:
                    batch.append(self._turn_queue.get_nowait())
                except asyncio.QueueEmpty:
                    break
            # Drop messages the user cancelled while the prior turn ran. The
            # cancel arrived as a message-update after the row was enqueued, so
            # this drain is the first point we can honor it. A cancelled message
            # is not consumed, so it's dropped before the consumed stamp below.
            kept = []
            for item in batch:
                message_id = item[2]
                if message_id and message_id in self._cancelled_message_ids:
                    self._cancelled_message_ids.discard(message_id)
                    logger.info(
                        "codex_native: dropping cancelled queued message %s",
                        message_id,
                    )
                    continue
                kept.append(item)
            if not kept:
                continue
            # Clear each message's queued badge as we pick the batch up — the
            # turn is starting, so it's no longer "queued". Mirrors the ACP /
            # claude_code consumed stamp.
            for _content, _att, message_id in kept:
                await self._mark_message_consumed(message_id)
            text, attachments = self._coalesce_turn_batch(kept)
            try:
                await self.session.deliver_user_message(text, attachments)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("codex_native: turn processing failed")

    async def _patch_session_config(self, delta: dict) -> None:
        """Best-effort PATCH so the mobile gear pill reflects mid-session
        model / effort / permission_mode changes. Fire-and-forget; the next
        successful PATCH overwrites any stale partial state."""
        if self.vicoa_client is None:
            return
        try:
            await self.vicoa_client.patch_agent_instance(
                self.session_id, session_config=delta
            )
            logger.info("codex_native: PATCH session_config %s", delta)
        except Exception:
            logger.warning(
                "codex_native: PATCH session_config failed (non-fatal)",
                exc_info=True,
            )

    async def _send_feedback_message(self, content: str) -> None:
        """POST a short agent-side message confirming the change to the
        chat surface. Mirrors HeadlessClaudeRunner._send_feedback_message
        (claude_code.py:965) — without it, the gear-pill toggle is silent
        in the chat and the user can't tell whether it took effect."""
        if self.vicoa_client is None:
            return
        try:
            await self.vicoa_client.send_message(
                content=content,
                agent_type=self.agent_name,
                agent_instance_id=self.session_id,
                requires_user_input=False,
            )
            logger.info("codex_native: sent feedback message: %s", content)
        except Exception:
            logger.warning(
                "codex_native: send feedback failed (non-fatal)", exc_info=True
            )

    async def _mark_awaiting_input_after_settings_change(self, setting: str) -> None:
        """Flip the agent_instance status to AWAITING_INPUT after a successful
        gear-pill change. The change fires while the session is idle, but the
        feedback POST itself transiently bumps the row to ACTIVE — this is the
        explicit "settle on AWAITING_INPUT" step so the mobile pill stops
        showing the stale active badge. Mirrors HeadlessClaudeRunner's
        helper of the same name (claude_code.py:939)."""
        if self.vicoa_client is None:
            return
        try:
            await self.vicoa_client.update_agent_instance_status(
                self.session_id, "AWAITING_INPUT"
            )
        except Exception as exc:
            logger.warning(
                "codex_native: failed to set status=AWAITING_INPUT after %s change: %s",
                setting,
                exc,
            )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Headless native codex app-server integration for Vicoa.",
    )
    parser.add_argument("--api-key", default=os.environ.get("VICOA_API_KEY"))
    parser.add_argument(
        "--base-url",
        default=os.environ.get("VICOA_BASE_URL")
        or os.environ.get("VICOA_API_URL")
        or "https://agents.vicoa.ai",
    )
    parser.add_argument("--project-path", default=os.getcwd())
    parser.add_argument("--name", default=os.environ.get("VICOA_AGENT_TYPE", "Codex"))
    parser.add_argument(
        "--session-id", default=os.environ.get("VICOA_AGENT_INSTANCE_ID")
    )
    parser.add_argument(
        "--codex-thread-id",
        default=None,
        help=(
            "Codex's own prior thread id, restored via thread/resume so the "
            "conversation continues. Falls back to a fresh thread when codex "
            "no longer knows it."
        ),
    )
    parser.add_argument(
        "--resume",
        default=None,
        help=(
            "Reattach to an existing Vicoa agent instance by id (skips "
            "registration, which would 409). Does NOT restore the "
            "conversation -- pass --codex-thread-id for that."
        ),
    )
    parser.add_argument(
        "--auth-method",
        choices=["chatgpt", "codex-api-key", "openai-api-key"],
        default=None,
    )
    parser.add_argument("--codex-api-key", default=None)
    parser.add_argument("--openai-api-key", default=None)
    parser.add_argument("--prompt", default=None)
    parser.add_argument(
        "--model",
        default=None,
        help="Codex model id (e.g. gpt-5). Default codex pick is gpt-5-codex, "
        "which is rejected on ChatGPT auth — pass an explicit model.",
    )
    parser.add_argument(
        "--reasoning-effort",
        default=None,
        choices=["low", "medium", "high", "xhigh"],
        help="ReasoningEffort override forwarded to turn/start as `effort`.",
    )
    # vicoa permission_mode -> codex per-turn overrides (approvalPolicy +
    # sandboxPolicy + collaborationMode). Resolved by the session at every
    # turn/start; see CodexAppServerSession._permission_mode_overrides.
    parser.add_argument(
        "--permission-mode",
        default=None,
        choices=["default", "bypassPermissions"],
        help="Vicoa permission preset: default (inherit codex config), "
        "bypassPermissions (Full Access).",
    )
    parser.add_argument(
        "--codex-binary",
        default=os.environ.get("VICOA_CODEX_BINARY"),
        help="Path to the `codex` binary (defaults to PATH lookup)",
    )
    # codex_acp.py exposes --codex-acp-command; ignore it here so the daemon's
    # current spawn-command builder doesn't break when it passes the flag
    # under the native-codex feature flag.
    parser.add_argument("--codex-acp-command", default=None, help=argparse.SUPPRESS)
    parser.add_argument(
        "--debug",
        action="store_true",
        default=os.environ.get("VICOA_DEBUG", "").strip().lower()
        in {"1", "true", "yes", "on"},
    )
    args = parser.parse_args()

    if not args.api_key:
        logger.error("Vicoa API key required: pass --api-key or set VICOA_API_KEY")
        return 1

    session_id = args.resume or args.session_id or str(uuid.uuid4())
    setup_logging(session_id, debug=args.debug)
    final_codex_api_key = args.codex_api_key or os.environ.get("CODEX_API_KEY")
    final_openai_api_key = (
        args.openai_api_key
        or os.environ.get("OPENAI_API_KEY")
        or read_codex_auth_openai_key()
    )
    auth_method = args.auth_method or (
        "codex-api-key"
        if final_codex_api_key
        else ("openai-api-key" if final_openai_api_key else "chatgpt")
    )

    # Compose `-c key=value` overrides for the codex binary command. Per
    # plan §3.7 / §5.7, only the knobs the chosen permission_mode actually
    # changes from codex defaults are emitted, so the user's
    # ~/.codex/config.toml keeps owning fields the UI doesn't touch.
    codex_overrides: List[str] = []
    if args.model:
        codex_overrides.extend(["-c", f"model={args.model}"])
    if args.reasoning_effort:
        codex_overrides.extend(
            ["-c", f"model_reasoning_effort={args.reasoning_effort}"]
        )
    if args.permission_mode:
        from integrations.headless.codex.permission_translate import (
            translate_permission_mode,
        )

        codex_overrides.extend(translate_permission_mode(args.permission_mode))

    binary_command: Optional[List[str]] = None
    if args.codex_binary:
        binary_command = [args.codex_binary, "app-server", *codex_overrides]
    elif codex_overrides:
        # Resolve PATH lookup here so we can append overrides even without
        # an explicit --codex-binary. spawn_codex_app_server's None default
        # also resolves codex, but it can't accept extra args alongside.
        codex_binary = shutil.which("codex")
        if codex_binary:
            binary_command = [codex_binary, "app-server", *codex_overrides]

    runner = CodexNativeRunner(
        vicoa_api_key=args.api_key,
        vicoa_base_url=args.base_url,
        session_id=session_id,
        cwd=args.project_path,
        agent_name=args.name,
        initial_prompt=args.prompt,
        thread_id=args.codex_thread_id,
        is_resuming=bool(args.resume),
        auth_method=auth_method,
        codex_api_key=final_codex_api_key,
        openai_api_key=final_openai_api_key,
        codex_binary_command=binary_command,
        model=args.model,
        effort=args.reasoning_effort,
        permission_mode=args.permission_mode,
    )

    logger.info(
        "codex_native: starting session=%s cwd=%s", session_id, args.project_path
    )

    try:
        return asyncio.run(runner.run())
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
