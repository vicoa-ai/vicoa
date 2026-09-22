"""Unit tests for ``vicoa session share`` / ``unshare``.

The endpoints are covered in ``servers/tests/test_share_endpoints.py``; what is
only reachable here is the request the CLI *builds* and what it prints: the
bare URL (so it composes into a ``gh pr`` command), the self-session default
from ``VICOA_AGENT_INSTANCE_ID``, link reuse vs ``--new``, and the refusal to
revoke without being told which link.
"""

import json
import types

import pytest

from vicoa.commands import instance as I

SESSION = "3f9c1a2b-0000-0000-0000-000000000000"


def _args(**over):
    base = {
        "json": False,
        "api_key": "k",
        "base_url": None,
        "session_id": SESSION,
        "audience": "public",
        "expires": None,
        "show_owner": False,
        "show_branch": False,
        "new": False,
        "list": False,
        "web_url": "https://web.example",
        "link": None,
        "all": False,
    }
    base.update(over)
    return types.SimpleNamespace(**base)


def _link(lid, token, **over):
    base = {
        "id": lid,
        "token": token,
        "kind": "session",
        "agent_instance_id": SESSION,
        "audience": "public",
        "show_owner": False,
        "show_branch": False,
        "expires_at": None,
        "view_count": 0,
        "created_at": "2026-09-22T10:00:00Z",
    }
    base.update(over)
    return base


class FakeServer:
    def __init__(self, links=None):
        self.links = list(links or [])
        self.sent = []

    def __call__(
        self, args, api_key, method, endpoint, *, params=None, json=None, **kw
    ):
        self.sent.append((method, endpoint, params, json))
        if endpoint == "/api/v1/shares" and method == "GET":
            return list(self.links)
        if endpoint == "/api/v1/shares" and method == "POST":
            created = _link("new-link-id", "newtoken", **(json or {}))
            self.links.insert(0, created)
            return created
        if endpoint.startswith("/api/v1/shares/") and method == "DELETE":
            return None
        raise AssertionError(f"unexpected {method} {endpoint}")


@pytest.fixture
def server(monkeypatch):
    srv = FakeServer()
    monkeypatch.setattr(I, "request", srv)
    return srv


class TestShare:
    def test_prints_only_the_url(self, server, capsys):
        assert I._cmd_share(_args(), "k") == 0
        assert capsys.readouterr().out == "https://web.example/share/newtoken\n"
        method, endpoint, _, body = server.sent[-1]
        assert (method, endpoint) == ("POST", "/api/v1/shares")
        assert body == {
            "kind": "session",
            "agent_instance_id": SESSION,
            "audience": "public",
            "show_owner": False,
            "show_branch": False,
        }

    def test_options_travel_in_the_body(self, server):
        I._cmd_share(
            _args(
                audience="authenticated", expires=7, show_owner=True, show_branch=True
            ),
            "k",
        )
        body = server.sent[-1][3]
        assert body["audience"] == "authenticated"
        assert body["expires_in_days"] == 7
        assert body["show_owner"] is True and body["show_branch"] is True

    def test_defaults_to_the_session_it_runs_in(self, server, monkeypatch, capsys):
        monkeypatch.setenv("VICOA_AGENT_INSTANCE_ID", SESSION)
        assert I._cmd_share(_args(session_id=None), "k") == 0
        assert server.sent[-1][3]["agent_instance_id"] == SESSION

    def test_no_session_and_no_env_is_an_error(self, server, monkeypatch, capsys):
        monkeypatch.delenv("VICOA_AGENT_INSTANCE_ID", raising=False)
        with pytest.raises(SystemExit) as exc:
            I._cmd_share(_args(session_id=None), "k")
        assert exc.value.code == 2
        assert "VICOA_AGENT_INSTANCE_ID" in capsys.readouterr().err

    def test_reuses_an_equivalent_live_link(self, server, capsys):
        """Running it twice for the same PR must not mint a second URL."""
        server.links = [_link("old", "oldtoken")]
        assert I._cmd_share(_args(), "k") == 0
        assert capsys.readouterr().out == "https://web.example/share/oldtoken\n"
        assert not any(m == "POST" for m, *_ in server.sent)

    def test_a_different_shape_is_a_new_link(self, server, capsys):
        server.links = [_link("old", "oldtoken", show_branch=True)]
        assert I._cmd_share(_args(), "k") == 0
        assert capsys.readouterr().out == "https://web.example/share/newtoken\n"

    def test_an_expiring_link_is_never_reused(self, server, capsys):
        server.links = [_link("old", "oldtoken", expires_at="2026-12-01T00:00:00Z")]
        I._cmd_share(_args(), "k")
        assert capsys.readouterr().out.endswith("/newtoken\n")
        # …and asking for an expiry always mints, even beside a non-expiring twin.
        server.links = [_link("old", "oldtoken")]
        I._cmd_share(_args(expires=3), "k")
        assert capsys.readouterr().out.endswith("/newtoken\n")

    def test_new_forces_a_mint(self, server, capsys):
        server.links = [_link("old", "oldtoken")]
        I._cmd_share(_args(new=True), "k")
        assert capsys.readouterr().out == "https://web.example/share/newtoken\n"

    def test_json_adds_url_and_reused(self, server, capsys):
        server.links = [_link("old", "oldtoken")]
        I._cmd_share(_args(json=True), "k")
        payload = json.loads(capsys.readouterr().out)
        assert payload["url"] == "https://web.example/share/oldtoken"
        assert payload["reused"] is True

    def test_list_prints_the_live_links(self, server, capsys):
        server.links = [_link("aaaa1111", "t1", view_count=4), _link("bbbb2222", "t2")]
        assert I._cmd_share(_args(list=True), "k") == 0
        out = capsys.readouterr().out
        assert "https://web.example/share/t1" in out
        assert "https://web.example/share/t2" in out
        assert "2 link(s)." in out
        assert not any(m == "POST" for m, *_ in server.sent)

    def test_web_url_falls_back_to_the_auth_url(self, server, monkeypatch):
        monkeypatch.setattr(I, "DEFAULT_AUTH_URL", "https://vicoa.ai", raising=False)
        assert I._share_url(_args(web_url=None), "tok").endswith("/share/tok")


class TestUnshare:
    def test_needs_link_or_all(self, server, capsys):
        server.links = [_link("aaaa1111", "t1")]
        assert I._cmd_unshare(_args(), "k") == 2
        assert not any(m == "DELETE" for m, *_ in server.sent)
        assert "--link" in capsys.readouterr().err

    def test_link_prefix_revokes_that_one(self, server, capsys):
        server.links = [_link("aaaa1111-x", "t1"), _link("bbbb2222-y", "t2")]
        assert I._cmd_unshare(_args(link="bbbb"), "k") == 0
        deleted = [e for m, e, *_ in server.sent if m == "DELETE"]
        assert deleted == ["/api/v1/shares/bbbb2222-y"]
        assert "Revoked 1 link(s)" in capsys.readouterr().out

    def test_unknown_link_is_an_error(self, server, capsys):
        server.links = [_link("aaaa1111-x", "t1")]
        assert I._cmd_unshare(_args(link="zzzz"), "k") == 1
        assert not any(m == "DELETE" for m, *_ in server.sent)

    def test_all_revokes_every_live_link(self, server):
        server.links = [_link("a", "t1"), _link("b", "t2")]
        assert I._cmd_unshare(_args(all=True), "k") == 0
        deleted = [e for m, e, *_ in server.sent if m == "DELETE"]
        assert deleted == ["/api/v1/shares/a", "/api/v1/shares/b"]
