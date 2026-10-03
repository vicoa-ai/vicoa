"""The caller's own drag order on the automations list (`PUT /automations/order`).

Who may call it is pinned by the authz matrix. This module covers what the
order does: unranked automations sit on top, newest first; every list mode and
the CLI's owner-only list follow it; it is per viewer, so ranking a
collaborator's automation moves nobody else's list.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from backend.db import automation_queries
from backend.tests.test_shared_automations import (
    _as,
    _automation,
    _grant,
    _ids,
    _link,
    _machine,
    _project,
    _user,
)

_T0 = datetime(2026, 9, 1, tzinfo=timezone.utc)


def _at(days: int) -> dict:
    return {"created_at": _T0 + timedelta(days=days)}


def _put(client, *ids) -> list[str]:
    response = client.put(
        "/api/v1/automations/order", json={"automation_ids": [str(i) for i in ids]}
    )
    assert response.status_code == 200, response.text
    return response.json()["automation_ids"]


class TestOrder:
    def test_unranked_is_newest_first(self, authenticated_client, test_db, test_user):
        box = _machine(test_db, test_user)
        old = _automation(test_db, test_user, box, "/a", **_at(0))
        new = _automation(test_db, test_user, box, "/b", **_at(1))
        test_db.commit()

        assert _ids(authenticated_client.get("/api/v1/automations")) == [
            str(new.id),
            str(old.id),
        ]

    def test_saved_order_is_what_every_list_returns(
        self, authenticated_client, test_db, test_user
    ):
        project = _project(test_db, test_user)
        box = _machine(test_db, test_user)
        _link(test_db, test_user, project, box, "/repo")
        a = _automation(test_db, test_user, box, "/repo", **_at(0))
        b = _automation(test_db, test_user, box, "/repo", **_at(1))
        c = _automation(test_db, test_user, box, "/repo", **_at(2))
        test_db.commit()

        stored = _put(authenticated_client, a.id, c.id, b.id)

        want = [str(a.id), str(c.id), str(b.id)]
        assert stored == want
        for url in (
            "/api/v1/automations",
            "/api/v1/automations?scope=all",
            f"/api/v1/automations?project_id={project.id}",
        ):
            assert _ids(authenticated_client.get(url)) == want, url
        # The author-only list the CLI, mobile and agent tools read.
        assert [
            str(x.id)
            for x in automation_queries.list_automations(test_db, test_user.id)
        ] == want

    def test_an_automation_left_out_sits_on_top(
        self, authenticated_client, test_db, test_user
    ):
        box = _machine(test_db, test_user)
        a = _automation(test_db, test_user, box, "/a", **_at(0))
        b = _automation(test_db, test_user, box, "/b", **_at(1))
        test_db.commit()
        _put(authenticated_client, a.id, b.id)

        # Created after the order was saved (another device, say).
        c = _automation(test_db, test_user, box, "/c", **_at(2))
        test_db.commit()

        assert _ids(authenticated_client.get("/api/v1/automations")) == [
            str(c.id),
            str(a.id),
            str(b.id),
        ]

    def test_duplicates_and_ids_the_caller_cannot_see_are_dropped(
        self, authenticated_client, test_db, test_user
    ):
        stranger = _user(test_db, "Stranger")
        box = _machine(test_db, test_user)
        their_box = _machine(test_db, stranger)
        mine = _automation(test_db, test_user, box, "/a")
        theirs = _automation(test_db, stranger, their_box, "/b")
        test_db.commit()

        stored = _put(authenticated_client, mine.id, theirs.id, uuid4(), mine.id)

        assert stored == [str(mine.id)]

    def test_an_empty_order_resets_to_newest_first(
        self, authenticated_client, test_db, test_user
    ):
        box = _machine(test_db, test_user)
        old = _automation(test_db, test_user, box, "/a", **_at(0))
        new = _automation(test_db, test_user, box, "/b", **_at(1))
        test_db.commit()
        _put(authenticated_client, old.id, new.id)

        _put(authenticated_client)

        assert _ids(authenticated_client.get("/api/v1/automations")) == [
            str(new.id),
            str(old.id),
        ]

    def test_order_is_not_matched_as_an_automation_id(self, authenticated_client):
        # `/automations/{automation_id}` is typed UUID; declared after it, "order"
        # would 422 (or 405) instead of reaching the order route.
        assert _put(authenticated_client) == []


class TestOrderIsPerViewer:
    def test_ranking_a_collaborators_automation_moves_only_your_list(
        self, client, test_db, test_user
    ):
        owner, viewer = test_user, _user(test_db, "Viewer")
        project = _project(test_db, owner)
        box = _machine(test_db, owner)
        _link(test_db, owner, project, box, "/repo")
        _grant(test_db, project, viewer, "viewer", by=owner)
        first = _automation(test_db, owner, box, "/repo", **_at(0))
        second = _automation(test_db, owner, box, "/repo", **_at(1))
        test_db.commit()

        with _as(client, viewer) as c:
            # A viewer can't edit these automations, but may arrange them.
            assert _put(c, first.id, second.id) == [str(first.id), str(second.id)]
            assert _ids(c.get(f"/api/v1/automations?project_id={project.id}")) == [
                str(first.id),
                str(second.id),
            ]

        with _as(client, owner) as c:
            # The author's list is still newest first.
            assert _ids(c.get("/api/v1/automations?scope=all")) == [
                str(second.id),
                str(first.id),
            ]

    def test_without_the_automations_scope_the_id_is_dropped(
        self, client, test_db, test_user
    ):
        owner, viewer = test_user, _user(test_db, "Viewer")
        project = _project(test_db, owner)
        box = _machine(test_db, owner)
        _link(test_db, owner, project, box, "/repo")
        _grant(test_db, project, viewer, "viewer", by=owner, scopes=["tasks"])
        automation = _automation(test_db, owner, box, "/repo")
        test_db.commit()

        with _as(client, viewer) as c:
            assert _put(c, automation.id) == []
