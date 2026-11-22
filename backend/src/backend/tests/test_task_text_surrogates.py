"""Task text that holds a lone surrogate.

JSON may escape a UTF-16 surrogate on its own (`"\\udc80"`), and Python decodes
it into a `str` that cannot be encoded as UTF-8. Python makes such strings
itself whenever it decodes bytes that are not UTF-8 with `surrogateescape`
(command-line arguments, and stdin under a C or POSIX locale), so a client
can send one without meaning to. Postgres can't store it: before this fix the
insert raised `UnicodeEncodeError` and the request ended as an unhandled 500,
which clients retried. Titles, descriptions and comment bodies now arrive with
each lone surrogate replaced by U+FFFD, the character a UTF-8 decoder shows for
a byte it can't read.

The bodies are sent as raw JSON text because httpx encodes `json=` to UTF-8
itself and would fail on the surrogate before the request left the test.
"""

import json

import pytest

from backend.models import (
    CreateTaskCommentRequest,
    CreateTaskRequest,
    UpdateTaskCommentRequest,
    UpdateTaskRequest,
)

REPLACEMENT = "�"
JSON_HEADERS = {"Content-Type": "application/json"}


def _raw(payload: str) -> dict:
    """Keyword arguments for a request whose JSON body is `payload` verbatim."""
    json.loads(payload)  # the test's own body must at least be valid JSON
    return {"content": payload, "headers": JSON_HEADERS}


class TestModels:
    @pytest.mark.parametrize(
        "raw",
        ["a\udc80b", "a\ud800b", "a\udfffb"],
        ids=["low-surrogate", "high-surrogate", "last-surrogate"],
    )
    def test_comment_body_gets_a_replacement_character(self, raw):
        assert CreateTaskCommentRequest(body=raw).body == f"a{REPLACEMENT}b"
        assert UpdateTaskCommentRequest(body=raw).body == f"a{REPLACEMENT}b"

    def test_each_surrogate_is_one_replacement(self):
        body = CreateTaskCommentRequest(body="\udcc3\udca9 ok").body
        assert body == f"{REPLACEMENT}{REPLACEMENT} ok"

    def test_task_title_and_description(self):
        created = CreateTaskRequest(title="t\udc80", description="d\udc80")
        assert (created.title, created.description) == (
            f"t{REPLACEMENT}",
            f"d{REPLACEMENT}",
        )
        updated = UpdateTaskRequest(title="t\udc80", description="d\udc80")
        assert (updated.title, updated.description) == (
            f"t{REPLACEMENT}",
            f"d{REPLACEMENT}",
        )

    def test_valid_text_is_unchanged(self):
        text = "plain, accents é, CJK 待办, emoji 😀"
        assert CreateTaskCommentRequest(body=text).body == text
        assert CreateTaskRequest(title=text, description=text).description == text

    def test_none_and_unset_stay_as_they_are(self):
        assert CreateTaskRequest(title="t").description is None
        update = UpdateTaskRequest(description=None)
        assert update.description is None
        # PATCH applies only the fields that were sent.
        assert update.model_fields_set == {"description"}
        assert UpdateTaskRequest().model_fields_set == set()

    def test_length_limits_still_apply(self):
        with pytest.raises(ValueError):
            CreateTaskCommentRequest(body="")
        with pytest.raises(ValueError):
            CreateTaskRequest(title="\udc80" * 256)
        with pytest.raises(ValueError):
            UpdateTaskRequest(title="")
        with pytest.raises(ValueError):
            UpdateTaskRequest(title="\udc80" * 256)
        # One surrogate becomes one character, so a title at the limit stays
        # at the limit.
        assert CreateTaskRequest(title="\udc80" * 255).title == REPLACEMENT * 255
        assert UpdateTaskRequest(title="\udc80" * 255).title == REPLACEMENT * 255


class TestEndpoints:
    @pytest.fixture
    def task(self, authenticated_client):
        resp = authenticated_client.post("/api/v1/tasks", json={"title": "Ship it"})
        assert resp.status_code == 201, resp.text
        return resp.json()

    def test_comment_with_a_lone_surrogate_is_stored(self, authenticated_client, task):
        resp = authenticated_client.post(
            f"/api/v1/tasks/{task['id']}/comments",
            **_raw('{"body": "build log: \\udc80\\udcff done"}'),
        )
        assert resp.status_code == 201, resp.text
        expected = f"build log: {REPLACEMENT}{REPLACEMENT} done"
        assert [c["body"] for c in resp.json()["comments"]] == [expected]

        timeline = authenticated_client.get(f"/api/v1/tasks/{task['id']}/timeline")
        assert [c["body"] for c in timeline.json()["comments"]] == [expected]

    def test_comment_edit_with_a_lone_surrogate(self, authenticated_client, task):
        created = authenticated_client.post(
            f"/api/v1/tasks/{task['id']}/comments", json={"body": "first"}
        ).json()
        comment_id = created["comments"][0]["id"]

        resp = authenticated_client.patch(
            f"/api/v1/tasks/{task['id']}/comments/{comment_id}",
            **_raw('{"body": "second \\udc80"}'),
        )
        assert resp.status_code == 200, resp.text
        assert [c["body"] for c in resp.json()["comments"]] == [f"second {REPLACEMENT}"]

    def test_surrogate_pair_is_kept(self, authenticated_client, task):
        """A pair that makes one character is valid text, not a lone surrogate."""
        resp = authenticated_client.post(
            f"/api/v1/tasks/{task['id']}/comments",
            **_raw('{"body": "shipped \\ud83d\\ude00"}'),
        )
        assert resp.status_code == 201, resp.text
        assert [c["body"] for c in resp.json()["comments"]] == ["shipped 😀"]

    def test_task_create_and_update(self, authenticated_client):
        resp = authenticated_client.post(
            "/api/v1/tasks",
            **_raw('{"title": "fix \\udc80", "description": "see \\udcff"}'),
        )
        assert resp.status_code == 201, resp.text
        task = resp.json()
        assert task["title"] == f"fix {REPLACEMENT}"
        assert task["description"] == f"see {REPLACEMENT}"

        resp = authenticated_client.patch(
            f"/api/v1/tasks/{task['id']}",
            **_raw('{"title": "\\ud800 again", "description": "more \\udc80"}'),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["title"] == f"{REPLACEMENT} again"
        assert resp.json()["description"] == f"more {REPLACEMENT}"

        # Clearing the description still works.
        resp = authenticated_client.patch(
            f"/api/v1/tasks/{task['id']}", json={"description": None}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["description"] is None
