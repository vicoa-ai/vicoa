"""Layer 1 unit tests for the runner's pure helpers.

These tests run in milliseconds and do not touch the SDK, the network, or the
filesystem. They guard against regressions in the markdown the dashboard parses
and in the permission-cache shape.
"""

from __future__ import annotations

from claude_agent_sdk import (
    AssistantMessage,
    RateLimitEvent,
    RateLimitInfo,
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
)

from integrations.headless.claude_code import (
    _format_dict_as_markdown,
    _format_rate_limit_event,
    _rate_limit_utilization,
)


# ---------------------------------------------------------------------------
# _parse_control_command
# ---------------------------------------------------------------------------


def test_parse_control_command_permission_mode(make_runner):
    runner = make_runner()
    parsed = runner._parse_control_command(
        '{"type": "control", "setting": "permission_mode", "value": "plan"}'
    )
    assert parsed == {"setting": "permission_mode", "value": "plan"}


def test_parse_control_command_interrupt_has_no_value(make_runner):
    runner = make_runner()
    parsed = runner._parse_control_command(
        '{"type": "control", "setting": "interrupt"}'
    )
    assert parsed == {"setting": "interrupt"}


def test_parse_control_command_rejects_missing_setting(make_runner):
    runner = make_runner()
    assert runner._parse_control_command('{"type": "control"}') is None


def test_parse_control_command_rejects_wrong_type(make_runner):
    runner = make_runner()
    assert (
        runner._parse_control_command(
            '{"type": "not_control", "setting": "permission_mode", "value": "plan"}'
        )
        is None
    )


def test_parse_control_command_returns_none_for_plain_text(make_runner):
    runner = make_runner()
    assert runner._parse_control_command("just chatting") is None
    assert runner._parse_control_command("") is None


def test_parse_control_command_accepts_trailing_token(make_runner):
    runner = make_runner()
    # Real control messages are "<label> {json}" — the token trails the body.
    parsed = runner._parse_control_command(
        'Turn thinking on. {"type": "control", "setting": "thinking", "value": "on"}'
    )
    assert parsed == {"setting": "thinking", "value": "on"}


def test_parse_control_command_rejects_json_embedded_in_prose(make_runner):
    runner = make_runner()
    # A user message that merely *quotes* control JSON amid prose (there is text
    # after the token) must NOT be treated as a control command — otherwise the
    # whole message is silently swallowed (the idle-session message-swallow bug).
    assert (
        runner._parse_control_command(
            'hello {"type": "control", "setting": "thinking", "value": "on"} bye'
        )
        is None
    )


# ---------------------------------------------------------------------------
# _bash_command_prefix
# ---------------------------------------------------------------------------


def test_bash_command_prefix_basic(make_runner):
    runner = make_runner()
    assert runner._bash_command_prefix({"command": "ls -la"}) == "ls"
    assert runner._bash_command_prefix({"command": "git status"}) == "git"


def test_bash_command_prefix_handles_missing_or_blank(make_runner):
    runner = make_runner()
    assert runner._bash_command_prefix({}) is None
    assert runner._bash_command_prefix({"command": ""}) is None
    assert runner._bash_command_prefix({"command": "   "}) is None


def test_bash_command_prefix_non_string(make_runner):
    runner = make_runner()
    assert runner._bash_command_prefix({"command": 42}) is None


# ---------------------------------------------------------------------------
# Permission cache (_is_cached_permission / _cache_permission)
# ---------------------------------------------------------------------------


def test_permission_cache_bash_is_per_prefix(make_runner):
    runner = make_runner()

    assert runner._is_cached_permission("Bash", {"command": "ls"}) is False
    runner._cache_permission("Bash", {"command": "ls"})

    # Same prefix → cached
    assert runner._is_cached_permission("Bash", {"command": "ls"}) is True
    assert runner._is_cached_permission("Bash", {"command": "ls -la"}) is True

    # Different prefix → not cached
    assert runner._is_cached_permission("Bash", {"command": "rm -rf /tmp/x"}) is False


def test_permission_cache_non_bash_is_per_tool(make_runner):
    runner = make_runner()

    assert runner._is_cached_permission("Edit", {"file_path": "/x"}) is False
    runner._cache_permission("Edit", {"file_path": "/x"})

    # Any subsequent Edit hits the cache regardless of input
    assert runner._is_cached_permission("Edit", {"file_path": "/y"}) is True
    assert runner._is_cached_permission("Write", {"file_path": "/x"}) is False


