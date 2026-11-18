"""Unit tests for ``vicoa task comment`` / ``vicoa task comments``.

The endpoints themselves are covered in ``servers/tests/test_task_endpoints.py``;
what is only reachable here is the request the CLI *builds* — the stdin body, the
``--reply-to`` mapping, and the ``VICOA_AGENT_INSTANCE_ID`` pickup that decides
whether a comment is signed by the agent or by the human whose key it used.
"""

import io
import json
import types

import pytest

from vicoa.commands import task as T


def _args(**over):
    """A namespace shaped like the one argparse hands the handler."""
    base = {"task_id": "t-1", "json": False, "api_key": "k", "base_url": None}
    base.update(over)
    return types.SimpleNamespace(**base)


def _capture_request(monkeypatch, reply=None):
    """Swap out the HTTP layer and record what the handler tried to send."""
    sent = {}

    def fake_request(args, api_key, method, endpoint, *, params=None, json=None):
        sent.update(method=method, endpoint=endpoint, json=json)
        return reply if reply is not None else {"comments": [], "activity": []}

    monkeypatch.setattr(T, "_request", fake_request)
    return sent


def _comment(cid, body, parent=None, created_at="2026-09-09T10:00:00Z", author=None):
    return {
        "id": cid,
        "parent_comment_id": parent,
        "author": author or {"type": "user", "name": "Nick"},
        "body": body,
        "reactions": [],
        "created_at": created_at,
        "edited_at": None,
        "deleted_at": None,
    }


class TestPostingAComment:
    def test_posts_the_body(self, monkeypatch):
        sent = _capture_request(
            monkeypatch, {"comments": [_comment("c1", "all green")]}
        )
        assert T._cmd_comment(_args(body="all green", reply_to=None), "k") == 0
        assert sent["method"] == "POST"
        assert sent["endpoint"] == "/api/v1/tasks/t-1/comments"
        assert sent["json"]["body"] == "all green"
        assert "parent_comment_id" not in sent["json"]

    def test_dash_reads_the_body_from_stdin(self, monkeypatch):
        """So an agent can pipe a multi-line markdown report in rather than
        fighting its own shell over quoting and newlines."""
        sent = _capture_request(monkeypatch)
        monkeypatch.setattr("sys.stdin", io.StringIO("## Done\n\n- fixed the flake\n"))
        assert T._cmd_comment(_args(body="-", reply_to=None), "k") == 0
        assert sent["json"]["body"] == "## Done\n\n- fixed the flake"

    def test_empty_body_is_refused_without_a_request(self, monkeypatch):
        sent = _capture_request(monkeypatch)
        assert T._cmd_comment(_args(body="   ", reply_to=None), "k") == 2
        assert sent == {}

    def test_reply_to_becomes_the_parent(self, monkeypatch):
        sent = _capture_request(monkeypatch)
        T._cmd_comment(_args(body="because", reply_to="c-root"), "k")
        assert sent["json"]["parent_comment_id"] == "c-root"

    def test_inside_a_session_it_names_the_session(self, monkeypatch):
        """The one thing that lets a comment be signed by the agent instead of
        by the human whose API key it is."""
        sent = _capture_request(monkeypatch)
        monkeypatch.setenv("VICOA_AGENT_INSTANCE_ID", "sess-9")
        T._cmd_comment(_args(body="done", reply_to=None), "k")
        assert sent["json"]["agent_instance_id"] == "sess-9"

    def test_outside_a_session_it_stays_silent(self, monkeypatch):
        sent = _capture_request(monkeypatch)
        monkeypatch.delenv("VICOA_AGENT_INSTANCE_ID", raising=False)
        T._cmd_comment(_args(body="done", reply_to=None), "k")
        assert "agent_instance_id" not in sent["json"]

    def test_reports_the_comment_it_just_posted(self, monkeypatch, capsys):
        """Not `comments[-1]`: the timeline comes back in thread order, so a
        reply is spliced under its root rather than appended at the end."""
        _capture_request(
            monkeypatch,
            {
                "comments": [
                    _comment("root", "why?", created_at="2026-09-09T10:00:00Z"),
                    _comment(
                        "new",
                        "because",
                        parent="root",
                        created_at="2026-09-09T11:00:00Z",
                    ),
                    _comment("later", "unrelated", created_at="2026-09-09T10:30:00Z"),
                ]
            },
        )
        T._cmd_comment(_args(body="because", reply_to="root"), "k")
        assert "Posted comment new" in capsys.readouterr().out

    def test_json_passes_the_timeline_straight_through(self, monkeypatch, capsys):
        payload = {"comments": [_comment("c1", "hi")], "activity": []}
        _capture_request(monkeypatch, payload)
        T._cmd_comment(_args(body="hi", reply_to=None, json=True), "k")
        assert json.loads(capsys.readouterr().out) == payload


