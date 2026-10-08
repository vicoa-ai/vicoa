"""Unit tests for the ``vicoa automation`` request-body builders.

Pure-function coverage for the flag → request-body translation (schedule
selection, session-config assembly, weekday parsing) — the part with real logic
the server never sees until it is already correct. The server-side CRUD is
covered in src/servers/tests/test_automation_endpoints.py.
"""

import argparse
from types import SimpleNamespace

import pytest

from vicoa.commands import automation as A


def _args(**kw):
    """An argparse-Namespace stand-in: every schedule/config flag defaults off."""
    base = dict(
        at=None,
        daily=False,
        hourly=False,
        weekdays=False,
        weekly=None,
        frequency_json=None,
        time=None,
        minute=None,
        timezone=None,
        agent=None,
        model=None,
        effort=None,
        permission_mode=None,
        session_config_json=None,
        worktree_json=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


class TestParseWeekdays:
    def test_parses_and_trims(self):
        assert A._parse_weekdays("1, 3 ,5") == [1, 3, 5]

    def test_rejects_out_of_range(self):
        with pytest.raises(ValueError):
            A._parse_weekdays("7")

    def test_rejects_non_integer(self):
        with pytest.raises(ValueError):
            A._parse_weekdays("mon")

    def test_rejects_empty(self):
        with pytest.raises(ValueError):
            A._parse_weekdays(" , ")


class TestScheduleFields:
    def test_once(self):
        fields = A._schedule_fields(_args(at="2999-01-01T09:00:00Z"))
        assert fields == {"schedule_kind": "once", "run_at": "2999-01-01T09:00:00Z"}

    def test_daily_default_time(self):
        fields = A._schedule_fields(_args(daily=True))
        assert fields == {
            "schedule_kind": "recurring",
            "frequency": {"kind": "daily", "time": "09:00"},
        }

    def test_daily_custom_time(self):
        fields = A._schedule_fields(_args(daily=True, time="18:30"))
        assert fields["frequency"] == {"kind": "daily", "time": "18:30"}

    def test_hourly_default_minute_zero(self):
        fields = A._schedule_fields(_args(hourly=True))
        assert fields["frequency"] == {"kind": "hourly", "minute": 0}

    def test_hourly_explicit_minute(self):
        fields = A._schedule_fields(_args(hourly=True, minute=30))
        assert fields["frequency"] == {"kind": "hourly", "minute": 30}

    def test_weekdays(self):
        fields = A._schedule_fields(_args(weekdays=True, time="08:00"))
        assert fields["frequency"] == {"kind": "weekdays", "time": "08:00"}

    def test_weekly(self):
        fields = A._schedule_fields(_args(weekly="1,3,5"))
        assert fields["frequency"] == {
            "kind": "weekly",
            "weekdays": [1, 3, 5],
            "time": "09:00",
        }

    def test_frequency_json_passthrough(self):
        raw = '{"kind":"custom","unit":"daily","interval":2,"time":"09:00"}'
        fields = A._schedule_fields(_args(frequency_json=raw))
        assert fields["frequency"]["unit"] == "daily"
        assert fields["schedule_kind"] == "recurring"

    def test_frequency_json_invalid(self):
        with pytest.raises(ValueError):
            A._schedule_fields(_args(frequency_json="{not json"))

    def test_timezone_attaches_to_recurring(self):
        fields = A._schedule_fields(_args(daily=True, timezone="America/New_York"))
        assert fields["timezone"] == "America/New_York"

    def test_timezone_alone_is_a_schedule_edit(self):
        # No selector, just a timezone → valid PATCH that re-times the run.
        assert A._schedule_fields(_args(timezone="UTC")) == {"timezone": "UTC"}

    def test_no_selector_is_empty(self):
        assert A._schedule_fields(_args()) == {}

    def test_mutually_exclusive(self):
        with pytest.raises(ValueError):
            A._schedule_fields(_args(daily=True, hourly=True))


class TestSessionConfig:
    def test_from_json(self):
        cfg = A._session_config(
            _args(session_config_json='{"agent":"codex","model":"gpt"}'),
            required=True,
        )
        assert cfg == {"agent": "codex", "model": "gpt"}

    def test_json_must_be_object(self):
        with pytest.raises(ValueError):
            A._session_config(_args(session_config_json="[1,2]"), required=True)

    def test_from_flags_claude_effort_maps_to_thinking(self):
        cfg = A._session_config(
            _args(agent="claude", model="opus", effort="high", permission_mode="plan"),
            required=True,
        )
        assert cfg == {
            "agent": "claude",
            "model": "opus",
            "permission_mode": "plan",
            "thinking_effort": "high",
        }

    def test_from_flags_codex_effort_maps_to_reasoning(self):
        cfg = A._session_config(_args(agent="codex", effort="medium"), required=True)
        assert cfg == {"agent": "codex", "reasoning_effort": "medium"}

    def test_effort_on_unsupported_agent_errors(self):
        with pytest.raises(ValueError):
            A._session_config(_args(agent="opencode", effort="high"), required=True)

    def test_required_but_absent_errors(self):
        with pytest.raises(ValueError):
            A._session_config(_args(), required=True)

    def test_optional_and_absent_returns_none(self):
        assert A._session_config(_args(), required=False) is None

    def test_flags_without_agent_errors(self):
        with pytest.raises(ValueError):
            A._session_config(_args(model="opus"), required=True)


class TestScheduleSummary:
    def test_once(self):
        assert A._schedule_summary({"schedule_kind": "once"}) == "once"

    def test_daily(self):
        a = {
            "schedule_kind": "recurring",
            "frequency": {"kind": "daily", "time": "09:00"},
        }
        assert A._schedule_summary(a) == "daily 09:00"

    def test_weekly(self):
        a = {
            "schedule_kind": "recurring",
            "frequency": {"kind": "weekly", "weekdays": [1, 3], "time": "07:00"},
        }
        assert A._schedule_summary(a) == "weekly [1,3] 07:00"

    def test_hourly(self):
        a = {"schedule_kind": "recurring", "frequency": {"kind": "hourly", "minute": 5}}
        assert A._schedule_summary(a) == "hourly :05"


def _cli_like_parser():
    """A top-level parser mimicking cli.py's global ``--agent`` default, which
    argparse leaks into every subcommand's namespace."""
    top = argparse.ArgumentParser()
    top.add_argument("--agent", default="claude")  # the run-path global
    sub = top.add_subparsers(dest="command")
    A.add_automation_subparser(sub)
    return top


class TestGlobalAgentDefaultLeak:
    """Regression: the top-level ``--agent`` default must not silently populate
    an automation's session_config. See set_defaults(agent=None) in the parser."""

    def test_bare_update_builds_no_session_config(self):
        ns = _cli_like_parser().parse_args(
            ["automation", "update", "11111111-1111-1111-1111-111111111111"]
        )
        assert A._session_config(ns, required=False) is None

    def test_bare_create_still_requires_explicit_agent(self):
        ns = _cli_like_parser().parse_args(
            ["automation", "create", "T", "--prompt", "p", "--daily"]
        )
        with pytest.raises(ValueError):
            A._session_config(ns, required=True)

    def test_create_honours_explicit_agent(self):
        ns = _cli_like_parser().parse_args(
            [
                "automation",
                "create",
                "T",
                "--prompt",
                "p",
                "--daily",
                "--agent",
                "codex",
            ]
        )
        assert A._session_config(ns, required=True) == {"agent": "codex"}


_AUTOMATION_ID = "11111111-1111-1111-1111-111111111111"
_PROFILE = {
    "id": "22222222-2222-2222-2222-222222222222",
    "name": "Reviewer",
    "agent": "claude",
    "config": {"model": "opus", "thinking_effort": "high"},
}


@pytest.fixture
def api(monkeypatch):
    """Record what the handlers send instead of hitting the server; the profile
    lookup answers with `_PROFILE`, and a GET answers with `api.current`."""
    sent: list[tuple[str, str, dict | None]] = []

    def fake_request(args, api_key, method, path, json=None):
        sent.append((method, path, json))
        if method == "GET":
            return api.current
        return {"id": _AUTOMATION_ID, "title": "T", "schedule_kind": "once"}

    import vicoa.commands.agent as agent_cmd

    monkeypatch.setattr(A, "request", fake_request)
    monkeypatch.setattr(A, "_resolve_machine_id", lambda args: "machine-1")
    monkeypatch.setattr(
        agent_cmd, "resolve_profile_by_name", lambda args, key, name: _PROFILE
    )
    api = SimpleNamespace(sent=sent, current={"agent_profile_id": None})
    return api


def _run(argv):
    ns = _cli_like_parser().parse_args(argv)
    return A._HANDLERS[ns.automation_command](ns, "key")


class TestAgentProfileFlag:
    def test_create_links_the_saved_agent_and_snapshots_its_config(self, api):
        code = _run(
            [
                "automation",
                "create",
                "T",
                "--prompt",
                "p",
                "--daily",
                "--agent-profile",
                "Reviewer",
            ]
        )
        assert code == 0
        ((method, _, body),) = api.sent
        assert method == "POST"
        assert body["agent_profile_id"] == _PROFILE["id"]
        assert body["session_config"] == {
            "agent": "claude",
            "model": "opus",
            "thinking_effort": "high",
        }

    def test_create_refuses_session_flags_next_to_a_saved_agent(self, api, capsys):
        code = _run(
            [
                "automation",
                "create",
                "T",
                "--prompt",
                "p",
                "--daily",
                "--agent-profile",
                "Reviewer",
                "--model",
                "sonnet",
            ]
        )
        assert code == 2
        assert api.sent == []
        assert "--model" in capsys.readouterr().err

    def test_update_relinks(self, api):
        assert (
            _run(
                ["automation", "update", _AUTOMATION_ID, "--agent-profile", "Reviewer"]
            )
            == 0
        )
        ((method, _, body),) = api.sent
        assert method == "PATCH"
        assert body["agent_profile_id"] == _PROFILE["id"]
        assert body["session_config"]["model"] == "opus"

    def test_update_none_unlinks_and_may_set_a_config(self, api):
        assert (
            _run(
                [
                    "automation",
                    "update",
                    _AUTOMATION_ID,
                    "--agent-profile",
                    "none",
                    "--session-config-json",
                    '{"agent": "codex"}',
                ]
            )
            == 0
        )
        ((method, _, body),) = api.sent
        assert method == "PATCH"
        assert body == {"agent_profile_id": None, "session_config": {"agent": "codex"}}

    def test_update_refuses_a_config_a_linked_automation_would_ignore(
        self, api, capsys
    ):
        api.current = {"agent_profile_id": _PROFILE["id"]}
        code = _run(
            [
                "automation",
                "update",
                _AUTOMATION_ID,
                "--session-config-json",
                '{"agent": "codex"}',
            ]
        )
        assert code == 2
        assert [m for m, _, _ in api.sent] == ["GET"]
        assert "--agent-profile none" in capsys.readouterr().err

    def test_update_config_on_an_unlinked_automation_goes_through(self, api):
        assert (
            _run(
                [
                    "automation",
                    "update",
                    _AUTOMATION_ID,
                    "--session-config-json",
                    '{"agent": "codex"}',
                ]
            )
            == 0
        )
        assert [m for m, _, _ in api.sent] == ["GET", "PATCH"]


_SESSION_ID = "33333333-3333-3333-3333-333333333333"


class TestSessionFlag:
    def test_create_targets_the_session_and_nothing_else(self, api):
        code = _run(
            [
                "automation",
                "create",
                "T",
                "--prompt",
                "p",
                "--hourly",
                "--session",
                _SESSION_ID,
            ]
        )
        assert code == 0
        ((method, _, body),) = api.sent
        assert method == "POST"
        assert body["agent_instance_id"] == _SESSION_ID
        # The session brings its own machine, folder and agent.
        for key in ("machine_id", "directory", "session_config", "worktree"):
            assert key not in body
        assert body["frequency"] == {"kind": "hourly", "minute": 0}

    def test_create_refuses_new_session_flags_next_to_a_session(self, api, capsys):
        code = _run(
            [
                "automation",
                "create",
                "T",
                "--prompt",
                "p",
                "--daily",
                "--session",
                _SESSION_ID,
                "--agent",
                "codex",
                "--directory",
                "/repo",
            ]
        )
        assert code == 2
        assert api.sent == []
        err = capsys.readouterr().err
        assert "--agent" in err and "--directory" in err

    def test_update_retargets(self, api):
        assert (
            _run(["automation", "update", _AUTOMATION_ID, "--session", _SESSION_ID])
            == 0
        )
        ((_, _, body),) = api.sent
        assert body == {"agent_instance_id": _SESSION_ID}

    def test_update_none_goes_back_to_new_sessions(self, api):
        code = _run(
            [
                "automation",
                "update",
                _AUTOMATION_ID,
                "--session",
                "none",
                "--directory",
                "/repo",
            ]
        )
        assert code == 0
        ((_, _, body),) = api.sent
        assert body == {"agent_instance_id": None, "directory": "/repo"}

    def test_detail_says_where_it_runs(self):
        assert A._runs_in({}) == "a new session each run"
        assert (
            A._runs_in(
                {"agent_instance_id": _SESSION_ID, "agent_instance_name": "Fix CI"}
            )
            == f"session {_SESSION_ID} (Fix CI)"
        )