def test_permission_cache_bash_without_prefix_is_noop(make_runner):
    runner = make_runner()
    runner._cache_permission("Bash", {"command": ""})
    assert runner._permission_state == {}


# ---------------------------------------------------------------------------
# _render_permission_prompt — the dashboard parses these labels back, so the
# exact wording is load-bearing. Options are uniform for every tool:
# "allow once" / "allow always" / "deny".
# ---------------------------------------------------------------------------


def test_render_permission_prompt_bash(make_runner):
    runner = make_runner()
    body = runner._render_permission_prompt("Bash", {"command": "git status"})
    assert "Allow execution of Bash git?" in body
    assert "```bash\ngit status\n```" in body
    assert "[OPTIONS]\n1. Allow once\n2. Always allow\n3. Deny\n[/OPTIONS]" in body


def test_render_permission_prompt_non_bash_uses_input_block(make_runner):
    runner = make_runner()
    body = runner._render_permission_prompt("Edit", {"file_path": "/a/b.py"})
    assert "Allow execution of Edit?" in body
    # _format_dict_as_markdown is used for non-Bash tools
    assert "**file_path:**" in body
    assert "/a/b.py" in body
    assert "[OPTIONS]\n1. Allow once\n2. Always allow\n3. Deny\n[/OPTIONS]" in body


def test_render_permission_prompt_uniform_options_across_tools(make_runner):
    """The dashboard renders the same three buttons regardless of tool."""
    runner = make_runner()
    bash = runner._render_permission_prompt("Bash", {"command": "rm -rf /tmp/x"})
    write = runner._render_permission_prompt("Write", {"file_path": "/x"})
    options_block = "[OPTIONS]\n1. Allow once\n2. Always allow\n3. Deny\n[/OPTIONS]"
    assert options_block in bash
    assert options_block in write


# ---------------------------------------------------------------------------
# _format_dict_as_markdown (module-level helper)
# ---------------------------------------------------------------------------


def test_format_dict_as_markdown_simple():
    out = _format_dict_as_markdown({"file_path": "/x", "limit": 10})
    assert "**file_path:**" in out
    assert "/x" in out
    assert "**limit:**" in out
    assert "10" in out


def test_format_dict_as_markdown_multiline_string_uses_code_block():
    out = _format_dict_as_markdown({"command": "line1\nline2"})
    assert "```\nline1\nline2\n```" in out


def test_format_dict_as_markdown_list_as_bullets():
    out = _format_dict_as_markdown({"todos": ["a", "b", "c"]})
    assert "  - a" in out
    assert "  - b" in out
    assert "  - c" in out


def test_format_dict_as_markdown_nested_dict_is_indented():
    out = _format_dict_as_markdown({"opts": {"flag": True, "n": 1}})
    # Inner content is indented two spaces
    assert "  **flag:**" in out
    assert "  **n:**" in out


# ---------------------------------------------------------------------------
# format_message_content — AskUserQuestion tool_use should be silently skipped
# so the dashboard's interactive picker (sent separately via
# _handle_ask_user_question's message_metadata) doesn't render alongside a
# duplicate plain-markdown copy.
# ---------------------------------------------------------------------------


def _assistant_message(*blocks) -> AssistantMessage:
    return AssistantMessage(content=list(blocks), model="claude-test")


def test_format_message_content_skips_ask_user_question_with_text(make_runner):
    """An AssistantMessage that contains an AUQ tool_use must skip the ENTIRE
    message, not just the ToolUseBlock.

    Rationale: the SDK fires can_use_tool on a separate task (the SDK
    spawns it via ``_spawn_control_request_handler``), which runs
    concurrently with ``run_conversation_turn``. If the runner also POSTs
    via ``send_to_vicoa`` for the text portion, the two concurrent agent
    POSTs race for ``instance.last_read_message_id`` on the backend. The
    loser's ``send_message`` poll passes a now-stale cursor and gets
    ``status: "stale"`` → ``TimeoutError`` → silent Deny → Claude says
    "Looks like the question timed out" and retries.

    Repro: session ``8a672901-29e9-4130-bc99-e73479a021dd`` (AUQ turn at
    21:34:58 — Message #3/#4 gap of 0.747s shows the race fired the deny
    path long before any real timeout could have elapsed).
    """
    runner = make_runner()
    message = _assistant_message(
        TextBlock(text="I'll ask you a question."),
        ToolUseBlock(
            id="tu_1",
            name="AskUserQuestion",
            input={"questions": [{"question": "Pick a color", "options": []}]},
        ),
    )
    formatted = runner.format_message_content(message)
    # Even the intro text is suppressed — sending it would race against the
    # AUQ POST. The picker (sent separately by _handle_ask_user_question
    # with message_metadata) is the canonical display.
    assert formatted == ""