class TestReadingTheThread:
    def test_replies_are_indented_under_their_root(self, monkeypatch, capsys):
        _capture_request(
            monkeypatch,
            {
                "comments": [
                    _comment("root", "why?"),
                    _comment("r1", "because", parent="root"),
                ],
                "activity": [],
            },
        )
        T._cmd_comments(_args(activity=False), "k")
        lines = capsys.readouterr().out.splitlines()
        assert any(line == "  why?" for line in lines)
        assert any(line == "      because" for line in lines)

    def test_an_agent_author_is_labelled(self, monkeypatch, capsys):
        """In a terminal "Claude" and "Nick" look identical without the tag —
        the web has an avatar doing that job."""
        _capture_request(
            monkeypatch,
            {
                "comments": [
                    _comment(
                        "c1",
                        "shipped",
                        author={"type": "agent", "name": "Reviewer"},
                    )
                ],
                "activity": [],
            },
        )
        T._cmd_comments(_args(activity=False), "k")
        assert "Reviewer (agent)" in capsys.readouterr().out

    def test_a_deleted_comment_shows_a_tombstone(self, monkeypatch, capsys):
        comment = _comment("c1", None)
        comment["deleted_at"] = "2026-09-09T12:00:00Z"
        _capture_request(monkeypatch, {"comments": [comment], "activity": []})
        T._cmd_comments(_args(activity=False), "k")
        assert "(deleted)" in capsys.readouterr().out

    def test_activity_is_opt_in(self, monkeypatch, capsys):
        timeline = {
            "comments": [],
            "activity": [
                {
                    "actor": {"type": "user", "name": "Nick"},
                    "action": "status_changed",
                    "details": {"from": "todo", "to": "done"},
                    "created_at": "2026-09-09T10:00:00Z",
                }
            ],
        }
        _capture_request(monkeypatch, timeline)
        T._cmd_comments(_args(activity=False), "k")
        assert "status changed" not in capsys.readouterr().out

        _capture_request(monkeypatch, timeline)
        T._cmd_comments(_args(activity=True), "k")
        out = capsys.readouterr().out
        assert "status changed (todo -> done)" in out


class TestTaskTable:
    def test_shows_the_identifier_when_there_is_one(self, capsys):
        T._print_task_table(
            [
                {"id": "aaaabbbbcccc", "identifier": "VIC-42", "title": "x"},
                {"id": "ddddeeeeffff", "identifier": None, "title": "y"},
            ]
        )
        out = capsys.readouterr().out
        assert "VIC-42" in out
        # A task predating the backfill renders without one rather than with a
        # placeholder that would look like a real reference.
        assert "—" in out


@pytest.mark.parametrize(
    "principal,expected",
    [
        (None, "someone"),
        ({"type": "user", "name": "Nick"}, "Nick"),
        ({"type": "agent", "name": "Reviewer"}, "Reviewer (agent)"),
        ({"type": "system", "name": None}, "Unknown"),
    ],
)
def test_principal_name(principal, expected):
    assert T._principal_name(principal) == expected


