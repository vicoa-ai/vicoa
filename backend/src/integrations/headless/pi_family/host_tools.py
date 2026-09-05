"""The omp host-tool channel: four frames over the agent's own RPC.

This is the thin adapter that lets ``integrations.agent_tools`` reach the model.
No MCP is involved anywhere — ``set_host_tools`` is a command on omp's own
stdio RPC and ``parameters`` is plain JSON Schema, so what sits behind it is
entirely ours::

    us  -> omp   set_host_tools([{name, label, description, parameters,
                                  loadMode}, …])     request/response
    omp -> us    host_tool_call   {id, toolCallId, toolName, arguments}   event
    us  -> omp   host_tool_result {id, result, isError?}   fire-and-forget
    us  -> omp   host_tool_update {id, partialResult}      fire-and-forget
    omp -> us    host_tool_cancel {id, targetId}           event

Four things measured from ``tests/fixtures/omp/03-hosttool.jsonl`` shape this
module:

* **Two distinct ids.** ``id`` is the correlation id that must be echoed in
  ``host_tool_result``; ``toolCallId`` is the model's ``toolu_…`` id and is
  what the ``tool_execution_*`` events key on. Conflating them strands the call.
* **Host tools render as ordinary tools for free.** The same call also emits
  the normal ``tool_execution_start`` / ``_update`` / ``_end`` triple, and a
  ``host_tool_update.partialResult`` comes straight back as
  ``tool_execution_update.partialResult``. So there is no rendering path here
  at all, and streaming progress works with no extra work.
* **Calls can overlap.** Each gets its own ``asyncio.Task``, which is why the
  handlers use the *async* client — a blocking sync HTTP call would stall the
  event stream mid-turn.
* **Cancellation must suppress the result, not merely stop the work.** A late
  result for a cancelled call corrupts omp's state, so the registry is checked
  again immediately before every send.

Pi does not implement ``set_host_tools`` (it answers ``Unknown command``), so
``spec.supports_host_tools`` gates the whole thing.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable, Dict, Optional

from integrations.agent_tools import AgentToolContext, dispatch
from integrations.agent_tools.registry import (
    AgentTool,
    ToolResult,
    build_registry,
    to_host_tool_definitions,
)
from integrations.headless.pi_family.rpc_types import as_dict, as_str
from integrations.headless.pi_family.transport import PiRpcError


logger = logging.getLogger(__name__)


#: Wall-clock cap on one host-tool call. Every handler is a bounded REST call,
#: so anything past this is a hung connection rather than slow work — and omp
#: waits forever, so without a cap one stuck call parks the turn indefinitely.
HOST_TOOL_TIMEOUT_SECONDS = 120.0


class HostToolRouter:
    """Runs ``host_tool_call`` frames against the agent-tool registry.

    Owns one ``asyncio.Task`` per in-flight call plus a cancelled-id set, which
    together are what make a ``host_tool_cancel`` actually suppress the result.
    """

    def __init__(
        self,
        *,
        context: AgentToolContext,
        send: Callable[[str, Dict[str, Any]], None],
        registry: Optional[Dict[str, AgentTool]] = None,
    ) -> None:
        self._context = context
        self._send = send
        self._registry = registry if registry is not None else build_registry()
        self._tasks: Dict[str, "asyncio.Task[None]"] = {}
        self._cancelled: set[str] = set()

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    @property
    def definitions(self) -> list[Dict[str, Any]]:
        return to_host_tool_definitions(self._registry)

    async def register(
        self, request: Callable[[str, Dict[str, Any]], Awaitable[Dict[str, Any]]]
    ) -> list[str]:
        """Send ``set_host_tools`` and return the accepted tool names.

        Best-effort by design: a build without host-tool support (or with a
        stricter schema check) must not take the session down — it just means
        the agent can't drive Vicoa this run.
        """
        try:
            data = await request("set_host_tools", {"tools": self.definitions})
        except PiRpcError as exc:
            if exc.is_unknown_command:
                logger.info("pi_family: host tools unsupported by this build; skipping")
            else:
                logger.warning("pi_family: set_host_tools rejected: %s", exc)
            return []
        except Exception:
            logger.warning("pi_family: set_host_tools failed", exc_info=True)
            return []
        names = data.get("toolNames")
        accepted = [str(name) for name in names] if isinstance(names, list) else []
        logger.info("pi_family: registered %d host tools", len(accepted))
        return accepted

    # ------------------------------------------------------------------
    # Call lifecycle
    # ------------------------------------------------------------------

    def handle_call(self, frame: Dict[str, Any]) -> None:
        """Start a ``host_tool_call``. Returns immediately; the task replies."""
        call_id = as_str(frame.get("id"))
        tool_name = as_str(frame.get("toolName"))
        if not call_id or not tool_name:
            logger.warning("pi_family: malformed host_tool_call: %r", frame)
            return
        arguments = as_dict(frame.get("arguments"))
        logger.info(
            "pi_family: host tool %s (id=%s, toolCallId=%s)",
            tool_name,
            call_id,
            as_str(frame.get("toolCallId")),
        )
        self._cancelled.discard(call_id)
        task = asyncio.create_task(self._run(call_id, tool_name, arguments))
        self._tasks[call_id] = task
        task.add_done_callback(lambda _t, key=call_id: self._tasks.pop(key, None))

    def handle_cancel(self, frame: Dict[str, Any]) -> None:
        """Abort the call named by ``targetId`` and suppress its result."""
        target = as_str(frame.get("targetId")) or as_str(frame.get("id"))
        if not target:
            return
        self._cancelled.add(target)
        task = self._tasks.get(target)
        if task is not None and not task.done():
            task.cancel()
        logger.info("pi_family: host tool call %s cancelled", target)

    async def aclose(self) -> None:
        """Cancel every in-flight call (session shutdown)."""
        for call_id, task in list(self._tasks.items()):
            self._cancelled.add(call_id)
            if not task.done():
                task.cancel()
        for task in list(self._tasks.values()):
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        self._tasks.clear()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _run(
        self, call_id: str, tool_name: str, arguments: Dict[str, Any]
    ) -> None:
        try:
            result = await asyncio.wait_for(
                dispatch(self._registry, self._context, tool_name, arguments),
                timeout=HOST_TOOL_TIMEOUT_SECONDS,
            )
        except asyncio.CancelledError:
            # Cancelled by ``handle_cancel`` or shutdown: send nothing. omp has
            # already discarded the call, and a late result would corrupt it.
            raise
        except asyncio.TimeoutError:
            result = ToolResult(
                text=(
                    f"`{tool_name}` timed out after {HOST_TOOL_TIMEOUT_SECONDS:.0f}s."
                ),
                is_error=True,
            )
        except BaseException as exc:  # noqa: BLE001 - the reply is mandatory
            # Backstop for anything `dispatch` cannot itself convert. The
            # invariant of this channel is that every `host_tool_call` gets
            # exactly one reply; a call that returns nothing blocks the agent
            # indefinitely, so no failure mode may skip the send.
            logger.exception("pi_family: host tool %s crashed", tool_name)
            result = ToolResult(text=f"`{tool_name}` failed: {exc}", is_error=True)
        self._send_result(call_id, result)

    def send_update(self, call_id: str, text: str) -> None:
        """Stream a partial result. Comes back as ``tool_execution_update``."""
        if call_id in self._cancelled:
            return
        self._send(
            "host_tool_update",
            {
                "id": call_id,
                "partialResult": {"content": [{"type": "text", "text": text}]},
            },
        )

    def _send_result(self, call_id: str, result: ToolResult) -> None:
        # Re-check immediately before the send, not just at the start of the
        # call: the cancel may have landed while the handler was awaiting.
        if call_id in self._cancelled:
            self._cancelled.discard(call_id)
            logger.info("pi_family: suppressing result for cancelled call %s", call_id)
            return
        payload: Dict[str, Any] = {"id": call_id, "result": result.to_payload()}
        if result.is_error:
            payload["isError"] = True
        self._send("host_tool_result", payload)


__all__ = ["HOST_TOOL_TIMEOUT_SECONDS", "HostToolRouter"]