def test_format_message_content_renders_other_tool_uses(make_runner):
    """Sanity: non-AUQ tool_use blocks still render — no over-broad skip."""
    runner = make_runner()
    message = _assistant_message(
        ToolUseBlock(id="tu_2", name="Bash", input={"command": "ls"})
    )
    formatted = runner.format_message_content(message)
    assert "Bash" in formatted
    assert "ls" in formatted


def test_format_message_content_ask_user_question_only_message(make_runner):
    """AssistantMessage that is only an AUQ tool_use → suppressed entirely."""
    runner = make_runner()
    message = _assistant_message(
        ToolUseBlock(
            id="tu_3",
            name="AskUserQuestion",
            input={"questions": [{"question": "X", "options": []}]},
        )
    )
    formatted = runner.format_message_content(message)
    assert formatted == ""


def test_format_message_content_text_only_message_unaffected(make_runner):
    """Plain text AssistantMessages still render normally — no over-broad skip."""
    runner = make_runner()
    message = _assistant_message(TextBlock(text="just talking"))
    assert runner.format_message_content(message) == "just talking"


def test_format_message_content_thinking_only_message_suppressed(make_runner):
    """A thinking-only AssistantMessage must be suppressed, not rendered as the
    bogus "Claude is thinking..." placeholder.

    Adaptive thinking emits ThinkingBlock-only turns (and with
    display="omitted" on Opus 4.7+ / Fable 5 the thinking text is empty).
    ``format_message_content`` renders none of those, so it must return ""
    and let the run loop's ``if formatted_content:`` guard drop the message —
    otherwise every thinking turn POSTs a spurious agent message to chat.
    """
    runner = make_runner()
    message = _assistant_message(
        ThinkingBlock(thinking="deciding what to do", signature="sig")
    )
    assert runner.format_message_content(message) == ""


def test_format_message_content_thinking_plus_text_renders_text(make_runner):
    """Sanity: a thinking block alongside text still renders the text only —
    the suppression is scoped to no-renderable-parts turns."""
    runner = make_runner()
    message = _assistant_message(
        ThinkingBlock(thinking="hmm", signature="sig"),
        TextBlock(text="here is the answer"),
    )
    assert runner.format_message_content(message) == "here is the answer"


# ---------------------------------------------------------------------------
# _is_persist_only_message — display-only artefacts that must not flow into
# the conversation as user input.
# ---------------------------------------------------------------------------


def test_is_persist_only_recognises_ask_user_question_summary(make_runner):
    runner = make_runner()
    summary = (
        "Q: Pick a color\nA: red\n"
        '{"type":"control","action":"persist_only",'
        '"kind":"ask_user_question_summary","value":"v1:eyJmb28iOiJiYXIifQ"}'
    )
    assert runner._is_persist_only_message(summary) is True


def test_is_persist_only_recognises_decline_to_answer(make_runner):
    """The dashboard's cancel-summary message ("Declined to answer")."""
    runner = make_runner()
    msg = 'Declined to answer\n{"type":"control","action":"persist_only"}'
    assert runner._is_persist_only_message(msg) is True


def test_is_persist_only_rejects_plain_user_message(make_runner):
    runner = make_runner()
    assert runner._is_persist_only_message("hello world") is False
    assert runner._is_persist_only_message("") is False


def test_is_persist_only_rejects_other_control_messages(make_runner):
    """A standard ask_user_question submit must NOT be classified persist_only."""
    runner = make_runner()
    submit = (
        "Submit AskUserQuestion answers. "
        '{"type":"control","setting":"ask_user_question","value":"submit:abc"}'
    )
    assert runner._is_persist_only_message(submit) is False


def test_prose_quoting_control_json_is_not_swallowed(make_runner):
    """Regression: a normal user message that *pastes/quotes* control JSON amid
    prose (the session ``49ed4485`` swallow) must route as ordinary input.

    The message discusses the ``session get`` output and embeds both a
    persist_only summary token and an ask_user_question submit token in the
    middle of the body, with plenty of text after them. None of the three
    content decoders may claim it, or ``_route`` drops it before it ever
    reaches the agent — and, because it is deduped into the WS catch-up buffer
    on the way out, the reconcile backstop can never recover it.
    """
    runner = make_runner()
    prose = (
        "Commit the current changes.\n"
        "2. Session get includes control messages like:\n"
        '  {"type":"control","action":"persist_only",'
        '"kind":"ask_user_question_summary","value":"v1:eyJhIjoxfQ"}\n\n'
        "[2026-08-01 18:19] USER\n"
        '  Submit answers. {"type":"control","setting":"ask_user_question",'
        '"value":"submit:eyJhIjoxfQ"}\n\n'
        "By default no."
    )
    assert runner._is_persist_only_message(prose) is False
    assert runner._parse_control_command(prose) is None
    assert runner._decode_ask_user_question_reply(prose) is None


