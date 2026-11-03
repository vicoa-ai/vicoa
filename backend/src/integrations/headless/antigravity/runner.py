"""Process-level runner for an Antigravity (``agy``) session.

Owns everything around :class:`AntigravitySession`: registration with
vicoa-server, the WebSocket subscriber, the serialized turn queue, control
commands, signal handling, and teardown. Structurally the same as
``pi_family.runner.PiFamilyRunner`` — deliberately, so the native wrappers
stay readable side by side — with what this agent cannot do left out rather
than stubbed: no steer (one prompt per turn, and the CLI must not be written
to mid-turn) and no permission or question dialogs (headless ``agy`` has
none). Model and permission-mode switches are launch flags underneath, applied
by restarting the binary on the same conversation before the next turn.
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

from integrations.headless import auq, control_command
from integrations.headless.antigravity import spec
from integrations.headless.antigravity.session import (
    AntigravitySession,
    AntigravityStartupError,
    startup_failure_message,
)
from integrations.headless.session_lifecycle import instance_update_requests_stop
from integrations.utils.heartbeat import AsyncSessionHeartbeat
from integrations.utils.registration import (
    REGISTRATION_ATTEMPT_TIMEOUT_SECONDS,
    register_with_retry,
)
from vicoa.attachments import AttachmentRef, extract_attachment_refs
from vicoa.sdk.async_client import AsyncVicoaClient
from vicoa.sdk.exceptions import AuthenticationError
from vicoa.session_markers import clear_session_registered, mark_session_registered
from vicoa.session_ws_client import SessionMessagesWsClient
from vicoa.utils import derive_ws_url, get_project_path


logger = logging.getLogger(__name__)


def setup_logging(
    session_id: str, *, console_output: bool = True, debug: bool = False
) -> None:
    """Per-session log file under ``~/.vicoa/antigravity/<id>.log``."""
    root = logging.getLogger()
    if any(
        getattr(h, "_antigravity_session", None) == session_id for h in root.handlers
    ):
        return

    log_dir = Path.home() / ".vicoa" / "antigravity"
    log_dir.mkdir(exist_ok=True, parents=True)
    log_file = log_dir / f"{session_id}.log"

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    file_handler._antigravity_session = session_id  # type: ignore[attr-defined]
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
    logger.info("antigravity: logging to %s", log_file)


class AntigravityRunner:
    """WS stream loop + lifecycle around one :class:`AntigravitySession`."""

    def __init__(
        self,
        *,
        vicoa_api_key: str,
        vicoa_base_url: str,
        session_id: str,
        cwd: str,
        agent_name: str,
        initial_prompt: Optional[str] = None,
        conversation_id: Optional[str] = None,
        model: Optional[str] = None,
        permission_mode: Optional[str] = None,
        system_prompt: Optional[str] = None,
        agent_command: Optional[str] = None,
        is_resuming: bool = False,
    ) -> None:
        self.api_key = vicoa_api_key
        self.base_url = vicoa_base_url
        self.session_id = session_id
        self.cwd = cwd
        self.project_path = get_project_path(self.cwd)
        self.agent_name = agent_name
        self.initial_prompt = initial_prompt
        self.conversation_id = conversation_id
        self.model = model
        self.permission_mode = permission_mode
        self.system_prompt = system_prompt
        self.agent_command = agent_command
        self.is_resuming = is_resuming

        self.running = True
        self.vicoa_client: Optional[AsyncVicoaClient] = None
        self.session: Optional[AntigravitySession] = None
        self._main_task: Optional["asyncio.Task[Any]"] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._ws_client: Optional[SessionMessagesWsClient] = None
        self._ws_thread: Optional[threading.Thread] = None
        self._heartbeat: Optional[AsyncSessionHeartbeat] = None
        # Set once the instance row is known to exist (registered, or reopened
        # on resume). Gates every write that would otherwise create the row.
        self._registered = False
        #: Serialized turn pipeline: one consumer runs turns one at a time and
        #: coalesces a burst sent during a turn into a single follow-up.
        self._turn_queue: "asyncio.Queue[tuple[str, tuple[AttachmentRef, ...], Optional[str]]]" = asyncio.Queue()
        self._consumer_task: Optional["asyncio.Task[None]"] = None
        #: Queued messages the user cancelled before we picked them up.
        self._cancelled_message_ids: set[str] = set()

    # ------------------------------------------------------------------
    # Launch
    # ------------------------------------------------------------------

    def resolve_binary(self) -> str:
        binary = self.agent_command or spec.resolve_agy_binary()
        if binary is None:
            raise FileNotFoundError(
                f"{spec.DISPLAY_NAME} CLI ('agy') not found on PATH. {spec.INSTALL_HINT}"
            )
        return binary

    def _build_session_config(self) -> dict:
        config = {
            "agent": spec.CATALOG_ID,
            "model": self.model,
            "permission_mode": self.permission_mode,
        }
        return {key: value for key, value in config.items() if value is not None}

    def _install_signal_handlers(self) -> None:
        loop = asyncio.get_running_loop()

        def handle_term() -> None:
            logger.info("antigravity: received termination signal")
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
            # The row exists (registered, or reopened on resume). Tell the
            # daemon, which holds the spawn RPC until this lands.
            self._registered = True
            mark_session_registered(self.session_id)

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
            logger.info("antigravity: interrupted, shutting down")
            self.running = False
            return 0
        except AntigravityStartupError as exc:
            logger.error("antigravity: startup failed: %s", exc)
            await self._report_startup_failure(str(exc))
            return 1
        except Exception as exc:
            logger.exception("antigravity: fatal error")
            await self._report_startup_failure(
                startup_failure_message(
                    stderr_tail=self._stderr_tail(), reason=str(exc)
                )
            )
            return 1
        finally:
            await self._teardown()

    async def _register(self) -> None:
        assert self.vicoa_client is not None
        if self.is_resuming:
            logger.info("antigravity: resuming instance %s", self.session_id)
            try:
                await self.vicoa_client.update_agent_instance_status(
                    self.session_id, "AWAITING_INPUT"
                )
            except Exception:
                logger.warning("antigravity: failed to reopen instance", exc_info=True)
            return
        # No ``name``: ``agent_name`` is the agent's display name, not a session
        # title (see codex_native's registration).
        client = self.vicoa_client
        await register_with_retry(
            lambda: client.register_agent_instance(
                agent_type=spec.CATALOG_ID,
                agent_instance_id=self.session_id,
                project=self.project_path,
                home_dir=str(Path.home()),
                session_config=self._build_session_config(),
                timeout=int(REGISTRATION_ATTEMPT_TIMEOUT_SECONDS),
            ),
            log=logger,
            label="antigravity",
        )

    async def _bring_up_agent(self) -> None:
        assert self.vicoa_client is not None
        binary = self.resolve_binary()
        session = AntigravitySession(
            vicoa_client=self.vicoa_client,
            instance_id=self.session_id,
            cwd=self.cwd,
            binary=binary,
            agent_type=self.agent_name,
            model=self.model,
            permission_mode=self.permission_mode,
            system_prompt=self.system_prompt,
            conversation_id=self.conversation_id,
        )
        self.session = session
        await session.start()

    async def _post_initial_prompt(self) -> None:
        """POST the spawn prompt as a user message so it shows in the chat.

        Not delivered straight to the session: vicoa-server broadcasts the
        POSTed row back to our own subscription, which routes it through the
        normal path. Delivering directly would run the prompt twice.
        """
        if not self.initial_prompt or self.vicoa_client is None:
            return
        if self._ws_client is not None:
            ready = await asyncio.to_thread(self._ws_client.wait_until_ready, 10.0)
            if not ready:
                logger.warning(
                    "antigravity: WS catch-up not ready after 10s; POSTing anyway"
                )
        try:
            # ``mark_as_read=False`` is load-bearing — see pi_family.runner.
            await self.vicoa_client.send_user_message(
                agent_instance_id=self.session_id,
                content=self.initial_prompt,
                mark_as_read=False,
            )
        except Exception:
            logger.exception("antigravity: failed to POST initial prompt")

    def _stderr_tail(self) -> str:
        return self.session.stderr_tail() if self.session is not None else ""

    async def _report_startup_failure(self, message: str) -> None:
        """Post a user-visible reason for a failed bring-up. Never raises.

        Only once the row exists — posting earlier would itself create the
        orphan instance this runner must never mint.
        """
        if not self._registered:
            print(f"Fatal error before registration: {message}", file=sys.stderr)
            return
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
            logger.warning(
                "antigravity: could not report startup failure", exc_info=True
            )

    async def _teardown(self) -> None:
        self.running = False
        if self._consumer_task is not None and not self._consumer_task.done():
            self._consumer_task.cancel()
            try:
                await self._consumer_task
            except (asyncio.CancelledError, Exception):
                pass
        if self._heartbeat is not None:
            try:
                await self._heartbeat.stop()
            except Exception:
                logger.exception("antigravity: heartbeat stop failed")
        if self._ws_client is not None:
            try:
                self._ws_client.stop()
            except Exception:
                logger.exception("antigravity: WS client stop failed")
        if self._ws_thread is not None and self._ws_thread.is_alive():
            self._ws_thread.join(timeout=5.0)
        if self.session is not None:
            try:
                await self.session.aclose()
            except Exception:
                logger.exception("antigravity: session aclose failed")
        if self.vicoa_client is not None:
            if self._registered:
                try:
                    await self.vicoa_client.end_session(self.session_id)
                except Exception:
                    logger.exception("antigravity: end_session failed")
            try:
                await self.vicoa_client.close()
            except Exception:
                pass
        clear_session_registered(self.session_id)

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
            name=f"antigravity-ws-{self.session_id[:8]}",
            daemon=True,
        )
        self._ws_thread.start()
        logger.info("antigravity: WS subscriber connected to %s", ws_url)

    def _ws_thread_target(self) -> None:
        client = self._ws_client
        if client is None:
            return
        try:
            client.run()
        except AuthenticationError as exc:
            logger.info("antigravity: WS link closed: %s", exc)

    def _on_ws_instance_update(self, body: Dict[str, Any]) -> None:
        try:
            if not instance_update_requests_stop(body):
                return
            loop = self._loop
            if loop is None or loop.is_closed():
                return
            loop.call_soon_threadsafe(self._stop_from_instance_update)
        except Exception:
            logger.exception("antigravity: instance-update callback raised")

    def _stop_from_instance_update(self) -> None:
        logger.info("antigravity: session closed elsewhere; stopping runner")
        self.running = False
        if self.session is not None:
            self.session.stopping = True
        task = self._main_task
        if task is not None and not task.done():
            task.cancel()

    def _on_ws_message_update(self, body: Dict[str, Any]) -> None:
        """Remember queued messages the user cancelled.

        A ``steer`` request is deliberately ignored: this agent has no way to
        deliver text into a running turn, so the message simply stays queued
        and runs next — the catalog leaves ``supports_steer`` unset so the
        clients don't offer the button.
        """
        try:
            metadata = body.get("message_metadata") or {}
            status = (metadata.get("queue") or {}).get("status")
            message_id = body.get("id")
            if status == "cancelled" and message_id:
                self._cancelled_message_ids.add(str(message_id))
        except Exception:
            logger.exception("antigravity: message-update callback raised")

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
            logger.exception("antigravity: WS callback raised")

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    async def _route(
        self,
        content: str,
        attachments: "tuple[AttachmentRef, ...]" = (),
        message_id: Optional[str] = None,
    ) -> None:
        if self.session is None:
            return
        if auq.is_persist_only_message(content):
            return
        parsed = control_command.parse_control_command(content)
        if parsed is not None:
            await self._handle_control(parsed)
            return
        self._turn_queue.put_nowait((content, attachments, message_id))

    async def _handle_control(self, parsed: Dict[str, str]) -> None:
        session = self.session
        if session is None:
            return
        setting = parsed.get("setting")
        value = parsed.get("value")
        logger.info("antigravity: control setting=%s value=%s", setting, value)

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
            # A launch flag, applied through a restart on the same
            # conversation before the next turn (session.set_model).
            if await session.set_model(value):
                self.model = session.model
                await self._send_feedback(
                    f"Model changed to {value} — applies from the next message"
                )
            else:
                await self._send_feedback(f"Could not switch to model {value}")
            await self._settle_after_settings_change("model")
            return
        if setting == "permission_mode" and value:
            if await session.set_permission_mode(value):
                self.permission_mode = value
                await self._send_feedback(
                    f"Permission mode changed to {value} — applies from the next message"
                )
            else:
                await self._send_feedback(
                    f"{self.agent_name} does not support permission mode {value}"
                )
            await self._settle_after_settings_change("permission_mode")
            return
        # Unknown settings are other agents' knobs. Ignore silently.

    async def _consume_user_messages(self) -> None:
        """Single consumer: run queued messages one turn at a time.

        Blocks for the next message, drains whatever else is already waiting,
        and coalesces the batch into ONE turn — so a burst the user sent during
        a turn runs together rather than one turn each.
        """
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
                    logger.info(
                        "antigravity: dropping cancelled message %s", message_id
                    )
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
                logger.exception("antigravity: turn processing failed")

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
            logger.debug("antigravity: mark_message_consumed failed", exc_info=True)

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
            logger.warning("antigravity: send feedback failed", exc_info=True)

    async def _settle_after_settings_change(self, setting: str) -> None:
        if self.vicoa_client is None:
            return
        try:
            await self.vicoa_client.update_agent_instance_status(
                self.session_id, "AWAITING_INPUT"
            )
        except Exception as exc:
            logger.warning(
                "antigravity: failed to settle status after %s change: %s", setting, exc
            )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Headless Antigravity (agy) integration for Vicoa."
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
            "conversation — pass --conversation-id for that."
        ),
    )
    parser.add_argument(
        "--conversation-id",
        default=None,
        help="agy conversation id to resume (--conversation), from a prior run's init event",
    )
    parser.add_argument("--model", default=None, help="Model id (see `agy models`)")
    parser.add_argument(
        "--permission-mode",
        default=None,
        help="Vicoa permission mode; translated to --mode / --dangerously-skip-permissions",
    )
    parser.add_argument(
        "--system-prompt",
        dest="system_prompt",
        default=None,
        help="Custom instructions, prepended to every prompt",
    )
    parser.add_argument(
        "--agent-command", default=None, help="Explicit agy binary path"
    )
    parser.add_argument("--prompt", default=None, help="Initial prompt")
    parser.add_argument("--debug", action="store_true")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()

    api_key = args.api_key or os.environ.get("VICOA_API_KEY")
    if not api_key:
        print(
            "Vicoa API key required: provide --api-key or set VICOA_API_KEY",
            file=sys.stderr,
        )
        return 1

    session_id = args.resume or args.session_id or str(uuid.uuid4())
    setup_logging(session_id, debug=args.debug)

    runner = AntigravityRunner(
        vicoa_api_key=api_key,
        vicoa_base_url=args.base_url,
        session_id=session_id,
        cwd=args.project_path or os.getcwd(),
        agent_name=args.name or spec.DISPLAY_NAME,
        initial_prompt=args.prompt,
        conversation_id=args.conversation_id,
        model=args.model,
        permission_mode=args.permission_mode,
        system_prompt=args.system_prompt,
        agent_command=args.agent_command,
        is_resuming=bool(args.resume),
    )
    try:
        return asyncio.run(runner.run())
    except KeyboardInterrupt:
        return 0


__all__ = ["AntigravityRunner", "build_arg_parser", "main", "setup_logging"]
