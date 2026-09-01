"""Unit tests for the ``vicoa session`` transcript formatting helpers.

Pure-function coverage for the parsing that decides what the default (clean)
transcript hides — control envelopes and tool-use payloads — mirroring the
web's control-messages / tool-use-parsing tests so the CLI and dashboard agree
on what counts as a control message or a tool use.
"""

import json
import re
import types
from datetime import datetime, timedelta, timezone

from vicoa.commands import instance as I

# A rendered timestamp header, e.g. "[2026-08-01 18:15]" — matched by pattern so
# the assertion is independent of the machine's local timezone (the raw UTC is
# converted to local time before display).
_TIMESTAMP_RE = re.compile(r"\[\d{4}-\d\d-\d\d \d\d:\d\d\]")


def _iso_ago(seconds: float) -> str:
    """ISO-8601 UTC timestamp ``seconds`` in the past — for heartbeat freshness."""
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()


class TestControlEnvelope:
    def test_bare_persist_only_blob_is_control(self):
        content = (
            '{"type":"control","action":"persist_only",'
            '"kind":"ask_user_question_summary","value":"v1:abc"}'
        )
        assert I._is_control_envelope(content)

    def test_labelled_submit_token_is_control(self):
        content = (
            "Submit AskUserQuestion answers. "
            '{"type":"control","setting":"ask_user_question","value":"submit:xyz"}'
        )
        assert I._is_control_envelope(content)

    def test_prose_quoting_control_json_is_not_control(self):
        # A real message that merely pastes control JSON amid prose stays visible.
        content = 'Look at {"type":"control","setting":"x"} then keep explaining it.'
        assert not I._is_control_envelope(content)

    def test_plain_message_is_not_control(self):
        assert not I._is_control_envelope("just a normal message")

    def test_empty_is_not_control(self):
        assert not I._is_control_envelope("")


class TestSplitToolUse:
    def test_edit_header_split_from_diff_payload(self):
        content = "🔧 Using tool: **Edit** - `/a/b.py`\n\n```diff\n+x\n-y\n```"
        header, payload = I._split_tool_use(content)
        assert header == "🔧 Using tool: **Edit** - `/a/b.py`"
        assert "diff" in payload

    def test_ask_user_question_has_no_payload(self):
        header, payload = I._split_tool_use("🔧 Using tool: AskUserQuestion")
        assert header == "🔧 Using tool: AskUserQuestion"
        assert payload == ""

    def test_plain_prefix_without_emoji(self):
        header, payload = I._split_tool_use("Using tool: Bash - `ls`\noutput line")
        assert header == "Using tool: Bash - `ls`"
        assert payload == "output line"

    def test_non_tool_message_returns_none(self):
        header, payload = I._split_tool_use("The agent finished the task.")
        assert header is None
        assert payload == ""


class TestModelOf:
    def test_reads_model_from_session_config(self):
        assert I._model_of({"session_config": {"model": "claude-opus-4-8"}}) == (
            "claude-opus-4-8"
        )

    def test_missing_model_returns_dash(self):
        assert I._model_of({"session_config": {}}) == "—"

    def test_no_session_config_returns_dash(self):
        assert I._model_of({}) == "—"


def _sample_messages():
    return [
        {
            "sender_type": "USER",
            "content": "fix the bug",
            "created_at": "2026-08-01T18:15:00Z",
            "sender_user_email": "nick@example.com",
            "requires_user_input": False,
        },
        {
            "sender_type": "AGENT",
            "content": "🔧 Using tool: AskUserQuestion",
            "created_at": "2026-08-01T18:15:30Z",
            "requires_user_input": True,
        },
        {
            "sender_type": "USER",
            "content": (
                "Submit AskUserQuestion answers. "
                '{"type":"control","setting":"ask_user_question","value":"submit:x"}'
            ),
            "created_at": "2026-08-01T18:16:00Z",
            "sender_user_email": "nick@example.com",
            "requires_user_input": False,
        },
        {
            "sender_type": "AGENT",
            "content": "🔧 Using tool: **Edit** - `/a/b.py`\n\n```diff\n+added\n```",
            "created_at": "2026-08-01T18:17:00Z",
            "requires_user_input": False,
        },
    ]


_HEADER = {"agent_instance_id": "abc", "name": "demo", "agent_type_name": "Claude Code"}


