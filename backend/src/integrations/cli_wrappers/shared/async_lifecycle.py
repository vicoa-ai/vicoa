"""Async-resource lifecycle helpers shared across CLI wrappers.

The wrappers run their asyncio loop (and the aiohttp session bound to it) on a
daemon thread, while shutdown executes on the main thread. Closing the session
from a *different* loop than the one its connector was created on raises
``RuntimeError: Future ... attached to a different loop`` from inside aiohttp.

``close_async_on_loop`` schedules the close on the owning loop via
``run_coroutine_threadsafe``, which is the only correct way to await a
loop-bound resource from another thread.
"""

import asyncio
from typing import Any, Callable, Coroutine, Optional


def close_async_on_loop(
    close_coro_factory: Callable[[], Coroutine[Any, Any, Any]],
    loop: Optional[asyncio.AbstractEventLoop],
    *,
    timeout: float = 5.0,
    log: Optional[Callable[[str], None]] = None,
    label: str = "async resource",
) -> bool:
    """Close an asyncio-bound resource on its owning loop.

    Args:
        close_coro_factory: Zero-arg callable returning a fresh coroutine each
            invocation (e.g. ``client.close``). We never invoke the factory
            when the loop isn't running, so no orphan coroutine triggers the
            "coroutine was never awaited" warning at GC.
        loop: The loop the resource is bound to (created the aiohttp session).
            ``None`` or a non-running loop is treated as "nothing to do".
        timeout: Seconds to wait for the close to finish before giving up.
        log: Optional logger; errors are logged here, the no-loop case is
            silent.
        label: Human label used in error messages.

    Returns:
        True if the close ran to completion; False otherwise.
    """
    if loop is None or not loop.is_running():
        return False
    try:
        fut = asyncio.run_coroutine_threadsafe(close_coro_factory(), loop)
        fut.result(timeout=timeout)
        return True
    except Exception as e:
        if log:
            log(f"[ERROR] Failed to close {label}: {e}")
        return False