class TestAsking:
    """``--ask [--to …]``: the comment is a question to one person
    (plans/todos/task-questions-waiting-on.md)."""

    def _asked(self, cid="q1", addressee="Ada"):
        comment = _comment(cid, "A or B?", author={"type": "agent", "name": "Claude"})
        comment["question"] = {
            "addressee": {"type": "user", "name": addressee},
            "closed_at": None,
            "closed_reason": None,
        }
        return {"comments": [comment]}

    def test_ask_without_to_lets_the_server_pick(self, monkeypatch, capsys):
        sent = _capture_request(monkeypatch, self._asked(addressee="Nick"))
        code = T._cmd_comment(_args(body="A or B?", reply_to=None, ask=True), "k")
        assert code == 0
        assert sent["json"]["ask"] == {}
        assert "Asked Nick in comment q1" in capsys.readouterr().out

    def test_to_names_the_person(self, monkeypatch):
        sent = _capture_request(monkeypatch, self._asked())
        T._cmd_comment(
            _args(body="A or B?", reply_to=None, ask=True, to="ada@example.com"), "k"
        )
        assert sent["json"]["ask"] == {"to": "ada@example.com"}

    def test_to_without_ask_is_refused(self, monkeypatch):
        sent = _capture_request(monkeypatch)
        code = T._cmd_comment(_args(body="hi", reply_to=None, to="Ada"), "k")
        assert code == 2
        assert sent == {}

    def test_a_plain_comment_sends_no_ask(self, monkeypatch):
        sent = _capture_request(monkeypatch, {"comments": [_comment("c1", "hi")]})
        T._cmd_comment(_args(body="hi", reply_to=None), "k")
        assert "ask" not in sent["json"]

    def test_an_older_server_that_ignores_ask_says_so(self, monkeypatch, capsys):
        _capture_request(monkeypatch, {"comments": [_comment("c1", "A or B?")]})
        code = T._cmd_comment(_args(body="A or B?", reply_to=None, ask=True), "k")
        assert code == 1
        assert "did not record it as a question" in capsys.readouterr().err

    def test_the_thread_shows_whom_a_question_waits_on(self, monkeypatch, capsys):
        _capture_request(monkeypatch, {**self._asked(), "activity": []})
        T._cmd_comments(_args(activity=False), "k")
        assert "  question to Ada (waiting)" in capsys.readouterr().out.splitlines()


class TestWaitingOn:
    def test_ls_sends_waiting_on_and_keeps_only_waiting_tasks(
        self, monkeypatch, capsys
    ):
        sent = {}
        waiting = {
            "id": "t1",
            "title": "Pick a name",
            "status": "blocked",
            "priority": "none",
            "labels": [],
            "open_questions": [{"comment_id": "q1"}],
        }
        # An older server ignores the filter and returns the whole backlog.
        unrelated = {**waiting, "id": "t2", "title": "Other", "open_questions": []}

        def fake_request(args, api_key, method, endpoint, *, params=None, json=None):
            sent.update(params=params)
            return [waiting, unrelated]

        monkeypatch.setattr(T, "_request", fake_request)
        args = _args(
            project=None,
            status=None,
            priority=None,
            label=None,
            assignee=None,
            waiting_on="me",
            json=True,
        )
        assert T._cmd_ls(args, "k") == 0
        assert sent["params"] == {"waiting_on": "me"}
        assert [t["id"] for t in json.loads(capsys.readouterr().out)] == ["t1"]

    def test_get_prints_open_questions(self, capsys):
        T._print_task_detail(
            {
                "id": "t1",
                "title": "Pick a name",
                "status": "blocked",
                "priority": "none",
                "labels": [],
                "open_questions": [
                    {
                        "comment_id": "q1",
                        "addressee": {"type": "user", "name": "Ada"},
                        "asked_by": {"type": "agent", "name": "Claude"},
                        "asked_at": "2026-11-18T10:00:00Z",
                    }
                ],
            }
        )
        out = capsys.readouterr().out
        assert (
            "waiting on:  Ada, asked by Claude (agent) at 2026-11-18T10:00:00Z "
            "(comment q1)" in out
        )