class TestRenderDefaults:
    def test_default_hides_control_and_tool_payload(self, capsys):
        I._print_instance_detail(
            _HEADER,
            _sample_messages(),
            timestamps=False,
            emails=False,
            control=False,
            tool_content=False,
        )
        out = capsys.readouterr().out
        # Control message body is gone; tool name shows but its diff does not.
        assert "submit:x" not in out
        assert "Using tool: AskUserQuestion" in out
        assert "+added" not in out
        # No timestamps / emails in the clean view.
        assert "nick@example.com" not in out
        assert not _TIMESTAMP_RE.search(out)
        # And the reader is told what was suppressed.
        assert "hidden" in out

    def test_full_reveals_everything(self, capsys):
        I._print_instance_detail(
            _HEADER,
            _sample_messages(),
            timestamps=True,
            emails=True,
            control=True,
            tool_content=True,
        )
        out = capsys.readouterr().out
        assert "submit:x" in out
        assert "+added" in out
        assert "nick@example.com" in out
        assert _TIMESTAMP_RE.search(out)


def _instance(**over):
    base = {
        "id": "abcdef12-0000",
        "agent_type_name": "Claude Code",
        "status": "AWAITING_INPUT",
        "name": "n",
        "project": "/x/proj",
        "chat_length": 1,
        "started_at": "2026-08-20T10:00:00Z",
        "session_config": {"model": "claude-opus-4-8"},
        "rate_limited": False,
        "rate_limit_resets_at": None,
    }
    base.update(over)
    return base


class TestRateLimitTable:
    def test_reset_column_shown_only_when_a_row_is_rate_limited(self, capsys):
        # No limited rows -> no RESET column.
        I._print_instance_table([_instance()], total=1)
        assert "RESET" not in capsys.readouterr().out
        # A limited row -> RESET column with the reset time.
        I._print_instance_table(
            [
                _instance(
                    rate_limited=True,
                    rate_limit_resets_at="2026-08-20T18:00:00Z",
                )
            ],
            total=1,
        )
        out = capsys.readouterr().out
        assert "RESET" in out
        # 18:00 UTC rendered as some local HH:MM (tz-independent check).
        assert re.search(r"\d{4}-\d\d-\d\d \d\d:\d\d", out)


class TestContinueAndMessage:
    def _args(self, **over):
        base = {"session_id": "abcdef12", "json": False, "text": None}
        base.update(over)
        return types.SimpleNamespace(**base)

    def test_continue_posts_literal_continue(self, monkeypatch):
        calls = []

        def fake_request(args, api_key, method, endpoint, *, params=None, json=None):
            calls.append((method, endpoint, json))
            # First call resolves the id (GET list); handler posts on the second.
            if method == "GET":
                return {"items": [{"id": "abcdef12-0000-0000"}]}
            return {"success": True, "message_id": "m1"}

        monkeypatch.setattr(I, "request", fake_request)
        rc = I._cmd_continue(self._args(), "key")
        assert rc == 0
        post = [c for c in calls if c[0] == "POST"][0]
        assert post[1] == "/api/v1/messages/user"
        assert post[2] == {
            "agent_instance_id": "abcdef12-0000-0000",
            "content": "continue",
        }

    def test_message_requires_non_empty_text(self, monkeypatch):
        def boom(*a, **k):
            raise AssertionError("request() must not run for empty message text")

        monkeypatch.setattr(I, "request", boom)
        rc = I._cmd_message(self._args(text="   "), "key")
        assert rc == 2

    def test_message_posts_given_text(self, monkeypatch):
        calls = []

        def fake_request(args, api_key, method, endpoint, *, params=None, json=None):
            calls.append((method, endpoint, json))
            if method == "GET":
                return {"items": [{"id": "abcdef12-0000-0000"}]}
            return {"success": True, "message_id": "m1"}

        monkeypatch.setattr(I, "request", fake_request)
        rc = I._cmd_message(self._args(text="run the tests"), "key")
        assert rc == 0
        post = [c for c in calls if c[0] == "POST"][0]
        assert post[2]["content"] == "run the tests"