# ---------------------------------------------------------------------------
# _format_rate_limit_event — the SDK emits RateLimitEvent on every status
# transition (including back to "allowed"). The reported repro
# (``ef853f34-…`` Message #6 at 22:18:51) showed a raw dataclass repr land
# in the dashboard for status="allowed", which was just informational noise.
# ---------------------------------------------------------------------------


def _rl_event(
    status: str,
    *,
    rate_limit_type: str | None = "five_hour",
    resets_at: int | None = 1778779200,
    utilization: float | None = None,
    overage_disabled_reason: str | None = None,
) -> RateLimitEvent:
    return RateLimitEvent(
        rate_limit_info=RateLimitInfo(
            status=status,  # type: ignore[arg-type]
            resets_at=resets_at,
            rate_limit_type=rate_limit_type,  # type: ignore[arg-type]
            utilization=utilization,
            overage_disabled_reason=overage_disabled_reason,
        ),
        uuid="event-uuid",
        session_id="session-uuid",
    )


def test_format_rate_limit_event_allowed_is_suppressed():
    """status="allowed" is the SDK's informational case — must not surface."""
    assert _format_rate_limit_event(_rl_event("allowed")) is None


def test_format_rate_limit_event_warning_renders_readable():
    out = _format_rate_limit_event(_rl_event("allowed_warning", utilization=0.85))
    assert out is not None
    assert "⚠️" in out
    assert "5-hour" in out
    assert "85% used" in out
    assert "resets " in out  # ISO datetime string


def test_format_rate_limit_event_rejected_includes_overage_reason():
    out = _format_rate_limit_event(
        _rl_event(
            "rejected",
            overage_disabled_reason="org_level_disabled",
        )
    )
    assert out is not None
    assert "🛑" in out
    assert "5-hour" in out
    assert "rate limit reached" in out
    assert "overage disabled: org_level_disabled" in out


def test_format_rate_limit_event_unknown_window_passes_through():
    """If the SDK adds a new rate_limit_type literal we don't have a label
    for, render the raw value rather than crashing."""
    out = _format_rate_limit_event(
        _rl_event("allowed_warning", rate_limit_type="brand_new_window")  # type: ignore[arg-type]
    )
    assert out is not None
    assert "brand_new_window" in out


def test_format_rate_limit_event_missing_resets_at():
    out = _format_rate_limit_event(_rl_event("rejected", resets_at=None))
    assert out is not None
    assert "reset time unknown" in out


def test_format_rate_limit_event_does_not_leak_raw_repr():
    """The original bug: ``str(RateLimitEvent(...))`` was leaking into the
    dashboard. Ensure the formatter never emits the dataclass repr."""
    out = _format_rate_limit_event(_rl_event("allowed_warning"))
    assert out is not None
    assert "RateLimitEvent(" not in out
    assert "RateLimitInfo(" not in out


# ---------------------------------------------------------------------------
# _rate_limit_utilization — the SDK's terminal "rejected" event doesn't
# always carry a utilization figure (repro: session 47c0a49c, banner had no
# "N% used" segment), which made claude_window() drop the window and left
# rate_limited_until unset for a session that was genuinely blocked.
# ---------------------------------------------------------------------------


def test_rate_limit_utilization_defaults_rejected_to_full():
    info = _rl_event("rejected", utilization=None).rate_limit_info
    assert _rate_limit_utilization(info) == 1.0


def test_rate_limit_utilization_keeps_real_rejected_value():
    info = _rl_event("rejected", utilization=0.97).rate_limit_info
    assert _rate_limit_utilization(info) == 0.97


def test_rate_limit_utilization_leaves_non_rejected_missing_value_alone():
    """Only "rejected" gets the 100% fallback — a warning with no utilization
    should still surface as "no figure to show", same as before."""
    info = _rl_event("allowed_warning", utilization=None).rate_limit_info
    assert _rate_limit_utilization(info) is None
