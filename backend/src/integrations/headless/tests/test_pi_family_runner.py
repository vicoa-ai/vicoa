"""Launch-command construction and control-command routing for the runner."""

from __future__ import annotations

import asyncio

import pytest

from integrations.agent_tools.context import DEPTH_ENV_VAR
from integrations.headless.pi_family import runner as runner_mod
from integrations.headless.pi_family.runner import PiFamilyRunner, build_arg_parser
from integrations.headless.pi_family.spec import PI_FAMILY_AGENTS


def make_runner(agent="omp", **kwargs):
    return PiFamilyRunner(
        spec=PI_FAMILY_AGENTS[agent],
        vicoa_api_key="key",
        vicoa_base_url="https://agents.vicoa.ai",
        session_id="sess-1",
        cwd="/work/repo",
        agent_name=PI_FAMILY_AGENTS[agent].display_name,
        agent_command=kwargs.pop("agent_command", f"/usr/local/bin/{agent}"),
        **kwargs,
    )


def test_the_base_command_selects_rpc_mode():
    assert make_runner().build_command() == ["/usr/local/bin/omp", "--mode", "rpc"]


def test_model_and_thinking_flags_are_appended_when_set():
    command = make_runner(
        model="anthropic/claude-haiku-4-5", thinking_effort="high"
    ).build_command()
    assert command[-4:] == [
        "--model",
        "anthropic/claude-haiku-4-5",
        "--thinking",
        "high",
    ]


@pytest.mark.parametrize("sentinel", ["auto", "default", "", "   "])
def test_the_defer_to_the_agent_model_sentinel_sends_no_model_flag(sentinel):
    """`default` means "keep whatever the user configured" — forcing it as a
    literal model name would fail to resolve."""
    assert "--model" not in make_runner(model=sentinel).build_command()


def test_an_unsupported_thinking_level_is_dropped_before_launch():
    """pi has no ``auto``; passing it would hard-fail at the CLI instead."""
    assert "--thinking" not in make_runner("pi", thinking_effort="auto").build_command()
    assert "--thinking" in make_runner("omp", thinking_effort="auto").build_command()


@pytest.mark.parametrize(
    "mode,flag_value",
    [
        ("default", "always-ask"),
        ("acceptEdits", "write"),
        ("bypassPermissions", "yolo"),
    ],
)
def test_vicoa_permission_modes_translate_to_omps_approval_flag(mode, flag_value):
    command = make_runner("omp", permission_mode=mode).build_command()
    assert command[-2:] == ["--approval-mode", flag_value]


def test_pi_never_gets_an_approval_flag_because_it_has_none():
    assert (
        "--approval-mode"
        not in make_runner("pi", permission_mode="default").build_command()
    )


def test_an_unmapped_permission_mode_is_dropped_rather_than_passed_through():
    assert (
        "--approval-mode"
        not in make_runner("omp", permission_mode="plan").build_command()
    )


def test_a_first_launch_carries_no_session_flag():
    """``--session`` only *resolves*: omp exits 1 with 'Session "…" not found.'
    for an id it did not issue, so passing a Vicoa id up front hard-fails."""
    assert "--session" not in make_runner().build_command()


def test_a_resume_passes_the_id_the_agent_itself_issued():
    command = make_runner(agent_session_id="01a06fcb-fe9a-71e6").build_command()
    assert command[-2:] == ["--session", "01a06fcb-fe9a-71e6"]


def test_a_missing_binary_raises_with_the_install_hint(monkeypatch):
    monkeypatch.setattr(runner_mod, "resolve_agent_binary", lambda _spec: None)
    runner = make_runner(agent_command=None)
    with pytest.raises(FileNotFoundError) as excinfo:
        runner.build_command()
    assert "omp.sh/install" in str(excinfo.value)


def test_the_child_environment_carries_the_agent_tool_depth(monkeypatch):
    monkeypatch.setenv(DEPTH_ENV_VAR, "1")
    assert make_runner().build_env()[DEPTH_ENV_VAR] == "1"


def test_depth_defaults_to_zero_for_a_human_started_session(monkeypatch):
    monkeypatch.delenv(DEPTH_ENV_VAR, raising=False)
    assert make_runner().build_env()[DEPTH_ENV_VAR] == "0"


def test_the_session_config_pill_omits_unset_values():
    runner = make_runner(model="x", thinking_effort=None, permission_mode=None)
    assert runner._build_session_config() == {"agent": "omp", "model": "x"}