class TestGetRoleFilter:
    _UUID = "abcdef12-0000-0000-0000-000000000000"

    def _args(self, **over):
        base = {
            "session_id": self._UUID,
            "limit": 50,
            "all_messages": False,
            "json": False,
            "full": False,
            "timestamps": False,
            "emails": False,
            "show_control": False,
            "tool_content": False,
            "role": None,
        }
        base.update(over)
        return types.SimpleNamespace(**base)

    def _patch_request(self, monkeypatch):
        """Serve a header on the instance GET and the sample page on messages."""

        def fake_request(args, api_key, method, endpoint, *, params=None, json=None):
            if endpoint.endswith("/messages"):
                return _sample_messages()
            return dict(_HEADER, agent_instance_id=self._UUID)

        monkeypatch.setattr(I, "request", fake_request)

    def test_role_user_keeps_only_user_messages_in_json(self, monkeypatch, capsys):
        self._patch_request(monkeypatch)
        rc = I._cmd_get(self._args(json=True, role="user", all_messages=True), "key")
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        senders = {m["sender_type"] for m in payload["messages"]}
        assert senders == {"USER"}
        assert len(payload["messages"]) == 2

    def test_role_agent_keeps_only_agent_messages_in_json(self, monkeypatch, capsys):
        self._patch_request(monkeypatch)
        rc = I._cmd_get(self._args(json=True, role="agent", all_messages=True), "key")
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        senders = {m["sender_type"] for m in payload["messages"]}
        assert senders == {"AGENT"}

    def test_no_role_returns_every_sender(self, monkeypatch, capsys):
        self._patch_request(monkeypatch)
        rc = I._cmd_get(self._args(json=True, all_messages=True), "key")
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert len(payload["messages"]) == len(_sample_messages())

    def test_text_note_warns_when_limit_precedes_filter(self, monkeypatch, capsys):
        # Without --all, the pre-filter --limit gotcha is surfaced.
        self._patch_request(monkeypatch)
        I._cmd_get(self._args(role="user", all_messages=False), "key")
        out = capsys.readouterr().out
        assert "user messages only" in out
        assert "--all" in out

    def test_all_suppresses_the_limit_note(self, monkeypatch, capsys):
        self._patch_request(monkeypatch)
        I._cmd_get(self._args(role="user", all_messages=True), "key")
        assert "--limit counts all senders" not in capsys.readouterr().out


class TestBuildSpawnMetadata:
    """`session start` metadata mirrors the web's toSpawnMetadata per agent."""

    def _args(self, **over):
        base = {
            "model": None,
            "effort": None,
            "permission_mode": None,
            "opencode_mode": None,
            "name": None,
        }
        base.update(over)
        return types.SimpleNamespace(**base)

    def test_claude_effort_dual_writes_enable_thinking(self):
        meta = I._validate_and_build_metadata(
            self._args(
                model="claude-sonnet-5",
                effort="high",
                permission_mode="default",
                name="demo",
            ),
            "claude",
        )
        assert meta == {
            "name": "demo",
            "model": "claude-sonnet-5",
            "thinking_effort": "high",
            "enable_thinking": True,
            "permission_mode": "default",
        }

    def test_claude_effort_off_sets_enable_thinking_false(self):
        meta = I._validate_and_build_metadata(self._args(effort="off"), "claude")
        assert meta["thinking_effort"] == "off"
        assert meta["enable_thinking"] is False

    def test_codex_uses_reasoning_effort_key(self):
        meta = I._validate_and_build_metadata(
            self._args(model="gpt-5.5", effort="medium", permission_mode="default"),
            "codex",
        )
        assert meta == {
            "model": "gpt-5.5",
            "reasoning_effort": "medium",
            "permission_mode": "default",
        }

    def test_opencode_default_model_dropped_mode_mapped(self):
        meta = I._validate_and_build_metadata(
            self._args(model="default", opencode_mode="plan"), "opencode"
        )
        assert meta == {"agent_mode": "plan"}

    def test_opencode_explicit_model_kept(self):
        meta = I._validate_and_build_metadata(
            self._args(model="opencode/big-pickle"), "opencode"
        )
        assert meta == {"model": "opencode/big-pickle"}

    def test_generic_acp_passes_model_and_permission(self):
        meta = I._validate_and_build_metadata(
            self._args(model="composer-2.5", permission_mode="plan"), "cursor"
        )
        assert meta == {"model": "composer-2.5", "permission_mode": "plan"}

    def test_invalid_effort_exits(self):
        import pytest

        with pytest.raises(SystemExit) as exc:
            I._validate_and_build_metadata(self._args(effort="bogus"), "claude")
        assert exc.value.code == 2

    def test_invalid_permission_mode_exits(self):
        import pytest

        with pytest.raises(SystemExit) as exc:
            I._validate_and_build_metadata(
                self._args(permission_mode="acceptEdits"), "codex"
            )
        assert exc.value.code == 2


