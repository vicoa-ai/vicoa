"""Sessions agents keep on this machine (``vicoa.local_sessions``, issue #235).

The Claude source is exercised against transcripts written to a throwaway
``CLAUDE_CONFIG_DIR``; the Codex source against canned app-server answers, so
no ``codex`` binary is needed. The daemon RPCs and the CLI's ``--resume``
bridge are covered with fake server clients.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from vicoa import local_sessions
from vicoa.local_sessions import claude, codex
from vicoa.local_sessions.types import (
    HistoryMessage,
    LocalSession,
    LocalSessionError,
    Transcript,
)
from vicoa.machine_daemon import MachineDaemon


# ---------------------------------------------------------------------------
# Claude
# ---------------------------------------------------------------------------


def _entry(
    kind: str, content: Any, *, at: str, cwd: str, entrypoint: str = "cli", **extra: Any
) -> dict:
    return {
        "type": kind,
        "entrypoint": entrypoint,
        "cwd": cwd,
        "gitBranch": "main",
        "uuid": str(uuid4()),
        "timestamp": at,
        "message": {"role": kind, "content": content},
        **extra,
    }


def _write_transcript(
    config: Path, cwd: str, entries: list[dict], session_id: str | None = None
) -> str:
    session_id = session_id or str(uuid4())
    project = config / "projects" / cwd.replace("/", "-")
    project.mkdir(parents=True, exist_ok=True)
    with (project / f"{session_id}.jsonl").open("w") as handle:
        for entry in entries:
            handle.write(json.dumps(entry) + "\n")
    return session_id


@pytest.fixture
def claude_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    config = tmp_path / "claude-config"
    config.mkdir()
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))
    return config


@pytest.fixture
def repo(tmp_path: Path) -> str:
    path = tmp_path / "repo"
    path.mkdir()
    return str(path)


def _conversation(cwd: str, entrypoint: str = "cli") -> list[dict]:
    at = "2026-11-14T09:0{}:00.000Z"
    return [
        {"type": "session-owner", "owner": "someone"},
        # Newer transcripts open with bookkeeping that can run past 100 KB.
        {"type": "queue-operation", "content": "x" * 80_000},
        _entry(
            "user",
            "Cap the retries <system-reminder>noise</system-reminder>",
            at=at.format(0),
            cwd=cwd,
            entrypoint=entrypoint,
        ),
        _entry(
            "assistant",
            [
                {"type": "thinking", "thinking": "Look at the loop first."},
                {"type": "text", "text": "Capping at 5."},
                {
                    "type": "tool_use",
                    "id": "t1",
                    "name": "Read",
                    "input": {"file_path": "upload/retry.ts"},
                },
            ],
            at=at.format(1),
            cwd=cwd,
            entrypoint=entrypoint,
        ),
        _entry(
            "user",
            [{"type": "tool_result", "tool_use_id": "t1", "content": "ok"}],
            at=at.format(2),
            cwd=cwd,
            entrypoint=entrypoint,
        ),
        _entry(
            "user",
            "injected",
            at=at.format(3),
            cwd=cwd,
            entrypoint=entrypoint,
            isMeta=True,
        ),
        _entry(
            "assistant",
            [{"type": "text", "text": "side chain"}],
            at=at.format(4),
            cwd=cwd,
            entrypoint=entrypoint,
            isSidechain=True,
        ),
        _entry(
            "user",
            "<command-name>/model</command-name>",
            at=at.format(5),
            cwd=cwd,
            entrypoint=entrypoint,
        ),
        _entry(
            "user",
            "<local-command-stdout>Set model to Opus</local-command-stdout>",
            at=at.format(6),
            cwd=cwd,
            entrypoint=entrypoint,
        ),
        _entry(
            "user",
            "summary of earlier turns",
            at=at.format(7),
            cwd=cwd,
            entrypoint=entrypoint,
            isCompactSummary=True,
        ),
        _entry(
            "user",
            "Also log the failure",
            at=at.format(8),
            cwd=cwd,
            entrypoint=entrypoint,
        ),
    ]


class TestClaudeSource:
    def test_reads_the_head_past_a_long_first_line(self, claude_home, repo):
        session_id = _write_transcript(
            claude_home, repo, _conversation(repo, "claude-desktop")
        )
        path = claude.find_transcript(session_id)
        assert path is not None
        head = claude._read_head(path)
        assert head.entrypoint == "claude-desktop"
        assert head.cwd == repo
        assert head.git_branch == "main"
        assert head.first_prompt == "Cap the retries"

    def test_lists_interactive_sessions_and_hides_scripted_ones(
        self, claude_home, repo
    ):
        mine = _write_transcript(claude_home, repo, _conversation(repo, "cli"))
        _write_transcript(claude_home, repo, _conversation(repo, "sdk-py"))

        listed = claude.list_sessions()
        assert [s.native_id for s in listed] == [mine]
        session = listed[0]
        assert session.source == "cli"
        assert session.source_label == "Terminal"
        assert session.cwd == repo
        assert session.title  # the SDK's summary or, failing that, the first prompt
        assert not session.scripted

        everything = claude.list_sessions(include_scripted=True)
        assert len(everything) == 2
        assert any(s.scripted and s.source == "sdk-py" for s in everything)

    def test_directory_filter(self, claude_home, repo, tmp_path):
        other = tmp_path / "elsewhere"
        other.mkdir()
        inside = _write_transcript(claude_home, repo, _conversation(repo))
        _write_transcript(claude_home, str(other), _conversation(str(other)))
        assert [s.native_id for s in claude.list_sessions(directory=repo)] == [inside]

    def test_transcript_follows_the_terminal_wrapper_rules(self, claude_home, repo):
        session_id = _write_transcript(claude_home, repo, _conversation(repo))
        transcript = claude.read_transcript(session_id)
        rows = [(m.sender, m.content, bool(m.metadata)) for m in transcript.messages]
        assert rows[0] == ("user", "Cap the retries", False)
        assert rows[1] == ("agent", "Look at the loop first.", True)  # thinking card
        assert rows[2][0] == "agent" and rows[2][1].startswith("Capping at 5.")
        assert "Read" in rows[2][1]
        # tool result, meta, side chain, command echo and compact summary are gone;
        # the slash command's output stays, on the agent's side.
        assert (
            "agent",
            "<local-command-stdout>Set model to Opus</local-command-stdout>",
            False,
        ) in rows
        assert rows[-1] == ("user", "Also log the failure", False)
        assert len(rows) == 5
        times = [m.created_at for m in transcript.messages]
        assert times == sorted(times)

    def test_unknown_session(self, claude_home):
        with pytest.raises(local_sessions.LocalSessionNotFound):
            claude.read_transcript(str(uuid4()))


# ---------------------------------------------------------------------------
# Codex
# ---------------------------------------------------------------------------


class TestCodexConversion:
    def test_items_become_rows_in_order(self):
        turns = [
            {
                "startedAt": 1_794_668_660,
                "completedAt": 1_794_668_670,
                "status": "completed",
                "items": [
                    {
                        "type": "userMessage",
                        "content": [
                            {"type": "text", "text": "Why is the deploy stale?"}
                        ],
                    },
                    {
                        "type": "reasoning",
                        "summary": ["Check the image tag."],
                        "content": [],
                    },
                    {"type": "agentMessage", "text": "The tag is pinned."},
                ],
            },
            {
                "startedAt": 1_794_668_700_000,  # milliseconds on this field
                "completedAt": None,
                "status": "failed",
                "error": {"message": "stream disconnected"},
                "items": [
                    {
                        "type": "userMessage",
                        "content": [{"type": "localImage", "path": "/tmp/a.png"}],
                    }
                ],
            },
        ]
        rows = codex.convert_turns(turns, fallback_at=None)
        assert [(r.sender, r.content) for r in rows] == [
            ("user", "Why is the deploy stale?"),
            ("agent", "Reasoning:\nCheck the image tag."),
            ("agent", "The tag is pinned."),
            ("user", "[Image]"),
            ("agent", "This turn failed: stream disconnected"),
        ]
        assert rows[1].metadata == {"thinking": {"source": "codex"}}
        assert rows[0].created_at == 1_794_668_660
        assert rows[2].created_at == 1_794_668_670
        assert rows[3].created_at == 1_794_668_700
        assert [r.created_at for r in rows] == sorted(r.created_at for r in rows)

    def test_session_reads_the_originator_from_the_rollout(self, tmp_path):
        rollout = tmp_path / "rollout.jsonl"
        rollout.write_text(
            json.dumps(
                {"type": "session_meta", "payload": {"originator": "Codex Desktop"}}
            )
            + "\n"
        )
        session = codex._session_from(
            {
                "id": "t1",
                "path": str(rollout),
                "cwd": "/repo",
                "preview": "Fix it\nmore",
                "updatedAt": 1_794_668_700,
                "source": "vscode",
            }
        )
        assert session.source == "Codex Desktop"
        assert session.source_label == "Codex desktop"
        assert session.title == "Fix it"
        assert not session.scripted

    def test_classification(self):
        assert codex.is_scripted("codex_exec", None)
        assert codex.is_scripted(None, "exec")
        assert codex.is_vicoa("vicoa")
        assert codex.is_vicoa("vicoa-frame-probe")
        assert not codex.is_vicoa("codex_cli_rs")


class _FakeTransport:
    def __init__(self, pages: list[dict]):
        self.pages = pages
        self.calls: list[tuple[str, dict]] = []

    async def send_request(
        self, method: str, params: dict, *, timeout: float | None = None
    ) -> dict:
        self.calls.append((method, params))
        return self.pages.pop(0)


def _thread(
    thread_id: str, cwd: str, rollout: Path, originator: str, **extra: Any
) -> dict:
    rollout.write_text(
        json.dumps({"type": "session_meta", "payload": {"originator": originator}})
        + "\n"
    )
    return {
        "id": thread_id,
        "cwd": cwd,
        "path": str(rollout),
        "preview": thread_id,
        "updatedAt": 1_794_668_700,
        **extra,
    }


def test_codex_list_filters_and_pages(tmp_path, monkeypatch):
    pages = [
        {
            "data": [
                _thread("cli", "/repo", tmp_path / "a.jsonl", "codex_cli_rs"),
                _thread("ours", "/repo", tmp_path / "b.jsonl", "vicoa"),
                _thread("script", "/repo", tmp_path / "c.jsonl", "codex_exec"),
                _thread(
                    "ephemeral",
                    "/repo",
                    tmp_path / "d.jsonl",
                    "codex_cli_rs",
                    ephemeral=True,
                ),
            ],
            "nextCursor": "page-2",
        },
        {
            "data": [
                _thread("desktop", "/other", tmp_path / "e.jsonl", "Codex Desktop")
            ],
            "nextCursor": None,
        },
    ]
    transport = _FakeTransport(pages)

    async def fake_app_server(work):
        return await work(transport)

    monkeypatch.setattr(codex, "_with_app_server", fake_app_server)
    listed = codex.list_sessions(limit=10)
    assert [s.native_id for s in listed] == ["cli", "desktop"]
    assert transport.calls[1] == ("thread/list", {"limit": 100, "cursor": "page-2"})


# ---------------------------------------------------------------------------
# Merging, linking and the import payload
# ---------------------------------------------------------------------------


def _session(
    agent: str, native_id: str, updated: float, cwd: str | None = "/repo"
) -> LocalSession:
    return LocalSession(
        agent=agent, native_id=native_id, title=native_id, cwd=cwd, updated_at=updated
    )


class _FakeSource:
    LABEL = "Fake agent"

    def __init__(
        self,
        sessions: list[LocalSession] | None = None,
        error: str | None = None,
        transcript: Transcript | None = None,
    ):
        self.sessions = sessions or []
        self.error = error
        self.transcript = transcript

    def list_sessions(self, *, directory=None, limit=50, include_scripted=False):
        if self.error:
            raise LocalSessionError(self.error)
        return self.sessions[:limit]

    def read_transcript(self, native_id):
        assert self.transcript is not None
        return self.transcript

    def has_session(self, native_id):
        known = {s.native_id for s in self.sessions}
        if self.transcript is not None:
            known.add(self.transcript.session.native_id)
        return native_id in known


class _MustNotBeAsked(_FakeSource):
    def has_session(self, native_id):
        raise AssertionError("asked after an earlier agent already claimed the id")


class _FakeClient:
    def __init__(self, matches: dict[str, str] | None = None):
        self.matches = matches or {}
        self.imported: list[dict] = []

    def lookup_native_sessions(self, *, machine_id, agent, native_session_ids):
        return {i: self.matches[i] for i in native_session_ids if i in self.matches}

    def import_session(self, payload, timeout=None):
        self.imported.append(payload)
        return {
            "agent_instance_id": "vicoa-1",
            "created": True,
            "message_count": len(payload["messages"]),
        }

    def close(self):
        pass


def test_list_merges_sources_newest_first_and_reports_failures(monkeypatch):
    monkeypatch.setitem(
        local_sessions.SOURCES,
        "claude",
        _FakeSource([_session("claude", "c1", 30), _session("claude", "c2", 10)]),
    )
    monkeypatch.setitem(
        local_sessions.SOURCES,
        "codex",
        _FakeSource(error="Codex isn't installed on this machine"),
    )
    result = local_sessions.list_local_sessions(limit=1)
    assert [s["native_id"] for s in result["sessions"]] == ["c1"]
    assert result["has_more"] is True
    assert result["errors"] == {"codex": "Codex isn't installed on this machine"}
    second = local_sessions.list_local_sessions(limit=1, offset=1)
    assert [s["native_id"] for s in second["sessions"]] == ["c2"]
    assert second["has_more"] is False


def test_mark_linked_sets_the_vicoa_session():
    sessions = [
        _session("claude", "c1", 1).to_wire(),
        _session("claude", "c2", 1).to_wire(),
    ]
    local_sessions.mark_linked(_FakeClient({"c1": "vicoa-c1"}), "machine-1", sessions)
    assert [s["vicoa_instance_id"] for s in sessions] == ["vicoa-c1", None]


def test_payload_trims_long_sessions_and_says_so(monkeypatch, tmp_path):
    monkeypatch.setattr(local_sessions, "MAX_IMPORTED_MESSAGES", 3)
    messages = [
        HistoryMessage("user" if i % 2 == 0 else "agent", f"m{i}", 1000.0 + i)
        for i in range(5)
    ]
    transcript = Transcript(
        session=_session("claude", "c1", 1, cwd=str(tmp_path)), messages=messages
    )
    payload = local_sessions.build_import_payload(
        transcript, machine_id="machine-1", home_dir="/home"
    )
    contents = [m["content"] for m in payload["messages"]]
    assert contents == [
        "3 earlier messages from this session weren't imported.",
        "m3",
        "m4",
    ]
    assert payload["machine_id"] == "machine-1"
    assert payload["project"] == str(tmp_path)
    assert payload["started_at"].startswith("1970-01-01T00:16:40")


def test_payload_carries_the_git_identity(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    transcript = Transcript(
        session=_session("codex", "t1", 1, cwd=str(tmp_path)), messages=[]
    )
    payload = local_sessions.build_import_payload(transcript, machine_id="m")
    assert Path(payload["repo_root"]).resolve() == tmp_path.resolve()


def test_payload_needs_a_folder():
    transcript = Transcript(session=_session("claude", "c1", 1, cwd=None), messages=[])
    with pytest.raises(LocalSessionError):
        local_sessions.build_import_payload(transcript, machine_id="m")


def test_import_posts_the_transcript(monkeypatch, tmp_path):
    transcript = Transcript(
        session=_session("claude", "c1", 1, cwd=str(tmp_path)),
        messages=[HistoryMessage("user", "hi", 1000.0)],
    )
    monkeypatch.setitem(
        local_sessions.SOURCES, "claude", _FakeSource(transcript=transcript)
    )
    client = _FakeClient()
    result = local_sessions.import_local_session(
        client, machine_id="m", agent="claude", native_id="c1"
    )
    assert result == {
        "agent": "claude",
        "agent_instance_id": "vicoa-1",
        "created": True,
        "message_count": 1,
        "title": "c1",
    }
    assert client.imported[0]["native_session_id"] == "c1"


def test_find_agent_asks_in_order_and_stops_at_the_first(monkeypatch, tmp_path):
    transcript = Transcript(
        session=_session("claude", "c1", 1, cwd=str(tmp_path)), messages=[]
    )
    monkeypatch.setitem(
        local_sessions.SOURCES, "claude", _FakeSource(transcript=transcript)
    )
    monkeypatch.setitem(local_sessions.SOURCES, "codex", _MustNotBeAsked())
    assert local_sessions.find_agent("c1") == "claude"


def test_find_agent_names_every_agent_it_looked_in(monkeypatch):
    monkeypatch.setitem(local_sessions.SOURCES, "claude", _FakeSource())
    monkeypatch.setitem(local_sessions.SOURCES, "codex", _FakeSource())
    with pytest.raises(local_sessions.LocalSessionNotFound) as caught:
        local_sessions.find_agent("nope")
    assert "looked in Fake agent, Fake agent" in str(caught.value)


def test_import_without_an_agent_finds_it(monkeypatch, tmp_path):
    transcript = Transcript(
        session=_session("codex", "t1", 1, cwd=str(tmp_path)), messages=[]
    )
    monkeypatch.setitem(local_sessions.SOURCES, "claude", _FakeSource())
    monkeypatch.setitem(
        local_sessions.SOURCES, "codex", _FakeSource(transcript=transcript)
    )
    result = local_sessions.import_local_session(
        _FakeClient(), machine_id="m", native_id="t1"
    )
    assert result["agent"] == "codex"


def test_agent_labels_come_from_the_sources():
    assert local_sessions.agent_label("claude") == "Claude Code"
    assert local_sessions.agent_label("codex") == "Codex"
    assert local_sessions.agent_label("unknown") == "unknown"


def test_unsupported_agent():
    with pytest.raises(LocalSessionError):
        local_sessions.import_local_session(
            _FakeClient(), machine_id="m", agent="cursor", native_id="x"
        )


# ---------------------------------------------------------------------------
# Daemon RPCs
# ---------------------------------------------------------------------------


@pytest.fixture
def daemon(monkeypatch) -> MachineDaemon:
    daemon = MachineDaemon(api_key="test-key", base_url="http://localhost:0")
    daemon.machine_id = "machine-1"
    monkeypatch.setattr(
        daemon, "_import_client", lambda: _FakeClient({"c1": "vicoa-c1"})
    )
    return daemon


def test_daemon_advertises_both_methods(daemon):
    methods = daemon._supported_rpc_methods()
    assert "list-local-sessions" in methods
    assert "import-local-session" in methods


def test_daemon_lists_and_marks(daemon, monkeypatch):
    monkeypatch.setitem(
        local_sessions.SOURCES,
        "claude",
        _FakeSource([_session("claude", "c1", 2), _session("claude", "c2", 1)]),
    )
    monkeypatch.setitem(local_sessions.SOURCES, "codex", _FakeSource())
    result = daemon._handle_rpc_request(
        {"method": "list-local-sessions", "params": {"limit": 10}}
    )
    assert [(s["native_id"], s["vicoa_instance_id"]) for s in result["sessions"]] == [
        ("c1", "vicoa-c1"),
        ("c2", None),
    ]


def test_daemon_import_validates_and_reports(daemon, monkeypatch, tmp_path):
    assert daemon._handle_rpc_request(
        {"method": "import-local-session", "params": {"agent": "claude"}}
    ) == {"error": "native_id is required"}
    transcript = Transcript(
        session=_session("claude", "c9", 1, cwd=str(tmp_path)), messages=[]
    )
    monkeypatch.setitem(
        local_sessions.SOURCES, "claude", _FakeSource(transcript=transcript)
    )
    result = daemon._handle_rpc_request(
        {
            "method": "import-local-session",
            "params": {"agent": "claude", "native_id": "c9"},
        }
    )
    assert result["agent_instance_id"] == "vicoa-1"
    assert result["created"] is True


def test_daemon_import_finds_the_agent_when_not_given(daemon, monkeypatch, tmp_path):
    transcript = Transcript(
        session=_session("codex", "t7", 1, cwd=str(tmp_path)), messages=[]
    )
    monkeypatch.setitem(local_sessions.SOURCES, "claude", _FakeSource())
    monkeypatch.setitem(
        local_sessions.SOURCES, "codex", _FakeSource(transcript=transcript)
    )
    result = daemon._handle_rpc_request(
        {"method": "import-local-session", "params": {"native_id": "t7"}}
    )
    assert result["agent"] == "codex"


def test_daemon_import_needs_a_registered_machine(daemon):
    daemon.machine_id = None
    result = daemon._handle_rpc_request(
        {
            "method": "import-local-session",
            "params": {"agent": "claude", "native_id": "c9"},
        }
    )
    assert result == {"error": "This machine isn't registered with Vicoa yet"}


# ---------------------------------------------------------------------------
# CLI: `vicoa --resume <native id>`
# ---------------------------------------------------------------------------


class _Args:
    base_url = "http://localhost:0"


def test_resume_resolves_an_already_linked_session(monkeypatch):
    from vicoa.commands import local_import

    monkeypatch.setattr(local_import, "_machine_id", lambda args: "machine-1")
    monkeypatch.setattr(
        local_import, "_client", lambda args, key: _FakeClient({"thread-1": "vicoa-9"})
    )
    assert local_import.resolve_resume_target(_Args(), "key", "thread-1", "codex") == (
        "codex",
        "vicoa-9",
    )


def test_resume_without_a_terminal_prints_the_import_command(
    monkeypatch, claude_home, repo, capsys
):
    from vicoa.commands import local_import

    session_id = _write_transcript(claude_home, repo, _conversation(repo))
    monkeypatch.setattr(local_import, "_machine_id", lambda args: "machine-1")
    monkeypatch.setattr(local_import, "_client", lambda args, key: _FakeClient())
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    assert (
        local_import.resolve_resume_target(_Args(), "key", session_id, "claude") is None
    )
    assert f"vicoa session import {session_id}" in capsys.readouterr().err


def test_resume_of_an_unknown_id(monkeypatch, claude_home, capsys):
    from vicoa.commands import local_import

    monkeypatch.setitem(local_sessions.SOURCES, "codex", _FakeSource())
    monkeypatch.setattr(local_import, "_machine_id", lambda args: "machine-1")
    monkeypatch.setattr(local_import, "_client", lambda args, key: _FakeClient())
    assert (
        local_import.resolve_resume_target(_Args(), "key", str(uuid4()), "claude")
        is None
    )
    err = capsys.readouterr().err
    # `vicoa --resume` runs Claude, so only Claude's sessions are looked in.
    assert "No session" in err and "(looked in Claude Code)" in err
