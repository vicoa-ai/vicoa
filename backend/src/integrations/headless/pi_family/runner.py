"""Process-level runner for a Pi-family session.

Owns everything around :class:`PiRuntimeSession`: registration with
vicoa-server, the WebSocket subscriber, the serialized turn queue, control
commands, signal handling, and teardown. Structurally the same as
``codex_native.CodexNativeRunner`` — deliberately, so the two headless native
wrappers stay readable side by side — with the Pi-family specifics confined to
the launch command and the control-command surface.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sys
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from integrations.agent_tools import AgentToolContext
from integrations.agent_tools.context import DEPTH_ENV_VAR, current_depth
from integrations.headless import auq, control_command
from integrations.headless.pi_family.host_tools import HostToolRouter
from integrations.headless.pi_family.protocol import (
    PiStartupError,
    ReadyGate,
    startup_failure_message,
)
from integrations.headless.pi_family.session import PiRuntimeSession
from integrations.headless.pi_family.spawn import PiSubprocess, spawn_pi_agent
from integrations.headless.pi_family.spec import (
    PI_FAMILY_AGENTS,
    PiFamilySpec,
    resolve_agent_binary,
)
from integrations.headless.session_lifecycle import instance_update_requests_stop
from integrations.utils.heartbeat import AsyncSessionHeartbeat
from vicoa.attachments import AttachmentRef, extract_attachment_refs
from vicoa.sdk.async_client import AsyncVicoaClient
from vicoa.sdk.exceptions import AuthenticationError
from vicoa.session_ws_client import SessionMessagesWsClient
from vicoa.utils import derive_ws_url, get_project_path


logger = logging.getLogger(__name__)


def setup_logging(
    session_id: str, *, console_output: bool = True, debug: bool = False
) -> None:
    """Per-session log file under ``~/.vicoa/pi_family/<id>.log``.

    Mirrors ``codex_native.setup_logging``: the file handler always captures
    DEBUG so a session's full wire trace is available post-mortem, while the
    console handler honours ``--debug``.
    """
    root = logging.getLogger()
    if any(getattr(h, "_pi_family_session", None) == session_id for h in root.handlers):
        return

    log_dir = Path.home() / ".vicoa" / "pi_family"
    log_dir.mkdir(exist_ok=True, parents=True)
    log_file = log_dir / f"{session_id}.log"

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    file_handler._pi_family_session = session_id  # type: ignore[attr-defined]
    root.addHandler(file_handler)

    if console_output and not any(
        isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
        for h in root.handlers
    ):
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG if debug else logging.INFO)
        console_handler.setFormatter(formatter)
        root.addHandler(console_handler)

    root.setLevel(logging.DEBUG if debug else logging.INFO)
    logger.info("pi_family: logging to %s", log_file)


class PiFamilyRunner:
    """WS stream loop + lifecycle around one :class:`PiRuntimeSession`."""

    def __init__(
        self,
        *,
        spec: PiFamilySpec,
        vicoa_api_key: str,
        vicoa_base_url: str,
        session_id: str,
        cwd: str,
        agent_name: str,
        initial_prompt: Optional[str] = None,
        agent_session_id: Optional[str] = None,
        model: Optional[str] = None,
        thinking_effort: Optional[str] = None,
        permission_mode: Optional[str] = None,
        agent_command: Optional[str] = None,
        is_resuming: bool = False,
    ) -> None:
        self.spec = spec
        self.api_key = vicoa_api_key
        self.base_url = vicoa_base_url
        self.session_id = session_id
        self.cwd = cwd
        self.project_path = get_project_path(self.cwd)
        self.agent_name = agent_name
        self.initial_prompt = initial_prompt
        self.agent_session_id = agent_session_id
        self.model = model
        self.thinking_effort = thinking_effort
        self.permission_mode = permission_mode
        self.agent_command = agent_command
        self.is_resuming = is_resuming

        self.running = True
        self.vicoa_client: Optional[AsyncVicoaClient] = None
        self.subprocess: Optional[PiSubprocess] = None
        self.session: Optional[PiRuntimeSession] = None
        self._main_task: Optional["asyncio.Task[Any]"] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._ws_client: Optional[SessionMessagesWsClient] = None
        self._ws_thread: Optional[threading.Thread] = None
        self._heartbeat: Optional[AsyncSessionHeartbeat] = None
        #: Serialized turn pipeline: one consumer runs turns one at a time and
        #: coalesces a burst sent during a turn into a single follow-up.
        self._turn_queue: "asyncio.Queue[tuple[str, tuple[AttachmentRef, ...], Optional[str]]]" = asyncio.Queue()
        self._consumer_task: Optional["asyncio.Task[None]"] = None
        #: Queued messages the user cancelled before we picked them up. The
        #: cancel arrives as a ``message-update`` after the row was enqueued, so
        #: it can only be honored at drain time.
        self._cancelled_message_ids: set[str] = set()

    # ------------------------------------------------------------------
    # Launch
    # ------------------------------------------------------------------

    def build_command(self) -> List[str]:
        """The full argv for the agent CLI.

        ``--session`` is only ever passed on a resume: the flag *resolves* an
        existing session and exits 1 for an unknown id, so handing it a
        Vicoa-generated id at first launch would hard-fail before the handshake.
        """
        binary = self.agent_command or resolve_agent_binary(self.spec)
        if binary is None:
            tried = ", ".join(self.spec.binaries)
            raise FileNotFoundError(
                f"{self.spec.display_name} CLI not found on PATH (tried: {tried}). "
                f"{self.spec.install_hint}"
            )
        command = [binary, "--mode", self.spec.protocol_mode, *self.spec.extra_args]

        model = (self.model or "").strip()
        if self.spec.model_arg and model and model not in {"auto", "default"}:
            command.extend([self.spec.model_arg, model])

        effort = (self.thinking_effort or "").strip()
        if self.spec.thinking_arg and effort in self.spec.thinking_levels:
            command.extend([self.spec.thinking_arg, effort])

        if self.spec.approval_mode_arg and self.permission_mode:
            flag_value = self.spec.approval_modes.get(self.permission_mode)
            if flag_value:
                command.extend([self.spec.approval_mode_arg, flag_value])

        if self.spec.session_arg and self.agent_session_id:
            command.extend([self.spec.session_arg, self.agent_session_id])
        return command

    def build_env(self) -> Dict[str, str]:
        """Child environment, carrying the agent-tool nesting depth forward.

        A session started *by* a tool call inherits its parent's depth + 1 (the
        daemon puts it in this process's environment); its own tools read the
        value back and refuse to spawn past the cap.
        """
        env = dict(os.environ)
        env[DEPTH_ENV_VAR] = str(current_depth())
        return env

    def _build_session_config(self) -> dict:
        config = {
            "agent": self.spec.catalog_id,
            "model": self.model,
            "thinking_effort": self.thinking_effort,
            "permission_mode": self.permission_mode,
        }
        return {key: value for key, value in config.items() if value is not None}

    def _install_signal_handlers(self) -> None:
        loop = asyncio.get_running_loop()

        def handle_term() -> None:
            logger.info("pi_family: received termination signal")
            self.running = False
            if self._main_task is not None and not self._main_task.done():
                self._main_task.cancel()

        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, handle_term)
            except NotImplementedError:
                pass  # Windows

    # ------------------------------------------------------------------
    # Run loop
    # ------------------------------------------------------------------

    async def run(self) -> int:
        self._main_task = asyncio.current_task()
        self._loop = asyncio.get_running_loop()
        self._install_signal_handlers()
        try:
            self.vicoa_client = AsyncVicoaClient(
                api_key=self.api_key, base_url=self.base_url
            )
            await self._register()

            self._heartbeat = AsyncSessionHeartbeat(
                agent_instance_id=self.session_id,
                vicoa_client=self.vicoa_client,
            )
            self._heartbeat.start()

            await self._bring_up_agent()

            self._consumer_task = asyncio.create_task(self._consume_user_messages())
            self._start_ws_client()
            await self._post_initial_prompt()

            while self.running:
                await asyncio.sleep(1.0)
            return 0
        except (KeyboardInterrupt, asyncio.CancelledError):
            logger.info("pi_family: interrupted, shutting down")
            self.running = False
            return 0
        except PiStartupError as exc:
            # Already a chat-ready message — post it verbatim, the same shape
            # ACP/Codex/Claude use for a failed spawn.
            logger.error("pi_family: startup failed: %s", exc)
            await self._report_startup_failure(str(exc))
            return 1
        except Exception as exc:
            logger.exception("pi_family: fatal error")
            await self._report_startup_failure(
                startup_failure_message(
                    self.spec.display_name,
                    stderr_tail=self._stderr_tail(),
                    reason=str(exc),
                )
            )
            return 1
        finally:
            await self._teardown()

    async def _register(self) -> None:
        assert self.vicoa_client is not None
        if self.is_resuming:
            logger.info("pi_family: resuming instance %s", self.session_id)
            try:
                # AWAITING_INPUT, not ACTIVE: the agent is idle waiting for the
                # user, and ACTIVE renders a spinner for an agent doing nothing.
                await self.vicoa_client.update_agent_instance_status(
                    self.session_id, "AWAITING_INPUT"
                )
            except Exception:
                logger.warning("pi_family: failed to reopen instance", exc_info=True)
            return
        # Bounded, and fatal on timeout: a registration that only succeeds after
        # the app's spawn wait has elapsed leaves an orphan agent running
        # unregistered — burning the user's quota — while the app has already
        # told them the spawn failed.
        try:
            await asyncio.wait_for(
                self.vicoa_client.register_agent_instance(
                    agent_type=self.spec.catalog_id,
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
                "pi_family: registration timed out for session %s — aborting",
                self.session_id,
            )
            raise

    async def _bring_up_agent(self) -> None:
        assert self.vicoa_client is not None
        command = self.build_command()
        logger.info("pi_family: launching %s", " ".join(command))
        ready_gate = ReadyGate()
        self.subprocess = await spawn_pi_agent(
            command=command,
            cwd=self.cwd,
            env=self.build_env(),
            agent_label=self.spec.catalog_id,
        )
        self.session = PiRuntimeSession(
            vicoa_client=self.vicoa_client,
            instance_id=self.session_id,
            cwd=self.cwd,
            transport=self.subprocess.transport,
            spec=self.spec,
            ready_gate=ready_gate,
            agent_type=self.agent_name,
            model=self.model,
            thinking_effort=self.thinking_effort,
            permission_mode=self.permission_mode,
            stderr_tail=self.subprocess.stderr_tail,
        )
        host_tools = None
        if self.spec.supports_host_tools:
            host_tools = HostToolRouter(
                context=AgentToolContext(
                    client=self.vicoa_client,
                    agent_instance_id=self.session_id,
                    project_path=self.cwd,
                ),
                send=self.subprocess.transport.send,
            )
        await self.session.start(host_tools=host_tools)

    async def _post_initial_prompt(self) -> None:
        """POST the spawn prompt as a user message so it shows in the chat.

        Deliberately not delivered straight to the session: vicoa-server
        broadcasts the POSTed row back to our own subscription, which routes it
        through the normal path. Delivering directly would run the prompt twice.
        """
        if not self.initial_prompt or self.vicoa_client is None:
            return
        if self._ws_client is not None:
            # Wait for the subscriber's catch-up handshake so the broadcast
            # lands on an attached subscription. An optimisation, not the
            # correctness guarantee — ``mark_as_read=False`` below covers the
            # timeout path.
            ready = await asyncio.to_thread(self._ws_client.wait_until_ready, 10.0)
            if not ready:
                logger.warning(
                    "pi_family: WS catch-up not ready after 10s; POSTing anyway"
                )
        try:
            # ``mark_as_read=False`` is load-bearing: the default points the
            # server's ``last_read_message_id`` at this row, and the catch-up
            # cursor fallback then excludes the prompt from its own recovery —
            # hanging the session forever when the wait above timed out.
            await self.vicoa_client.send_user_message(
                agent_instance_id=self.session_id,
                content=self.initial_prompt,
                mark_as_read=False,
            )
        except Exception:
            logger.exception("pi_family: failed to POST initial prompt")

    def _stderr_tail(self) -> str:
        return self.subprocess.stderr_tail() if self.subprocess is not None else ""

    async def _report_startup_failure(self, message: str) -> None:
        """Post a user-visible reason for a failed bring-up. Never raises."""
        if self.vicoa_client is None:
            return
        try:
            await self.vicoa_client.send_message(
                content=message,
                agent_type=self.agent_name,
                agent_instance_id=self.session_id,
                requires_user_input=False,
            )
        except Exception:
            logger.warning("pi_family: could not report startup failure", exc_info=True)

    async def _teardown(self) -> None:
        self.running = False
        if self._consumer_task is not None and not self._consumer_task.done():
            self._consumer_task.cancel()
            try:
                await self._consumer_task
            except (asyncio.CancelledError, Exception):
                pass
        # Stop heartbeating before end_session so an in-flight beat can't make
        # a finished session look freshly alive.
        if self._heartbeat is not None:
            try:
                await self._heartbeat.stop()
            except Exception:
                logger.exception("pi_family: heartbeat stop failed")
        if self._ws_client is not None:
            try:
                self._ws_client.stop()
            except Exception:
                logger.exception("pi_family: WS client stop failed")
        if self._ws_thread is not None and self._ws_thread.is_alive():
            self._ws_thread.join(timeout=5.0)
        if self.session is not None:
            try:
                await self.session.aclose()
            except Exception:
                logger.exception("pi_family: session aclose failed")
        if self.subprocess is not None:
            try:
                await self.subprocess.aclose()
            except Exception:
                logger.exception("pi_family: subprocess aclose failed")
        if self.vicoa_client is not None:
            try:
                await self.vicoa_client.end_session(self.session_id)
            except Exception:
                logger.exception("pi_family: end_session failed")
            try:
                await self.vicoa_client.close()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # WebSocket plumbing
    # ------------------------------------------------------------------

    def _start_ws_client(self) -> None:
        ws_url = os.environ.get("VICOA_WS_URL") or derive_ws_url(self.base_url)
        self._ws_client = SessionMessagesWsClient(
            ws_url=ws_url,
            api_key=self.api_key,
            instance_id=self.session_id,
            on_user_message=self._on_ws_user_message,
            cli_version=os.environ.get("VICOA_CLI_VERSION"),
            on_message_update=self._on_ws_message_update,
            on_instance_update=self._on_ws_instance_update,
        )
        self._ws_thread = threading.Thread(
            target=self._ws_thread_target,
            name=f"pi-family-ws-{self.session_id[:8]}",
            daemon=True,
        )
        self._ws_thread.start()
        logger.info("pi_family: WS subscriber connected to %s", ws_url)

    def _ws_thread_target(self) -> None:
        """Absorb a fatal-auth error so the thread exits quietly.

        A 4401 close raises ``AuthenticationError``; without this the thread
        would die with a traceback on stderr.
        """
        client = self._ws_client
        if client is None:
            return
        try:
            client.run()
        except AuthenticationError as exc:
            logger.info("pi_family: WS link closed: %s", exc)

    def _on_ws_instance_update(self, body: Dict[str, Any]) -> None:
        try:
            if not instance_update_requests_stop(body):
                return
            loop = self._loop
            if loop is None or loop.is_closed():
                return
            loop.call_soon_threadsafe(self._stop_from_instance_update)
        except Exception:
            logger.exception("pi_family: instance-update callback raised")

    def _stop_from_instance_update(self) -> None:
        logger.info("pi_family: session closed elsewhere; stopping runner")
        self.running = False
        if self.session is not None:
            self.session.stopping = True
        task = self._main_task
        if task is not None and not task.done():
            task.cancel()

    def _on_ws_message_update(self, body: Dict[str, Any]) -> None:
        """Remember queued messages the user cancelled.

        ``set.add`` is atomic under the GIL, so — unlike the routing callback —
        no loop hop is needed.
        """
        try:
            metadata = body.get("message_metadata") or {}
            status = (metadata.get("queue") or {}).get("status")
            message_id = body.get("id")
            if status == "cancelled" and message_id:
                self._cancelled_message_ids.add(str(message_id))
        except Exception:
            logger.exception("pi_family: message-update callback raised")

    def _on_ws_user_message(self, body: Dict[str, Any]) -> None:
        try:
            sender = (body.get("sender_type") or "").lower()
            content = body.get("content") or ""
            attachments = tuple(extract_attachment_refs(body.get("message_metadata")))
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
            logger.exception("pi_family: WS callback raised")

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    async def _route(
        self,
        content: str,
        attachments: "tuple[AttachmentRef, ...]" = (),
        message_id: Optional[str] = None,
    ) -> None:
        """Dispatch an inbound user message.

        Order matters: AUQ replies are JSON-wrapped control messages, so they
        must be checked before generic control parsing or a new turn.
        """
        session = self.session
        if session is None:
            return
        if auq.is_persist_only_message(content):
            return
        if await session.maybe_route_auq_reply(content):
            return
        parsed = control_command.parse_control_command(content)
        if parsed is not None:
            await self._handle_control(parsed)
            return
        # A permission reply must resolve inline: the turn awaiting it is what
        # would drain the queue, so enqueuing it behind that turn deadlocks.
        if content and session.try_resolve_pending_reply(content):
            await self._mark_message_consumed(message_id)
            return
        self._turn_queue.put_nowait((content, attachments, message_id))

    async def _handle_control(self, parsed: Dict[str, str]) -> None:
        session = self.session
        if session is None:
            return
        setting = parsed.get("setting")
        value = parsed.get("value")
        logger.info("pi_family: control setting=%s value=%s", setting, value)

        if setting == "interrupt":
            # Post the notice BEFORE interrupting: an agent-message POST
            # re-opens the row as ACTIVE, so a notice sent afterwards would
            # undo the AWAITING_INPUT the interrupt is about to write.
            await self._send_feedback(
                f"Interrupted · What should {self.agent_name} do instead?"
            )
            await session.interrupt()
            return
        if setting == "model" and value:
            if await session.set_model(value):
                self.model = value
                await self._send_feedback(f"Model changed to {value}")
            else:
                await self._send_feedback(f"Could not switch to model {value}")
            await self._settle_after_settings_change("model")
            return
        if setting in {"thinking", "effort", "thinking_effort"} and value:
            if await session.set_thinking_level(value):
                self.thinking_effort = value
                await self._send_feedback(f"Thinking effort changed to {value}")
            else:
                await self._send_feedback(
                    f"{self.agent_name} does not support thinking level {value}"
                )
            await self._settle_after_settings_change("thinking_effort")
            return
        if setting == "permission_mode" and value:
            # The approval mode is a launch flag, not an RPC — there is no way
            # to change it on a live process. Say so rather than silently
            # recording a value that has no effect.
            await self._send_feedback(
                f"{self.agent_name} sets its approval mode at launch. Start a "
                f"new session to use “{value}”."
            )
            await self._settle_after_settings_change("permission_mode")
            return
        if setting == "compact":
            await self._send_feedback("Compacting the conversation…")
            await session.compact(value or None)
            await self._settle_after_settings_change("compact")
            return
        if setting == "autocompact" and value is not None:
            enabled = str(value).lower() not in {"off", "false", "0", "no"}
            if await session.set_auto_compaction(enabled):
                await self._send_feedback(
                    f"Auto-compaction {'enabled' if enabled else 'disabled'}"
                )
            await self._settle_after_settings_change("autocompact")
            return
        if setting == "handoff":
            saved = await session.handoff(value or None)
            await self._send_feedback(
                f"Handoff written to `{saved}`" if saved else "Handoff complete"
            )
            await self._settle_after_settings_change("handoff")
            return
        # Unknown settings are other agents' knobs. Ignore silently.

    async def _consume_user_messages(self) -> None:
        """Single consumer: run queued messages one turn at a time.

        Blocks for the next message, drains whatever else is already waiting,
        and coalesces the batch into ONE turn — so a burst the user sent during
        a turn runs together rather than one turn each. When a turn is already
        running, the batch is *steered* into it instead, which is the whole
        point of having ``steer`` on this protocol.
        """
        session = self.session
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
            kept = []
            for item in batch:
                message_id = item[2]
                if message_id and message_id in self._cancelled_message_ids:
                    self._cancelled_message_ids.discard(message_id)
                    logger.info("pi_family: dropping cancelled message %s", message_id)
                    continue
                kept.append(item)
            if not kept:
                continue
            for _content, _attachments, message_id in kept:
                await self._mark_message_consumed(message_id)
            text, attachments = self._coalesce(kept)
            session = self.session
            if session is None:
                continue
            try:
                await session.deliver_user_message(text, attachments)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("pi_family: turn processing failed")

    @staticmethod
    def _coalesce(
        batch: "List[tuple[str, tuple[AttachmentRef, ...], Optional[str]]]",
    ) -> "tuple[str, tuple[AttachmentRef, ...]]":
        text = "\n\n".join(content for content, _, _ in batch if content)
        attachments: "tuple[AttachmentRef, ...]" = tuple(
            attachment for _, refs, _ in batch for attachment in refs
        )
        return text, attachments

    async def _mark_message_consumed(self, message_id: Optional[str]) -> None:
        """Clear a message's queued badge. Best-effort; never aborts a turn."""
        if not message_id or self.vicoa_client is None:
            return
        try:
            await self.vicoa_client.mark_message_consumed(message_id)
        except Exception:
            logger.debug("pi_family: mark_message_consumed failed", exc_info=True)

    async def _send_feedback(self, content: str) -> None:
        if self.vicoa_client is None:
            return
        try:
            await self.vicoa_client.send_message(
                content=content,
                agent_type=self.agent_name,
                agent_instance_id=self.session_id,
                requires_user_input=False,
            )
        except Exception:
            logger.warning("pi_family: send feedback failed", exc_info=True)

    async def _settle_after_settings_change(self, setting: str) -> None:
        """Settle on AWAITING_INPUT after a gear-pill change.

        The change fires while idle, but the feedback POST itself transiently
        bumps the row to ACTIVE — this is the explicit settle so the pill stops
        showing a stale active badge.
        """
        if self.vicoa_client is None:
            return
        try:
            await self.vicoa_client.update_agent_instance_status(
                self.session_id, "AWAITING_INPUT"
            )
        except Exception as exc:
            logger.warning(
                "pi_family: failed to settle status after %s change: %s", setting, exc
            )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Headless native Pi / Oh My Pi integration for Vicoa."
    )
    parser.add_argument(
        "--agent",
        required=True,
        choices=sorted(PI_FAMILY_AGENTS),
        help="Which Pi-family agent to run",
    )
    parser.add_argument("--api-key", default=os.environ.get("VICOA_API_KEY"))
    parser.add_argument(
        "--base-url",
        default=os.environ.get("VICOA_BASE_URL")
        or os.environ.get("VICOA_API_URL")
        or "https://agents.vicoa.ai",
    )
    parser.add_argument("--project-path", default=None)
    parser.add_argument("--name", default=None, help="Agent display name override")
    parser.add_argument(
        "--session-id", default=os.environ.get("VICOA_AGENT_INSTANCE_ID")
    )
    parser.add_argument(
        "--resume",
        default=None,
        help=(
            "Reattach to an existing Vicoa agent instance by id (skips "
            "registration, which would 409). Does NOT restore the "
            "conversation — pass --pi-session-id for that."
        ),
    )
    parser.add_argument(
        "--pi-session-id",
        default=None,
        help=(
            "The agent's own prior session id, resolved with --session so the "
            "conversation continues. The agent only ever resolves this id, so "
            "it must be one it issued."
        ),
    )
    parser.add_argument("--model", default=None, help="Model id from the catalog")
    parser.add_argument(
        "--thinking-effort", default=None, help="Thinking level (off…max)"
    )
    parser.add_argument(
        "--permission-mode",
        default=None,
        help="Vicoa permission mode; translated to the agent's approval flag",
    )
    parser.add_argument("--agent-command", default=None, help="Explicit binary path")
    parser.add_argument("--prompt", default=None, help="Initial prompt")
    parser.add_argument("--debug", action="store_true")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    spec = PI_FAMILY_AGENTS[args.agent]

    api_key = args.api_key or os.environ.get("VICOA_API_KEY")
    if not api_key:
        print(
            "Vicoa API key required: provide --api-key or set VICOA_API_KEY",
            file=sys.stderr,
        )
        return 1

    session_id = args.resume or args.session_id or str(uuid.uuid4())
    setup_logging(session_id, debug=args.debug)

    runner = PiFamilyRunner(
        spec=spec,
        vicoa_api_key=api_key,
        vicoa_base_url=args.base_url,
        session_id=session_id,
        cwd=args.project_path or os.getcwd(),
        agent_name=args.name or spec.display_name,
        initial_prompt=args.prompt,
        agent_session_id=args.pi_session_id,
        model=args.model,
        thinking_effort=args.thinking_effort,
        permission_mode=args.permission_mode,
        agent_command=args.agent_command,
        is_resuming=bool(args.resume),
    )
    try:
        return asyncio.run(runner.run())
    except KeyboardInterrupt:
        return 0


__all__ = ["PiFamilyRunner", "build_arg_parser", "main", "setup_logging"]