class TestSessionStart:
    def _args(self, **over):
        base = {
            "json": True,
            "list_machines": False,
            "list_models": False,
            "machine": "Laptop",
            "dir": "/tmp/proj",
            "agent": "claude",
            "model": "claude-sonnet-5",
            "effort": "high",
            "permission_mode": "default",
            "opencode_mode": None,
            "name": "demo",
            "prompt": "do it",
            "task": None,
            "wait": False,
            "wait_timeout": 60.0,
            "allow_offline": False,
        }
        base.update(over)
        return types.SimpleNamespace(**base)

    def _fake_request(self, calls, *, machines=None):
        machines = machines or [
            {
                "machine_id": "mach-1234",
                "display_name": "Laptop",
                "hostname": "host",
                "last_heartbeat_at": _iso_ago(5),  # fresh -> online
            }
        ]

        def fake_request(args, api_key, method, endpoint, *, params=None, json=None):
            calls.append((method, endpoint, json))
            if method == "GET" and endpoint == "/api/v1/machines":
                return {"machines": machines}
            if method == "POST" and endpoint.endswith("/spawn-requests"):
                return {"request_id": "req-1", "agent_instance_id": "inst-1"}
            if method == "GET" and endpoint.startswith("/api/v1/agent-instances/"):
                return {"status": "ACTIVE"}
            return None

        return fake_request

    def test_posts_spawn_request_with_metadata(self, monkeypatch, capsys):
        calls = []
        monkeypatch.setattr(I, "request", self._fake_request(calls))
        rc = I._cmd_start(self._args(), "key")
        assert rc == 0
        post = [c for c in calls if c[0] == "POST"][0]
        assert post[1] == "/api/v1/machines/mach-1234/spawn-requests"
        assert post[2]["directory"] == "/tmp/proj"
        assert post[2]["agent"] == "claude"
        assert post[2]["prompt"] == "do it"
        assert post[2]["metadata"]["model"] == "claude-sonnet-5"
        assert post[2]["metadata"]["thinking_effort"] == "high"
        assert post[2]["metadata"]["name"] == "demo"
        out = json.loads(capsys.readouterr().out)
        assert out["agent_instance_id"] == "inst-1"
        assert out["machine_id"] == "mach-1234"

    def test_blank_prompt_omitted(self, monkeypatch):
        calls = []
        monkeypatch.setattr(I, "request", self._fake_request(calls))
        I._cmd_start(self._args(prompt="   "), "key")
        post = [c for c in calls if c[0] == "POST"][0]
        assert "prompt" not in post[2]

    def test_task_link_patches_instance(self, monkeypatch):
        calls = []
        monkeypatch.setattr(I, "request", self._fake_request(calls))
        I._cmd_start(self._args(task="task-uuid"), "key")
        patch = [c for c in calls if c[0] == "PATCH"][0]
        assert patch[1] == "/api/v1/agent-instances/inst-1"
        assert patch[2] == {"task_id": "task-uuid"}

    def test_missing_dir_returns_2(self, monkeypatch):
        def boom(*a, **k):
            raise AssertionError("request() must not run without --dir")

        monkeypatch.setattr(I, "request", boom)
        assert I._cmd_start(self._args(dir=None), "key") == 2

    def test_no_machine_and_no_local_daemon_exits(self, monkeypatch):
        import pytest

        calls = []
        monkeypatch.setattr(I, "request", self._fake_request(calls))
        monkeypatch.setattr(I, "_local_machine_id", lambda args: None)
        with pytest.raises(SystemExit) as exc:
            I._cmd_start(self._args(machine=None), "key")
        assert exc.value.code == 1

    def test_defaults_to_local_machine(self, monkeypatch):
        calls = []
        monkeypatch.setattr(I, "request", self._fake_request(calls))
        monkeypatch.setattr(I, "_local_machine_id", lambda args: "mach-1234")
        rc = I._cmd_start(self._args(machine=None), "key")
        assert rc == 0
        post = [c for c in calls if c[0] == "POST"][0]
        assert post[1] == "/api/v1/machines/mach-1234/spawn-requests"

    def test_offline_machine_refused_by_default(self, monkeypatch, capsys):
        calls = []
        machines = [
            {
                "machine_id": "mach-1234",
                "display_name": "Laptop",
                "hostname": "host",
                "last_heartbeat_at": _iso_ago(600),  # stale -> offline
            }
        ]
        monkeypatch.setattr(I, "request", self._fake_request(calls, machines=machines))
        rc = I._cmd_start(self._args(), "key")
        assert rc == 1
        assert not any(c[0] == "POST" for c in calls)
        assert "offline" in capsys.readouterr().err

    def test_offline_machine_allow_offline_queues(self, monkeypatch, capsys):
        calls = []
        machines = [
            {
                "machine_id": "mach-1234",
                "display_name": "Laptop",
                "hostname": "host",
                "last_heartbeat_at": _iso_ago(600),  # stale -> offline
            }
        ]
        monkeypatch.setattr(I, "request", self._fake_request(calls, machines=machines))
        rc = I._cmd_start(self._args(json=False, allow_offline=True), "key")
        assert rc == 0
        assert any(c[0] == "POST" for c in calls)
        assert "Queued" in capsys.readouterr().out

    def test_machine_resolved_by_name_substring(self, monkeypatch):
        calls = []
        monkeypatch.setattr(I, "request", self._fake_request(calls))
        I._cmd_start(self._args(machine="lap"), "key")
        post = [c for c in calls if c[0] == "POST"][0]
        assert post[1] == "/api/v1/machines/mach-1234/spawn-requests"

    def test_ambiguous_machine_exits(self, monkeypatch):
        import pytest

        calls = []
        machines = [
            {"machine_id": "m-1", "display_name": "Laptop A", "hostname": "a"},
            {"machine_id": "m-2", "display_name": "Laptop B", "hostname": "b"},
        ]
        monkeypatch.setattr(I, "request", self._fake_request(calls, machines=machines))
        with pytest.raises(SystemExit) as exc:
            I._cmd_start(self._args(machine="laptop"), "key")
        assert exc.value.code == 1

    def test_list_machines_short_circuits(self, monkeypatch, capsys):
        calls = []
        monkeypatch.setattr(I, "request", self._fake_request(calls))
        rc = I._cmd_start(self._args(list_machines=True), "key")
        assert rc == 0
        # Only the machines GET runs — no spawn.
        assert all(c[0] == "GET" for c in calls)
        assert not any("spawn-requests" in c[1] for c in calls)

    def test_wait_polls_until_not_starting(self, monkeypatch, capsys):
        calls = []
        monkeypatch.setattr(I, "request", self._fake_request(calls))
        monkeypatch.setattr(I, "_wait_for_status", lambda *a, **k: "ACTIVE")
        out_rc = I._cmd_start(self._args(wait=True), "key")
        assert out_rc == 0
        assert json.loads(capsys.readouterr().out)["status"] == "ACTIVE"