def test_a_burst_of_messages_coalesces_into_one_turn():
    text, attachments = PiFamilyRunner._coalesce(
        [("first", (), "m1"), ("", (), "m2"), ("second", (), "m3")]
    )
    assert text == "first\n\nsecond"
    assert attachments == ()


def test_the_arg_parser_accepts_only_the_two_agents():
    parser = build_arg_parser()
    assert parser.parse_args(["--agent", "pi"]).agent == "pi"
    with pytest.raises(SystemExit):
        parser.parse_args(["--agent", "claude"])


class StubSession:
    def __init__(self):
        self.interrupted = False
        self.model = None
        self.thinking = None
        self.compacted = False
        self.autocompact = None
        self.handed_off = False

    async def interrupt(self):
        self.interrupted = True

    async def set_model(self, value):
        self.model = value
        return True

    async def set_thinking_level(self, value):
        self.thinking = value
        return True

    async def compact(self, instructions=None):
        self.compacted = True
        return True

    async def set_auto_compaction(self, enabled):
        self.autocompact = enabled
        return True

    async def handoff(self, instructions=None):
        self.handed_off = True
        return "/tmp/handoff.md"

    async def maybe_route_auq_reply(self, _content):
        return False

    def try_resolve_pending_reply(self, _text):
        return False


class StubClient:
    def __init__(self):
        self.rows: list[str] = []
        self.statuses: list[str] = []

    async def send_message(self, **kwargs):
        self.rows.append(kwargs.get("content", ""))

    async def update_agent_instance_status(self, _instance_id, status):
        self.statuses.append(status)

    async def mark_message_consumed(self, _message_id):
        return None


def wire(runner):
    runner.session = StubSession()
    runner.vicoa_client = StubClient()
    return runner.session, runner.vicoa_client


async def test_interrupt_posts_its_notice_before_interrupting():
    """Every agent-message POST re-opens the row as ACTIVE, so a notice sent
    after the interrupt would undo the AWAITING_INPUT it just wrote."""
    runner = make_runner()
    session, client = wire(runner)
    await runner._route('Stop. {"type":"control","setting":"interrupt"}')
    await asyncio.sleep(0)
    assert session.interrupted
    assert client.rows and "Interrupted" in client.rows[0]


async def test_a_model_control_switches_the_model_and_confirms_in_chat():
    runner = make_runner()
    session, client = wire(runner)
    await runner._route(
        'Model {"type":"control","setting":"model","value":"anthropic/x"}'
    )
    assert session.model == "anthropic/x"
    assert any("Model changed to anthropic/x" in row for row in client.rows)
    assert client.statuses[-1] == "AWAITING_INPUT"


async def test_a_thinking_control_is_accepted_under_each_spelling():
    for setting in ("thinking", "effort", "thinking_effort"):
        runner = make_runner()
        session, _client = wire(runner)
        await runner._route(
            'E {"type":"control","setting":"%s","value":"high"}' % setting
        )
        assert session.thinking == "high", setting


async def test_a_permission_mode_change_says_it_needs_a_new_session():
    """The approval mode is a launch flag; there is no RPC for it. Silently
    recording a value that has no effect would be worse than saying so."""
    runner = make_runner()
    _session, client = wire(runner)
    await runner._route(
        'Mode {"type":"control","setting":"permission_mode","value":"bypassPermissions"}'
    )
    assert any("new session" in row for row in client.rows)


async def test_compact_autocompact_and_handoff_reach_the_session():
    runner = make_runner()
    session, _client = wire(runner)
    await runner._route('C {"type":"control","setting":"compact","value":"be brief"}')
    assert session.compacted
    await runner._route('A {"type":"control","setting":"autocompact","value":"off"}')
    assert session.autocompact is False
    await runner._route('H {"type":"control","setting":"handoff","value":"notes"}')
    assert session.handed_off


async def test_an_unknown_control_setting_is_ignored_without_starting_a_turn():
    runner = make_runner()
    _session, _client = wire(runner)
    await runner._route(
        'X {"type":"control","setting":"reasoning_effort","value":"high"}'
    )
    assert runner._turn_queue.empty()


async def test_an_ordinary_message_is_enqueued_for_the_turn_consumer():
    runner = make_runner()
    _session, _client = wire(runner)
    await runner._route("please fix the tests", (), "m1")
    assert runner._turn_queue.get_nowait()[0] == "please fix the tests"
