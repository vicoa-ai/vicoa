"""Reconnect-options regression tests.

When mid-session settings change (model / effort / thinking) trigger
``_reconnect_claude_client``, the rebuilt ``ClaudeAgentOptions`` must use
``resume=session_id`` rather than ``session_id=session_id``. The SDK refuses
to create a *new* session whose ID is already live in the same process —
observed in production headless logs::

    Error: Session ID 23e7bd29-…-7967caf1c32e is already in use.

so reconnect crashes and the user-facing "Failed to change model" toast
fires. The right contract is "load the existing session," which is what
``resume`` means in the SDK.
"""

from __future__ import annotations

import uuid


_SESSION_UUID = "23e7bd29-55bb-4262-ac49-7967caf1c32e"


def _prime(runner) -> None:
    """Set the minimum attributes ``_build_claude_options`` reads.

    The conftest fixture skips ``__init__``, so we attach only what the
    builder actually touches — no SDK / vicoa I/O fires from this.
    """
    runner.session_id = _SESSION_UUID
    runner.enable_thinking = False
    runner.thinking_effort = "low"
    runner.model = "claude-sonnet-4-6"
    runner.permission_mode = "acceptEdits"
    runner.allowed_tools = None
    runner.disallowed_tools = None
    runner.cwd = "/tmp"
    runner.extra_args = None
    # Cold start, not a resume. Set explicitly because a resuming runner also
    # has to emit ``resume=`` on its *first* connect (see is_resuming tests).
    runner.is_resuming = False


def test_initial_options_use_session_id(make_runner) -> None:
    """First connect: SDK creates the session at the given ID (transcript file
    path is predictable). ``resume`` must stay None."""
    runner = make_runner()
    _prime(runner)
    runner._initial_connect_done = False

    options = runner._build_claude_options()

    assert options.session_id == _SESSION_UUID
    assert options.resume is None


def test_reconnect_options_use_resume_not_session_id(make_runner) -> None:
    """Reconnect: ``session_id`` is already live in the SDK's internal
    registry, so re-passing it raises "Session ID … is already in use" and
    the new client never connects. ``resume`` is the documented way to
    continue an existing session."""
    runner = make_runner()
    _prime(runner)
    runner._initial_connect_done = True

    options = runner._build_claude_options()

    assert options.resume == _SESSION_UUID
    assert options.session_id is None


def test_reconnect_with_non_uuid_session_omits_both(make_runner) -> None:
    """If the runner's session_id isn't a valid UUID (very unlikely on real
    spawns but guarded in the builder), reconnect must not pass either
    ``session_id`` or ``resume`` — the SDK will auto-generate one."""
    runner = make_runner()
    _prime(runner)
    runner.session_id = "not-a-uuid"
    runner._initial_connect_done = True

    options = runner._build_claude_options()

    assert options.resume is None
    assert options.session_id is None


def test_resume_uses_resume_on_the_very_first_connect(make_runner) -> None:
    """Resuming a session that already has an on-disk transcript.

    This is the cold-start case ``_initial_connect_done`` cannot cover: it
    answers "have I connected before *in this process*", which is always False
    on a relaunch. But the transcript at
    ~/.claude/projects/<cwd-slug>/<session_id>.jsonl already owns the id, so
    passing ``session_id=`` fails with "Session ID … is already in use" — the
    exact reason resume was unreachable for daemon-spawned sessions.
    """
    runner = make_runner()
    _prime(runner)
    runner._initial_connect_done = False
    runner.is_resuming = True

    options = runner._build_claude_options()

    assert options.resume == _SESSION_UUID
    assert options.session_id is None


def test_resume_flag_defaults_false_on_real_init(monkeypatch) -> None:
    """A normal spawn must still take the ``session_id=`` branch."""
    monkeypatch.setattr(
        "integrations.headless.claude_code.setup_logging",
        lambda *a, **kw: None,
    )
    from integrations.headless.claude_code import HeadlessClaudeRunner

    runner = HeadlessClaudeRunner(
        vicoa_api_key="k",
        session_id=str(uuid.uuid4()),
        console_output=False,
    )
    assert runner.is_resuming is False
    assert runner.claude_options.resume is None
    assert runner.claude_options.session_id is not None


def test_real_init_with_resume_emits_resume(monkeypatch) -> None:
    """End-to-end through __init__: the options built during construction
    already carry ``resume``, since connect() happens before any rebuild."""
    monkeypatch.setattr(
        "integrations.headless.claude_code.setup_logging",
        lambda *a, **kw: None,
    )
    from integrations.headless.claude_code import HeadlessClaudeRunner

    session_id = str(uuid.uuid4())
    runner = HeadlessClaudeRunner(
        vicoa_api_key="k",
        session_id=session_id,
        console_output=False,
        is_resuming=True,
    )
    assert runner.claude_options.resume == session_id
    assert runner.claude_options.session_id is None


def test_initial_connect_flag_defaults_false_on_real_init(monkeypatch) -> None:
    """``__init__`` must set ``_initial_connect_done = False`` so the first
    ``_build_claude_options`` call (from inside ``__init__`` itself) hits the
    ``session_id=`` branch."""
    # Skip the filesystem side-effect of setup_logging.
    monkeypatch.setattr(
        "integrations.headless.claude_code.setup_logging",
        lambda *a, **kw: None,
    )
    from integrations.headless.claude_code import HeadlessClaudeRunner

    runner = HeadlessClaudeRunner(
        vicoa_api_key="k",
        session_id=str(uuid.uuid4()),
        console_output=False,
    )
    assert runner._initial_connect_done is False