class TestRateLimitedLsParams:
    def _args(self, **over):
        base = {"rate_limited": True, "limit": 50, "json": True, "active": False}
        base.update(over)
        return types.SimpleNamespace(**base)

    def _capture(self, monkeypatch):
        captured: dict = {}

        def fake_request(args, api_key, method, endpoint, *, params=None, json=None):
            captured.update(params or {})
            return {"items": [], "total": 0}

        monkeypatch.setattr(I, "request", fake_request)
        return captured

    def test_ls_forwards_caller_instance_id_from_env(self, monkeypatch):
        captured = self._capture(monkeypatch)
        monkeypatch.setenv("VICOA_AGENT_INSTANCE_ID", "sess-123")
        I._cmd_ls(self._args(), "key")
        assert captured.get("rate_limited_only") == "true"
        assert captured.get("caller_instance_id") == "sess-123"

    def test_ls_omits_caller_when_env_absent(self, monkeypatch):
        captured = self._capture(monkeypatch)
        monkeypatch.delenv("VICOA_AGENT_INSTANCE_ID", raising=False)
        I._cmd_ls(self._args(), "key")
        assert captured.get("rate_limited_only") == "true"
        assert "caller_instance_id" not in captured

    def test_ls_without_rate_limited_sends_neither(self, monkeypatch):
        captured = self._capture(monkeypatch)
        monkeypatch.setenv("VICOA_AGENT_INSTANCE_ID", "sess-123")
        I._cmd_ls(self._args(rate_limited=False), "key")
        assert "rate_limited_only" not in captured
        assert "caller_instance_id" not in captured
