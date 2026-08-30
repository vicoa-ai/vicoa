"""Shared fixtures for the headless Claude runner tests.

Constructs a ``HeadlessClaudeRunner`` without running its ``__init__``. The real
constructor reads/writes ``~/.vicoa/claude_headless/{session_id}.log`` and is
configured for production use — bypassing it keeps these tests fast and
side-effect-free.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from typing import Any, Dict, Optional

import pytest

from integrations.headless import auq, permission as permission_module
from integrations.headless.claude_code import HeadlessClaudeRunner
from integrations.headless.subagent import SubAgentTracker
from integrations.headless.usage import UsageState

# Re-exported here so tests can ``from conftest import FakeAsyncVicoaClient``
# (pytest adds this directory to sys.path automatically).
from _fakes import FakeAsyncVicoaClient  # noqa: F401  (re-export)


def _build_runner(
    *,
    vicoa_client: Optional[Any] = None,
    session_id: str = "test-session",
    permission_state: Optional[Dict[str, Any]] = None,
) -> HeadlessClaudeRunner:
    """Create a half-initialised runner that's safe to use in unit tests.

    Skips ``__init__`` so the constructor's logging side effects and Claude SDK
    option building don't fire. Only the attributes the tested helpers actually
    read are set.
    """
    runner = HeadlessClaudeRunner.__new__(HeadlessClaudeRunner)
    runner.vicoa_client = vicoa_client
    runner.session_id = session_id
    runner.agent_name = "Claude Code"
    runner.logger = logging.getLogger(f"test.{session_id}")
    runner._permission_state = permission_state if permission_state is not None else {}
    # Cache wraps the SAME dict so writes via either path stay consistent —
    # tests inspect ``runner._permission_state`` directly.
    runner._permission_cache = permission_module.PermissionCache(
        runner._permission_state
    )
    runner._auq_registry = auq.AskUserQuestionRegistry()
    runner._permission_registry = permission_module.PermissionReplyRegistry()
    # The SSE listener / queue-fallback path puts non-routed messages here.
    # Tests assert it stays empty after permission replies (regression for
    # the §2c bug from session 269d5bf3-…).
    runner._user_message_queue = asyncio.Queue()
    # Cross-channel dedupe state (see ``HeadlessClaudeRunner.__init__``) —
    # ``_route`` / ``_enqueue_already_queued`` read/write these directly.
    runner._seen_user_message_ids = set()
    runner._seen_user_message_order = deque(maxlen=1024)
    runner._cancelled_message_ids = set()
    # Out-of-band control-command queue: SSE listener enqueues so it doesn't
    # block on slow reconnects; ``_run_control_worker`` drains.
    runner._control_command_queue = asyncio.Queue()
    runner._control_worker_task = None
    # Reconcile backstop (see _run_reconcile_backstop): the idle flag it reads.
    runner._awaiting_input = False
    runner._ws_client = None
    # asyncio.Lock can be constructed outside a running loop in Python 3.10+.
    runner._send_lock = asyncio.Lock()
    runner.interrupt_requested = False
    runner.running = True
    runner._stopping = False
    runner.enable_thinking = True
    # Match __init__'s defaults; the permission_mode control handler reads both
    # (roll back on a failed change; re-assert the model on the 'auto' recovery).
    runner.permission_mode = None
    runner.model = None
    runner.claude_client = None
    # Live context-window + rate-limit usage state (see ``__init__``). A full
    # ``run_conversation_turn`` pass stamps context via ``_usage`` and schedules
    # the throttled plan-usage fetch, which reads ``_last_limits_fetch``.
    runner._usage = UsageState()
    runner._usage_last_core = None
    # Stamp "just fetched" so ``_schedule_limits_fetch`` throttles itself out —
    # keeps the fixture side-effect-free (no live OAuth plan-usage HTTP call).
    runner._last_limits_fetch = time.monotonic()
    runner._limits_fetch_task = None
    # Labels Task/Agent launches for sub-agent child tagging (Task C1/C3).
    runner._subagent_tracker = SubAgentTracker()
    # Sub-agents announced but not yet settled; defers the awaiting-input
    # settle while background (``run_in_background: true``) sub-agents run.
    runner._pending_background_tasks = set()
    # Session-lifetime stream reader + event-derived turn state (see
    # ``HeadlessClaudeRunner.__init__``). The reader task is started lazily
    # by ``run_conversation_turn`` via ``_ensure_stream_reader``.
    runner._open_turns = deque()
    runner._foreground_turn_done = None
    runner._foreground_settle_deferred = False
    runner._stream_reader_task = None
    runner._reader_client = None
    runner._stream_recovery_task = None
    runner._status_watchdog_task = None
    runner._last_stream_activity = 0.0
    # Back-ref so fakes that schedule delayed control-command deliveries can
    # find the runner. Used by FakeAsyncVicoaClient when ``auq_reply`` is set.
    if vicoa_client is not None and hasattr(vicoa_client, "runner"):
        vicoa_client.runner = runner
    return runner


@pytest.fixture
def make_runner():
    """Factory fixture for partially-initialised runners.

    Usage::

        def test_something(make_runner):
            runner = make_runner()                    # no vicoa client
            runner = make_runner(vicoa_client=fake)   # layer 2 wiring

    Teardown cancels any session-lifetime stream reader a test left parked
    on a fake stream, so tests don't leak "Task was destroyed but it is
    pending" warnings. Tests that assert on post-turn reader behaviour
    should still stop it explicitly via ``await runner._stop_stream_reader()``.
    """
    created = []

    def _factory(**kwargs):
        runner = _build_runner(**kwargs)
        created.append(runner)
        return runner

    yield _factory

    for runner in created:
        task = getattr(runner, "_stream_reader_task", None)
        if task is not None and not task.done():
            try:
                task.cancel()
            except RuntimeError:
                # The test's event loop is already closed.
                pass
